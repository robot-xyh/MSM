from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pytest

from dual_optical_online_benchmark.contracts import (
    BenchmarkProtocol,
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    snapshot_fingerprint,
)
from dual_optical_100target_gnn.corruption import corrupt_episode_causal
from dual_optical_100target_gnn.dataset import (
    CAUSAL_DATASET_SCHEMA_VERSION,
    PROTOCOL_CAUSAL_ONLINE,
    dataset_fingerprint,
    prepare_causal_dataset,
    protocol_profile,
    sample_entries,
)
from dual_optical_100target_gnn.graph import GeometryGate
from dual_optical_100target_gnn.loader import load_offline_labels, load_online_episode
from dual_optical_100target_gnn.model import BipartiteEdgeGNN
from dual_optical_100target_gnn.online_benchmark import (
    dominant_truth,
    freeze_route,
    load_frozen_route,
)
from dual_optical_100target_gnn.online import (
    OnlineGNNAssociator,
    anonymous_graph_from_snapshot,
)
from dual_optical_100target_gnn.schema import (
    CAUSAL_FORMAL_SPLITS,
    CORRUPTION_LEVELS,
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CausalProtocolConfig,
    CorruptionSummary,
    GraphLabels,
    OnlineGraph,
)
from dual_optical_100target_gnn.training import (
    CausalTrainingConfig,
    _validation_selection_key,
    train_causal_ensemble_and_freeze,
    verify_freeze_manifest,
)


def test_causal_profile_is_exact_24_6_20_and_training_is_200_25() -> None:
    assert protocol_profile(CAUSAL_FORMAL_SPLITS, 100) == PROTOCOL_CAUSAL_ONLINE
    assert [len(CAUSAL_FORMAL_SPLITS[name]) for name in ("train", "val", "test")] == [
        24,
        6,
        20,
    ]
    config = CausalTrainingConfig(device="cpu")
    assert config.max_epochs == 200
    assert config.patience == 25
    assert len(config.initialization_seeds) == 5


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"TRUTH-001": 5, "TRUTH-002": 4}, "TRUTH-001"),
        ({"TRUTH-001": 5, "TRUTH-002": 5}, None),
        ({"FA": 6, "TRUTH-001": 5}, None),
        ({"FA-Optical_A-P01": 6, "TRUTH-001": 5}, None),
        ({}, None),
    ],
)
def test_dominant_truth_uses_unique_non_false_alarm_maximum(
    counts, expected
) -> None:
    assert dominant_truth(counts) == expected


def test_shared_snapshot_tracks_are_anonymous_before_graph_build(
    monkeypatch,
) -> None:
    sample = SnapshotTrackSample(
        sweep_index=0,
        timestamp=1.0,
        direction_ned=(1.0, 0.0, 0.0),
        detection_count=1,
        bbox_area_px2=4.0,
        confidence=0.8,
    )
    snapshot = RevolutionSnapshot(
        protocol_fingerprint=BenchmarkProtocol().fingerprint,
        seed=20261001,
        split="train",
        corruption_level="light",
        revolution_index=1,
        cutoff_timestamp=2.0,
        camera_ids=("Optical_A", "Optical_B"),
        camera_positions_ned={
            "Optical_A": (0.0, -1000.0, -100.0),
            "Optical_B": (0.0, 1000.0, -100.0),
        },
        focal_length_px=25000.0,
        tracks={
            "Optical_A": (
                SnapshotTrack("A-1", "Optical_A", (sample,), "measured"),
            ),
            "Optical_B": (
                SnapshotTrack("B-1", "Optical_B", (sample,), "truth_like"),
            ),
        },
    )
    captured = {}

    def capture(episode, summary, *, gate):
        captured["source_kinds"] = {
            track.source_kind
            for camera_tracks in episode.tracks.values()
            for track in camera_tracks
        }
        return "graph", {"candidate_edge_count": 0}

    monkeypatch.setattr(
        "dual_optical_100target_gnn.online.build_online_graph", capture
    )
    graph, _ = anonymous_graph_from_snapshot(snapshot, GeometryGate())
    assert graph == "graph"
    assert captured["source_kinds"] == {"anonymous"}


def test_causal_dataset_contains_six_prefixes_per_corruption(episode_factory, tmp_path) -> None:
    inputs = {seed: episode_factory(seed) for seed in (701, 702, 703)}
    path = prepare_causal_dataset(
        inputs,
        tmp_path / "causal_dataset",
        splits={"train": (701,), "val": (702,), "test": (703,)},
        expected_target_count=4,
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == CAUSAL_DATASET_SCHEMA_VERSION
    assert manifest["causal_prefix_protocol"] is True
    assert manifest["revolutions_per_seed"] == 6
    entries = sample_entries(manifest, "train")
    assert len(entries) == 18
    assert {(item["corruption_level"], item["revolution_index"]) for item in entries} == {
        (level, revolution)
        for level in CORRUPTION_LEVELS
        for revolution in range(1, 7)
    }
    assert all(len(item["input_fingerprint_sha256"]) == 64 for item in entries)


def test_causal_corruption_keeps_prior_miss_decisions(episode_factory) -> None:
    episode = load_online_episode(episode_factory(704))
    labels = load_offline_labels(episode_factory(704), episode)
    config = CORRUPTION_LEVELS["heavy"]

    def prefix(cutoff: float):
        tracks = {
            camera_id: tuple(
                type(track)(
                    track.track_id,
                    track.camera_id,
                    tuple(sample for sample in track.samples if sample.timestamp <= cutoff),
                    track.source_kind,
                )
                for track in episode.tracks[camera_id]
            )
            for camera_id in episode.camera_ids
        }
        return type(episode)(
            episode.seed,
            episode.schema_version,
            episode.configured_target_count,
            episode.camera_ids,
            episode.camera_positions_ned,
            episode.focal_length_px,
            tracks,
            episode.source_hashes,
        )

    early, _, _ = corrupt_episode_causal(prefix(2.0), labels, config)
    later, _, _ = corrupt_episode_causal(prefix(4.0), labels, config)
    for camera_id in episode.camera_ids:
        early_samples = {
            (track.track_id, sample.sweep_index, sample.timestamp)
            for track in early.tracks[camera_id]
            if track.source_kind == "measured"
            for sample in track.samples
        }
        later_prior_samples = {
            (track.track_id, sample.sweep_index, sample.timestamp)
            for track in later.tracks[camera_id]
            if track.source_kind == "measured"
            for sample in track.samples
            if sample.timestamp <= 2.0
        }
        assert early_samples == later_prior_samples


def _tiny_graph() -> tuple[OnlineGraph, GraphLabels]:
    graph = OnlineGraph(
        seed=1,
        corruption_level="light",
        camera_ids=("Optical_A", "Optical_B"),
        track_ids_a=("A-1",),
        track_ids_b=("B-1",),
        node_features_a=np.ones((1, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        node_features_b=np.ones((1, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        edge_index=np.asarray([[0], [0]], dtype=np.int64),
        edge_features=np.ones((1, len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        geometry_cost=np.asarray([0.1], dtype=np.float32),
        corruption_summary=CorruptionSummary("light", 1, 0, 1, 0, 0),
    )
    labels = GraphLabels(
        edge_labels=np.asarray([1.0], dtype=np.float32),
        identity_a=("ID-1",),
        identity_b=("ID-1",),
        expected_identities=("ID-1",),
    )
    graph.validate()
    labels.validate(graph)
    return graph, labels


def _formal_manifest(path: Path) -> Path:
    samples = []
    for split, seeds in CAUSAL_FORMAL_SPLITS.items():
        for seed in seeds:
            for level in CORRUPTION_LEVELS:
                for revolution in range(1, 7):
                    stem = f"seed_{seed}_{level}_rev_{revolution:02d}"
                    samples.append(
                        {
                            "seed": seed,
                            "split": split,
                            "corruption_level": level,
                            "revolution_index": revolution,
                            "cutoff_timestamp_s": float(revolution * 2),
                            "online_path": f"online/{stem}.npz",
                            "online_sha256": "a" * 64,
                            "input_fingerprint_sha256": "b" * 64,
                            "offline_label_path": f"offline_labels/{stem}.npz",
                            "offline_label_sha256": "c" * 64,
                            "corruption": {},
                            "online_diagnostics": {},
                        }
                    )
    manifest = {
        "schema_version": CAUSAL_DATASET_SCHEMA_VERSION,
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "splits": {name: list(values) for name, values in CAUSAL_FORMAL_SPLITS.items()},
        "formal_protocol": True,
        "expanded_formal_protocol": False,
        "causal_prefix_protocol": True,
        "protocol_profile": PROTOCOL_CAUSAL_ONLINE,
        "protocol_fingerprint_sha256": BenchmarkProtocol().fingerprint,
        "revolutions_per_seed": 6,
        "causal_scenario_contract": asdict(CausalProtocolConfig()),
        "expected_target_count": 100,
        "corruption_levels": {
            name: asdict(config) for name, config in CORRUPTION_LEVELS.items()
        },
        "geometry_gate": asdict(GeometryGate()),
        "sources": {str(seed): {} for seeds in CAUSAL_FORMAL_SPLITS.values() for seed in seeds},
        "samples": samples,
        "truth_isolation": {
            "online_files_contain_identity": False,
            "labels_are_offline_only": True,
            "actor_fields_are_features": False,
            "world_truth_fields_are_features": False,
        },
    }
    manifest["dataset_fingerprint_sha256"] = dataset_fingerprint(manifest)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def _selection(base_f1: float) -> dict[str, object]:
    candidates = []
    for route in ("learned", "hybrid"):
        for threshold in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            candidates.append(
                {
                    "route": route,
                    "probability_threshold": threshold,
                    "unmatched_cost": float(-np.log(threshold)),
                    "sample_count": 1,
                    "macro_precision": base_f1,
                    "macro_recall": base_f1,
                    "macro_f1": base_f1 + (0.001 if route == "hybrid" else 0.0),
                    "false_association_count": 1,
                    "duplicate_identity_match_count": 0,
                    "correct_assignment_count": 1,
                    "selected_assignment_count": 2,
                    "candidate_positive_edge_count": 1,
                    "expected_identity_count": 1,
                    "candidate_true_edge_identity_count": 1,
                    "candidate_true_edge_retention": 1.0,
                    "scoring_latency_p50_ms": 1.0,
                    "scoring_latency_p95_ms": 2.0,
                    "assignment_latency_p50_ms": 0.1,
                    "assignment_latency_p95_ms": 0.2,
                }
            )
    selected = max(candidates, key=_validation_selection_key)
    best_by_route = {
        route: max(
            (item for item in candidates if item["route"] == route),
            key=_validation_selection_key,
        )
        for route in ("learned", "hybrid")
    }
    return {
        "selection_basis": [],
        "fixed_probability_threshold_candidates": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        "hybrid_weights": {"geometry": 0.4, "learned": 0.6},
        "cost_contract": "negative_log_effective_probability_v2",
        "probability_calibration": {
            route: {
                "edge_count": 2,
                "positive_edge_count": 1,
                "negative_edge_count": 1,
                "brier_score": 0.1,
                "expected_calibration_error": 0.1,
                "bins": [],
            }
            for route in ("learned", "hybrid")
        },
        "route_status": {
            route: {"failed_closed": False, "reason": "validated"}
            for route in ("learned", "hybrid")
        },
        "selected_route": selected["route"],
        "selected_probability_threshold": selected["probability_threshold"],
        "selected_unmatched_cost": selected["unmatched_cost"],
        "best_by_route": best_by_route,
        "candidates": candidates,
    }


def test_five_initializations_freeze_one_without_test_access(tmp_path, monkeypatch) -> None:
    dataset_manifest = _formal_manifest(tmp_path / "dataset_manifest.json")
    graph, labels = _tiny_graph()
    accessed = []

    def load_split(_manifest, _root, split):
        accessed.append(split)
        if split == "test":
            raise AssertionError("test split opened before freeze")
        return [(graph, labels)]

    monkeypatch.setattr(
        "dual_optical_100target_gnn.training._load_split",
        load_split,
    )
    model_state = BipartiteEdgeGNN(
        len(NODE_FEATURE_NAMES), len(EDGE_FEATURE_NAMES)
    ).state_dict()

    def fit(_train, _val, _normalizer, _config, initialization_seed, _device):
        index = list(CausalTrainingConfig().initialization_seeds).index(initialization_seed)
        base_f1 = 0.80 + (0.05 if index == 2 else index * 0.001)
        return (
            {key: value.clone() for key, value in model_state.items()},
            [{"epoch": 1, "train_loss": 1.0, "val_loss": 0.5}],
            _selection(base_f1),
            0.5,
            1.0,
            {
                "schema_version": "dual-optical-edge-sampling-evidence-v1",
                "positive_retention_ratio": 1.0,
            },
        )

    monkeypatch.setattr(
        "dual_optical_100target_gnn.training._fit_initialization",
        fit,
    )
    freeze_path = train_causal_ensemble_and_freeze(
        dataset_manifest,
        tmp_path / "frozen",
        config=CausalTrainingConfig(device="cpu"),
    )
    assert accessed == ["train", "val"]
    freeze, _ = verify_freeze_manifest(freeze_path)
    assert freeze["initialization_count"] == 5
    assert freeze["selected_initialization_index"] == 3
    assert freeze["test_accessed_before_freeze"] is False
    assert freeze["freeze_allowed"] is True
    assert freeze["promotion_allowed"] is False
    assert (
        freeze["promotion_status"]
        == "pending_reserved_test_same_input_comparison"
    )
    assert len(freeze["protocol_fingerprint_sha256"]) == 64
    assert len(freeze["train_input_fingerprint_sha256"]) == 64
    assert len(freeze["validation_input_fingerprint_sha256"]) == 64
    assert len(freeze["weights_sha256"]) == 64
    summary = json.loads(
        (freeze_path.parent / freeze["initialization_selection"]).read_text(
            encoding="utf-8"
        )
    )
    assert sum(item["checkpoint_retained"] for item in summary["candidates"]) == 1
    assert not list(freeze_path.parent.glob("initialization_*_weights.pt"))

    route = load_frozen_route(freeze_path)
    snapshot = RevolutionSnapshot(
        protocol_fingerprint=BenchmarkProtocol().fingerprint,
        seed=20261101,
        split="test",
        corruption_level="light",
        revolution_index=1,
        cutoff_timestamp=2.0,
        camera_ids=("Optical_A", "Optical_B"),
        camera_positions_ned={
            "Optical_A": (0.0, -1000.0, -100.0),
            "Optical_B": (0.0, 1000.0, -100.0),
        },
        focal_length_px=25000.0,
        tracks={"Optical_A": (), "Optical_B": ()},
    )
    publication = route.publish(snapshot)
    assert publication.route_name == "gnn"
    assert publication.input_fingerprint == snapshot_fingerprint(snapshot)
    assert publication.availability in {
        "empty_candidate_graph_gpu",
        "empty_candidate_graph_cpu_fallback",
    }
    assert publication.matches == ()
    assert publication.model_fingerprint == freeze["model_fingerprint_sha256"]

    detailed = OnlineGNNAssociator(str(freeze_path), device="cpu")
    monkeypatch.setattr(
        "dual_optical_100target_gnn.online.build_online_graph",
        lambda episode, summary, gate: (graph, {"candidate_edge_count": 1}),
    )
    monkeypatch.setattr(
        detailed,
        "_probabilities",
        lambda candidate_graph: (np.asarray([0.99], dtype=np.float32), 0.25),
    )
    first = detailed.associate(snapshot)
    assert first.publication.availability == "tentative_cpu_fallback"
    assert first.inference_backend == "cpu_fallback"
    assert first.cpu_inference_ms == 0.25
    assert first.gpu_inference_ms is None
    assert first.target_count == 100
    assert first.publication.matches == ()
    assert first.raw_matches[0].decision_state == "raw"
    assert first.tentative_matches == ()

    second_snapshot = RevolutionSnapshot(
        protocol_fingerprint=BenchmarkProtocol().fingerprint,
        seed=20261101,
        split="test",
        corruption_level="light",
        revolution_index=2,
        cutoff_timestamp=4.0,
        camera_ids=snapshot.camera_ids,
        camera_positions_ned=snapshot.camera_positions_ned,
        focal_length_px=snapshot.focal_length_px,
        tracks=snapshot.tracks,
    )
    second = detailed.associate(second_snapshot)
    assert second.publication.matches == ()
    assert second.tentative_matches[0].decision_state == "tentative"
    assert second.confirmed_matches == ()

    third_snapshot = RevolutionSnapshot(
        protocol_fingerprint=BenchmarkProtocol().fingerprint,
        seed=20261101,
        split="test",
        corruption_level="light",
        revolution_index=3,
        cutoff_timestamp=6.0,
        camera_ids=snapshot.camera_ids,
        camera_positions_ned=snapshot.camera_positions_ned,
        focal_length_px=snapshot.focal_length_px,
        tracks=snapshot.tracks,
        target_count=100,
    )
    third = detailed.associate(third_snapshot)
    assert third.target_count == 100
    assert third.publication.matches[0].decision_state == "confirmed"
    assert third.confirmed_matches[0].decision_state == "confirmed"

    mismatched_scale = RevolutionSnapshot(
        protocol_fingerprint=BenchmarkProtocol().fingerprint,
        seed=20261102,
        split="test",
        corruption_level="light",
        revolution_index=1,
        cutoff_timestamp=2.0,
        camera_ids=snapshot.camera_ids,
        camera_positions_ned=snapshot.camera_positions_ned,
        focal_length_px=snapshot.focal_length_px,
        tracks=snapshot.tracks,
        target_count=40,
    )
    with pytest.raises(ValueError, match="target_count does not match"):
        detailed.associate(mismatched_scale)


def test_all_failed_initializations_write_structured_failure(
    tmp_path, monkeypatch
) -> None:
    dataset_manifest = _formal_manifest(tmp_path / "dataset_manifest.json")
    graph, labels = _tiny_graph()
    monkeypatch.setattr(
        "dual_optical_100target_gnn.training._load_split",
        lambda _manifest, _root, _split: [(graph, labels)],
    )
    model_state = BipartiteEdgeGNN(
        len(NODE_FEATURE_NAMES), len(EDGE_FEATURE_NAMES)
    ).state_dict()

    def fit(_train, _val, _normalizer, _config, _seed, _device):
        selection = _selection(0.0)
        selection.update(
            {
                "freeze_allowed": False,
                "promotion_allowed": False,
                "promotion_status": "validation_failed_closed",
                "validation_failed_closed": True,
                "validation_failure_reasons": [
                    "all_routes_failed_validation_hard_gates"
                ],
            }
        )
        return (
            {key: value.clone() for key, value in model_state.items()},
            [{"epoch": 1, "train_loss": 1.0, "val_loss": 1.0}],
            selection,
            1.0,
            1.0,
            {
                "schema_version": "dual-optical-edge-sampling-evidence-v1",
                "positive_retention_ratio": 1.0,
            },
        )

    monkeypatch.setattr(
        "dual_optical_100target_gnn.training._fit_initialization",
        fit,
    )
    output_dir = tmp_path / "failed"
    with pytest.raises(ValueError, match="validation failed closed"):
        train_causal_ensemble_and_freeze(
            dataset_manifest,
            output_dir,
            config=CausalTrainingConfig(device="cpu"),
        )

    failure = json.loads(
        (output_dir / "freeze_failure.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (output_dir / failure["validation_evidence"]).read_text(
            encoding="utf-8"
        )
    )
    assert failure["status"] == "failed_closed"
    assert failure["freeze_allowed"] is False
    assert failure["promotion_allowed"] is False
    assert failure["promotion_status"] == "validation_failed_closed"
    assert evidence["freeze_allowed"] is False
    assert evidence["promotion_allowed"] is False
    assert evidence["promotion_status"] == "validation_failed_closed"
    assert not (output_dir / "freeze_manifest.json").exists()


def test_freeze_route_public_wrapper(monkeypatch, tmp_path) -> None:
    expected = tmp_path / "freeze_manifest.json"
    monkeypatch.setattr(
        "dual_optical_100target_gnn.online_benchmark.train_causal_ensemble_and_freeze",
        lambda dataset_manifest, output_dir, *, config: expected,
    )
    assert freeze_route(tmp_path / "dataset.json", tmp_path / "frozen") == expected


def test_freeze_route_dispatches_main_calibration_manifest(
    monkeypatch, tmp_path
) -> None:
    manifest = tmp_path / "calibration_manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": "dual-optical-online-dataset-v1"}),
        encoding="utf-8",
    )
    prepared = object()
    expected = tmp_path / "frozen" / "freeze_manifest.json"
    monkeypatch.setattr(
        "dual_optical_100target_gnn.online_benchmark._prepare_shared_calibration",
        lambda path: prepared,
    )

    def train(path, output_dir, *, config, prepared=None):
        assert path == manifest.resolve()
        assert output_dir == tmp_path / "frozen"
        assert config.device == "auto"
        assert prepared is not None
        return expected

    monkeypatch.setattr(
        "dual_optical_100target_gnn.online_benchmark.train_causal_ensemble_and_freeze",
        train,
    )
    assert freeze_route(manifest, tmp_path / "frozen") == expected
