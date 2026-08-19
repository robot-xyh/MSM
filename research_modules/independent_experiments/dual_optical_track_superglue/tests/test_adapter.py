from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from research_modules.independent_experiments.dual_optical_track_superglue.adapter import (
    adapt_frozen_graph,
    adapt_shared_feature_graph,
    adapt_snapshot,
)
from research_modules.independent_experiments.dual_optical_100target_gnn.graph import (
    EDGE_FEATURE_NAMES as GNN_EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES as GNN_NODE_FEATURE_NAMES,
    GeometryGate,
)
from research_modules.independent_experiments.dual_optical_100target_gnn.online import (
    anonymous_graph_from_snapshot,
)
from research_modules.independent_experiments.dual_optical_track_superglue.schema import (
    EDGE_FEATURE_NAMES,
    TRACK_FEATURE_NAMES,
)


class TruthPoisonTrack:
    def __init__(self, source) -> None:
        self.track_id = source.track_id
        self.camera_id = source.camera_id
        self.samples = source.samples
        self.track_state = source.track_state
        self.recent_sweep_hits = source.recent_sweep_hits

    @property
    def actor_id(self):
        raise AssertionError("online adapter attempted to read AirSim actor identity")

    @property
    def truth_id(self):
        raise AssertionError("online adapter attempted to read offline truth identity")


def test_snapshot_adapter_uses_anonymous_fields_only(snapshot_factory) -> None:
    source = snapshot_factory()
    tracks = {
        camera: tuple(TruthPoisonTrack(track) for track in source.tracks[camera])
        for camera in source.camera_ids
    }
    snapshot = SimpleNamespace(
        seed=source.seed,
        split=source.split,
        corruption_level=source.corruption_level,
        revolution_index=source.revolution_index,
        cutoff_timestamp=source.cutoff_timestamp,
        camera_ids=source.camera_ids,
        camera_positions_ned=source.camera_positions_ned,
        focal_length_px=source.focal_length_px,
        tracks=tracks,
        tracker_fingerprint=source.tracker_fingerprint,
        geometry_candidate_pairs=source.geometry_candidate_pairs,
        candidate_graph_fingerprint=source.candidate_graph_fingerprint,
    )
    graph = adapt_snapshot(snapshot)
    assert graph.observation_history_a.shape == (2, 6, 10)
    assert graph.track_features_a.shape == (2, 15)
    assert graph.edge_features.shape == (2, 2, 18)
    assert int(np.sum(graph.candidate_mask)) == 3
    assert np.all(graph.edge_features[~graph.candidate_mask] == 0.0)


def test_frozen_graph_adapter_preserves_existing_15_18_features(snapshot_factory) -> None:
    snapshot = snapshot_factory()
    node_a = np.arange(30, dtype=np.float32).reshape(2, 15)
    node_b = np.arange(30, 60, dtype=np.float32).reshape(2, 15)
    edge_features = np.arange(54, dtype=np.float32).reshape(3, 18)
    frozen = SimpleNamespace(
        track_ids_a=("A-track-0", "A-track-1"),
        track_ids_b=("B-track-0", "B-track-1"),
        node_features_a=node_a,
        node_features_b=node_b,
        edge_index=np.asarray([[0, 0, 1], [0, 1, 1]], dtype=np.int64),
        edge_features=edge_features,
    )
    graph = adapt_frozen_graph(frozen, snapshot)
    assert np.array_equal(graph.track_features_a, node_a)
    assert np.array_equal(graph.track_features_b, node_b)
    assert np.array_equal(graph.edge_features[graph.candidate_mask], edge_features)


def test_formal_adapter_is_exactly_equivalent_to_baseline_gnn_features(
    snapshot_factory,
) -> None:
    snapshot = snapshot_factory()
    baseline, _ = anonymous_graph_from_snapshot(snapshot, GeometryGate())
    adapted = adapt_shared_feature_graph(snapshot)

    assert TRACK_FEATURE_NAMES == GNN_NODE_FEATURE_NAMES
    assert EDGE_FEATURE_NAMES == GNN_EDGE_FEATURE_NAMES
    assert adapted.track_ids_a == baseline.track_ids_a
    assert adapted.track_ids_b == baseline.track_ids_b
    assert np.array_equal(adapted.track_features_a, baseline.node_features_a)
    assert np.array_equal(adapted.track_features_b, baseline.node_features_b)

    expected_mask = np.zeros_like(adapted.candidate_mask)
    expected_edges = np.zeros_like(adapted.edge_features)
    for edge, (row, column) in enumerate(baseline.edge_index.T):
        expected_mask[int(row), int(column)] = True
        expected_edges[int(row), int(column)] = baseline.edge_features[edge]
    assert np.array_equal(adapted.candidate_mask, expected_mask)
    assert np.array_equal(adapted.edge_features, expected_edges)
