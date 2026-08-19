"""Train-only fitting, validation selection, and failure-closed evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import random
from typing import Iterable, Mapping, Sequence

import numpy as np
import torch

from .config import ModelConfig, TrainingConfig
from .matching import NamedMatch, TemporalMatchConfirmer, extract_mutual_matches
from .model import SuperGlueOutput, TrackSuperGlue
from .normalization import FeatureNormalizer
from .schema import AssociationLabels, TrainingExample
from .tensors import graph_tensors


@dataclass(frozen=True)
class ValidationSelection:
    initialization_seed: int
    threshold: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    correct_assignment_count: int
    selected_assignment_count: int
    expected_assignment_count: int
    validation_failed_closed: bool

    def to_dict(self) -> dict[str, int | float | bool]:
        return asdict(self)


@dataclass(frozen=True)
class InitializationSummary:
    initialization_seed: int
    trained_epochs: int
    best_epoch: int
    best_validation_loss: float
    stopped_early: bool
    validation_selection: ValidationSelection

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["validation_selection"] = self.validation_selection.to_dict()
        return payload


@dataclass(frozen=True)
class EnsembleTrainingResult:
    model_config: ModelConfig
    normalizer: FeatureNormalizer
    selected_state_dict: Mapping[str, torch.Tensor]
    validation_selection: ValidationSelection
    initialization_summaries: tuple[InitializationSummary, ...]
    training_example_count: int = 0
    optimized_training_example_count: int = 0
    skipped_empty_training_example_count: int = 0


def resolve_device(value: str) -> torch.device:
    if value == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if value == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return torch.device(value)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def association_loss(
    output: SuperGlueOutput,
    labels: AssociationLabels,
    *,
    matched_weight: float = 0.5,
    dustbin_weight: float = 0.5,
) -> torch.Tensor:
    """Balance matched-pair and unmatched-dustbin contributions 50/50."""

    probabilities = output.transport.assignment
    count_a, count_b = probabilities.shape[0] - 1, probabilities.shape[1] - 1
    tiny = torch.finfo(probabilities.dtype).tiny
    matched_pairs = set(labels.matched_pairs)
    matched_rows = {row for row, _ in matched_pairs}
    matched_columns = {column for _, column in matched_pairs}
    matched_terms = [
        -torch.log(probabilities[row, column].clamp_min(tiny))
        for row, column in sorted(matched_pairs)
    ]
    dustbin_terms = [
        -torch.log(probabilities[row, count_b].clamp_min(tiny))
        for row in range(count_a)
        if row not in matched_rows
    ] + [
        -torch.log(probabilities[count_a, column].clamp_min(tiny))
        for column in range(count_b)
        if column not in matched_columns
    ]
    zero = probabilities.sum() * 0.0
    matched_loss = torch.stack(matched_terms).mean() if matched_terms else zero
    dustbin_loss = torch.stack(dustbin_terms).mean() if dustbin_terms else zero
    return matched_weight * matched_loss + dustbin_weight * dustbin_loss


def _forward(
    model: TrackSuperGlue,
    example: TrainingExample,
    normalizer: FeatureNormalizer,
    device: torch.device,
) -> SuperGlueOutput:
    tensors = graph_tensors(example.graph, normalizer, device)
    return model(*tensors.model_arguments())


def _mean_loss(
    model: TrackSuperGlue,
    examples: Sequence[TrainingExample],
    normalizer: FeatureNormalizer,
    device: torch.device,
    config: TrainingConfig,
) -> float:
    model.eval()
    losses = []
    with torch.no_grad():
        for example in examples:
            output = _forward(model, example, normalizer, device)
            losses.append(
                float(
                    association_loss(
                        output,
                        example.labels,
                        matched_weight=config.matched_loss_weight,
                        dustbin_weight=config.dustbin_loss_weight,
                    ).detach().cpu()
                )
            )
    return float(np.mean(losses)) if losses else math.inf


def evaluate_validation(
    model: TrackSuperGlue,
    examples: Sequence[TrainingExample],
    normalizer: FeatureNormalizer,
    threshold: float,
    device: torch.device,
    initialization_seed: int,
) -> ValidationSelection:
    """Evaluate causal 2-of-3 publications without opening a test split."""

    if any(example.graph.split == "test" for example in examples):
        raise ValueError("test labels must remain sealed during validation")
    model.eval()
    confirmer = TemporalMatchConfirmer()
    metrics = []
    correct_total = selected_total = expected_total = 0
    ordered = sorted(
        examples,
        key=lambda item: (
            item.graph.seed,
            item.graph.corruption_level,
            item.graph.revolution_index,
        ),
    )
    with torch.no_grad():
        for example in ordered:
            output = _forward(model, example, normalizer, device)
            raw = extract_mutual_matches(
                output.transport.assignment,
                torch.as_tensor(example.graph.candidate_mask, dtype=torch.bool),
                threshold,
            )
            named = tuple(
                NamedMatch(
                    example.graph.track_ids_a[match.index_a],
                    example.graph.track_ids_b[match.index_b],
                    match.score,
                )
                for match in raw
            )
            confirmed = confirmer.update(
                (example.graph.seed, example.graph.corruption_level),
                example.graph.revolution_index,
                named,
            )
            selected = {
                (
                    example.graph.track_ids_a.index(match.track_a_id),
                    example.graph.track_ids_b.index(match.track_b_id),
                )
                for match in confirmed
            }
            expected = set(example.labels.matched_pairs)
            correct = len(selected & expected)
            precision = correct / len(selected) if selected else 0.0
            recall = correct / len(expected) if expected else 0.0
            f1 = (
                2.0 * precision * recall / (precision + recall)
                if precision + recall
                else 0.0
            )
            metrics.append((precision, recall, f1))
            correct_total += correct
            selected_total += len(selected)
            expected_total += len(expected)
    macro = np.mean(np.asarray(metrics, dtype=float), axis=0) if metrics else np.zeros(3)
    failed_closed = selected_total == 0 or correct_total == 0 or not np.all(np.isfinite(macro))
    return ValidationSelection(
        initialization_seed=initialization_seed,
        threshold=float(threshold),
        macro_precision=float(macro[0]),
        macro_recall=float(macro[1]),
        macro_f1=float(macro[2]),
        correct_assignment_count=correct_total,
        selected_assignment_count=selected_total,
        expected_assignment_count=expected_total,
        validation_failed_closed=bool(failed_closed),
    )


def _selection_key(selection: ValidationSelection) -> tuple[float, int, float, float]:
    return (
        -1.0 if selection.validation_failed_closed else selection.macro_f1,
        selection.correct_assignment_count,
        selection.macro_precision,
        selection.threshold,
    )


def _clone_state_dict(model: TrackSuperGlue) -> dict[str, torch.Tensor]:
    return {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}


def train_ensemble(
    training_examples: Iterable[TrainingExample],
    validation_examples: Iterable[TrainingExample],
    *,
    training_config: TrainingConfig | None = None,
    model_config: ModelConfig | None = None,
) -> EnsembleTrainingResult:
    """Train five initializations and select only on the validation split."""

    config = training_config or TrainingConfig()
    model_values = model_config or ModelConfig(dropout=config.dropout)
    train = tuple(training_examples)
    validation = tuple(validation_examples)
    if not train or not validation:
        raise ValueError("both training and validation examples are required")
    for example in (*train, *validation):
        example.validate()
    if any(example.graph.split != "train" for example in train):
        raise ValueError("training inputs must be marked train")
    if any(example.graph.split != "validation" for example in validation):
        raise ValueError("validation inputs must be marked validation")
    optimizable_train = tuple(
        example
        for example in train
        if example.graph.track_ids_a and example.graph.track_ids_b
    )
    if not optimizable_train:
        raise ValueError("training requires at least one two-sided track graph")
    normalizer = FeatureNormalizer.fit(example.graph for example in train)
    device = resolve_device(config.device)
    candidates: list[
        tuple[ValidationSelection, InitializationSummary, Mapping[str, torch.Tensor]]
    ] = []
    for initialization_seed in config.initialization_seeds:
        seed_everything(initialization_seed)
        model = TrackSuperGlue(model_values).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        best_loss = math.inf
        best_epoch = 0
        best_state = _clone_state_dict(model)
        stale_epochs = 0
        trained_epochs = 0
        for epoch in range(1, config.max_epochs + 1):
            trained_epochs = epoch
            model.train()
            order = list(range(len(optimizable_train)))
            random.Random(initialization_seed + epoch).shuffle(order)
            for index in order:
                optimizer.zero_grad(set_to_none=True)
                example = optimizable_train[index]
                output = _forward(model, example, normalizer, device)
                loss = association_loss(
                    output,
                    example.labels,
                    matched_weight=config.matched_loss_weight,
                    dustbin_weight=config.dustbin_loss_weight,
                )
                if not torch.isfinite(loss):
                    raise FloatingPointError("training loss became non-finite")
                loss.backward()
                optimizer.step()
            validation_loss = _mean_loss(model, validation, normalizer, device, config)
            if validation_loss < best_loss - 1.0e-8:
                best_loss = validation_loss
                best_epoch = epoch
                best_state = _clone_state_dict(model)
                stale_epochs = 0
            else:
                stale_epochs += 1
            if stale_epochs >= config.patience:
                break
        model.load_state_dict(best_state)
        selections = [
            evaluate_validation(
                model,
                validation,
                normalizer,
                threshold,
                device,
                initialization_seed,
            )
            for threshold in config.validation_thresholds
        ]
        selected = max(selections, key=_selection_key)
        summary = InitializationSummary(
            initialization_seed=initialization_seed,
            trained_epochs=trained_epochs,
            best_epoch=best_epoch,
            best_validation_loss=float(best_loss),
            stopped_early=trained_epochs < config.max_epochs,
            validation_selection=selected,
        )
        candidates.append((selected, summary, best_state))
    selected, _, selected_state = max(candidates, key=lambda item: _selection_key(item[0]))
    return EnsembleTrainingResult(
        model_config=model_values,
        normalizer=normalizer,
        selected_state_dict=selected_state,
        validation_selection=selected,
        initialization_summaries=tuple(item[1] for item in candidates),
        training_example_count=len(train),
        optimized_training_example_count=len(optimizable_train),
        skipped_empty_training_example_count=len(train) - len(optimizable_train),
    )
