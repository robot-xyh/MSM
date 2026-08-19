"""Frozen model and training defaults for the candidate route."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


INITIALIZATION_SEEDS = (1103, 2207, 3301, 4409, 5501)
VALIDATION_THRESHOLDS = tuple(round(0.3 + 0.1 * index, 1) for index in range(7))


@dataclass(frozen=True)
class ModelConfig:
    observation_feature_dim: int = 10
    track_feature_dim: int = 15
    edge_feature_dim: int = 18
    history_length: int = 6
    descriptor_dim: int = 64
    attention_cycles: int = 2
    attention_heads: int = 4
    sinkhorn_iterations: int = 30
    dropout: float = 0.1

    def __post_init__(self) -> None:
        positive = {
            "observation_feature_dim": self.observation_feature_dim,
            "track_feature_dim": self.track_feature_dim,
            "edge_feature_dim": self.edge_feature_dim,
            "history_length": self.history_length,
            "descriptor_dim": self.descriptor_dim,
            "attention_cycles": self.attention_cycles,
            "attention_heads": self.attention_heads,
            "sinkhorn_iterations": self.sinkhorn_iterations,
        }
        if any(value <= 0 for value in positive.values()):
            raise ValueError("model dimensions and iteration counts must be positive")
        if self.descriptor_dim != 64:
            raise ValueError("the frozen route requires a 64-dimensional descriptor")
        if self.history_length != 6:
            raise ValueError("the frozen route requires the latest six observations")
        if self.attention_cycles != 2 or self.attention_heads != 4:
            raise ValueError("the frozen route requires two four-head attention cycles")
        if self.sinkhorn_iterations != 30:
            raise ValueError("the frozen route requires 30 log-Sinkhorn iterations")
        if self.track_feature_dim != 15 or self.edge_feature_dim != 18:
            raise ValueError("the route requires the existing 15/18 feature contract")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "ModelConfig":
        return cls(**{key: values[key] for key in asdict(cls()) if key in values})


@dataclass(frozen=True)
class TrainingConfig:
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-4
    dropout: float = 0.1
    max_epochs: int = 200
    patience: int = 25
    initialization_seeds: tuple[int, ...] = INITIALIZATION_SEEDS
    validation_thresholds: tuple[float, ...] = VALIDATION_THRESHOLDS
    matched_loss_weight: float = 0.5
    dustbin_loss_weight: float = 0.5
    device: str = "cpu"

    def __post_init__(self) -> None:
        if self.learning_rate <= 0.0 or self.weight_decay < 0.0:
            raise ValueError("optimizer values are invalid")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if self.max_epochs <= 0 or self.patience <= 0:
            raise ValueError("epoch and patience values must be positive")
        if len(self.initialization_seeds) != 5:
            raise ValueError("formal training requires five initializations")
        if self.validation_thresholds != VALIDATION_THRESHOLDS:
            raise ValueError("validation thresholds must be 0.3 through 0.9")
        if abs(self.matched_loss_weight - 0.5) > 1.0e-12:
            raise ValueError("matched loss contribution must be 50 percent")
        if abs(self.dustbin_loss_weight - 0.5) > 1.0e-12:
            raise ValueError("dustbin loss contribution must be 50 percent")
        if self.device not in {"cpu", "cuda", "auto"}:
            raise ValueError("device must be cpu, cuda, or auto")

    def to_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values["initialization_seeds"] = list(self.initialization_seeds)
        values["validation_thresholds"] = list(self.validation_thresholds)
        return values
