"""Balanced 40/60/100 training and five-initialization model freezing."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import math
from pathlib import Path
import random
from typing import Mapping, Sequence

import numpy as np
import torch
from torch import nn

from .contracts import TargetTrackGraph
from .model import (
    FeatureNormalizer,
    TargetTrackCostGNN,
    freeze_model,
    graph_tensors,
)


SUPPORTED_TARGET_COUNTS = (40, 60, 100)
DEFAULT_INITIALIZATION_SEEDS = (1103, 2207, 3301, 4409, 5501)


@dataclass(frozen=True)
class TargetTrackTrainingExample:
    """Offline binary edge labels kept outside every online publication record."""

    example_id: str
    split: str
    target_count: int
    seed: int
    graph: TargetTrackGraph
    edge_labels: np.ndarray

    def validate(self) -> None:
        if not self.example_id:
            raise ValueError("training example ID cannot be empty")
        if self.split not in {"train", "validation", "test"}:
            raise ValueError("training example split is invalid")
        if self.target_count not in SUPPORTED_TARGET_COUNTS:
            raise ValueError("training example target scale must be 40, 60, or 100")
        self.graph.validate()
        if self.seed != self.graph.seed:
            raise ValueError("training example seed does not match graph")
        if self.edge_labels.shape != self.graph.rule_cost.shape:
            raise ValueError("edge labels do not match graph candidate edges")
        if not np.all(np.isin(self.edge_labels, (0.0, 1.0))):
            raise ValueError("edge labels must be binary")


@dataclass(frozen=True)
class FiveInitializationConfig:
    initialization_seeds: tuple[int, ...] = DEFAULT_INITIALIZATION_SEEDS
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-4
    max_epochs: int = 100
    patience: int = 15
    dropout: float = 0.1
    correction_weight: float = 0.5
    maximum_abs_correction: float = 1.0
    unmatched_cost: float = 1.0
    logit_temperature: float = 0.25
    sampling_seed: int = 7319
    train_samples_per_scale: int | None = None
    validation_samples_per_scale: int | None = None
    device: str = "auto"

    def __post_init__(self) -> None:
        if len(self.initialization_seeds) < 5 or len(set(self.initialization_seeds)) != len(
            self.initialization_seeds
        ):
            raise ValueError("training requires at least five distinct initialization seeds")
        if self.learning_rate <= 0.0 or self.weight_decay < 0.0:
            raise ValueError("optimizer settings are invalid")
        if self.max_epochs <= 0 or self.patience <= 0:
            raise ValueError("epoch and patience settings must be positive")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if self.correction_weight < 0.0 or self.maximum_abs_correction <= 0.0:
            raise ValueError("cost correction settings are invalid")
        if self.unmatched_cost <= 0.0 or self.logit_temperature <= 0.0:
            raise ValueError("assignment-loss settings are invalid")
        for value in (
            self.train_samples_per_scale,
            self.validation_samples_per_scale,
        ):
            if value is not None and value <= 0:
                raise ValueError("per-scale sample counts must be positive")


@dataclass(frozen=True)
class InitializationResult:
    initialization_seed: int
    best_epoch: int
    best_validation_loss: float
    final_training_loss: float
    stopped_epoch: int


@dataclass(frozen=True)
class FiveInitializationOutcome:
    output_dir: str
    selected_initialization_seed: int
    selected_validation_loss: float
    train_example_ids: tuple[str, ...]
    validation_example_ids: tuple[str, ...]
    initialization_results: tuple[InitializationResult, ...]
    freeze_manifest: Mapping[str, object]


def balanced_multiscale_samples(
    examples: Sequence[TargetTrackTrainingExample],
    *,
    split: str,
    samples_per_scale: int | None = None,
    random_seed: int = 7319,
) -> tuple[TargetTrackTrainingExample, ...]:
    """Select equal counts at 40/60/100 without ever accepting test labels."""

    if split not in {"train", "validation"}:
        raise ValueError("balanced model selection may use only train or validation labels")
    groups: dict[int, list[TargetTrackTrainingExample]] = {
        count: [] for count in SUPPORTED_TARGET_COUNTS
    }
    for example in examples:
        example.validate()
        if example.split == "test":
            raise ValueError("test labels cannot enter model training or selection")
        if example.split == split:
            groups[example.target_count].append(example)
    missing = [count for count, values in groups.items() if not values]
    if missing:
        raise ValueError(f"balanced sampling is missing target scales: {missing}")
    selected_count = samples_per_scale or min(len(values) for values in groups.values())
    if any(len(values) < selected_count for values in groups.values()):
        raise ValueError("requested balanced sample count exceeds an available scale")
    selected_by_scale: dict[int, list[TargetTrackTrainingExample]] = {}
    for count, values in groups.items():
        ordered = sorted(values, key=lambda item: (item.seed, item.example_id))
        generator = np.random.default_rng(random_seed + count * 1009)
        indices = generator.choice(len(ordered), size=selected_count, replace=False)
        selected_by_scale[count] = [ordered[int(index)] for index in sorted(indices)]
    interleaved = []
    for index in range(selected_count):
        for count in SUPPORTED_TARGET_COUNTS:
            interleaved.append(selected_by_scale[count][index])
    return tuple(interleaved)


def _device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    return device


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _positive_weight(examples: Sequence[TargetTrackTrainingExample]) -> float:
    positive = sum(int(np.sum(example.edge_labels)) for example in examples)
    total = sum(len(example.edge_labels) for example in examples)
    negative = total - positive
    if positive == 0:
        raise ValueError("training set contains no positive candidate edges")
    return float(np.clip(negative / positive, 1.0, 20.0))


def _graph_loss(
    model: TargetTrackCostGNN,
    example: TargetTrackTrainingExample,
    normalizer: FeatureNormalizer,
    criterion: nn.Module,
    device: torch.device,
    config: FiveInitializationConfig,
) -> torch.Tensor | None:
    if example.graph.edge_index.shape[1] == 0:
        return None
    corrections = model(*graph_tensors(example.graph, normalizer, device))
    rule_cost = torch.as_tensor(
        example.graph.rule_cost, dtype=torch.float32, device=device
    )
    final_cost = rule_cost + config.correction_weight * corrections
    logits = (config.unmatched_cost - final_cost) / config.logit_temperature
    labels = torch.as_tensor(example.edge_labels, dtype=torch.float32, device=device)
    return criterion(logits, labels)


def _mean_loss(
    model: TargetTrackCostGNN,
    examples: Sequence[TargetTrackTrainingExample],
    normalizer: FeatureNormalizer,
    criterion: nn.Module,
    device: torch.device,
    config: FiveInitializationConfig,
) -> torch.Tensor:
    losses = [
        loss
        for example in examples
        if (
            loss := _graph_loss(
                model, example, normalizer, criterion, device, config
            )
        )
        is not None
    ]
    if not losses:
        raise ValueError("selected examples contain no hard-whitelisted edges")
    return torch.stack(losses).mean()


def train_and_freeze_five_initializations(
    examples: Sequence[TargetTrackTrainingExample],
    output_dir: str | Path,
    *,
    config: FiveInitializationConfig | None = None,
) -> FiveInitializationOutcome:
    """Train one shared multiscale model and freeze it before test labels are opened."""

    config = config or FiveInitializationConfig()
    if any(example.split == "test" for example in examples):
        raise ValueError("test labels cannot be passed to the training entry point")
    train_examples = balanced_multiscale_samples(
        examples,
        split="train",
        samples_per_scale=config.train_samples_per_scale,
        random_seed=config.sampling_seed,
    )
    validation_examples = balanced_multiscale_samples(
        examples,
        split="validation",
        samples_per_scale=config.validation_samples_per_scale,
        random_seed=config.sampling_seed + 1,
    )
    normalizer = FeatureNormalizer.fit(example.graph for example in train_examples)
    device = _device(config.device)
    positive_weight = _positive_weight(train_examples)
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(positive_weight, dtype=torch.float32, device=device)
    )
    run_results = []
    candidate_states: dict[int, Mapping[str, torch.Tensor]] = {}
    for initialization_seed in config.initialization_seeds:
        _set_seed(initialization_seed)
        first_graph = train_examples[0].graph
        model = TargetTrackCostGNN(
            target_feature_dim=first_graph.target_features.shape[1],
            track_feature_dim=first_graph.track_features.shape[1],
            edge_feature_dim=first_graph.edge_features.shape[1],
            hidden_dim=64,
            dropout=config.dropout,
            maximum_abs_correction=config.maximum_abs_correction,
        ).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        best_validation = float("inf")
        best_epoch = 0
        best_state: Mapping[str, torch.Tensor] | None = None
        stale_epochs = 0
        final_training = float("inf")
        stopped_epoch = config.max_epochs
        for epoch in range(1, config.max_epochs + 1):
            model.train()
            optimizer.zero_grad(set_to_none=True)
            training_loss = _mean_loss(
                model,
                train_examples,
                normalizer,
                criterion,
                device,
                config,
            )
            training_loss.backward()
            optimizer.step()
            final_training = float(training_loss.detach().cpu())
            model.eval()
            with torch.no_grad():
                validation_loss = float(
                    _mean_loss(
                        model,
                        validation_examples,
                        normalizer,
                        criterion,
                        device,
                        config,
                    ).detach().cpu()
                )
            if validation_loss < best_validation - 1.0e-8:
                best_validation = validation_loss
                best_epoch = epoch
                best_state = {
                    key: value.detach().cpu().clone()
                    for key, value in model.state_dict().items()
                }
                stale_epochs = 0
            else:
                stale_epochs += 1
                if stale_epochs >= config.patience:
                    stopped_epoch = epoch
                    break
        if best_state is None or not math.isfinite(best_validation):
            raise RuntimeError("one GNN initialization did not produce a finite model")
        candidate_states[initialization_seed] = best_state
        run_results.append(
            InitializationResult(
                initialization_seed=initialization_seed,
                best_epoch=best_epoch,
                best_validation_loss=best_validation,
                final_training_loss=final_training,
                stopped_epoch=stopped_epoch,
            )
        )

    selected = min(
        run_results,
        key=lambda item: (item.best_validation_loss, item.initialization_seed),
    )
    first_graph = train_examples[0].graph
    frozen_model = TargetTrackCostGNN(
        target_feature_dim=first_graph.target_features.shape[1],
        track_feature_dim=first_graph.track_features.shape[1],
        edge_feature_dim=first_graph.edge_features.shape[1],
        hidden_dim=64,
        dropout=config.dropout,
        maximum_abs_correction=config.maximum_abs_correction,
    )
    frozen_model.load_state_dict(deepcopy(candidate_states[selected.initialization_seed]))
    frozen_model.eval()
    manifest = freeze_model(
        frozen_model,
        normalizer,
        output_dir,
        metadata={
            "selection_policy": "lowest_balanced_validation_loss",
            "labels_opened": ["train", "validation"],
            "test_labels_opened": False,
            "target_counts": list(SUPPORTED_TARGET_COUNTS),
            "initialization_results": [asdict(item) for item in run_results],
            "selected_initialization_seed": selected.initialization_seed,
            "train_example_ids": [item.example_id for item in train_examples],
            "validation_example_ids": [
                item.example_id for item in validation_examples
            ],
        },
    )
    return FiveInitializationOutcome(
        output_dir=str(Path(output_dir)),
        selected_initialization_seed=selected.initialization_seed,
        selected_validation_loss=selected.best_validation_loss,
        train_example_ids=tuple(item.example_id for item in train_examples),
        validation_example_ids=tuple(
            item.example_id for item in validation_examples
        ),
        initialization_results=tuple(run_results),
        freeze_manifest=manifest,
    )
