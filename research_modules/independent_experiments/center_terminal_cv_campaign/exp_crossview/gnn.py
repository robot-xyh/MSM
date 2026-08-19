"""Pure-PyTorch sparse candidate-edge ranking without torch_geometric."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import torch
from torch import nn

from ..common.contracts import LocalVisualTrackRecord
from .config import CameraCalibration
from .contracts import CandidateEdge, assert_online_anonymous
from .geometry import normalize, recognition_extent, validate_record_ray


NODE_FEATURE_NAMES = (
    "observation_count",
    "duration_s",
    "mean_bbox_extent_100px",
    "mean_track_quality",
    "camera_confidence",
    "bearing_rate_rad_s",
    "mean_arrival_delay_s",
)
EDGE_FEATURE_NAMES = (
    "time_offset_normalized",
    "ray_separation_normalized",
    "reprojection_normalized",
    "intersection_angle_20deg",
    "motion_fit_normalized",
    "motion_turn_normalized",
    "bbox_scale_difference",
    "camera_confidence",
    "sample_support",
)


@dataclass(frozen=True)
class SparseCandidateGraph:
    camera_a_id: str
    camera_b_id: str
    track_ids_a: tuple[str, ...]
    track_ids_b: tuple[str, ...]
    node_features_a: np.ndarray
    node_features_b: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    geometry_cost: np.ndarray

    def validate(self) -> None:
        if self.node_features_a.shape != (len(self.track_ids_a), len(NODE_FEATURE_NAMES)):
            raise ValueError("camera A node feature shape is invalid")
        if self.node_features_b.shape != (len(self.track_ids_b), len(NODE_FEATURE_NAMES)):
            raise ValueError("camera B node feature shape is invalid")
        if self.edge_index.shape != (2, len(self.edge_features)):
            raise ValueError("edge index shape is invalid")
        if self.edge_features.shape[1:] != (len(EDGE_FEATURE_NAMES),):
            raise ValueError("edge feature shape is invalid")
        if self.geometry_cost.shape != (len(self.edge_features),):
            raise ValueError("geometry cost shape is invalid")
        if not all(
            np.all(np.isfinite(values))
            for values in (
                self.node_features_a,
                self.node_features_b,
                self.edge_features,
                self.geometry_cost,
            )
        ):
            raise ValueError("graph features must be finite")

    def to_online_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": "terminal-crossview-sparse-graph-v1",
            "camera_a_id": self.camera_a_id,
            "camera_b_id": self.camera_b_id,
            "track_ids_a": self.track_ids_a,
            "track_ids_b": self.track_ids_b,
            "node_feature_names": NODE_FEATURE_NAMES,
            "edge_feature_names": EDGE_FEATURE_NAMES,
            "node_features_a": self.node_features_a.tolist(),
            "node_features_b": self.node_features_b.tolist(),
            "edge_index": self.edge_index.tolist(),
            "edge_features": self.edge_features.tolist(),
            "geometry_cost": self.geometry_cost.tolist(),
        }
        assert_online_anonymous(payload)
        return payload


def _node_features(
    history: Sequence[LocalVisualTrackRecord],
    calibration: CameraCalibration,
) -> tuple[float, ...]:
    ordered = sorted(history, key=lambda item: item.measurement_timestamp)
    duration = max(0.0, ordered[-1].measurement_timestamp - ordered[0].measurement_timestamp)
    bearing_rate = 0.0
    if duration > 1.0e-9 and len(ordered) >= 2:
        first = validate_record_ray(ordered[0], calibration)
        last = validate_record_ray(ordered[-1], calibration)
        bearing_rate = float(np.linalg.norm(last - first) / duration)
    return (
        min(len(ordered) / 10.0, 2.0),
        min(duration / 2.0, 2.0),
        min(float(np.mean([recognition_extent(item) for item in ordered])) / 100.0, 3.0),
        float(np.mean([item.track_quality for item in ordered])),
        calibration.confidence,
        min(bearing_rate, 2.0),
        min(
            float(
                np.mean(
                    [item.arrival_timestamp - item.measurement_timestamp for item in ordered]
                )
            ),
            1.0,
        ),
    )


def graph_from_candidates(
    histories_a: Mapping[str, Sequence[LocalVisualTrackRecord]],
    histories_b: Mapping[str, Sequence[LocalVisualTrackRecord]],
    candidates: Sequence[CandidateEdge],
    calibration_a: CameraCalibration,
    calibration_b: CameraCalibration,
) -> SparseCandidateGraph:
    if any(not item.gate_passed for item in candidates):
        raise ValueError("GNN input must contain geometry-gated edges only")
    track_ids_a = tuple(sorted(histories_a))
    track_ids_b = tuple(sorted(histories_b))
    index_a = {value: index for index, value in enumerate(track_ids_a)}
    index_b = {value: index for index, value in enumerate(track_ids_b)}
    edge_index = np.asarray(
        (
            [index_a[item.track_a_id] for item in candidates],
            [index_b[item.track_b_id] for item in candidates],
        ),
        dtype=np.int64,
    )
    if not candidates:
        edge_index = np.empty((2, 0), dtype=np.int64)
    graph = SparseCandidateGraph(
        camera_a_id=calibration_a.camera_id,
        camera_b_id=calibration_b.camera_id,
        track_ids_a=track_ids_a,
        track_ids_b=track_ids_b,
        node_features_a=np.asarray(
            [_node_features(histories_a[value], calibration_a) for value in track_ids_a],
            dtype=np.float32,
        ),
        node_features_b=np.asarray(
            [_node_features(histories_b[value], calibration_b) for value in track_ids_b],
            dtype=np.float32,
        ),
        edge_index=edge_index,
        edge_features=np.asarray(
            [item.edge_features for item in candidates], dtype=np.float32
        ).reshape((-1, len(EDGE_FEATURE_NAMES))),
        geometry_cost=np.asarray(
            [item.geometry_cost for item in candidates], dtype=np.float32
        ),
    )
    graph.validate()
    return graph


@dataclass(frozen=True)
class GraphNormalizer:
    node_mean: tuple[float, ...]
    node_std: tuple[float, ...]
    edge_mean: tuple[float, ...]
    edge_std: tuple[float, ...]

    @classmethod
    def fit(cls, graphs: Sequence[SparseCandidateGraph]) -> "GraphNormalizer":
        nodes = [
            values
            for graph in graphs
            for values in (graph.node_features_a, graph.node_features_b)
            if len(values)
        ]
        edges = [graph.edge_features for graph in graphs if len(graph.edge_features)]
        if not nodes or not edges:
            raise ValueError("normalization requires non-empty training graphs")
        node_values = np.vstack(nodes).astype(float)
        edge_values = np.vstack(edges).astype(float)
        node_std = np.std(node_values, axis=0)
        edge_std = np.std(edge_values, axis=0)
        node_std[node_std < 1.0e-6] = 1.0
        edge_std[edge_std < 1.0e-6] = 1.0
        return cls(
            tuple(float(value) for value in np.mean(node_values, axis=0)),
            tuple(float(value) for value in node_std),
            tuple(float(value) for value in np.mean(edge_values, axis=0)),
            tuple(float(value) for value in edge_std),
        )

    def normalize(
        self, graph: SparseCandidateGraph
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        node_mean = np.asarray(self.node_mean, dtype=np.float32)
        node_std = np.asarray(self.node_std, dtype=np.float32)
        edge_mean = np.asarray(self.edge_mean, dtype=np.float32)
        edge_std = np.asarray(self.edge_std, dtype=np.float32)
        return (
            (graph.node_features_a - node_mean) / node_std,
            (graph.node_features_b - node_mean) / node_std,
            (graph.edge_features - edge_mean) / edge_std,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "node_mean": self.node_mean,
            "node_std": self.node_std,
            "edge_mean": self.edge_mean,
            "edge_std": self.edge_std,
            "fit_split": "train_only",
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "GraphNormalizer":
        if payload.get("fit_split") != "train_only":
            raise ValueError("normalizer was not fitted on the train split")
        return cls(
            tuple(float(value) for value in payload["node_mean"]),  # type: ignore[arg-type]
            tuple(float(value) for value in payload["node_std"]),  # type: ignore[arg-type]
            tuple(float(value) for value in payload["edge_mean"]),  # type: ignore[arg-type]
            tuple(float(value) for value in payload["edge_std"]),  # type: ignore[arg-type]
        )


class _MessageBlock(nn.Module):
    def __init__(self, hidden_dim: int) -> None:
        super().__init__()
        self.to_a = nn.Linear(hidden_dim * 2, hidden_dim)
        self.to_b = nn.Linear(hidden_dim * 2, hidden_dim)
        self.self_a = nn.Linear(hidden_dim, hidden_dim)
        self.self_b = nn.Linear(hidden_dim, hidden_dim)
        self.norm_a = nn.LayerNorm(hidden_dim)
        self.norm_b = nn.LayerNorm(hidden_dim)

    @staticmethod
    def _aggregate(messages: torch.Tensor, index: torch.Tensor, count: int) -> torch.Tensor:
        output = torch.zeros((count, messages.shape[1]), device=messages.device, dtype=messages.dtype)
        degree = torch.zeros((count, 1), device=messages.device, dtype=messages.dtype)
        if len(index):
            output.index_add_(0, index, messages)
            degree.index_add_(0, index, torch.ones((len(index), 1), device=index.device))
        return output / degree.clamp_min(1.0)

    def forward(
        self,
        nodes_a: torch.Tensor,
        nodes_b: torch.Tensor,
        edges: torch.Tensor,
        edge_index: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        index_a, index_b = edge_index
        messages_a = torch.relu(self.to_a(torch.cat((nodes_b[index_b], edges), dim=1)))
        messages_b = torch.relu(self.to_b(torch.cat((nodes_a[index_a], edges), dim=1)))
        updated_a = self.norm_a(self.self_a(nodes_a) + self._aggregate(messages_a, index_a, len(nodes_a)))
        updated_b = self.norm_b(self.self_b(nodes_b) + self._aggregate(messages_b, index_b, len(nodes_b)))
        return torch.relu(updated_a), torch.relu(updated_b)


class SparseEdgeGNN(nn.Module):
    def __init__(self, hidden_dim: int = 48) -> None:
        super().__init__()
        self.node_encoder = nn.Sequential(
            nn.Linear(len(NODE_FEATURE_NAMES), hidden_dim), nn.ReLU(), nn.LayerNorm(hidden_dim)
        )
        self.edge_encoder = nn.Sequential(
            nn.Linear(len(EDGE_FEATURE_NAMES), hidden_dim), nn.ReLU(), nn.LayerNorm(hidden_dim)
        )
        self.message_blocks = nn.ModuleList((_MessageBlock(hidden_dim), _MessageBlock(hidden_dim)))
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )
        self.hidden_dim = int(hidden_dim)

    def forward(
        self,
        node_features_a: torch.Tensor,
        node_features_b: torch.Tensor,
        edge_features: torch.Tensor,
        edge_index: torch.Tensor,
    ) -> torch.Tensor:
        nodes_a = self.node_encoder(node_features_a)
        nodes_b = self.node_encoder(node_features_b)
        edges = self.edge_encoder(edge_features)
        for block in self.message_blocks:
            nodes_a, nodes_b = block(nodes_a, nodes_b, edges, edge_index)
        index_a, index_b = edge_index
        pairs = torch.cat(
            (nodes_a[index_a], nodes_b[index_b], torch.abs(nodes_a[index_a] - nodes_b[index_b]), edges),
            dim=1,
        )
        return self.classifier(pairs).squeeze(1)


def _graph_tensors(
    graph: SparseCandidateGraph,
    normalizer: GraphNormalizer,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    node_a, node_b, edges = normalizer.normalize(graph)
    return (
        torch.as_tensor(node_a, dtype=torch.float32, device=device),
        torch.as_tensor(node_b, dtype=torch.float32, device=device),
        torch.as_tensor(edges, dtype=torch.float32, device=device),
        torch.as_tensor(graph.edge_index, dtype=torch.long, device=device),
    )


class GNNCandidateScorer:
    def __init__(
        self,
        model: SparseEdgeGNN,
        normalizer: GraphNormalizer,
        *,
        device: str | torch.device = "cpu",
    ) -> None:
        self.device = torch.device(device)
        self.model = model.to(self.device).eval()
        self.normalizer = normalizer

    def score(
        self,
        histories_a: Mapping[str, Sequence[LocalVisualTrackRecord]],
        histories_b: Mapping[str, Sequence[LocalVisualTrackRecord]],
        candidates: Sequence[CandidateEdge],
        calibration_a: CameraCalibration,
        calibration_b: CameraCalibration,
    ) -> Mapping[tuple[str, str], float]:
        if not candidates:
            return {}
        graph = graph_from_candidates(
            histories_a, histories_b, candidates, calibration_a, calibration_b
        )
        with torch.no_grad():
            probabilities = torch.sigmoid(
                self.model(*_graph_tensors(graph, self.normalizer, self.device))
            ).cpu().numpy()
        return {
            (candidate.track_a_id, candidate.track_b_id): float(probability)
            for candidate, probability in zip(candidates, probabilities, strict=True)
        }


def save_model_bundle(
    output_dir: Path,
    model: SparseEdgeGNN,
    normalizer: GraphNormalizer,
    manifest: Mapping[str, object],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output_dir / "weights.pt")
    (output_dir / "normalizer.json").write_text(
        json.dumps(normalizer.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    hashes = {}
    for filename in ("weights.pt", "normalizer.json"):
        digest = hashlib.sha256()
        with (output_dir / filename).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        hashes[filename] = digest.hexdigest()
    payload = {
        **dict(manifest),
        "schema_version": "terminal-crossview-gnn-freeze-v2",
        "hidden_dim": model.hidden_dim,
        "weights_file": "weights.pt",
        "normalizer_file": "normalizer.json",
        "node_feature_names": NODE_FEATURE_NAMES,
        "edge_feature_names": EDGE_FEATURE_NAMES,
        "sha256": hashes,
        "torch_geometric_used": False,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return output_dir


def load_model_bundle(
    model_dir: Path,
    *,
    device: str | torch.device = "cpu",
    evaluation_seeds: Sequence[int] = (),
) -> GNNCandidateScorer:
    manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "terminal-crossview-gnn-freeze-v2":
        raise ValueError("unsupported GNN model bundle")
    if tuple(manifest.get("node_feature_names", ())) != NODE_FEATURE_NAMES:
        raise ValueError("GNN node feature contract mismatch")
    if tuple(manifest.get("edge_feature_names", ())) != EDGE_FEATURE_NAMES:
        raise ValueError("GNN edge feature contract mismatch")
    hashes = manifest.get("sha256")
    if not isinstance(hashes, Mapping):
        raise ValueError("GNN model bundle is missing SHA256 metadata")
    for filename_key in ("weights_file", "normalizer_file"):
        filename = str(manifest[filename_key])
        if filename not in {"weights.pt", "normalizer.json"}:
            raise ValueError("GNN model bundle contains an unexpected file path")
        expected = str(hashes.get(filename, ""))
        digest = hashlib.sha256()
        with (model_dir / filename).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError(f"SHA256 mismatch for GNN bundle file {filename}")
    train_seeds = {int(value) for value in manifest.get("train_seeds", ())}
    validation_seeds = {int(value) for value in manifest.get("validation_seeds", ())}
    if int(manifest.get("seed_overlap_count", -1)) != 0:
        raise ValueError("GNN model bundle does not certify seed isolation")
    if train_seeds & validation_seeds:
        raise ValueError("GNN model bundle has overlapping train and validation seeds")
    overlap = (train_seeds | validation_seeds) & {
        int(value) for value in evaluation_seeds
    }
    if overlap:
        raise ValueError(
            "GNN model seed overlaps evaluation replay: "
            + ", ".join(str(value) for value in sorted(overlap))
        )
    model = SparseEdgeGNN(hidden_dim=int(manifest["hidden_dim"]))
    state = torch.load(model_dir / str(manifest["weights_file"]), map_location=device, weights_only=True)
    model.load_state_dict(state)
    normalizer = GraphNormalizer.from_dict(
        json.loads((model_dir / str(manifest["normalizer_file"])).read_text(encoding="utf-8"))
    )
    return GNNCandidateScorer(model, normalizer, device=device)


__all__ = [
    "GNNCandidateScorer",
    "GraphNormalizer",
    "SparseCandidateGraph",
    "SparseEdgeGNN",
    "graph_from_candidates",
    "load_model_bundle",
    "save_model_bundle",
]
