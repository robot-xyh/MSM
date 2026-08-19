from __future__ import annotations

import json

import numpy as np
import pytest

from dual_optical_target_track_gnn import (
    CausalityError,
    ConfirmedTrackPair,
    FeatureNormalizer,
    TargetHypothesis,
    TargetTrackCostGNN,
    TargetTrackPublication,
    build_target_track_graph,
    publish_with_confirmation,
    route_costs,
    solve_target_track_assignment,
)
from dual_optical_target_track_gnn.contracts import (
    EDGE_FEATURE_NAMES,
    TARGET_FEATURE_NAMES,
    TRACK_FEATURE_NAMES,
    TargetTrackGraph,
    payload_fingerprint,
)
from dual_optical_target_track_gnn.graph import TargetTrackGate, target_track_evidence

from conftest import (
    CAMERA_POSITIONS,
    TARGET_POSITION,
    TARGET_VELOCITY,
    make_confirmed_pair,
    make_snapshot,
    make_track,
)


def make_hypothesis(
    hypothesis_id: str = "H-001",
    *,
    created_revolution_index: int = 2,
    position: np.ndarray = TARGET_POSITION,
    velocity: np.ndarray = TARGET_VELOCITY,
) -> TargetHypothesis:
    reference_timestamp = 1.0
    state = np.concatenate((position + velocity * reference_timestamp, velocity))
    covariance = np.diag((25.0, 25.0, 25.0, 1.0, 1.0, 1.0))
    seed_snapshot = make_snapshot(
        1,
        (make_track("camera_a", "A-seed", (0.1, 0.2)),),
        (make_track("camera_b", "B-seed", (1.1, 1.2)),),
    )
    confirmed_pair, _ = make_confirmed_pair(
        seed_snapshot, "A-seed", "B-seed"
    )
    return TargetHypothesis(
        hypothesis_id=hypothesis_id,
        created_revolution_index=created_revolution_index,
        reference_timestamp=reference_timestamp,
        state_ned=tuple(float(value) for value in state),
        covariance_6x6=tuple(float(value) for value in covariance.reshape(-1)),
        support_count=8,
        confirmed_pairs=(confirmed_pair,),
        fit_rms_mrad=0.1,
        fit_condition_number=100.0,
        last_observation_timestamp=1.5,
    )


def manual_graph(
    *,
    seed: int,
    revolution: int,
    camera_id: str,
    hypothesis_count: int,
    track_count: int,
    edges: tuple[tuple[int, int, float], ...],
) -> TargetTrackGraph:
    hypothesis_ids = tuple(f"H-{index}" for index in range(hypothesis_count))
    track_ids = tuple(f"{camera_id}-T-{index}" for index in range(track_count))
    edge_index = (
        np.asarray([(a, b) for a, b, _ in edges], dtype=np.int64).T
        if edges
        else np.empty((2, 0), dtype=np.int64)
    )
    fingerprint = payload_fingerprint(
        {
            "schema_version": "dual-optical-target-track-gnn-v1",
            "seed": seed,
            "revolution_index": revolution,
            "camera_id": camera_id,
            "edges": [
                [hypothesis_ids[a], track_ids[b]] for a, b, _ in edges
            ],
        }
    )
    graph = TargetTrackGraph(
        seed=seed,
        revolution_index=revolution,
        camera_id=camera_id,
        hypothesis_ids=hypothesis_ids,
        track_ids=track_ids,
        target_features=np.ones(
            (hypothesis_count, len(TARGET_FEATURE_NAMES)), dtype=np.float32
        ),
        track_features=np.ones(
            (track_count, len(TRACK_FEATURE_NAMES)), dtype=np.float32
        ),
        edge_index=edge_index,
        edge_features=np.ones((len(edges), len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        rule_cost=np.asarray([cost for _, _, cost in edges], dtype=np.float32),
        whitelist_fingerprint=fingerprint,
    )
    graph.validate()
    return graph


def test_graph_rejects_same_revolution_hypothesis_and_identity_sources() -> None:
    current_track = make_track("camera_a", "A-current", (4.1, 4.2, 4.3))
    snapshot = make_snapshot(3, (current_track,), ())
    with pytest.raises(CausalityError):
        build_target_track_graph(
            snapshot,
            (make_hypothesis(created_revolution_index=3),),
            "camera_a",
        )

    identity_track = make_track(
        "camera_a",
        "truth_id-17",
        (4.1, 4.2),
        source_kind="truth",
    )
    contaminated = make_snapshot(3, (identity_track,), ())
    with pytest.raises(ValueError, match="forbidden|anonymous"):
        build_target_track_graph(
            contaminated, (make_hypothesis(),), "camera_a"
        )


def test_seed_samples_cannot_be_reused_as_target_track_evidence() -> None:
    hypothesis = make_hypothesis()
    old_track = make_track(
        "camera_a", "A-seed", (0.1, 0.2, 1.0, 1.5)
    )
    evidence = target_track_evidence(
        hypothesis,
        old_track,
        CAMERA_POSITIONS["camera_a"],
        cutoff_timestamp=6.0,
        gate=TargetTrackGate(minimum_track_samples=1),
    )
    assert not evidence.gate_passed
    assert "new_evidence" in evidence.rejection_reasons

    later_snapshot = make_snapshot(3, (old_track,), ())
    graph = build_target_track_graph(
        later_snapshot, (hypothesis,), "camera_a",
        gate=TargetTrackGate(minimum_track_samples=1),
    )
    assert graph.edge_index.shape == (2, 0)
    assert graph.rejection_counts["new_evidence"] == 1
    for route in ("deterministic",):
        result = solve_target_track_assignment(graph, route)
        assert result.selected_pairs == ()


def test_public_online_records_do_not_expose_identity_fields() -> None:
    payload = make_hypothesis().to_dict()
    encoded = json.dumps(payload, sort_keys=True)
    assert "global_track_id" not in encoded
    assert "truth_id" not in encoded
    assert "actor_id" not in encoded


def test_public_graph_json_round_trip(tmp_path) -> None:
    graph = manual_graph(
        seed=8,
        revolution=3,
        camera_id="camera_a",
        hypothesis_count=2,
        track_count=2,
        edges=((0, 0, 0.1), (1, 1, 0.2)),
    )
    path = tmp_path / "graph.json"
    graph.write_json(path)
    restored = TargetTrackGraph.read_json(path)
    assert restored.whitelist_fingerprint == graph.whitelist_fingerprint
    assert np.array_equal(restored.edge_index, graph.edge_index)
    assert np.allclose(restored.rule_cost, graph.rule_cost)

    hypothesis_path = tmp_path / "hypothesis.json"
    hypothesis = make_hypothesis()
    hypothesis.write_json(hypothesis_path)
    assert TargetHypothesis.read_json(hypothesis_path) == hypothesis

    assignment = solve_target_track_assignment(graph, "deterministic")
    publication = publish_with_confirmation(graph, assignment)[0]
    publication_path = tmp_path / "publication.json"
    publication.write_json(publication_path)
    assert TargetTrackPublication.read_json(publication_path) == publication


def test_empty_graph_and_no_match_return_explicit_unmatched_sets() -> None:
    empty = manual_graph(
        seed=1,
        revolution=3,
        camera_id="camera_a",
        hypothesis_count=0,
        track_count=0,
        edges=(),
    )
    result = solve_target_track_assignment(empty, "deterministic")
    assert result.selected_pairs == ()
    assert result.unmatched_hypothesis_indices == ()
    assert result.unmatched_track_indices == ()

    no_match = manual_graph(
        seed=1,
        revolution=3,
        camera_id="camera_a",
        hypothesis_count=2,
        track_count=3,
        edges=(),
    )
    result = solve_target_track_assignment(no_match, "deterministic")
    assert result.unmatched_hypothesis_indices == (0, 1)
    assert result.unmatched_track_indices == (0, 1, 2)


def test_hungarian_enforces_one_to_one_and_two_of_three_confirmation() -> None:
    graph_3 = manual_graph(
        seed=9,
        revolution=3,
        camera_id="camera_a",
        hypothesis_count=2,
        track_count=2,
        edges=((0, 0, 0.1), (0, 1, 0.2), (1, 0, 0.15), (1, 1, 0.1)),
    )
    result_3 = solve_target_track_assignment(graph_3, "deterministic")
    assert result_3.duplicate_assignment_count == 0
    assert {(item.hypothesis_index, item.track_index) for item in result_3.selected_pairs} == {
        (0, 0),
        (1, 1),
    }
    publications_3 = publish_with_confirmation(graph_3, result_3)
    assert {item.decision_state for item in publications_3} == {"tentative"}

    graph_4 = manual_graph(
        seed=9,
        revolution=4,
        camera_id="camera_a",
        hypothesis_count=2,
        track_count=2,
        edges=((0, 0, 0.1), (0, 1, 0.2), (1, 0, 0.15), (1, 1, 0.1)),
    )
    result_4 = solve_target_track_assignment(graph_4, "deterministic")
    publications_4 = publish_with_confirmation(
        graph_4, result_4, publications_3
    )
    assert {item.decision_state for item in publications_4} == {"confirmed"}
    assert {item.agreement_count for item in publications_4} == {2}


def test_variable_graph_sizes_and_both_routes_share_exact_whitelist() -> None:
    for count in (1, 4, 11):
        edges = tuple((index, index, 0.1) for index in range(count))
        graph = manual_graph(
            seed=100 + count,
            revolution=4,
            camera_id="camera_b",
            hypothesis_count=count,
            track_count=count + 2,
            edges=edges,
        )
        graph.validate()
        assert graph.edge_index.shape == (2, count)

    graph = manual_graph(
        seed=55,
        revolution=4,
        camera_id="camera_b",
        hypothesis_count=2,
        track_count=2,
        # Edge (0, 1) is deliberately absent from the hard whitelist.
        edges=((0, 0, 0.2), (1, 1, 0.2)),
    )
    normalizer = FeatureNormalizer.fit((graph,))
    model = TargetTrackCostGNN(
        graph.target_features.shape[1],
        graph.track_features.shape[1],
        graph.edge_features.shape[1],
        dropout=0.0,
    )
    deterministic_correction, deterministic_cost = route_costs(
        graph, "deterministic"
    )
    learned_correction, learned_cost = route_costs(
        graph,
        "gnn_assisted",
        model=model,
        normalizer=normalizer,
    )
    assert deterministic_correction.shape == learned_correction.shape == (2,)
    assert deterministic_cost.shape == learned_cost.shape == (2,)
    assert graph.edge_index.T.tolist() == [[0, 0], [1, 1]]
    assert graph.whitelist_fingerprint == graph.compute_whitelist_fingerprint()
