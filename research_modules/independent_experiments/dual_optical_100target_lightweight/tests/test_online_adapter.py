from __future__ import annotations

from dataclasses import replace
import json

import numpy as np
import pytest

from dual_optical_100target_gnn.dataset import load_dataset_manifest, load_entry, sample_entries
from dual_optical_100target_gnn.schema import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CorruptionSummary,
    OnlineGraph,
)
from dual_optical_100target_lightweight.models import fit_all_models
from dual_optical_100target_lightweight.assignment import solve_probability_assignment
from dual_optical_100target_lightweight.online import (
    FrozenRoute,
    OnlineAssociationPublication,
    OnlineLightweightAdapter,
    RevolutionSnapshot,
)


def _fitted_routes(dataset_manifest):
    manifest, root = load_dataset_manifest(dataset_manifest)
    training = []
    for entry in sample_entries(manifest, "train"):
        graph, labels = load_entry(root, entry, include_labels=True)
        assert labels is not None
        training.append((graph, labels))
    models = fit_all_models(training, manifest["geometry_gate"], random_seed=3)
    selected = {}
    for model in models:
        selected.setdefault(model.kind, model)
    routes = tuple(FrozenRoute.create(model, 0.3) for model in selected.values())
    return manifest, training[0][0], routes


def _snapshot(graph, revolution_index, cutoff):
    return RevolutionSnapshot.from_graph(
        graph,
        revolution_index=revolution_index,
        cutoff_timestamp=cutoff,
        observation_max_timestamp=cutoff - 0.1,
        snapshot_mode="cumulative",
    )


def test_online_adapter_runs_four_routes_and_confirms_consecutive_pairs(dataset_manifest):
    manifest, graph, routes = _fitted_routes(dataset_manifest)
    adapter = OnlineLightweightAdapter(
        routes,
        manifest["geometry_gate"],
        allowed_seeds=(graph.seed,),
        confirmation_window_revolutions=3,
        confirmation_hits=2,
    )
    first = adapter.process(_snapshot(graph, 1, 2.0))
    second = adapter.process(_snapshot(graph, 2, 4.0))
    third = adapter.process(_snapshot(graph, 3, 6.0))

    assert {item.route_id for item in first} == {
        "geometry_nonnegative",
        "platt_geometry_cost",
        "isotonic_geometry_cost",
        "logistic_edge_features",
    }
    assert len({item.input_fingerprint_sha256 for item in first}) == 1
    assert all(item.scoring_ms >= 0.0 for item in first)
    assert all(item.hungarian_ms >= 0.0 for item in first)
    assert all(item.end_to_end_ms >= item.scoring_ms + item.hungarian_ms for item in first)
    assert all(item.latency_budget_met for item in first)
    assert all(not item.matches for item in first)
    assert all(item.rejection_reasons["suppressed_before_second_revolution"] > 0 for item in first)
    for first_item, second_item, third_item in zip(first, second, third):
        second_pairs = {(item.track_a_id, item.track_b_id) for item in second_item.matches}
        assert all(item.confirmation_state == "raw" for item in second_item.matches)
        third_confirmed = {
            (item.track_a_id, item.track_b_id)
            for item in third_item.matches
            if item.confirmation_state == "confirmed"
        }
        assert second_pairs <= third_confirmed
        restored = OnlineAssociationPublication.from_dict(first_item.to_dict())
        assert restored.to_dict() == first_item.to_dict()


def test_two_of_three_confirmation_survives_one_missing_revolution(
    dataset_manifest, monkeypatch
):
    manifest, graph, routes = _fitted_routes(dataset_manifest)
    route = routes[0]
    adapter = OnlineLightweightAdapter(
        (route,),
        manifest["geometry_gate"],
        confirmation_window_revolutions=3,
        confirmation_hits=2,
    )
    first = adapter.process(_snapshot(graph, 1, 2.0))[0]
    empty = replace(
        graph,
        edge_index=np.empty((2, 0), dtype=np.int64),
        edge_features=np.empty((0, len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        geometry_cost=np.empty((0,), dtype=np.float32),
    )
    adapter.process(_snapshot(empty, 2, 4.0))
    third = adapter.process(_snapshot(graph, 3, 6.0))[0]
    expected_pairs = {
        (graph.track_ids_a[item.index_a], graph.track_ids_b[item.index_b])
        for item in solve_probability_assignment(
            graph,
            route.model.predict_proba(graph, manifest["geometry_gate"]),
            route.probability_threshold,
            route.unmatched_cost,
        ).selected_pairs
    }
    confirmed = {
        (item.track_a_id, item.track_b_id)
        for item in third.matches
        if item.confirmation_state == "confirmed"
    }
    assert not first.matches
    assert expected_pairs
    assert expected_pairs <= confirmed


def test_timeout_fails_closed_and_does_not_advance_confirmation_history(
    dataset_manifest,
):
    manifest, graph, routes = _fitted_routes(dataset_manifest)
    route = routes[0]
    adapter = OnlineLightweightAdapter(
        (route,),
        manifest["geometry_gate"],
        latency_budget_ms=1.0,
    )
    first = adapter.process(
        _snapshot(graph, 1, 2.0), upstream_elapsed_ms=2.0
    )[0]
    assert first.availability == "timeout"
    assert not first.matches
    assert first.rejection_reasons["deadline_exceeded"] == 1

    adapter.latency_budget_ms = 1000.0
    second = adapter.process(_snapshot(graph, 2, 4.0))[0]
    third = adapter.process(_snapshot(graph, 3, 6.0))[0]
    assert all(item.confirmation_state == "raw" for item in second.matches)
    assert all(item.confirmation_state == "confirmed" for item in third.matches)


def test_snapshot_rejects_future_data_and_fingerprint_tamper(dataset_manifest):
    _, graph, _ = _fitted_routes(dataset_manifest)
    with pytest.raises(ValueError, match="after cutoff"):
        RevolutionSnapshot.from_graph(
            graph,
            revolution_index=1,
            cutoff_timestamp=2.0,
            observation_max_timestamp=2.01,
        )
    snapshot = _snapshot(graph, 1, 2.0)
    payload = snapshot.to_dict()
    payload["input_fingerprint_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        RevolutionSnapshot.from_dict(payload)


def test_snapshot_serialization_is_stable(dataset_manifest, tmp_path):
    _, graph, _ = _fitted_routes(dataset_manifest)
    snapshot = _snapshot(graph, 1, 2.0)
    path = snapshot.write_json(tmp_path / "snapshot.json")
    restored = RevolutionSnapshot.read_json(path)
    assert restored.input_fingerprint_sha256 == snapshot.input_fingerprint_sha256
    assert restored.to_dict() == snapshot.to_dict()
    serialized = json.dumps(restored.to_dict()).lower()
    assert "truth_id" not in serialized
    assert "actor_name" not in serialized


def test_empty_graph_and_no_candidate_graph_return_availability(dataset_manifest):
    manifest, graph, routes = _fitted_routes(dataset_manifest)
    empty = OnlineGraph(
        seed=graph.seed,
        corruption_level=graph.corruption_level,
        camera_ids=graph.camera_ids,
        track_ids_a=(),
        track_ids_b=(),
        node_features_a=np.empty((0, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        node_features_b=np.empty((0, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        edge_index=np.empty((2, 0), dtype=np.int64),
        edge_features=np.empty((0, len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        geometry_cost=np.empty((0,), dtype=np.float32),
        corruption_summary=CorruptionSummary("light", 1, 0, 0, 0, 0),
    )
    empty.validate()
    adapter = OnlineLightweightAdapter(routes, manifest["geometry_gate"])
    publications = adapter.process(_snapshot(empty, 1, 2.0))
    assert all(item.availability == "empty_graph" for item in publications)
    assert all(not item.matches for item in publications)

    no_candidates = replace(
        graph,
        edge_index=np.empty((2, 0), dtype=np.int64),
        edge_features=np.empty((0, len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        geometry_cost=np.empty((0,), dtype=np.float32),
    )
    no_candidates.validate()
    adapter.reset()
    publications = adapter.process(_snapshot(no_candidates, 1, 2.0))
    assert all(item.availability == "no_candidates" for item in publications)


def test_adapter_rejects_unreserved_seed_and_nonmonotonic_prefix(dataset_manifest):
    manifest, graph, routes = _fitted_routes(dataset_manifest)
    adapter = OnlineLightweightAdapter(
        routes, manifest["geometry_gate"], allowed_seeds=(graph.seed,)
    )
    adapter.process(_snapshot(graph, 1, 2.0))
    with pytest.raises(ValueError, match="increasing order"):
        adapter.process(_snapshot(graph, 1, 2.0))
    wrong_seed = replace(graph, seed=graph.seed + 100)
    with pytest.raises(ValueError, match="reserved-test"):
        adapter.process(_snapshot(wrong_seed, 1, 2.0))
