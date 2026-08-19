"""Disjoint-seed training and validation for the optional sparse GNN."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from torch import nn

from .association import build_pair_candidates
from .config import CrossViewConfig
from .contracts import track_key
from .fixture import build_fixture
from .gnn import (
    GNNCandidateScorer,
    GraphNormalizer,
    SparseCandidateGraph,
    SparseEdgeGNN,
    _graph_tensors,
    graph_from_candidates,
    save_model_bundle,
)
from .replay_io import (
    load_replay_manifest,
    load_saved_replay_online,
    load_saved_replay_truth,
)


AIRSIM_TEST_SEED = 20260816


@dataclass(frozen=True)
class TrainingConfig:
    train_seeds: tuple[int, ...] = tuple(range(20261000, 20261060))
    validation_seeds: tuple[int, ...] = tuple(range(20262000, 20262020))
    epochs: int = 20
    learning_rate: float = 1.0e-3
    hidden_dim: int = 48
    target_counts: tuple[int, ...] = (20, 40)
    # Kept for callers of the first experimental API. New code uses target_counts.
    target_count: int | None = None
    device: str = "cpu"
    model_seed: int = 20263001
    training_replay_manifests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.train_seeds or not self.validation_seeds:
            raise ValueError("train and validation seed sets must be non-empty")
        if set(self.train_seeds) & set(self.validation_seeds):
            raise ValueError("train and validation seeds must be disjoint")
        if AIRSIM_TEST_SEED in set(self.train_seeds) | set(self.validation_seeds):
            raise ValueError("AirSim test seed 20260816 cannot enter GNN training")
        if self.model_seed == AIRSIM_TEST_SEED:
            raise ValueError("AirSim test seed 20260816 cannot initialize GNN training")
        if self.epochs <= 0 or self.learning_rate <= 0.0:
            raise ValueError("training schedule must be positive")
        if self.hidden_dim <= 0:
            raise ValueError("hidden_dim must be positive")
        if not self.effective_target_counts or any(
            value <= 0 for value in self.effective_target_counts
        ):
            raise ValueError("target counts must be positive")

    @property
    def effective_target_counts(self) -> tuple[int, ...]:
        values = (self.target_count,) if self.target_count is not None else self.target_counts
        return tuple(dict.fromkeys(int(value) for value in values))


@dataclass(frozen=True)
class _LabeledGraph:
    graph: SparseCandidateGraph
    labels: np.ndarray
    target_count: int
    dataset_id: str


def _graphs_for_records(
    records,
    calibrations,
    truth,
    *,
    target_count: int,
    dataset_id: str,
) -> tuple[_LabeledGraph, ...]:
    histories: dict[str, dict[str, list[object]]] = {}
    for record in records:
        histories.setdefault(record.camera_id, {}).setdefault(record.local_track_id, []).append(record)
    config = CrossViewConfig()
    examples: list[_LabeledGraph] = []
    for camera_a, camera_b in combinations(sorted(histories), 2):
        candidates = build_pair_candidates(
            histories[camera_a],  # type: ignore[arg-type]
            histories[camera_b],  # type: ignore[arg-type]
            calibrations[camera_a],
            calibrations[camera_b],
            config,
        )
        passed = tuple(item for item in candidates if item.gate_passed)
        if not passed:
            continue
        graph = graph_from_candidates(
            histories[camera_a],  # type: ignore[arg-type]
            histories[camera_b],  # type: ignore[arg-type]
            passed,
            calibrations[camera_a],
            calibrations[camera_b],
        )
        labels = np.asarray(
            [
                float(
                    truth.track_to_target[track_key(item.camera_a_id, item.track_a_id)]
                    == truth.track_to_target[track_key(item.camera_b_id, item.track_b_id)]
                )
                for item in passed
            ],
            dtype=np.float32,
        )
        examples.append(_LabeledGraph(graph, labels, target_count, dataset_id))
    return tuple(examples)


def _graphs_for_seed(seed: int, target_count: int) -> tuple[_LabeledGraph, ...]:
    bundle = build_fixture(
        "dense_multicamera", seed=seed, target_count=target_count, frame_count=5
    )
    return _graphs_for_records(
        bundle.records,
        bundle.calibrations,
        bundle.truth,
        target_count=target_count,
        dataset_id=f"synthetic:{target_count}:{seed}",
    )


def _graphs_for_training_replay(path: str) -> tuple[int, tuple[_LabeledGraph, ...]]:
    manifest = load_replay_manifest(Path(path))
    if manifest.test_only or manifest.campaign_seed == AIRSIM_TEST_SEED:
        raise ValueError(
            "test-only replay or AirSim seed 20260816 cannot enter GNN training"
        )
    online = load_saved_replay_online(manifest)
    truth = load_saved_replay_truth(manifest)
    return manifest.campaign_seed, _graphs_for_records(
        online.records,
        online.calibrations,
        truth,
        target_count=manifest.target_count,
        dataset_id=f"replay:{manifest.scenario_id}:{manifest.campaign_seed}",
    )


def _evaluate(
    model: SparseEdgeGNN,
    normalizer: GraphNormalizer,
    examples: Sequence[_LabeledGraph],
    device: torch.device,
) -> dict[str, float]:
    model.eval()
    probabilities: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    with torch.no_grad():
        for example in examples:
            logits = model(*_graph_tensors(example.graph, normalizer, device))
            probabilities.append(torch.sigmoid(logits).cpu().numpy())
            labels.append(example.labels)
    predicted = np.concatenate(probabilities) >= 0.5
    expected = np.concatenate(labels) >= 0.5
    tp = int(np.sum(predicted & expected))
    fp = int(np.sum(predicted & ~expected))
    fn = int(np.sum(~predicted & expected))
    return {
        "edge_precision": tp / (tp + fp) if tp + fp else 1.0,
        "edge_recall": tp / (tp + fn) if tp + fn else 1.0,
        "edge_count": float(len(expected)),
    }


def train_and_save(
    output_dir: Path,
    *,
    config: TrainingConfig | None = None,
) -> Path:
    cfg = config or TrainingConfig()
    torch.manual_seed(cfg.model_seed)
    np.random.seed(cfg.model_seed)
    train_examples = tuple(
        example
        for seed in cfg.train_seeds
        for target_count in cfg.effective_target_counts
        for example in _graphs_for_seed(seed, target_count)
    )
    validation_examples = tuple(
        example
        for seed in cfg.validation_seeds
        for target_count in cfg.effective_target_counts
        for example in _graphs_for_seed(seed, target_count)
    )
    replay_train_seeds: list[int] = []
    replay_examples: list[_LabeledGraph] = []
    for manifest_path in cfg.training_replay_manifests:
        replay_seed, examples = _graphs_for_training_replay(manifest_path)
        if replay_seed in set(cfg.validation_seeds):
            raise ValueError("training replay seed overlaps validation seeds")
        replay_train_seeds.append(replay_seed)
        replay_examples.extend(examples)
    if len(set(replay_train_seeds)) != len(replay_train_seeds):
        raise ValueError("training replay seeds must be unique")
    if set(replay_train_seeds) & set(cfg.train_seeds):
        raise ValueError("training replay seed duplicates a synthetic training seed")
    train_examples = tuple((*train_examples, *replay_examples))
    if not train_examples or not validation_examples:
        raise ValueError("training fixtures produced no geometry-gated graph")
    normalizer = GraphNormalizer.fit(tuple(item.graph for item in train_examples))
    device = torch.device(cfg.device)
    model = SparseEdgeGNN(hidden_dim=cfg.hidden_dim).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)
    all_labels = np.concatenate([item.labels for item in train_examples])
    positives = max(1, int(np.sum(all_labels >= 0.5)))
    negatives = max(1, int(np.sum(all_labels < 0.5)))
    loss_function = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([negatives / positives], dtype=torch.float32, device=device)
    )
    for _ in range(cfg.epochs):
        model.train()
        for example in train_examples:
            optimizer.zero_grad(set_to_none=True)
            logits = model(*_graph_tensors(example.graph, normalizer, device))
            labels = torch.as_tensor(example.labels, dtype=torch.float32, device=device)
            loss = loss_function(logits, labels)
            loss.backward()
            optimizer.step()
    validation = _evaluate(model, normalizer, validation_examples, device)
    validation_by_target_count = {
        str(target_count): _evaluate(
            model,
            normalizer,
            tuple(
                example
                for example in validation_examples
                if example.target_count == target_count
            ),
            device,
        )
        for target_count in cfg.effective_target_counts
    }
    all_train_seeds = tuple((*cfg.train_seeds, *replay_train_seeds))
    manifest = {
        "train_seeds": all_train_seeds,
        "validation_seeds": cfg.validation_seeds,
        "seed_overlap_count": 0,
        "train_example_count": len(train_examples),
        "validation_example_count": len(validation_examples),
        "training_config": asdict(cfg),
        "validation_metrics": validation,
        "validation_metrics_by_target_count": validation_by_target_count,
        "target_counts": cfg.effective_target_counts,
        "train_dataset_ids": sorted({item.dataset_id for item in train_examples}),
        "validation_dataset_ids": sorted(
            {item.dataset_id for item in validation_examples}
        ),
        "online_feature_policy": "time_ray_geometry_motion_bbox_camera_confidence_only",
    }
    return save_model_bundle(output_dir, model.cpu(), normalizer, manifest)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train and freeze the optional cross-view sparse edge GNN"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--train-seeds", type=int, nargs="+", default=list(range(20261000, 20261060))
    )
    parser.add_argument(
        "--validation-seeds",
        type=int,
        nargs="+",
        default=list(range(20262000, 20262020)),
    )
    parser.add_argument("--target-counts", type=int, nargs="+", default=[20, 40])
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=1.0e-3)
    parser.add_argument("--hidden-dim", type=int, default=48)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--model-seed", type=int, default=20263001)
    parser.add_argument(
        "--training-replay-manifest",
        type=Path,
        action="append",
        default=[],
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    train_and_save(
        args.output_dir,
        config=TrainingConfig(
            train_seeds=tuple(args.train_seeds),
            validation_seeds=tuple(args.validation_seeds),
            target_counts=tuple(args.target_counts),
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            hidden_dim=args.hidden_dim,
            device=args.device,
            model_seed=args.model_seed,
            training_replay_manifests=tuple(
                str(path) for path in args.training_replay_manifest
            ),
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["AIRSIM_TEST_SEED", "TrainingConfig", "main", "train_and_save"]
