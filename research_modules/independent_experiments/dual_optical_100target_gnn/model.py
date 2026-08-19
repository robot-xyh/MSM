"""Small dependency-free PyTorch bipartite message-passing network."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
from torch import nn

from .schema import OnlineGraph


@dataclass(frozen=True)
class FeatureNormalizer:
    node_mean: tuple[float, ...]
    node_std: tuple[float, ...]
    edge_mean: tuple[float, ...]
    edge_std: tuple[float, ...]

    @classmethod
    def fit(cls, graphs: Iterable[OnlineGraph]) -> "FeatureNormalizer":
        graph_list = list(graphs)
        nodes = [
            values
            for graph in graph_list
            for values in (graph.node_features_a, graph.node_features_b)
            if len(values)
        ]
        edges = [graph.edge_features for graph in graph_list if len(graph.edge_features)]
        if not nodes or not edges:
            raise ValueError("normalization requires non-empty training nodes and edges")
        node_values = np.vstack(nodes).astype(np.float64)
        edge_values = np.vstack(edges).astype(np.float64)
        node_std = np.std(node_values, axis=0)
        edge_std = np.std(edge_values, axis=0)
        node_std[node_std < 1e-6] = 1.0
        edge_std[edge_std < 1e-6] = 1.0
        return cls(
            tuple(float(value) for value in np.mean(node_values, axis=0)),
            tuple(float(value) for value in node_std),
            tuple(float(value) for value in np.mean(edge_values, axis=0)),
            tuple(float(value) for value in edge_std),
        )

    def normalize_graph(self, graph: OnlineGraph) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        node_mean = np.asarray(self.node_mean, dtype=np.float32)
        node_std = np.asarray(self.node_std, dtype=np.float32)
        edge_mean = np.asarray(self.edge_mean, dtype=np.float32)
        edge_std = np.asarray(self.edge_std, dtype=np.float32)
        return (
            (graph.node_features_a - node_mean) / node_std,
            (graph.node_features_b - node_mean) / node_std,
            (graph.edge_features - edge_mean) / edge_std,
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(
                {
                    "node_mean": self.node_mean,
                    "node_std": self.node_std,
                    "edge_mean": self.edge_mean,
                    "edge_std": self.edge_std,
                    "fit_split": "train_only",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "FeatureNormalizer":
        values = json.loads(Path(path).read_text(encoding="utf-8"))
        if values.get("fit_split") != "train_only":
            raise ValueError("normalizer was not marked train-only")
        return cls(
            tuple(values["node_mean"]),
            tuple(values["node_std"]),
            tuple(values["edge_mean"]),
            tuple(values["edge_std"]),
        )


class MessagePassingBlock(nn.Module):
    def __init__(self, hidden_dim: int, dropout: float) -> None:
        super().__init__()
        self.to_a = nn.Linear(hidden_dim * 2, hidden_dim)
        self.to_b = nn.Linear(hidden_dim * 2, hidden_dim)
        self.self_a = nn.Linear(hidden_dim, hidden_dim)
        self.self_b = nn.Linear(hidden_dim, hidden_dim)
        self.norm_a = nn.LayerNorm(hidden_dim)
        self.norm_b = nn.LayerNorm(hidden_dim)
        self.dropout = nn.Dropout(dropout)

    @staticmethod
    def _mean_aggregate(messages: torch.Tensor, index: torch.Tensor, count: int) -> torch.Tensor:
        result = torch.zeros(
            (count, messages.shape[1]), device=messages.device, dtype=messages.dtype
        )
        result.index_add_(0, index, messages)
        degree = torch.zeros((count, 1), device=messages.device, dtype=messages.dtype)
        degree.index_add_(0, index, torch.ones((len(index), 1), device=messages.device, dtype=messages.dtype))
        return result / degree.clamp_min(1.0)

    def forward(
        self,
        node_a: torch.Tensor,
        node_b: torch.Tensor,
        edge_hidden: torch.Tensor,
        edge_index: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        index_a, index_b = edge_index
        message_a = torch.relu(self.to_a(torch.cat([node_b[index_b], edge_hidden], dim=1)))
        message_b = torch.relu(self.to_b(torch.cat([node_a[index_a], edge_hidden], dim=1)))
        aggregate_a = self._mean_aggregate(message_a, index_a, len(node_a))
        aggregate_b = self._mean_aggregate(message_b, index_b, len(node_b))
        updated_a = self.norm_a(self.self_a(node_a) + aggregate_a)
        updated_b = self.norm_b(self.self_b(node_b) + aggregate_b)
        return self.dropout(torch.relu(updated_a)), self.dropout(torch.relu(updated_b))


class BipartiteEdgeGNN(nn.Module):
    def __init__(
        self,
        node_feature_dim: int,
        edge_feature_dim: int,
        *,
        hidden_dim: int = 64,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.node_encoder = nn.Sequential(
            nn.Linear(node_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.edge_encoder = nn.Sequential(
            nn.Linear(edge_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.layers = nn.ModuleList(
            [MessagePassingBlock(hidden_dim, dropout) for _ in range(2)]
        )
        self.edge_classifier = nn.Sequential(
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )
        self.hidden_dim = int(hidden_dim)
        self.dropout_rate = float(dropout)

    def forward(
        self,
        node_features_a: torch.Tensor,
        node_features_b: torch.Tensor,
        edge_features: torch.Tensor,
        edge_index: torch.Tensor,
    ) -> torch.Tensor:
        node_a = self.node_encoder(node_features_a)
        node_b = self.node_encoder(node_features_b)
        edge_hidden = self.edge_encoder(edge_features)
        for layer in self.layers:
            node_a, node_b = layer(node_a, node_b, edge_hidden, edge_index)
        index_a, index_b = edge_index
        pair_hidden = torch.cat(
            [
                node_a[index_a],
                node_b[index_b],
                torch.abs(node_a[index_a] - node_b[index_b]),
                edge_hidden,
            ],
            dim=1,
        )
        return self.edge_classifier(pair_hidden).squeeze(1)


def graph_tensors(
    graph: OnlineGraph,
    normalizer: FeatureNormalizer,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    node_a, node_b, edges = normalizer.normalize_graph(graph)
    return (
        torch.as_tensor(node_a, dtype=torch.float32, device=device),
        torch.as_tensor(node_b, dtype=torch.float32, device=device),
        torch.as_tensor(edges, dtype=torch.float32, device=device),
        torch.as_tensor(graph.edge_index, dtype=torch.long, device=device),
    )


def save_weights_only(model: BipartiteEdgeGNN, path: str | Path) -> None:
    torch.save(model.state_dict(), Path(path))


def load_weights_only(
    model: BipartiteEdgeGNN,
    path: str | Path,
    *,
    map_location: str | torch.device = "cpu",
) -> None:
    state = torch.load(Path(path), map_location=map_location, weights_only=True)
    model.load_state_dict(state)
