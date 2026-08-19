"""Pure-PyTorch sparse bipartite candidate scorer used after geometry gating."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import random
from typing import Iterable, Mapping, Sequence

import numpy as np
import torch
from torch import nn

from ..common import LocalVisualTrackRecord, SourceCueRecord
from .association import AssociationConfig, CandidateEvaluation, CenterHandoverAssociator
from .fixture import HandoverFixture, build_offline_fixture


MODEL_SCHEMA = "center-handover-sparse-gnn-v2"
MODEL_MANIFEST_SCHEMA = "center-handover-sparse-gnn-artifact-v1"
FEATURE_STRATEGY = {
    "schema_version": "center-handover-gnn-features-v2",
    "source_features": [
        "existence_probability",
        "position_covariance_trace_scaled",
        "source_validity_duration_scaled",
    ],
    "local_features": [
        "track_quality",
        "recognition_extent_scaled",
        "pixel_u_scaled",
        "pixel_v_scaled",
    ],
    "edge_features": [
        "mahalanobis_distance_scaled",
        "pixel_residual_norm_scaled",
        "multi_frame_motion_residual_scaled",
        "prediction_age_scaled",
        "geometry_cost_scaled",
        "multi_frame_motion_available",
        "geometry_gate_passed",
    ],
    "online_identity_features": [],
    "truth_features": [],
}
FORBIDDEN_AIRSIM_SEED = 20260816


@dataclass(frozen=True)
class TrainingConfig:
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    target_counts: tuple[int, ...] = (20, 40)
    frame_timestamps: tuple[float, ...] = (0.2, 0.3, 0.4)
    epochs: int = 30
    learning_rate: float = 2.0e-3
    random_seed: int = 20260701
    source_position_sigma_m: float = 12.0
    device: str = "cpu"

    def __post_init__(self) -> None:
        ensure_seed_isolation(self.train_seeds, self.validation_seeds)
        ensure_no_forbidden_training_seed(self.train_seeds, self.validation_seeds)
        if not self.train_seeds or not self.validation_seeds:
            raise ValueError("training and validation seed sets must be non-empty")
        if set(self.target_counts) != {20, 40}:
            raise ValueError("center GNN synthetic training must cover 20 and 40 targets")
        if (
            len(self.frame_timestamps) < 3
            or tuple(sorted(self.frame_timestamps)) != self.frame_timestamps
        ):
            raise ValueError("training requires at least three ordered frame timestamps")
        if len(set(self.frame_timestamps)) != len(self.frame_timestamps):
            raise ValueError("training frame timestamps must be unique")
        if self.epochs <= 0 or self.learning_rate <= 0.0:
            raise ValueError("epochs and learning_rate must be positive")
        if self.source_position_sigma_m <= 0.0:
            raise ValueError("source_position_sigma_m must be positive")
        if self.device != "cpu":
            raise ValueError("center GNN training is fixed to CPU")


@dataclass(frozen=True)
class SparseCandidateGraph:
    source_features: torch.Tensor
    local_features: torch.Tensor
    edge_features: torch.Tensor
    edge_index: torch.Tensor
    candidate_ids: tuple[str, ...]

    def to(self, device: torch.device | str) -> "SparseCandidateGraph":
        return SparseCandidateGraph(
            source_features=self.source_features.to(device),
            local_features=self.local_features.to(device),
            edge_features=self.edge_features.to(device),
            edge_index=self.edge_index.to(device),
            candidate_ids=self.candidate_ids,
        )


class SparseBipartiteGNN(nn.Module):
    """One message-passing layer over geometry-approved source/local edges."""

    def __init__(
        self,
        source_dim: int = 3,
        local_dim: int = 4,
        edge_dim: int = 7,
        hidden_dim: int = 32,
    ) -> None:
        super().__init__()
        self.source_dim = source_dim
        self.local_dim = local_dim
        self.edge_dim = edge_dim
        self.hidden_dim = hidden_dim
        self.source_encoder = nn.Sequential(nn.Linear(source_dim, hidden_dim), nn.ReLU())
        self.local_encoder = nn.Sequential(nn.Linear(local_dim, hidden_dim), nn.ReLU())
        self.edge_encoder = nn.Sequential(nn.Linear(edge_dim, hidden_dim), nn.ReLU())
        self.edge_head = nn.Sequential(
            nn.Linear(hidden_dim * 4, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, graph: SparseCandidateGraph) -> torch.Tensor:
        if graph.edge_features.shape[0] == 0:
            return torch.empty(
                (0,), dtype=graph.edge_features.dtype, device=graph.edge_features.device
            )
        source_hidden = self.source_encoder(graph.source_features)
        local_hidden = self.local_encoder(graph.local_features)
        edge_hidden = self.edge_encoder(graph.edge_features)
        source_indices = graph.edge_index[0]
        local_indices = graph.edge_index[1]

        source_messages = torch.zeros_like(source_hidden)
        local_messages = torch.zeros_like(local_hidden)
        source_messages.index_add_(0, source_indices, edge_hidden)
        local_messages.index_add_(0, local_indices, edge_hidden)
        source_degree = torch.zeros((source_hidden.shape[0], 1), device=edge_hidden.device)
        local_degree = torch.zeros((local_hidden.shape[0], 1), device=edge_hidden.device)
        source_degree.index_add_(
            0, source_indices, torch.ones((len(source_indices), 1), device=edge_hidden.device)
        )
        local_degree.index_add_(
            0, local_indices, torch.ones((len(local_indices), 1), device=edge_hidden.device)
        )
        source_messages = source_messages / source_degree.clamp_min(1.0)
        local_messages = local_messages / local_degree.clamp_min(1.0)
        joined = torch.cat(
            (
                edge_hidden,
                source_hidden[source_indices],
                local_hidden[local_indices],
                source_messages[source_indices] + local_messages[local_indices],
            ),
            dim=1,
        )
        return self.edge_head(joined).squeeze(1)


class SparseGNNScorer:
    def __init__(self, model: SparseBipartiteGNN, *, device: str = "cpu") -> None:
        if device != "cpu":
            raise ValueError("frozen center-handover GNN inference is fixed to CPU")
        self.device = torch.device(device)
        self.model = model.to(self.device).eval()

    def __call__(
        self,
        candidates: Sequence[CandidateEvaluation],
        sources: Sequence[SourceCueRecord],
        locals_: Sequence[LocalVisualTrackRecord],
    ) -> Mapping[str, float]:
        graph = build_candidate_graph(candidates, sources, locals_).to(self.device)
        with torch.no_grad():
            probabilities = torch.sigmoid(self.model(graph)).cpu().numpy()
        return {
            candidate_id: float(probability)
            for candidate_id, probability in zip(
                graph.candidate_ids, probabilities, strict=True
            )
        }


def build_candidate_graph(
    candidates: Sequence[CandidateEvaluation],
    sources: Sequence[SourceCueRecord],
    locals_: Sequence[LocalVisualTrackRecord],
) -> SparseCandidateGraph:
    eligible = [candidate for candidate in candidates if candidate.eligible]
    source_features = torch.tensor(
        [
            (
                float(source.existence_probability),
                min(
                    max(
                        float(np.trace(np.asarray(source.covariance_6x6)[:3, :3]))
                        / 1000.0,
                        0.0,
                    ),
                    10.0,
                ),
                min(
                    max(
                        float(source.valid_until - source.measurement_timestamp) / 5.0,
                        0.0,
                    ),
                    2.0,
                ),
            )
            for source in sources
        ],
        dtype=torch.float32,
    )
    local_features = torch.tensor(
        [
            (
                float(local.track_quality),
                min(float(local.recognition_extent_px) / 100.0, 2.0),
                float(local.center_px[0]) / 2000.0,
                float(local.center_px[1]) / 1200.0,
            )
            for local in locals_
        ],
        dtype=torch.float32,
    )
    if eligible:
        edge_features = torch.tensor(
            [_edge_features(item) for item in eligible], dtype=torch.float32
        )
        edge_index = torch.tensor(
            ([item.source_index for item in eligible], [item.local_index for item in eligible]),
            dtype=torch.long,
        )
    else:
        edge_features = torch.empty((0, 7), dtype=torch.float32)
        edge_index = torch.empty((2, 0), dtype=torch.long)
    return SparseCandidateGraph(
        source_features=source_features,
        local_features=local_features,
        edge_features=edge_features,
        edge_index=edge_index,
        candidate_ids=tuple(item.candidate_id for item in eligible),
    )


def train_sparse_gnn(
    config: TrainingConfig,
) -> tuple[SparseBipartiteGNN, dict[str, float]]:
    random.seed(config.random_seed)
    np.random.seed(config.random_seed)
    torch.manual_seed(config.random_seed)
    train_samples = build_training_samples(
        config.train_seeds,
        target_counts=config.target_counts,
        frame_timestamps=config.frame_timestamps,
        source_position_sigma_m=config.source_position_sigma_m,
    )
    validation_samples = build_training_samples(
        config.validation_seeds,
        target_counts=config.target_counts,
        frame_timestamps=config.frame_timestamps,
        source_position_sigma_m=config.source_position_sigma_m,
    )
    model = SparseBipartiteGNN().cpu()
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    model.train()
    for _ in range(config.epochs):
        order = torch.randperm(len(train_samples)).tolist()
        for index in order:
            graph, labels = train_samples[index]
            logits = model(graph)
            if logits.numel() == 0:
                continue
            positive = float(labels.sum().item())
            negative = float(labels.numel() - positive)
            weight = torch.tensor(max(negative / max(positive, 1.0), 1.0))
            loss = nn.functional.binary_cross_entropy_with_logits(
                logits, labels, pos_weight=weight
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    metrics = evaluate_model(model, validation_samples)
    metrics["train_sample_count"] = float(len(train_samples))
    metrics["validation_motion_edge_fraction"] = _motion_edge_fraction(
        validation_samples
    )
    return model.eval(), metrics


def build_training_samples(
    seeds: Iterable[int],
    *,
    target_counts: Sequence[int] = (20, 40),
    frame_timestamps: Sequence[float] = (0.2, 0.3, 0.4),
    source_position_sigma_m: float = 12.0,
) -> list[tuple[SparseCandidateGraph, torch.Tensor]]:
    seed_values = tuple(int(value) for value in seeds)
    ensure_no_forbidden_training_seed(seed_values, ())
    samples: list[tuple[SparseCandidateGraph, torch.Tensor]] = []
    training_config = AssociationConfig(mahalanobis_gate_d2=25.0, dummy_cost=30.0)
    for seed in seed_values:
        for target_count in target_counts:
            fixture = build_offline_fixture(
                target_count=int(target_count),
                seed=seed,
                source_position_sigma_m=source_position_sigma_m,
                frame_timestamps=frame_timestamps,
            )
            associator = CenterHandoverAssociator(
                fixture.camera_models, config=training_config
            )
            for frame in fixture.frames:
                result = associator.process_frame(fixture.source_cues, frame)
                graph = build_candidate_graph(result.candidates, fixture.source_cues, frame)
                labels = _edge_truth_labels(graph, result.candidates, fixture)
                if labels.numel() and labels.sum() > 0 and labels.sum() < labels.numel():
                    samples.append((graph, labels))
    if not samples:
        raise RuntimeError("training fixture produced no mixed positive/negative sparse graphs")
    return samples


def _edge_truth_labels(
    graph: SparseCandidateGraph,
    candidates: Sequence[CandidateEvaluation],
    fixture: HandoverFixture,
) -> torch.Tensor:
    source_truth = {label.source_track_id: label for label in fixture.source_truth}
    local_truth = {label.local_track_id: label.truth_target_id for label in fixture.local_truth}
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    labels: list[float] = []
    for candidate_id in graph.candidate_ids:
        candidate = by_id[candidate_id]
        source_label = source_truth[candidate.source_track_id]
        labels.append(
            1.0
            if source_label.is_correct_source
            and source_label.truth_target_id == local_truth[candidate.local_track_id]
            else 0.0
        )
    return torch.tensor(labels, dtype=torch.float32)


def evaluate_model(
    model: SparseBipartiteGNN,
    samples: Sequence[tuple[SparseCandidateGraph, torch.Tensor]],
) -> dict[str, float]:
    model.eval()
    true_positive = false_positive = false_negative = true_negative = 0
    with torch.no_grad():
        for graph, labels in samples:
            predictions = torch.sigmoid(model(graph)) >= 0.5
            truth = labels >= 0.5
            true_positive += int(torch.sum(predictions & truth))
            false_positive += int(torch.sum(predictions & ~truth))
            false_negative += int(torch.sum(~predictions & truth))
            true_negative += int(torch.sum(~predictions & ~truth))
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    return {
        "edge_precision": precision,
        "edge_recall": recall,
        "edge_accuracy": (true_positive + true_negative)
        / max(true_positive + false_positive + false_negative + true_negative, 1),
        "sample_count": float(len(samples)),
    }


def save_model(
    path: Path,
    model: SparseBipartiteGNN,
    *,
    config: TrainingConfig,
    validation_metrics: Mapping[str, float],
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = _json_normalize(
        {
            "model_dimensions": {
                "source_dim": model.source_dim,
                "local_dim": model.local_dim,
                "edge_dim": model.edge_dim,
                "hidden_dim": model.hidden_dim,
            },
            "feature_strategy": FEATURE_STRATEGY,
            "training_config": asdict(config),
            "train_seeds": list(config.train_seeds),
            "validation_seeds": list(config.validation_seeds),
            "validation_metrics": dict(validation_metrics),
        }
    )
    _validate_model_metadata(metadata)
    metadata_digest = _metadata_sha256(metadata)
    torch.save(
        {
            "schema_version": MODEL_SCHEMA,
            "metadata_sha256": metadata_digest,
            "metadata": metadata,
            "state_dict": model.cpu().state_dict(),
        },
        path,
    )
    model_digest = _sha256_file(path)
    manifest = {
        "schema_version": MODEL_MANIFEST_SCHEMA,
        "model_schema_version": MODEL_SCHEMA,
        "model_file": path.name,
        "model_sha256": model_digest,
        "metadata_sha256": metadata_digest,
        "metadata": metadata,
    }
    model_manifest_path(path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_model(path: Path) -> tuple[SparseBipartiteGNN, dict[str, object]]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"GNN model does not exist: {path}")
    sidecar = model_manifest_path(path)
    if not sidecar.is_file():
        raise FileNotFoundError(f"GNN model manifest does not exist: {sidecar}")
    manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MODEL_MANIFEST_SCHEMA:
        raise ValueError("unsupported sparse GNN artifact manifest schema")
    if manifest.get("model_schema_version") != MODEL_SCHEMA:
        raise ValueError("unsupported sparse GNN model schema")
    if manifest.get("model_file") != path.name:
        raise ValueError("GNN model manifest references a different model file")
    if manifest.get("model_sha256") != _sha256_file(path):
        raise ValueError("GNN model SHA256 mismatch")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("GNN model metadata is missing")
    _validate_model_metadata(metadata)
    metadata_digest = _metadata_sha256(metadata)
    if manifest.get("metadata_sha256") != metadata_digest:
        raise ValueError("GNN model metadata SHA256 mismatch")

    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload.get("schema_version") != MODEL_SCHEMA:
        raise ValueError("unsupported sparse GNN model schema")
    if payload.get("metadata_sha256") != metadata_digest or payload.get("metadata") != metadata:
        raise ValueError("GNN model payload metadata does not match its manifest")
    dimensions = metadata["model_dimensions"]
    model = SparseBipartiteGNN(**dimensions)
    model.load_state_dict(payload["state_dict"])
    return model.cpu().eval(), metadata


def model_manifest_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".manifest.json")


def ensure_seed_isolation(
    train_seeds: Sequence[int], validation_seeds: Sequence[int]
) -> None:
    overlap = set(int(value) for value in train_seeds) & set(
        int(value) for value in validation_seeds
    )
    if overlap:
        raise ValueError(f"training and validation seeds overlap: {sorted(overlap)}")


def ensure_no_forbidden_training_seed(
    train_seeds: Sequence[int], validation_seeds: Sequence[int]
) -> None:
    used = set(int(value) for value in train_seeds) | set(
        int(value) for value in validation_seeds
    )
    if FORBIDDEN_AIRSIM_SEED in used:
        raise ValueError("AirSim seed 20260816 is held out and cannot enter training or validation")


def _validate_model_metadata(metadata: Mapping[str, object]) -> None:
    if metadata.get("feature_strategy") != FEATURE_STRATEGY:
        raise ValueError("GNN feature strategy schema mismatch")
    dimensions = metadata.get("model_dimensions")
    expected_dimensions = {"source_dim": 3, "local_dim": 4, "edge_dim": 7, "hidden_dim": 32}
    if dimensions != expected_dimensions:
        raise ValueError("GNN model dimensions do not match the frozen feature strategy")
    train_seeds = metadata.get("train_seeds")
    validation_seeds = metadata.get("validation_seeds")
    if not isinstance(train_seeds, list) or not isinstance(validation_seeds, list):
        raise ValueError("GNN model seed metadata is missing")
    ensure_seed_isolation(train_seeds, validation_seeds)
    ensure_no_forbidden_training_seed(train_seeds, validation_seeds)
    training_config = metadata.get("training_config")
    if not isinstance(training_config, dict):
        raise ValueError("GNN training configuration is missing")
    if set(training_config.get("target_counts", ())) != {20, 40}:
        raise ValueError("GNN model was not trained at both 20-target and 40-target scales")
    if training_config.get("device") != "cpu":
        raise ValueError("GNN model was not trained with the frozen CPU policy")
    if len(training_config.get("frame_timestamps", ())) < 3:
        raise ValueError("GNN model lacks multi-frame training metadata")
    metrics = metadata.get("validation_metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("GNN validation metrics are missing")


def _motion_edge_fraction(
    samples: Sequence[tuple[SparseCandidateGraph, torch.Tensor]],
) -> float:
    edge_count = sum(int(graph.edge_features.shape[0]) for graph, _ in samples)
    motion_count = sum(
        int(torch.sum(graph.edge_features[:, 5] > 0.5).item())
        for graph, _ in samples
        if graph.edge_features.numel()
    )
    return motion_count / max(edge_count, 1)


def _metadata_sha256(metadata: Mapping[str, object]) -> str:
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_normalize(value: object) -> dict[str, object]:
    return json.loads(json.dumps(value, sort_keys=True))


def _edge_features(candidate: CandidateEvaluation) -> tuple[float, ...]:
    residual_norm = (
        0.0 if candidate.residual_px is None else float(np.linalg.norm(candidate.residual_px))
    )
    motion = 0.0 if candidate.motion_residual_px_s is None else candidate.motion_residual_px_s
    return (
        min(float(candidate.mahalanobis_d2 or 0.0) / 25.0, 4.0),
        min(residual_norm / 200.0, 4.0),
        min(float(motion) / 100.0, 4.0),
        min(max(candidate.prediction_age_s / 20.0, 0.0), 2.0),
        min(candidate.baseline_cost / 30.0, 4.0),
        1.0 if candidate.motion_residual_px_s is not None else 0.0,
        1.0,
    )
