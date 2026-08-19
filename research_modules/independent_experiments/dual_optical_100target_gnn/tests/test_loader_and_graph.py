from __future__ import annotations

import numpy as np

from dual_optical_100target_gnn.corruption import corrupt_episode
from dual_optical_100target_gnn.graph import build_graph
from dual_optical_100target_gnn.loader import load_offline_labels, load_online_episode
from dual_optical_100target_gnn.schema import (
    CORRUPTION_LEVELS,
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
)


def test_loader_supports_v2_and_v3_without_online_identity(episode_factory):
    for version in (2, 3):
        root = episode_factory(100 + version, version=version)
        episode = load_online_episode(root)
        assert episode.schema_version.endswith(f"v{version}")
        assert sum(len(items) for items in episode.tracks.values()) == 8
        assert "truth" not in repr(episode).lower()
        labels = load_offline_labels(root, episode)
        assert len(labels.expected_identities) == 4


def test_corruption_is_reproducible_and_persistent_tracks_span_four_sweeps(episode_factory):
    root = episode_factory(123)
    episode = load_online_episode(root)
    labels = load_offline_labels(root, episode)
    first, first_labels, summary_a = corrupt_episode(episode, labels, CORRUPTION_LEVELS["heavy"])
    second, second_labels, summary_b = corrupt_episode(episode, labels, CORRUPTION_LEVELS["heavy"])
    assert first == second
    assert first_labels == second_labels
    assert summary_a == summary_b
    persistent = [
        track
        for camera in first.camera_ids
        for track in first.tracks[camera]
        if track.source_kind == "persistent_false_alarm"
    ]
    assert len(persistent) == 4
    assert all(track.sweep_count >= 4 for track in persistent)
    assert summary_a.transient_false_track_count == 8 * 4 * 2


def test_graph_uses_anonymous_features_and_preserves_positive_candidates(episode_factory):
    root = episode_factory(124)
    episode = load_online_episode(root)
    labels = load_offline_labels(root, episode)
    corrupted, corrupted_labels, summary = corrupt_episode(
        episode, labels, CORRUPTION_LEVELS["light"]
    )
    graph, graph_labels, diagnostics = build_graph(corrupted, corrupted_labels, summary)
    assert graph.node_features_a.shape[1] == len(NODE_FEATURE_NAMES)
    assert graph.edge_features.shape[1] == len(EDGE_FEATURE_NAMES)
    assert diagnostics["full_pair_count"] == 16
    assert np.sum(graph_labels.edge_labels) == 4
    assert not any("ID-" in value for value in graph.track_ids_a + graph.track_ids_b)
    graph.validate()
    graph_labels.validate(graph)


def test_graph_scale_is_driven_by_input_track_count(episode_factory):
    root = episode_factory(125, target_count=100)
    episode = load_online_episode(root)
    labels = load_offline_labels(root, episode)
    corrupted, corrupted_labels, summary = corrupt_episode(
        episode, labels, CORRUPTION_LEVELS["heavy"]
    )
    graph, graph_labels, diagnostics = build_graph(
        corrupted, corrupted_labels, summary
    )
    assert 90 <= len(graph.track_ids_a) <= 102
    assert 90 <= len(graph.track_ids_b) <= 102
    assert diagnostics["full_pair_count"] == len(graph.track_ids_a) * len(
        graph.track_ids_b
    )
    assert int(np.sum(graph_labels.edge_labels)) >= 90
