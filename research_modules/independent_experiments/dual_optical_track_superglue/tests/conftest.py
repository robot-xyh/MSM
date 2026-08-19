from __future__ import annotations

import math
from pathlib import Path
import sys

import numpy as np
import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
for path in (REPOSITORY_ROOT, PACKAGE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from research_modules.independent_experiments.dual_optical_online_benchmark.contracts import (
    BenchmarkProtocol,
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    candidate_graph_fingerprint,
)

from research_modules.independent_experiments.dual_optical_track_superglue.schema import (
    AssociationLabels,
    TrackGraphInput,
    TrainingExample,
)


def _direction(x: float, y: float, z: float) -> tuple[float, float, float]:
    norm = math.sqrt(x * x + y * y + z * z)
    return x / norm, y / norm, z / norm


def make_snapshot(
    revolution_index: int = 3,
    *,
    split: str = "validation",
    seed: int = 1234,
) -> RevolutionSnapshot:
    sample_count = min(6, revolution_index * 2)

    def track(camera_id: str, index: int) -> SnapshotTrack:
        samples = []
        for sample_index in range(sample_count):
            timestamp = 0.5 + sample_index * max(
                (2.0 * revolution_index - 1.0) / max(sample_count - 1, 1), 0.1
            )
            y = 0.025 * index + 0.002 * sample_index
            if camera_id == "B":
                y -= 0.015
            samples.append(
                SnapshotTrackSample(
                    sweep_index=min(int(timestamp // 2.0), revolution_index - 1),
                    timestamp=min(timestamp, 2.0 * revolution_index),
                    direction_ned=_direction(1.0, y, -0.01 * index),
                    detection_count=1,
                    bbox_area_px2=4.0 + index,
                    confidence=0.9,
                    state_vector=(0.0, 0.0, 0.05, 0.01),
                )
            )
        return SnapshotTrack(
            track_id=f"{camera_id}-track-{index}",
            camera_id=camera_id,
            samples=tuple(samples),
            track_state="confirmed",
            recent_sweep_hits=(True, True, True),
        )

    tracks = {camera: tuple(track(camera, index) for index in range(2)) for camera in ("A", "B")}
    pairs = (
        ("A-track-0", "B-track-0"),
        ("A-track-0", "B-track-1"),
        ("A-track-1", "B-track-1"),
    )
    summary = {"policy": "unit-test-frozen-whitelist"}
    return RevolutionSnapshot(
        protocol_fingerprint=BenchmarkProtocol().fingerprint,
        seed=seed,
        split=split,
        corruption_level="light",
        revolution_index=revolution_index,
        cutoff_timestamp=2.0 * revolution_index,
        camera_ids=("A", "B"),
        camera_positions_ned={"A": (0.0, 0.0, 0.0), "B": (0.0, 2000.0, 0.0)},
        focal_length_px=5000.0,
        tracks=tracks,
        target_count=2,
        tracker_fingerprint="unit-test-tracker-v2",
        geometry_candidate_pairs=pairs,
        candidate_graph_fingerprint=candidate_graph_fingerprint(pairs, summary),
        candidate_graph_summary=summary,
    )


def make_graph(
    *,
    split: str = "train",
    revolution_index: int = 3,
    seed: int = 1234,
) -> TrackGraphInput:
    generator = np.random.default_rng(seed + revolution_index)
    candidate_mask = np.asarray([[True, True], [False, True]], dtype=bool)
    edge_features = np.zeros((2, 2, 18), dtype=np.float32)
    edge_features[candidate_mask] = generator.normal(size=(3, 18)).astype(np.float32)
    graph = TrackGraphInput(
        seed=seed,
        split=split,
        corruption_level="light",
        revolution_index=revolution_index,
        cutoff_timestamp=2.0 * revolution_index,
        track_ids_a=("A0", "A1"),
        track_ids_b=("B0", "B1"),
        observation_history_a=generator.normal(size=(2, 6, 10)).astype(np.float32),
        observation_history_b=generator.normal(size=(2, 6, 10)).astype(np.float32),
        history_lengths_a=np.asarray([6, 4], dtype=np.int64),
        history_lengths_b=np.asarray([5, 3], dtype=np.int64),
        track_features_a=generator.normal(size=(2, 15)).astype(np.float32),
        track_features_b=generator.normal(size=(2, 15)).astype(np.float32),
        candidate_mask=candidate_mask,
        edge_features=edge_features,
    )
    graph.validate()
    return graph


@pytest.fixture
def graph_factory():
    return make_graph


@pytest.fixture
def snapshot_factory():
    return make_snapshot


@pytest.fixture
def training_example(graph_factory) -> TrainingExample:
    return TrainingExample(graph_factory(split="train"), AssociationLabels(((0, 0), (1, 1))))
