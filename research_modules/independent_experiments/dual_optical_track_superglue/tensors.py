"""CPU/GPU tensor conversion kept separate from snapshot adaptation."""

from __future__ import annotations

from dataclasses import dataclass

import torch

from .normalization import FeatureNormalizer
from .schema import TrackGraphInput


@dataclass(frozen=True)
class GraphTensors:
    histories_a: torch.Tensor
    histories_b: torch.Tensor
    lengths_a: torch.Tensor
    lengths_b: torch.Tensor
    track_features_a: torch.Tensor
    track_features_b: torch.Tensor
    edge_features: torch.Tensor
    candidate_mask: torch.Tensor

    def model_arguments(self) -> tuple[torch.Tensor, ...]:
        return (
            self.histories_a,
            self.histories_b,
            self.lengths_a,
            self.lengths_b,
            self.track_features_a,
            self.track_features_b,
            self.edge_features,
            self.candidate_mask,
        )


def graph_tensors(
    graph: TrackGraphInput,
    normalizer: FeatureNormalizer,
    device: torch.device | str = "cpu",
) -> GraphTensors:
    values = normalizer.normalize(graph)
    return GraphTensors(
        histories_a=torch.as_tensor(values.observation_history_a, dtype=torch.float32, device=device),
        histories_b=torch.as_tensor(values.observation_history_b, dtype=torch.float32, device=device),
        lengths_a=torch.as_tensor(values.history_lengths_a, dtype=torch.long, device=device),
        lengths_b=torch.as_tensor(values.history_lengths_b, dtype=torch.long, device=device),
        track_features_a=torch.as_tensor(values.track_features_a, dtype=torch.float32, device=device),
        track_features_b=torch.as_tensor(values.track_features_b, dtype=torch.float32, device=device),
        edge_features=torch.as_tensor(values.edge_features, dtype=torch.float32, device=device),
        candidate_mask=torch.as_tensor(values.candidate_mask, dtype=torch.bool, device=device),
    )
