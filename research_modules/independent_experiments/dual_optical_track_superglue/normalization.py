"""Train-only normalization for anonymous sequence, node, and edge features."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from .schema import TrackGraphInput


def _moments(values: np.ndarray) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if values.ndim != 2 or not len(values):
        raise ValueError("normalizer fitting requires non-empty two-dimensional values")
    mean = np.mean(values.astype(np.float64), axis=0)
    std = np.std(values.astype(np.float64), axis=0)
    std[std < 1.0e-6] = 1.0
    return tuple(float(value) for value in mean), tuple(float(value) for value in std)


@dataclass(frozen=True)
class FeatureNormalizer:
    observation_mean: tuple[float, ...]
    observation_std: tuple[float, ...]
    track_mean: tuple[float, ...]
    track_std: tuple[float, ...]
    edge_mean: tuple[float, ...]
    edge_std: tuple[float, ...]

    @classmethod
    def identity(
        cls,
        observation_dim: int = 10,
        track_dim: int = 15,
        edge_dim: int = 18,
    ) -> "FeatureNormalizer":
        return cls(
            (0.0,) * observation_dim,
            (1.0,) * observation_dim,
            (0.0,) * track_dim,
            (1.0,) * track_dim,
            (0.0,) * edge_dim,
            (1.0,) * edge_dim,
        )

    @classmethod
    def fit(cls, graphs: Iterable[TrackGraphInput]) -> "FeatureNormalizer":
        graph_list = list(graphs)
        if not graph_list:
            raise ValueError("normalizer fitting requires training graphs")
        observations = []
        tracks = []
        edges = []
        for graph in graph_list:
            graph.validate()
            for history, lengths in (
                (graph.observation_history_a, graph.history_lengths_a),
                (graph.observation_history_b, graph.history_lengths_b),
            ):
                observations.extend(history[index, : int(length)] for index, length in enumerate(lengths))
            if len(graph.track_features_a):
                tracks.append(graph.track_features_a)
            if len(graph.track_features_b):
                tracks.append(graph.track_features_b)
            if np.any(graph.candidate_mask):
                edges.append(graph.edge_features[graph.candidate_mask])
        if not observations or not tracks or not edges:
            raise ValueError("training graphs require observations, tracks, and candidate edges")
        observation_mean, observation_std = _moments(np.vstack(observations))
        track_mean, track_std = _moments(np.vstack(tracks))
        edge_mean, edge_std = _moments(np.vstack(edges))
        return cls(
            observation_mean,
            observation_std,
            track_mean,
            track_std,
            edge_mean,
            edge_std,
        )

    def normalize(self, graph: TrackGraphInput) -> TrackGraphInput:
        graph.validate()
        observation_mean = np.asarray(self.observation_mean, dtype=np.float32)
        observation_std = np.asarray(self.observation_std, dtype=np.float32)
        track_mean = np.asarray(self.track_mean, dtype=np.float32)
        track_std = np.asarray(self.track_std, dtype=np.float32)
        edge_mean = np.asarray(self.edge_mean, dtype=np.float32)
        edge_std = np.asarray(self.edge_std, dtype=np.float32)

        def normalized_history(values: np.ndarray, lengths: np.ndarray) -> np.ndarray:
            result = np.zeros_like(values, dtype=np.float32)
            for index, length in enumerate(lengths):
                width = int(length)
                result[index, :width] = (
                    values[index, :width] - observation_mean
                ) / observation_std
            return result

        edge_features = np.zeros_like(graph.edge_features, dtype=np.float32)
        edge_features[graph.candidate_mask] = (
            graph.edge_features[graph.candidate_mask] - edge_mean
        ) / edge_std
        return graph.replaced(
            observation_history_a=normalized_history(
                graph.observation_history_a, graph.history_lengths_a
            ),
            observation_history_b=normalized_history(
                graph.observation_history_b, graph.history_lengths_b
            ),
            track_features_a=(graph.track_features_a - track_mean) / track_std,
            track_features_b=(graph.track_features_b - track_mean) / track_std,
            edge_features=edge_features,
        )

    def save(self, path: str | Path) -> None:
        payload = {
            "schema_version": "track-superglue-normalizer-v1",
            "fit_split": "train_only",
            "observation_mean": self.observation_mean,
            "observation_std": self.observation_std,
            "track_mean": self.track_mean,
            "track_std": self.track_std,
            "edge_mean": self.edge_mean,
            "edge_std": self.edge_std,
        }
        Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "FeatureNormalizer":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema_version") != "track-superglue-normalizer-v1":
            raise ValueError("unsupported normalizer schema")
        if payload.get("fit_split") != "train_only":
            raise ValueError("normalizer was not fitted on train-only input")
        return cls(
            tuple(payload["observation_mean"]),
            tuple(payload["observation_std"]),
            tuple(payload["track_mean"]),
            tuple(payload["track_std"]),
            tuple(payload["edge_mean"]),
            tuple(payload["edge_std"]),
        )
