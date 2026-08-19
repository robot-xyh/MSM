from __future__ import annotations

import numpy as np
import pytest
import torch

from dual_optical_100target_gnn.assignment import solve_assignment
from dual_optical_100target_gnn.corruption import corrupt_episode
from dual_optical_100target_gnn.graph import build_graph
from dual_optical_100target_gnn.loader import load_offline_labels, load_online_episode
from dual_optical_100target_gnn.metrics import evaluate_assignment
from dual_optical_100target_gnn.model import BipartiteEdgeGNN, FeatureNormalizer, graph_tensors
from dual_optical_100target_gnn.schema import (
    CORRUPTION_LEVELS,
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CorruptionSummary,
    OnlineGraph,
)


def _graph(root):
    episode = load_online_episode(root)
    labels = load_offline_labels(root, episode)
    corrupted, corrupted_labels, summary = corrupt_episode(
        episode, labels, CORRUPTION_LEVELS["medium"]
    )
    return build_graph(corrupted, corrupted_labels, summary)[:2]


def test_two_layer_gnn_outputs_one_logit_per_edge(episode_factory):
    graph, labels = _graph(episode_factory(201))
    normalizer = FeatureNormalizer.fit([graph])
    model = BipartiteEdgeGNN(
        len(NODE_FEATURE_NAMES),
        len(EDGE_FEATURE_NAMES),
        hidden_dim=64,
        dropout=0.1,
    )
    logits = model(*graph_tensors(graph, normalizer, torch.device("cpu")))
    assert logits.shape == labels.edge_labels.shape
    assert len(model.layers) == 2
    assert model.hidden_dim == 64
    assert model.dropout_rate == 0.1


def test_hungarian_assignment_is_one_to_one(episode_factory):
    graph, labels = _graph(episode_factory(202))
    probabilities = np.where(labels.edge_labels > 0.5, 0.99, 0.01).astype(np.float32)
    for mode in ("geometry", "learned", "hybrid"):
        result = solve_assignment(
            graph,
            probabilities if mode != "geometry" else None,
            mode,
        )
        assert result.duplicate_track_assignment_count == 0
        assert len({pair.index_a for pair in result.selected_pairs}) == len(result.selected_pairs)
        assert len({pair.index_b for pair in result.selected_pairs}) == len(result.selected_pairs)
        metrics = evaluate_assignment(graph, labels, result)
        assert 0.0 <= metrics.f1 <= 1.0


def test_edges_above_unmatched_threshold_cannot_displace_legal_global_match():
    graph = OnlineGraph(
        seed=1,
        corruption_level="light",
        camera_ids=("A", "B"),
        track_ids_a=("A-1", "A-2"),
        track_ids_b=("B-1", "B-2"),
        node_features_a=np.zeros((2, 8), dtype=np.float32),
        node_features_b=np.zeros((2, 8), dtype=np.float32),
        edge_index=np.asarray(((0, 0, 1), (0, 1, 0)), dtype=np.int64),
        edge_features=np.zeros((3, 12), dtype=np.float32),
        geometry_cost=np.asarray((0.1, 1.3, 0.2), dtype=np.float32),
        corruption_summary=CorruptionSummary("light", 1, 0, 0, 0, 0),
    )
    graph.validate()
    result = solve_assignment(graph, None, "geometry", unmatched_cost=1.2)
    assert [(pair.index_a, pair.index_b) for pair in result.selected_pairs] == [(0, 0)]
    assert result.unmatched_a == (1,)
    assert result.unmatched_b == (1,)


def test_learned_assignment_rejects_invalid_probabilities(episode_factory):
    graph, _ = _graph(episode_factory(203))
    invalid = np.full(graph.geometry_cost.shape, np.nan, dtype=np.float32)
    with pytest.raises(ValueError, match="finite"):
        solve_assignment(graph, invalid, "learned")
    invalid.fill(1.1)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        solve_assignment(graph, invalid, "learned")
