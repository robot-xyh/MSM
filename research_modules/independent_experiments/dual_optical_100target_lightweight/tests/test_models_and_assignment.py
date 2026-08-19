from __future__ import annotations

import json

import numpy as np

from dual_optical_100target_gnn.dataset import (
    load_dataset_manifest,
    load_entry,
    sample_entries,
)
from dual_optical_100target_gnn.schema import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CorruptionSummary,
    OnlineGraph,
)
from dual_optical_100target_lightweight.assignment import solve_probability_assignment
from dual_optical_100target_lightweight.models import (
    LOGISTIC_C_GRID,
    ORIGINAL_GEOMETRY_WEIGHTS,
    LightweightModel,
    fit_all_models,
    geometry_components,
)


def _training_data(dataset_manifest):
    manifest, root = load_dataset_manifest(dataset_manifest)
    data = []
    for entry in sample_entries(manifest, "train"):
        graph, labels = load_entry(root, entry, include_labels=True)
        assert labels is not None
        data.append((graph, labels))
    return manifest, data


def test_geometry_components_reproduce_shared_original_cost(dataset_manifest):
    manifest, data = _training_data(dataset_manifest)
    for graph, _ in data:
        components = geometry_components(graph.edge_features, manifest["geometry_gate"])
        assert components.shape == (len(graph.geometry_cost), 8)
        assert np.allclose(
            components @ ORIGINAL_GEOMETRY_WEIGHTS,
            graph.geometry_cost,
            rtol=1e-5,
            atol=1e-6,
        )


def test_all_lightweight_models_fit_and_serialize_without_truth(dataset_manifest):
    manifest, data = _training_data(dataset_manifest)
    models = fit_all_models(data, manifest["geometry_gate"], random_seed=7)
    assert len(models) == 3 + len(LOGISTIC_C_GRID)
    assert {
        float(model.parameters["C"])
        for model in models
        if model.kind == "logistic_edge_features"
    } == set(LOGISTIC_C_GRID)
    geometry_model = next(model for model in models if model.kind == "geometry_nonnegative")
    assert np.all(np.asarray(geometry_model.parameters["weights"]) >= 0.0)
    for model in models:
        probabilities = model.predict_proba(data[0][0], manifest["geometry_gate"])
        assert probabilities.shape == data[0][0].geometry_cost.shape
        assert np.all((probabilities > 0.0) & (probabilities < 1.0))
        payload = model.to_dict()
        serialized = json.dumps(payload).lower()
        assert "truth_id\": true" not in serialized
        assert "actor_name\": true" not in serialized
        assert "true_world_position\": true" not in serialized
        restored = LightweightModel.from_dict(payload)
        assert np.allclose(
            restored.predict_proba(data[0][0], manifest["geometry_gate"]),
            probabilities,
        )


def test_probability_threshold_blocks_edge_before_hungarian():
    graph = OnlineGraph(
        seed=1,
        corruption_level="light",
        camera_ids=("A", "B"),
        track_ids_a=("A1", "A2"),
        track_ids_b=("B1", "B2"),
        node_features_a=np.zeros((2, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        node_features_b=np.zeros((2, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        edge_index=np.asarray(((0, 0, 1), (0, 1, 0)), dtype=np.int64),
        edge_features=np.zeros((3, len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        geometry_cost=np.asarray((0.1, 0.1, 0.1), dtype=np.float32),
        corruption_summary=CorruptionSummary("light", 1, 0, 0, 0, 0),
    )
    graph.validate()
    result = solve_probability_assignment(
        graph,
        np.asarray((0.95, 0.49, 0.90), dtype=np.float64),
        0.5,
    )
    assert [(pair.index_a, pair.index_b) for pair in result.selected_pairs] == [
        (0, 0)
    ]
    assert result.duplicate_track_assignment_count == 0


def test_probability_threshold_and_unmatched_cost_are_independent():
    graph = OnlineGraph(
        seed=2,
        corruption_level="light",
        camera_ids=("A", "B"),
        track_ids_a=("A1",),
        track_ids_b=("B1",),
        node_features_a=np.zeros((1, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        node_features_b=np.zeros((1, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        edge_index=np.asarray(((0,), (0,)), dtype=np.int64),
        edge_features=np.zeros((1, len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        geometry_cost=np.zeros((1,), dtype=np.float32),
        corruption_summary=CorruptionSummary("light", 2, 0, 0, 0, 0),
    )
    graph.validate()
    probability = np.asarray((0.70,), dtype=np.float64)
    rejected_by_cost = solve_probability_assignment(graph, probability, 0.3, 0.25)
    accepted_by_cost = solve_probability_assignment(graph, probability, 0.3, 0.40)
    assert rejected_by_cost.selected_pairs == ()
    assert len(accepted_by_cost.selected_pairs) == 1


def test_covariance_aware_components_use_normalized_residuals(dataset_manifest):
    manifest, data = _training_data(dataset_manifest)
    graph, _ = data[0]
    features = graph.edge_features.copy()
    coplanarity_index = EDGE_FEATURE_NAMES.index("normalized_coplanarity_residual")
    motion_index = EDGE_FEATURE_NAMES.index("normalized_motion_residual")
    sigma_index = EDGE_FEATURE_NAMES.index("combined_bearing_sigma_mrad")
    features[:, coplanarity_index] = 3.0
    features[:, motion_index] = 1.5
    features[:, sigma_index] = 2.0
    components = geometry_components(
        features, manifest["geometry_gate"], covariance_aware=True
    )
    assert np.allclose(components[:, 0], 1.0)
    assert np.allclose(components[:, 5], 0.5)
