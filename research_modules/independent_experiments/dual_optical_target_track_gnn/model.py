"""Two-encoder bipartite GNN that emits bounded rule-cost corrections."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import torch
from torch import nn

from .contracts import TargetTrackGraph


MODEL_SCHEMA_VERSION = "dual-optical-target-track-gnn-weights-v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class FeatureNormalizer:
    target_mean: tuple[float, ...]
    target_std: tuple[float, ...]
    track_mean: tuple[float, ...]
    track_std: tuple[float, ...]
    edge_mean: tuple[float, ...]
    edge_std: tuple[float, ...]

    @staticmethod
    def _statistics(values: np.ndarray) -> tuple[tuple[float, ...], tuple[float, ...]]:
        mean = np.mean(values.astype(np.float64), axis=0)
        std = np.std(values.astype(np.float64), axis=0)
        std[std < 1.0e-6] = 1.0
        return (
            tuple(float(value) for value in mean),
            tuple(float(value) for value in std),
        )

    @classmethod
    def fit(cls, graphs: Iterable[TargetTrackGraph]) -> "FeatureNormalizer":
        graph_list = list(graphs)
        for graph in graph_list:
            graph.validate()
        targets = [graph.target_features for graph in graph_list if len(graph.target_features)]
        tracks = [graph.track_features for graph in graph_list if len(graph.track_features)]
        edges = [graph.edge_features for graph in graph_list if len(graph.edge_features)]
        if not targets or not tracks or not edges:
            raise ValueError("normalization requires target, track, and edge training values")
        target_mean, target_std = cls._statistics(np.vstack(targets))
        track_mean, track_std = cls._statistics(np.vstack(tracks))
        edge_mean, edge_std = cls._statistics(np.vstack(edges))
        return cls(
            target_mean=target_mean,
            target_std=target_std,
            track_mean=track_mean,
            track_std=track_std,
            edge_mean=edge_mean,
            edge_std=edge_std,
        )

    def normalize_graph(
        self, graph: TargetTrackGraph
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        graph.validate()
        target_mean = np.asarray(self.target_mean, dtype=np.float32)
        target_std = np.asarray(self.target_std, dtype=np.float32)
        track_mean = np.asarray(self.track_mean, dtype=np.float32)
        track_std = np.asarray(self.track_std, dtype=np.float32)
        edge_mean = np.asarray(self.edge_mean, dtype=np.float32)
        edge_std = np.asarray(self.edge_std, dtype=np.float32)
        if graph.target_features.shape[1] != len(target_mean):
            raise ValueError("target normalizer width does not match graph")
        if graph.track_features.shape[1] != len(track_mean):
            raise ValueError("track normalizer width does not match graph")
        if graph.edge_features.shape[1] != len(edge_mean):
            raise ValueError("edge normalizer width does not match graph")
        return (
            (graph.target_features - target_mean) / target_std,
            (graph.track_features - track_mean) / track_std,
            (graph.edge_features - edge_mean) / edge_std,
        )

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "fit_split": "train_only"}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FeatureNormalizer":
        if payload.get("fit_split") != "train_only":
            raise ValueError("normalizer must be fitted on training data only")
        return cls(
            target_mean=tuple(float(value) for value in payload["target_mean"]),
            target_std=tuple(float(value) for value in payload["target_std"]),
            track_mean=tuple(float(value) for value in payload["track_mean"]),
            track_std=tuple(float(value) for value in payload["track_std"]),
            edge_mean=tuple(float(value) for value in payload["edge_mean"]),
            edge_std=tuple(float(value) for value in payload["edge_std"]),
        )


class MessageExchange(nn.Module):
    def __init__(self, hidden_dim: int, dropout: float) -> None:
        super().__init__()
        self.to_target = nn.Linear(hidden_dim * 2, hidden_dim)
        self.to_track = nn.Linear(hidden_dim * 2, hidden_dim)
        self.target_self = nn.Linear(hidden_dim, hidden_dim)
        self.track_self = nn.Linear(hidden_dim, hidden_dim)
        self.target_norm = nn.LayerNorm(hidden_dim)
        self.track_norm = nn.LayerNorm(hidden_dim)
        self.dropout = nn.Dropout(dropout)

    @staticmethod
    def _mean(messages: torch.Tensor, index: torch.Tensor, count: int) -> torch.Tensor:
        result = torch.zeros(
            (count, messages.shape[1]), dtype=messages.dtype, device=messages.device
        )
        if len(index):
            result.index_add_(0, index, messages)
        degree = torch.zeros((count, 1), dtype=messages.dtype, device=messages.device)
        if len(index):
            degree.index_add_(
                0,
                index,
                torch.ones((len(index), 1), dtype=messages.dtype, device=messages.device),
            )
        return result / degree.clamp_min(1.0)

    def forward(
        self,
        target_hidden: torch.Tensor,
        track_hidden: torch.Tensor,
        edge_hidden: torch.Tensor,
        edge_index: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        target_index, track_index = edge_index
        to_target = torch.relu(
            self.to_target(torch.cat((track_hidden[track_index], edge_hidden), dim=1))
        )
        to_track = torch.relu(
            self.to_track(torch.cat((target_hidden[target_index], edge_hidden), dim=1))
        )
        target_aggregate = self._mean(to_target, target_index, len(target_hidden))
        track_aggregate = self._mean(to_track, track_index, len(track_hidden))
        updated_target = self.target_norm(
            self.target_self(target_hidden) + target_aggregate
        )
        updated_track = self.track_norm(self.track_self(track_hidden) + track_aggregate)
        return (
            self.dropout(torch.relu(updated_target)),
            self.dropout(torch.relu(updated_track)),
        )


class TargetTrackCostGNN(nn.Module):
    """Two-round heterogeneous graph network with a bounded correction head."""

    def __init__(
        self,
        target_feature_dim: int,
        track_feature_dim: int,
        edge_feature_dim: int,
        *,
        hidden_dim: int = 64,
        dropout: float = 0.1,
        maximum_abs_correction: float = 1.0,
    ) -> None:
        super().__init__()
        if hidden_dim != 64:
            raise ValueError("the target-track GNN contract fixes hidden_dim=64")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if maximum_abs_correction <= 0.0:
            raise ValueError("maximum_abs_correction must be positive")
        self.target_encoder = nn.Sequential(
            nn.Linear(target_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.track_encoder = nn.Sequential(
            nn.Linear(track_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.edge_encoder = nn.Sequential(
            nn.Linear(edge_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )
        self.exchanges = nn.ModuleList(
            [MessageExchange(hidden_dim, dropout) for _ in range(2)]
        )
        self.correction_head = nn.Sequential(
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )
        self.target_feature_dim = int(target_feature_dim)
        self.track_feature_dim = int(track_feature_dim)
        self.edge_feature_dim = int(edge_feature_dim)
        self.hidden_dim = int(hidden_dim)
        self.dropout_rate = float(dropout)
        self.maximum_abs_correction = float(maximum_abs_correction)

    def forward(
        self,
        target_features: torch.Tensor,
        track_features: torch.Tensor,
        edge_features: torch.Tensor,
        edge_index: torch.Tensor,
    ) -> torch.Tensor:
        target_hidden = self.target_encoder(target_features)
        track_hidden = self.track_encoder(track_features)
        edge_hidden = self.edge_encoder(edge_features)
        for exchange in self.exchanges:
            target_hidden, track_hidden = exchange(
                target_hidden, track_hidden, edge_hidden, edge_index
            )
        target_index, track_index = edge_index
        pair_hidden = torch.cat(
            (
                target_hidden[target_index],
                track_hidden[track_index],
                torch.abs(target_hidden[target_index] - track_hidden[track_index]),
                edge_hidden,
            ),
            dim=1,
        )
        raw = self.correction_head(pair_hidden).squeeze(1)
        return torch.tanh(raw) * self.maximum_abs_correction


def graph_tensors(
    graph: TargetTrackGraph,
    normalizer: FeatureNormalizer,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    targets, tracks, edges = normalizer.normalize_graph(graph)
    return (
        torch.as_tensor(targets, dtype=torch.float32, device=device),
        torch.as_tensor(tracks, dtype=torch.float32, device=device),
        torch.as_tensor(edges, dtype=torch.float32, device=device),
        torch.as_tensor(graph.edge_index, dtype=torch.long, device=device),
    )


def predict_cost_corrections(
    model: TargetTrackCostGNN,
    graph: TargetTrackGraph,
    normalizer: FeatureNormalizer,
    *,
    device: str | torch.device = "cpu",
) -> np.ndarray:
    if graph.edge_index.shape[1] == 0:
        return np.empty(0, dtype=np.float32)
    target_device = torch.device(device)
    model = model.to(target_device)
    model.eval()
    with torch.no_grad():
        corrections = model(*graph_tensors(graph, normalizer, target_device))
    values = corrections.detach().cpu().numpy().astype(np.float32)
    if values.shape != graph.rule_cost.shape or not np.all(np.isfinite(values)):
        raise ValueError("GNN returned an invalid cost correction vector")
    if np.any(np.abs(values) > model.maximum_abs_correction + 1.0e-6):
        raise ValueError("GNN correction exceeded its declared bound")
    return values


def freeze_model(
    model: TargetTrackCostGNN,
    normalizer: FeatureNormalizer,
    output_dir: str | Path,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Write weights plus a JSON manifest; no executable object is serialized."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    weights_path = root / "target_track_gnn_weights.pt"
    torch.save(model.state_dict(), weights_path)
    manifest = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "weights_file": weights_path.name,
        "weights_sha256": _sha256_file(weights_path),
        "model": {
            "target_feature_dim": model.target_feature_dim,
            "track_feature_dim": model.track_feature_dim,
            "edge_feature_dim": model.edge_feature_dim,
            "hidden_dim": model.hidden_dim,
            "message_passing_rounds": 2,
            "dropout": model.dropout_rate,
            "maximum_abs_correction": model.maximum_abs_correction,
        },
        "normalizer": normalizer.to_dict(),
        "metadata": dict(metadata or {}),
    }
    (root / "freeze_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_frozen_model(
    output_dir: str | Path,
    *,
    map_location: str | torch.device = "cpu",
) -> tuple[TargetTrackCostGNN, FeatureNormalizer, Mapping[str, Any]]:
    root = Path(output_dir)
    manifest = json.loads((root / "freeze_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MODEL_SCHEMA_VERSION:
        raise ValueError("unsupported target-track GNN freeze schema")
    model_values = manifest["model"]
    if int(model_values.get("message_passing_rounds", -1)) != 2:
        raise ValueError("frozen model does not use two message-passing rounds")
    model = TargetTrackCostGNN(
        target_feature_dim=int(model_values["target_feature_dim"]),
        track_feature_dim=int(model_values["track_feature_dim"]),
        edge_feature_dim=int(model_values["edge_feature_dim"]),
        hidden_dim=int(model_values["hidden_dim"]),
        dropout=float(model_values["dropout"]),
        maximum_abs_correction=float(model_values["maximum_abs_correction"]),
    )
    weights_path = root / str(manifest["weights_file"])
    if _sha256_file(weights_path) != manifest["weights_sha256"]:
        raise ValueError("frozen target-track GNN weight hash mismatch")
    state = torch.load(weights_path, map_location=map_location, weights_only=True)
    model.load_state_dict(state)
    model.eval()
    return model, FeatureNormalizer.from_dict(manifest["normalizer"]), manifest
