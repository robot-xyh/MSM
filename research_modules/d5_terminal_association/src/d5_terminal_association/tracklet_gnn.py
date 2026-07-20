"""Native PyTorch edge classifier for the sparse camera-tracklet graph.

Evaluator labels enter only through :func:`build_offline_edge_training_batch`.
The online forward path consumes numeric node/edge features and emits one
same-target probability per existing sparse edge.  It never emits or binds a
``global_track_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .sparse_tracklet_graph import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    SparseTrackletGraph,
)


@dataclass(frozen=True)
class OfflineTrackletTruthLabel:
    """Evaluator-only tracklet label kept outside every online graph payload."""

    tracklet_key: str
    truth_entity_id: str
    measurement_timestamp: float

    def __post_init__(self) -> None:
        if not str(self.tracklet_key) or not str(self.truth_entity_id):
            raise ValueError("offline tracklet and truth IDs must be non-empty")
        if not np.isfinite(self.measurement_timestamp):
            raise ValueError("measurement_timestamp must be finite")


@dataclass(frozen=True)
class OfflineEdgeTrainingBatch:
    """Labels, hard-negative selection, and imbalance weight for one graph."""

    graph: SparseTrackletGraph
    targets: torch.Tensor
    training_mask: torch.Tensor
    hard_negative_mask: torch.Tensor
    positive_weight: torch.Tensor
    positive_count: int
    negative_count: int
    hard_negative_count: int

    def __post_init__(self) -> None:
        edge_count = self.graph.edge_count
        if self.targets.shape != (edge_count,):
            raise ValueError("targets must contain one value per graph edge")
        if self.training_mask.shape != (edge_count,) or self.training_mask.dtype != torch.bool:
            raise ValueError("training_mask must be a bool tensor per graph edge")
        if self.hard_negative_mask.shape != (edge_count,) or self.hard_negative_mask.dtype != torch.bool:
            raise ValueError("hard_negative_mask must be a bool tensor per graph edge")
        if self.positive_weight.numel() != 1:
            raise ValueError("positive_weight must be scalar")


@dataclass(frozen=True)
class SmallSampleTrainingEvidence:
    """Deterministic unit-scale training evidence, not an admission result."""

    epochs: int
    initial_loss: float
    final_loss: float
    positive_count: int
    negative_count: int
    hard_negative_count: int
    final_training_accuracy: float


def build_offline_edge_training_batch(
    graph: SparseTrackletGraph,
    labels: Iterable[OfflineTrackletTruthLabel],
    *,
    hard_negative_ratio: float = 3.0,
    max_hard_negatives_without_positive: int = 64,
    max_label_time_delta_s: float = 1.0e-6,
) -> OfflineEdgeTrainingBatch:
    """Join an independent truth stream after online graph construction.

    Negatives with the smallest geometry gate score are retained first.  This
    makes the selected negatives difficult candidates rather than random
    cross-camera pairs that geometry would already reject.
    """

    if hard_negative_ratio < 0.0:
        raise ValueError("hard_negative_ratio must be non-negative")
    if max_hard_negatives_without_positive <= 0:
        raise ValueError("max_hard_negatives_without_positive must be positive")
    if max_label_time_delta_s < 0.0 or not np.isfinite(max_label_time_delta_s):
        raise ValueError("max_label_time_delta_s must be finite and non-negative")
    node_time_by_key = {
        node.tracklet_key: node.measurement_timestamp for node in graph.nodes
    }
    label_by_key: dict[str, OfflineTrackletTruthLabel] = {}
    for label in labels:
        if label.tracklet_key in label_by_key:
            raise ValueError(f"duplicate offline label for {label.tracklet_key}")
        node_time = node_time_by_key.get(label.tracklet_key)
        if node_time is not None and abs(label.measurement_timestamp - node_time) > max_label_time_delta_s:
            raise ValueError(f"offline label timestamp does not align with {label.tracklet_key}")
        label_by_key[label.tracklet_key] = label

    targets = torch.zeros(graph.edge_count, dtype=torch.float32)
    eligible = torch.zeros(graph.edge_count, dtype=torch.bool)
    positive_indices: list[int] = []
    negative_indices: list[int] = []
    for edge_index, edge in enumerate(graph.edges):
        left = label_by_key.get(edge.source_tracklet_key)
        right = label_by_key.get(edge.target_tracklet_key)
        if left is None or right is None:
            continue
        eligible[edge_index] = True
        if left.truth_entity_id == right.truth_entity_id:
            targets[edge_index] = 1.0
            positive_indices.append(edge_index)
        else:
            negative_indices.append(edge_index)

    ordered_negatives = sorted(
        negative_indices,
        key=lambda index: (
            graph.edges[index].gate_score,
            graph.edges[index].source_tracklet_key,
            graph.edges[index].target_tracklet_key,
        ),
    )
    if positive_indices:
        negative_limit = int(math.ceil(len(positive_indices) * hard_negative_ratio))
        if hard_negative_ratio > 0.0:
            negative_limit = max(1, negative_limit)
    else:
        negative_limit = max_hard_negatives_without_positive
    selected_negatives = ordered_negatives[:negative_limit]

    training_mask = torch.zeros(graph.edge_count, dtype=torch.bool)
    hard_negative_mask = torch.zeros(graph.edge_count, dtype=torch.bool)
    if positive_indices:
        training_mask[torch.as_tensor(positive_indices, dtype=torch.long)] = True
    if selected_negatives:
        selected = torch.as_tensor(selected_negatives, dtype=torch.long)
        training_mask[selected] = True
        hard_negative_mask[selected] = True
    training_mask &= eligible
    selected_positive_count = len(positive_indices)
    selected_negative_count = len(selected_negatives)
    positive_weight = (
        max(1.0, selected_negative_count / selected_positive_count)
        if selected_positive_count
        else 1.0
    )
    return OfflineEdgeTrainingBatch(
        graph=graph,
        targets=targets,
        training_mask=training_mask,
        hard_negative_mask=hard_negative_mask,
        positive_weight=torch.tensor(float(positive_weight), dtype=torch.float32),
        positive_count=selected_positive_count,
        negative_count=selected_negative_count,
        hard_negative_count=len(selected_negatives),
    )


class NativeTrackletEdgeClassifier(nn.Module):
    """Small symmetric message-passing network using native ``index_add_``."""

    def __init__(
        self,
        *,
        node_feature_dim: int = len(NODE_FEATURE_NAMES),
        edge_feature_dim: int = len(EDGE_FEATURE_NAMES),
        hidden_dim: int = 32,
        message_passing_steps: int = 2,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()
        if node_feature_dim <= 0 or edge_feature_dim <= 0 or hidden_dim <= 0:
            raise ValueError("feature and hidden dimensions must be positive")
        if message_passing_steps <= 0:
            raise ValueError("message_passing_steps must be positive")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        self.node_feature_dim = int(node_feature_dim)
        self.edge_feature_dim = int(edge_feature_dim)
        self.hidden_dim = int(hidden_dim)
        self.message_passing_steps = int(message_passing_steps)
        self.dropout = float(dropout)
        self.uses_native_index_add = True

        self.node_encoder = nn.Sequential(
            nn.Linear(self.node_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.edge_encoder = nn.Sequential(
            nn.Linear(self.edge_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.message_networks = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(hidden_dim * 3, hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                    nn.Linear(hidden_dim, hidden_dim),
                )
                for _ in range(message_passing_steps)
            ]
        )
        self.update_networks = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(hidden_dim * 2, hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                    nn.Linear(hidden_dim, hidden_dim),
                )
                for _ in range(message_passing_steps)
            ]
        )
        self.normalizations = nn.ModuleList([nn.LayerNorm(hidden_dim) for _ in range(message_passing_steps)])
        self.edge_head = nn.Sequential(
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )
        edge_scales = torch.ones(self.edge_feature_dim, dtype=torch.float32)
        canonical_scales = torch.tensor(
            [0.35, 6.0, 10.0, 25.0, 1.0, 1.0, 1.0, 200.0, 1.0, 8.0, 0.5, 6.0, 1.0, 4.0],
            dtype=torch.float32,
        )
        if self.edge_feature_dim == canonical_scales.numel():
            edge_scales = canonical_scales
        self.register_buffer("edge_feature_scales", edge_scales)

    def edge_logits(
        self,
        node_features: torch.Tensor,
        edge_index: torch.Tensor,
        edge_features: torch.Tensor,
    ) -> torch.Tensor:
        """Return internal logits for loss computation."""

        self._validate_inputs(node_features, edge_index, edge_features)
        if edge_index.shape[1] == 0:
            return node_features.new_empty((0,))
        normalized_nodes = torch.nan_to_num(node_features, nan=0.0, posinf=20.0, neginf=-20.0).clamp(-20.0, 20.0)
        normalized_edges = torch.nan_to_num(
            edge_features / self.edge_feature_scales.to(edge_features),
            nan=0.0,
            posinf=20.0,
            neginf=-20.0,
        ).clamp(-20.0, 20.0)
        node_state = self.node_encoder(normalized_nodes)
        edge_state = self.edge_encoder(normalized_edges)
        source = edge_index[0]
        target = edge_index[1]

        for message_network, update_network, normalization in zip(
            self.message_networks,
            self.update_networks,
            self.normalizations,
            strict=True,
        ):
            pair_state = torch.cat((node_state[source], node_state[target], edge_state), dim=-1)
            messages = message_network(pair_state)
            aggregate = torch.zeros_like(node_state)
            aggregate.index_add_(0, source, messages)
            aggregate.index_add_(0, target, messages)
            degree = torch.zeros(node_state.shape[0], dtype=node_state.dtype, device=node_state.device)
            ones = torch.ones(source.shape[0], dtype=node_state.dtype, device=node_state.device)
            degree.index_add_(0, source, ones)
            degree.index_add_(0, target, ones)
            aggregate = aggregate / degree.clamp_min(1.0).unsqueeze(-1)
            update = update_network(torch.cat((node_state, aggregate), dim=-1))
            node_state = normalization(node_state + update)

        source_state = node_state[source]
        target_state = node_state[target]
        symmetric_pair = torch.cat(
            (
                source_state + target_state,
                torch.abs(source_state - target_state),
                source_state * target_state,
                edge_state,
            ),
            dim=-1,
        )
        return self.edge_head(symmetric_pair).squeeze(-1)

    def forward(
        self,
        node_features: torch.Tensor,
        edge_index: torch.Tensor,
        edge_features: torch.Tensor,
    ) -> torch.Tensor:
        """Return one same-target probability for each sparse graph edge."""

        return torch.sigmoid(self.edge_logits(node_features, edge_index, edge_features))

    def forward_graph(
        self,
        graph: SparseTrackletGraph,
        *,
        device: torch.device | str | None = None,
    ) -> torch.Tensor:
        node_features, edge_index, edge_features = graph_tensors(graph, device=device)
        return self(node_features, edge_index, edge_features)

    def _validate_inputs(
        self,
        node_features: torch.Tensor,
        edge_index: torch.Tensor,
        edge_features: torch.Tensor,
    ) -> None:
        if node_features.ndim != 2 or node_features.shape[1] != self.node_feature_dim:
            raise ValueError("node_features has an incompatible shape")
        if edge_index.ndim != 2 or edge_index.shape[0] != 2:
            raise ValueError("edge_index must have shape (2, edge_count)")
        if edge_index.dtype != torch.long:
            raise ValueError("edge_index must use torch.long")
        if edge_features.shape != (edge_index.shape[1], self.edge_feature_dim):
            raise ValueError("edge_features has an incompatible shape")
        if edge_index.numel() and (edge_index.min() < 0 or edge_index.max() >= node_features.shape[0]):
            raise ValueError("edge_index references an unknown node")


def graph_tensors(
    graph: SparseTrackletGraph,
    *,
    device: torch.device | str | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Convert immutable NumPy graph arrays to native PyTorch tensors."""

    return (
        torch.as_tensor(np.array(graph.node_features, copy=True), dtype=torch.float32, device=device),
        torch.as_tensor(np.array(graph.edge_index, copy=True), dtype=torch.long, device=device),
        torch.as_tensor(np.array(graph.edge_features, copy=True), dtype=torch.float32, device=device),
    )


def train_small_sample(
    model: NativeTrackletEdgeClassifier,
    batch: OfflineEdgeTrainingBatch,
    *,
    epochs: int = 80,
    learning_rate: float = 1.0e-2,
    weight_decay: float = 0.0,
    device: torch.device | str | None = None,
) -> SmallSampleTrainingEvidence:
    """Run deterministic small-sample fitting for tests and research smoke use."""

    if epochs <= 0 or learning_rate <= 0.0 or weight_decay < 0.0:
        raise ValueError("epochs/learning_rate must be positive and weight_decay non-negative")
    if not bool(torch.any(batch.training_mask)):
        raise ValueError("offline training batch contains no selected edges")
    model.to(device=device)
    node_features, edge_index, edge_features = graph_tensors(batch.graph, device=device)
    targets = batch.targets.to(device=device)
    training_mask = batch.training_mask.to(device=device)
    positive_weight = batch.positive_weight.to(device=device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    losses: list[float] = []
    model.train()
    for _ in range(int(epochs)):
        optimizer.zero_grad(set_to_none=True)
        logits = model.edge_logits(node_features, edge_index, edge_features)
        loss = F.binary_cross_entropy_with_logits(
            logits[training_mask],
            targets[training_mask],
            pos_weight=positive_weight,
        )
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach().cpu()))

    model.eval()
    with torch.no_grad():
        probabilities = model(node_features, edge_index, edge_features)
        predictions = probabilities[training_mask] >= 0.5
        expected = targets[training_mask] >= 0.5
        accuracy = float((predictions == expected).float().mean().cpu())
    return SmallSampleTrainingEvidence(
        epochs=int(epochs),
        initial_loss=losses[0],
        final_loss=losses[-1],
        positive_count=batch.positive_count,
        negative_count=batch.negative_count,
        hard_negative_count=batch.hard_negative_count,
        final_training_accuracy=accuracy,
    )


__all__ = [
    "NativeTrackletEdgeClassifier",
    "OfflineEdgeTrainingBatch",
    "OfflineTrackletTruthLabel",
    "SmallSampleTrainingEvidence",
    "build_offline_edge_training_batch",
    "graph_tensors",
    "train_small_sample",
]
