from __future__ import annotations

import inspect

import numpy as np
import pytest

import d5_terminal_association.tracklet_model_bundle as bundle_module
from d5_terminal_association.sparse_tracklet_graph import (
    EDGE_FEATURE_NAMES,
    SparseTrackletGraphConfig,
)
from d5_terminal_association.tracklet_dataset import (
    LoadedTrackletGraph,
    join_offline_observation_labels,
)
from d5_terminal_association.tracklet_supplemental_curriculum import (
    _build_curriculum_frame,
    _camera_local_kinematic_measurement,
)
from d5_terminal_association.tracklet_training import (
    ROBUST_TRAINING_PROFILE_VERSION,
    ROBUST_TRAINING_VIEW_IDS,
    TrackletTrainingConfig,
    build_robust_training_feature_view,
)


def test_camera_local_measurement_error_is_deterministic_and_identity_free() -> None:
    parameters = inspect.signature(
        _camera_local_kinematic_measurement
    ).parameters
    assert all("truth" not in name and "label" not in name for name in parameters)

    first = _camera_local_kinematic_measurement(
        observation_id="anonymous-observation-a",
        bbox_side=8.0,
        angular_velocity_rad_s=np.array([0.01, -0.02]),
        bbox_scale_rate_s=0.003,
    )
    repeated = _camera_local_kinematic_measurement(
        observation_id="anonymous-observation-a",
        bbox_side=8.0,
        angular_velocity_rad_s=np.array([0.01, -0.02]),
        bbox_scale_rate_s=0.003,
    )
    independent = _camera_local_kinematic_measurement(
        observation_id="anonymous-observation-b",
        bbox_side=8.0,
        angular_velocity_rad_s=np.array([0.01, -0.02]),
        bbox_scale_rate_s=0.003,
    )

    assert first[0] == repeated[0]
    assert np.array_equal(first[1], repeated[1])
    assert first[2] == repeated[2]
    assert not np.array_equal(first[1], independent[1])


def test_positive_edges_do_not_keep_exact_scale_and_motion_shortcuts() -> None:
    graph, offline, _, factors = _build_curriculum_frame(
        1000,
        scenario="nominal",
        scale=20,
        frame_index=0,
        gate_config=SparseTrackletGraphConfig(),
    )
    joined = join_offline_observation_labels(graph, offline)
    labels = {
        item.tracklet_key: item.truth_entity_id
        for item in joined.tracklet_labels
    }
    positive_indices = [
        index
        for index, edge in enumerate(graph.edges)
        if labels[edge.source_tracklet_key] == labels[edge.target_tracklet_key]
    ]
    shortcut_columns = [
        EDGE_FEATURE_NAMES.index("bbox_log_scale_delta"),
        EDGE_FEATURE_NAMES.index("bbox_scale_rate_delta_s"),
        EDGE_FEATURE_NAMES.index("angular_velocity_delta_rad_s"),
    ]

    assert positive_indices
    assert factors["camera_local_measurement_noise"] == graph.node_count
    for column in shortcut_columns:
        values = graph.edge_features[positive_indices, column]
        assert np.any(values > 1.0e-8)
        assert len(np.unique(values)) > 1


@pytest.mark.parametrize("profile_id", ROBUST_TRAINING_VIEW_IDS)
def test_robust_training_views_are_deterministic_and_do_not_mutate_source(
    profile_id: str,
) -> None:
    graph, _, _, _ = _build_curriculum_frame(
        7,
        scenario="delayed_noisy",
        scale=200,
        frame_index=0,
        gate_config=SparseTrackletGraphConfig(),
    )
    loaded = LoadedTrackletGraph(
        episode_uid="robust-view-test",
        scenario_version="delayed_noisy-200v200-v1",
        seed=7,
        episode_id="frame-0",
        node_features=graph.node_features,
        edge_index=graph.edge_index,
        edge_features=graph.edge_features,
        tracklet_keys=tuple(node.tracklet_key for node in graph.nodes),
        camera_keys=tuple(node.camera_key for node in graph.nodes),
        measurement_timestamps=np.asarray(
            [node.measurement_timestamp for node in graph.nodes],
            dtype=float,
        ),
        arrival_timestamps=np.asarray(
            [node.arrival_timestamp for node in graph.nodes],
            dtype=float,
        ),
        gate_scores=np.asarray(
            [edge.gate_score for edge in graph.edges],
            dtype=float,
        ),
        candidate_counts=graph.candidate_counts,
    )
    original_nodes = loaded.node_features.copy()
    original_edges = loaded.edge_features.copy()

    first_nodes, first_edges, first_meta = build_robust_training_feature_view(
        loaded,
        profile_id,
    )
    second_nodes, second_edges, second_meta = (
        build_robust_training_feature_view(loaded, profile_id)
    )

    assert np.array_equal(first_nodes, second_nodes)
    assert np.array_equal(first_edges, second_edges)
    assert first_meta == second_meta
    assert first_meta["label_accessed"] is False
    assert first_meta["candidate_topology_changed"] is False
    assert np.array_equal(loaded.node_features, original_nodes)
    assert np.array_equal(loaded.edge_features, original_edges)
    assert not first_nodes.flags.writeable
    assert not first_edges.flags.writeable


def test_robust_training_profile_is_frozen() -> None:
    config = TrackletTrainingConfig(
        robust_training_profile_version=ROBUST_TRAINING_PROFILE_VERSION,
        robust_training_view_ids=ROBUST_TRAINING_VIEW_IDS,
    )
    assert config.robust_training_view_ids == ROBUST_TRAINING_VIEW_IDS

    with pytest.raises(ValueError, match="profile or view catalog changed"):
        TrackletTrainingConfig(
            robust_training_profile_version=ROBUST_TRAINING_PROFILE_VERSION,
            robust_training_view_ids=ROBUST_TRAINING_VIEW_IDS[:-1],
        )


def test_model_and_runtime_source_lineage_are_separate_and_cross_bound() -> None:
    provenance = bundle_module._implementation_provenance()
    model_sources = provenance["source_files"]
    runtime_sources = provenance["runtime_source_files"]

    assert set(model_sources) == {
        "tracklet_gnn.py",
        "tracklet_model_bundle.py",
        "tracklet_training.py",
        "tracklet_training_audit.py",
    }
    assert len(runtime_sources) == 10
    assert "tracklet_g1_evidence_assembler.py" in runtime_sources
    assert all(
        model_sources[name] == runtime_sources[name]
        for name in model_sources
    )
    assert (
        provenance["implementation_sha256"]
        != provenance["runtime_implementation_sha256"]
    )
