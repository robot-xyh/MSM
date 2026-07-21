"""Multi-episode behavior cloning and native PPO orchestration for D3."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .learning import EDGE_FEATURE_NAMES, FeatureDistributionGuard
from .learning_data import LearningFrameRecord
from .native_ppo import (
    ClippedPPOTrainer,
    PPOUpdateResult,
    SharedEdgeActorCriticPolicy,
    collect_ppo_transitions,
    nn,
    torch,
)


@dataclass(frozen=True)
class BehaviorCloningTrainingResult:
    epoch_count: int
    mini_batch_frames: int
    train_frame_count: int
    validation_frame_count: int
    train_edge_count: int
    validation_edge_count: int
    initial_train_loss: float
    final_train_loss: float
    validation_loss: float
    positive_class_weight_cap: float
    whole_seed_metrics: Mapping[str, Mapping[str, float | int | str]]
    normalization_mean: tuple[float, ...]
    normalization_scale: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "training_kind": "behavior_cloning",
            "epoch_count": int(self.epoch_count),
            "mini_batch_frames": int(self.mini_batch_frames),
            "train_frame_count": int(self.train_frame_count),
            "validation_frame_count": int(self.validation_frame_count),
            "train_edge_count": int(self.train_edge_count),
            "validation_edge_count": int(self.validation_edge_count),
            "initial_train_loss": float(self.initial_train_loss),
            "final_train_loss": float(self.final_train_loss),
            "validation_loss": float(self.validation_loss),
            "positive_class_weight_cap": float(self.positive_class_weight_cap),
            "whole_seed_metrics": {
                key: dict(value) for key, value in sorted(self.whole_seed_metrics.items())
            },
        }


@dataclass(frozen=True)
class NativePPOTrainingResult:
    update_count: int
    train_frame_count: int
    update_results: tuple[PPOUpdateResult, ...]
    reward_mean: float
    reward_min: float
    reward_max: float
    normalization_mean: tuple[float, ...]
    normalization_scale: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "training_kind": "native_clipped_ppo",
            "update_count": int(self.update_count),
            "train_frame_count": int(self.train_frame_count),
            "reward_mean": float(self.reward_mean),
            "reward_min": float(self.reward_min),
            "reward_max": float(self.reward_max),
            "updates": [item.to_dict() for item in self.update_results],
        }


def train_behavior_cloning(
    records: Iterable[LearningFrameRecord],
    *,
    policy: SharedEdgeActorCriticPolicy | None = None,
    epochs: int = 20,
    mini_batch_frames: int = 8,
    learning_rate: float = 1.0e-3,
    seed: int = 0,
    positive_class_weight_cap: float = 1.0,
) -> tuple[SharedEdgeActorCriticPolicy, BehaviorCloningTrainingResult]:
    """Clone rule-selected edges and low-frequency hold/replan suggestions."""

    if torch is None or nn is None:  # pragma: no cover
        raise ImportError("PyTorch is required for behavior cloning")
    items = _training_records(records, allowed_splits={"train", "validation"})
    train_records = tuple(
        item for item in items if item.split == "train" and len(item.candidate_edge_indices)
    )
    validation_records = tuple(
        item
        for item in items
        if item.split == "validation" and len(item.candidate_edge_indices)
    )
    if not train_records or not validation_records:
        raise ValueError("BC requires non-empty train and validation seed groups")
    if (
        epochs < 1
        or mini_batch_frames < 1
        or learning_rate <= 0.0
        or not isfinite(float(positive_class_weight_cap))
        or float(positive_class_weight_cap) < 1.0
    ):
        raise ValueError("BC epochs, mini-batch size, and learning rate must be positive")
    _assert_disjoint_seed_groups(train_records, validation_records)
    torch.manual_seed(int(seed))
    rng = np.random.default_rng(int(seed))
    model = policy or SharedEdgeActorCriticPolicy()
    guard = FeatureDistributionGuard.fit(
        tuple(item.candidate_features for item in train_records)
    )
    mean = np.asarray(guard.mean, dtype=np.float32)
    scale = np.asarray(guard.scale, dtype=np.float32)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(learning_rate))

    initial_train_loss = _evaluate_bc_loss(
        model,
        train_records,
        mean,
        scale,
        positive_class_weight_cap=float(positive_class_weight_cap),
    )
    model.train()
    for _ in range(int(epochs)):
        order = rng.permutation(len(train_records))
        for start in range(0, len(train_records), int(mini_batch_frames)):
            batch = tuple(
                train_records[int(index)]
                for index in order[start : start + int(mini_batch_frames)]
            )
            optimizer.zero_grad()
            loss = _bc_batch_loss(
                model,
                batch,
                mean,
                scale,
                positive_class_weight_cap=float(positive_class_weight_cap),
            )
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
    final_train_loss = _evaluate_bc_loss(
        model,
        train_records,
        mean,
        scale,
        positive_class_weight_cap=float(positive_class_weight_cap),
    )
    validation_loss = _evaluate_bc_loss(
        model,
        validation_records,
        mean,
        scale,
        positive_class_weight_cap=float(positive_class_weight_cap),
    )
    seed_metrics = _whole_seed_metrics(model, items, mean, scale)
    scalars = (initial_train_loss, final_train_loss, validation_loss)
    if not all(isfinite(value) for value in scalars):
        raise FloatingPointError("behavior cloning produced non-finite loss")
    result = BehaviorCloningTrainingResult(
        epoch_count=int(epochs),
        mini_batch_frames=int(mini_batch_frames),
        train_frame_count=len(train_records),
        validation_frame_count=len(validation_records),
        train_edge_count=sum(len(item.candidate_edge_indices) for item in train_records),
        validation_edge_count=sum(
            len(item.candidate_edge_indices) for item in validation_records
        ),
        initial_train_loss=initial_train_loss,
        final_train_loss=final_train_loss,
        validation_loss=validation_loss,
        positive_class_weight_cap=float(positive_class_weight_cap),
        whole_seed_metrics=seed_metrics,
        normalization_mean=tuple(float(value) for value in mean),
        normalization_scale=tuple(float(value) for value in scale),
    )
    return model, result


def train_native_ppo(
    records: Iterable[LearningFrameRecord],
    *,
    policy: SharedEdgeActorCriticPolicy | None = None,
    updates: int = 2,
    epochs_per_update: int = 4,
    mini_batch_frames: int = 8,
    learning_rate: float = 3.0e-4,
    clip_ratio: float = 0.2,
    seed: int = 0,
    normalization_mean: Sequence[float] | None = None,
    normalization_scale: Sequence[float] | None = None,
) -> tuple[SharedEdgeActorCriticPolicy, NativePPOTrainingResult]:
    """Run clipped PPO on offline/synthetic reward frames without solving plans."""

    if torch is None or nn is None:  # pragma: no cover
        raise ImportError("PyTorch is required for native PPO")
    items = _training_records(records, allowed_splits={"train"})
    train_records = tuple(
        item for item in items if item.split == "train" and len(item.candidate_edge_indices)
    )
    if not train_records:
        raise ValueError("PPO requires non-empty train seed groups")
    if updates < 1:
        raise ValueError("PPO updates must be positive")
    torch.manual_seed(int(seed))
    model = policy or SharedEdgeActorCriticPolicy()
    if normalization_mean is None or normalization_scale is None:
        guard = FeatureDistributionGuard.fit(
            tuple(item.candidate_features for item in train_records)
        )
        mean = np.asarray(guard.mean, dtype=np.float32)
        scale = np.asarray(guard.scale, dtype=np.float32)
    else:
        mean = np.asarray(normalization_mean, dtype=np.float32).reshape(-1)
        scale = np.asarray(normalization_scale, dtype=np.float32).reshape(-1)
    if mean.shape != (len(EDGE_FEATURE_NAMES),) or scale.shape != mean.shape:
        raise ValueError("PPO normalization statistics have the wrong feature shape")
    trainer = ClippedPPOTrainer(
        model,
        learning_rate=learning_rate,
        clip_ratio=clip_ratio,
        epochs=epochs_per_update,
        mini_batch_frames=mini_batch_frames,
        seed=seed,
    )
    update_results: list[PPOUpdateResult] = []
    rewards: list[float] = []
    for update_index in range(int(updates)):
        torch.manual_seed(int(seed) + update_index)
        transitions = collect_ppo_transitions(
            model,
            train_records,
            feature_mean=mean,
            feature_scale=scale,
        )
        rewards.extend(item.reward for item in transitions)
        update_results.append(trainer.update(transitions))
    result = NativePPOTrainingResult(
        update_count=int(updates),
        train_frame_count=len(train_records),
        update_results=tuple(update_results),
        reward_mean=float(np.mean(rewards)),
        reward_min=float(np.min(rewards)),
        reward_max=float(np.max(rewards)),
        normalization_mean=tuple(float(value) for value in mean),
        normalization_scale=tuple(float(value) for value in scale),
    )
    return model, result


def _bc_batch_loss(
    policy: SharedEdgeActorCriticPolicy,
    records: Sequence[LearningFrameRecord],
    mean: np.ndarray,
    scale: np.ndarray,
    *,
    positive_class_weight_cap: float = 1.0,
) -> Any:
    device = next(policy.parameters()).device
    edge_losses: list[Any] = []
    advice_losses: list[Any] = []
    residual_losses: list[Any] = []
    for record in records:
        normalized = (record.candidate_features - mean) / scale
        features = torch.as_tensor(normalized, dtype=torch.float32, device=device)
        mask = torch.ones(features.shape[0], dtype=torch.bool, device=device)
        latent_mean, _, selection, advice_logits, _ = policy(features, mask)
        labels = torch.as_tensor(
            record.selected_edge_labels, dtype=torch.float32, device=device
        )
        positive_count = int(torch.count_nonzero(labels > 0.5).item())
        negative_count = int(labels.numel()) - positive_count
        positive_weight = min(
            float(positive_class_weight_cap),
            max(1.0, negative_count / max(1, positive_count)),
        )
        edge_weights = torch.where(
            labels > 0.5,
            torch.full_like(labels, positive_weight),
            torch.ones_like(labels),
        )
        edge_losses.append(
            (
                nn.functional.binary_cross_entropy_with_logits(
                    selection,
                    labels,
                    reduction="none",
                )
                * edge_weights
            ).sum()
            / edge_weights.sum()
        )
        teacher_residual = torch.where(
            labels > 0.5,
            torch.full_like(labels, -1.0),
            torch.full_like(labels, 1.0),
        )
        predicted_residual = policy.residual_bound * torch.tanh(latent_mean)
        residual_losses.append(
            (
                nn.functional.smooth_l1_loss(
                    predicted_residual,
                    teacher_residual,
                    reduction="none",
                )
                * edge_weights
            ).sum()
            / edge_weights.sum()
        )
        if record.advice_allowed:
            advice_target = 1 if record.hold_label else 2 if record.replan_label else 0
            advice_losses.append(
                nn.functional.cross_entropy(
                    advice_logits.reshape(1, -1),
                    torch.as_tensor([advice_target], dtype=torch.long, device=device),
                )
            )
    edge_loss = torch.stack(edge_losses).mean()
    residual_loss = torch.stack(residual_losses).mean()
    advice_loss = (
        torch.stack(advice_losses).mean()
        if advice_losses
        else torch.zeros((), dtype=edge_loss.dtype, device=edge_loss.device)
    )
    return edge_loss + 0.25 * residual_loss + 0.25 * advice_loss


def _evaluate_bc_loss(
    policy: SharedEdgeActorCriticPolicy,
    records: Sequence[LearningFrameRecord],
    mean: np.ndarray,
    scale: np.ndarray,
    *,
    positive_class_weight_cap: float = 1.0,
) -> float:
    policy.eval()
    with torch.no_grad():
        return float(
            _bc_batch_loss(
                policy,
                records,
                mean,
                scale,
                positive_class_weight_cap=positive_class_weight_cap,
            ).item()
        )


def _whole_seed_metrics(
    policy: SharedEdgeActorCriticPolicy,
    records: Sequence[LearningFrameRecord],
    mean: np.ndarray,
    scale: np.ndarray,
) -> dict[str, Mapping[str, float | int | str]]:
    groups: dict[tuple[int, str], list[LearningFrameRecord]] = {}
    for record in records:
        groups.setdefault((record.seed, record.split), []).append(record)
    metrics: dict[str, Mapping[str, float | int | str]] = {}
    device = next(policy.parameters()).device
    policy.eval()
    with torch.no_grad():
        for (seed, split), frames in sorted(groups.items()):
            edge_correct = 0
            edge_count = 0
            advice_correct = 0
            advice_count = 0
            for record in frames:
                if not len(record.candidate_edge_indices):
                    continue
                normalized = (record.candidate_features - mean) / scale
                features = torch.as_tensor(
                    normalized, dtype=torch.float32, device=device
                )
                mask = torch.ones(features.shape[0], dtype=torch.bool, device=device)
                _, _, selection, advice_logits, _ = policy(features, mask)
                predicted = (torch.sigmoid(selection) >= 0.5).cpu().numpy()
                labels = record.selected_edge_labels.astype(bool)
                edge_correct += int(np.count_nonzero(predicted == labels))
                edge_count += len(labels)
                if record.advice_allowed:
                    target = 1 if record.hold_label else 2 if record.replan_label else 0
                    advice_correct += int(int(torch.argmax(advice_logits).item()) == target)
                    advice_count += 1
            key = f"seed:{seed}"
            metrics[key] = {
                "seed": int(seed),
                "split": split,
                "scenario_count": len({frame.scenario_version for frame in frames}),
                "frame_count": len(frames),
                "edge_count": edge_count,
                "edge_accuracy": (
                    0.0 if edge_count == 0 else edge_correct / edge_count
                ),
                "advice_frame_count": advice_count,
                "advice_accuracy": (
                    0.0 if advice_count == 0 else advice_correct / advice_count
                ),
            }
    return metrics


def _assert_disjoint_seed_groups(
    first: Sequence[LearningFrameRecord],
    second: Sequence[LearningFrameRecord],
) -> None:
    first_groups = {item.seed_group for item in first}
    second_groups = {item.seed_group for item in second}
    overlap = first_groups & second_groups
    if overlap:
        raise ValueError(f"train/validation seed leakage detected: {sorted(overlap)}")


def _training_records(
    records: Iterable[LearningFrameRecord],
    *,
    allowed_splits: set[str],
) -> tuple[LearningFrameRecord, ...]:
    """Materialize only explicit training splits and reject test consumption."""

    items = tuple(records)
    if not items:
        raise ValueError("at least one training frame is required")
    seen_frames: set[tuple[str, int, str, int]] = set()
    seed_splits: dict[int, str] = {}
    for item in items:
        if item.split == "test":
            raise ValueError(
                "training entry points cannot consume test seed frames; "
                "use the independent shadow evaluation entry point"
            )
        if item.split not in allowed_splits:
            raise ValueError(
                f"training entry point received unsupported split: {item.split}"
            )
        frame_key = (*item.episode_group, int(item.frame_index))
        if frame_key in seen_frames:
            raise ValueError(f"duplicate training frame: {frame_key}")
        seen_frames.add(frame_key)
        prior = seed_splits.setdefault(item.seed_group, item.split)
        if prior != item.split:
            raise ValueError("one numeric seed appears in multiple training splits")
    return items
