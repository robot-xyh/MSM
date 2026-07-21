from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np
import pytest
import torch

from d5_terminal_association.models import CameraModel, GlobalTrack
from d5_terminal_association.scalable_3d_adapter import (
    Scalable3DAdapterConfig,
    run_scalable_3d_online_association,
)
from d5_terminal_association.sparse_tracklet_graph import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CameraLocalTracklet,
    SparseCandidateEdge,
    SparseTrackletGraph,
    TrackletCameraGeometry,
)
from d5_terminal_association.tracklet_dataset import (
    DATASET_SCHEMA_VERSION,
    GRAPH_SCHEMA_VERSION,
    finalize_tracklet_dataset,
    load_tracklet_dataset,
    split_episode_groups,
    stage_tracklet_dataset_episode,
)
from d5_terminal_association.tracklet_gnn import (
    NativeTrackletEdgeClassifier,
    OfflineTrackletTruthLabel,
)
from d5_terminal_association.tracklet_model_bundle import (
    MODEL_BUNDLE_SCHEMA_VERSION,
    ModelBundleValidationError,
    load_tracklet_model_bundle,
    load_tracklet_model_bundle_for_runtime,
    write_tracklet_model_bundle,
)
from d5_terminal_association.tracklet_training import (
    TrackletTrainingConfig,
    evaluate_tracklet_edge_model,
    run_evaluation_pipeline,
    run_training_pipeline,
)
from d5_terminal_association.tracklet_training_audit import (
    assess_tracklet_model_promotion,
    run_tracklet_training_audit,
)


def _anonymous_graph(seed: int = 1) -> tuple[SparseTrackletGraph, tuple[OfflineTrackletTruthLabel, ...]]:
    nodes: list[CameraLocalTracklet] = []
    node_rows: list[np.ndarray] = []
    timestamp = 10.0 + seed * 0.001
    for camera_index in range(3):
        for local_index in range(2):
            center = np.array(
                [320.0 + 80.0 * local_index + 0.5 * camera_index, 240.0 + camera_index],
                dtype=float,
            )
            nodes.append(
                CameraLocalTracklet(
                    resource_id=f"RESOURCE-{camera_index}",
                    camera_id="CAM-0",
                    local_track_id=f"trk-{local_index:04d}",
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp + 0.01,
                    center_px=center,
                    covariance_px=np.eye(2, dtype=float),
                    bbox_xyxy=(center[0] - 5.0, center[1] - 4.0, center[0] + 5.0, center[1] + 4.0),
                    confidence=0.95,
                )
            )
            row = np.zeros(len(NODE_FEATURE_NAMES), dtype=np.float32)
            row[0] = center[0] / 640.0
            row[1] = center[1] / 480.0
            row[2] = np.log(80.0 / (640.0 * 480.0))
            row[3] = np.log(10.0 / 8.0)
            row[7] = 0.95
            row[8] = 2.0 / (640.0 * 480.0)
            row[9] = 0.5
            node_rows.append(row)

    edges: list[SparseCandidateEdge] = []
    edge_rows: list[np.ndarray] = []
    for source in range(len(nodes)):
        for target in range(source + 1, len(nodes)):
            if nodes[source].camera_key == nodes[target].camera_key:
                continue
            pixel_delta = float(np.linalg.norm(nodes[source].center_px - nodes[target].center_px))
            values = np.zeros(len(EDGE_FEATURE_NAMES), dtype=np.float32)
            values[0] = 0.0
            values[1] = pixel_delta / 10.0
            values[2] = pixel_delta / 20.0
            values[3] = pixel_delta / 5.0
            values[4] = 0.0
            values[7] = 100.0
            values[9] = pixel_delta / 20.0
            values[10] = 0.2
            values[11] = pixel_delta / 10.0
            values[12] = 0.95 * 0.95
            gate_score = float(values[1] + values[2] + values[9])
            edges.append(
                SparseCandidateEdge(
                    source_index=source,
                    target_index=target,
                    source_tracklet_key=nodes[source].tracklet_key,
                    target_tracklet_key=nodes[target].tracklet_key,
                    shared_global_track_ids=(),
                    feature_values=tuple(float(value) for value in values),
                    gate_score=gate_score,
                )
            )
            edge_rows.append(values)
    edge_index = np.asarray(
        [[edge.source_index for edge in edges], [edge.target_index for edge in edges]],
        dtype=np.int64,
    )
    graph = SparseTrackletGraph(
        nodes=tuple(nodes),
        node_features=np.asarray(node_rows, dtype=np.float32),
        edge_index=edge_index,
        edge_features=np.asarray(edge_rows, dtype=np.float32),
        edges=tuple(edges),
        candidate_counts={"candidate_tracklet_edges": len(edges)},
    )
    labels = tuple(
        OfflineTrackletTruthLabel(
            tracklet_key=node.tracklet_key,
            truth_entity_id=f"ENTITY-{node.local_track_id[-4:]}",
            measurement_timestamp=node.measurement_timestamp,
        )
        for node in nodes
    )
    return graph, labels


def _stage_dataset(root: Path, seeds: range = range(1, 6)) -> None:
    for seed in seeds:
        graph, labels = _anonymous_graph(seed)
        stage_tracklet_dataset_episode(
            root,
            graph,
            labels,
            scenario_version="synthetic-crossing-v1",
            seed=seed,
            episode_id="episode-a",
            generation_config={"candidate_graph": "geometry-gated", "max_neighbors": 8},
            labels_complete=True,
            candidate_recall_available=True,
        )
    finalize_tracklet_dataset(root, split_seed=77)


def _write_bundle(root: Path) -> NativeTrackletEdgeClassifier:
    torch.manual_seed(7)
    model = NativeTrackletEdgeClassifier(hidden_dim=8, message_passing_steps=1)
    write_tracklet_model_bundle(
        root,
        model,
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        training_config_sha256="d" * 64,
        calibration_temperature=1.0,
        decision_threshold=0.6,
        validation_results={"f1": {"available": True, "value": 0.8}},
    )
    return model


def _rewrite_manifest_checksum(
    bundle: Path,
    update: Callable[[dict[str, Any]], None],
) -> None:
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    update(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    weights_sha = hashlib.sha256((bundle / "weights.pt").read_bytes()).hexdigest()
    (bundle / "SHA256SUMS").write_text(
        f"{manifest_sha}  manifest.json\n{weights_sha}  weights.pt\n",
        encoding="ascii",
    )


def test_whole_scenario_seed_groups_never_leak_across_splits(tmp_path: Path) -> None:
    for seed in range(1, 7):
        graph, labels = _anonymous_graph(seed)
        for scenario in ("scenario-small-v3", "scenario-large-v3"):
            stage_tracklet_dataset_episode(
                tmp_path,
                graph,
                labels,
                scenario_version=scenario,
                seed=seed,
                episode_id="episode-a",
                generation_config={"graph": "v1"},
                labels_complete=True,
            )
        if seed == 1:
            stage_tracklet_dataset_episode(
                tmp_path,
                graph,
                labels,
                scenario_version="scenario-small-v3",
                seed=seed,
                episode_id="episode-b",
                generation_config={"graph": "v1"},
                labels_complete=True,
            )
    manifest = finalize_tracklet_dataset(tmp_path, split_seed=19)
    dataset = load_tracklet_dataset(tmp_path)

    group_splits: dict[tuple[str, int], set[str]] = {}
    seed_splits: dict[int, set[str]] = {}
    for episode in dataset.episodes:
        key = (episode.graph.scenario_version, episode.graph.seed)
        group_splits.setdefault(key, set()).add(episode.split)
        seed_splits.setdefault(episode.graph.seed, set()).add(episode.split)
    assert all(len(splits) == 1 for splits in group_splits.values())
    assert all(len(splits) == 1 for splits in seed_splits.values())
    assert {episode.split for episode in dataset.episodes} == {"train", "validation", "test"}
    seeds_by_split = {
        split: {
            episode.graph.seed for episode in dataset.episodes if episode.split == split
        }
        for split in ("train", "validation", "test")
    }
    assert seeds_by_split["test"].isdisjoint(seeds_by_split["train"])
    assert seeds_by_split["test"].isdisjoint(seeds_by_split["validation"])
    assert manifest["split_policy"]["edge_level_random_split"] is False
    assert manifest["split_policy"]["shared_seed_values_atomic_across_scenarios"] is True
    assert manifest["split_policy"]["unit"] == "whole_episode_grouped_by_scenario_version_and_seed"
    assert manifest["schema_version"] == "d5.tracklet-dataset.v2"


def test_tracklet_split_is_deterministic_and_requires_three_unique_seeds() -> None:
    descriptors = [
        {
            "scenario_version": scenario,
            "seed": seed,
            "episode_uid": f"episode-{scenario}-{seed}",
        }
        for seed in range(8)
        for scenario in ("scale-small-v1", "scale-large-v1")
    ]
    forward = split_episode_groups(
        descriptors,
        split_seed=31,
        validation_fraction=0.2,
        test_fraction=0.2,
    )
    reversed_input = split_episode_groups(
        list(reversed(descriptors)),
        split_seed=31,
        validation_fraction=0.2,
        test_fraction=0.2,
    )
    assert dict(forward) == dict(reversed_input)

    with pytest.raises(ValueError, match="at least three unique seed values"):
        split_episode_groups(
            [item for item in descriptors if item["seed"] < 2],
            split_seed=31,
            validation_fraction=0.2,
            test_fraction=0.2,
        )


def test_online_graph_and_evaluator_truth_are_physically_separate(tmp_path: Path) -> None:
    graph, labels = _anonymous_graph(3)
    descriptor = stage_tracklet_dataset_episode(
        tmp_path,
        graph,
        labels,
        scenario_version="scenario-v1",
        seed=3,
        episode_id="episode-a",
        generation_config={"graph": "v1"},
        labels_complete=True,
        candidate_recall_available=True,
    )
    graph_path = tmp_path / descriptor["graph_file"]
    labels_path = tmp_path / descriptor["labels_file"]

    with np.load(graph_path, allow_pickle=False) as archive:
        assert all("truth" not in name.lower() for name in archive.files)
        assert "shared_global_track_ids" not in archive.files
        assert tuple(archive["node_feature_names"].tolist()) == NODE_FEATURE_NAMES
        assert tuple(archive["edge_feature_names"].tolist()) == EDGE_FEATURE_NAMES
    graph_bytes = graph_path.read_bytes()
    assert b"truth_entity_id" not in graph_bytes
    assert b"ENTITY-" not in graph_bytes
    label_text = labels_path.read_text(encoding="utf-8")
    assert "truth_entity_id" in label_text
    assert "ENTITY-" in label_text


def test_formal_training_bundle_round_trip_and_evaluation_cli_api(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    bundle_dir = tmp_path / "bundle"
    report_path = tmp_path / "training-report.json"
    evaluation_path = tmp_path / "evaluation-report.json"
    _stage_dataset(dataset_dir)

    report = run_training_pipeline(
        dataset_dir,
        bundle_dir,
        report_path,
        config=TrackletTrainingConfig(
            seed=11,
            epochs=2,
            learning_rate=0.005,
            hidden_dim=8,
            message_passing_steps=1,
            graphs_per_optimizer_step=2,
            latency_repeats=1,
        ),
    )
    dataset = load_tracklet_dataset(dataset_dir)
    scorer = load_tracklet_model_bundle(
        bundle_dir,
        expected_dataset_manifest_sha256=dataset.manifest_sha256,
        expected_split_sha256=dataset.manifest["split_sha256"],
        expected_training_set_sha256=dataset.manifest["training_set_sha256"],
    )
    evaluation = run_evaluation_pipeline(
        dataset_dir,
        bundle_dir,
        evaluation_path,
        latency_repeats=1,
    )

    assert report["admission_status"] == "research_candidate_not_default"
    assert scorer.manifest["admission"]["default_model"] is False
    assert scorer.manifest["schema_version"] == MODEL_BUNDLE_SCHEMA_VERSION
    assert scorer.manifest["dataset_schema_version"] == DATASET_SCHEMA_VERSION
    assert scorer.manifest["graph_schema_version"] == GRAPH_SCHEMA_VERSION
    assert scorer.manifest["calibration"]["source_split"] == "validation"
    assert report["test"]["metrics"]["model_size"]["available"] is True
    assert set(report["test"]["metrics"]) >= {
        "precision",
        "recall",
        "f1",
        "false_merge_rate",
        "candidate_recall",
        "brier_score",
        "ece",
        "p50_inference_latency_ms",
        "p95_inference_latency_ms",
        "model_size",
    }
    assert evaluation["evaluation"]["split"] == "test"
    assert report_path.is_file() and evaluation_path.is_file()
    assert (bundle_dir / "manifest.json").is_file()
    assert (bundle_dir / "weights.pt").is_file()
    assert (bundle_dir / "SHA256SUMS").is_file()


def test_readiness_audit_fails_closed_on_insufficient_class_support(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    output_dir = tmp_path / "audit"
    for seed in range(1, 11):
        graph, labels = _anonymous_graph(seed)
        stage_tracklet_dataset_episode(
            dataset_dir,
            graph,
            labels,
            scenario_version="synthetic-crossing-5v5-v1",
            seed=seed,
            episode_id="episode-a",
            generation_config={"candidate_graph": "geometry-gated"},
            labels_complete=True,
            candidate_recall_available=True,
        )
    finalize_tracklet_dataset(dataset_dir, split_seed=77)

    report, json_path, markdown_path, audit_sha256 = run_tracklet_training_audit(
        dataset_dir,
        output_dir,
    )

    assert report["dataset"]["validated_graph_sha256_count"] == 10
    assert report["split_integrity"]["whole_seed_atomic"] is True
    assert report["split_integrity"]["reserved_evaluation_seed_overlap"]["train"] == []
    assert report["training_readiness"]["status"] == "fail_closed"
    assert report["development_training"]["status"] == "allowed_not_admissible"
    assert report["promotion_readiness"]["g1_assist_eligible"] is False
    assert any(
        name.endswith("negative_edge_support")
        for name in report["training_readiness"]["failed_gates"]
    )
    assert json_path.is_file() and markdown_path.is_file()
    assert len(audit_sha256) == 64


def test_partial_label_training_is_development_only_and_audit_bound(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    for seed in range(1, 11):
        graph, labels = _anonymous_graph(seed)
        stage_tracklet_dataset_episode(
            dataset_dir,
            graph,
            labels,
            scenario_version="synthetic-crossing-5v5-v1",
            seed=seed,
            episode_id="episode-a",
            generation_config={"candidate_graph": "geometry-gated"},
            labels_complete=False,
            candidate_recall_available=False,
        )
    finalize_tracklet_dataset(dataset_dir, split_seed=77)
    audit, _, _, audit_sha256 = run_tracklet_training_audit(
        dataset_dir,
        tmp_path / "audit",
    )
    config = TrackletTrainingConfig(
        seed=29,
        epochs=1,
        hidden_dim=8,
        message_passing_steps=1,
        latency_repeats=1,
    )

    with pytest.raises(ValueError, match="formal calibration requires complete validation truth"):
        run_training_pipeline(
            dataset_dir,
            tmp_path / "formal-bundle",
            tmp_path / "formal-report.json",
            config=config,
        )

    report = run_training_pipeline(
        dataset_dir,
        tmp_path / "development-bundle",
        tmp_path / "development-report.json",
        config=config,
        development_only=True,
        readiness_audit_sha256=audit_sha256,
    )
    scorer = load_tracklet_model_bundle(
        tmp_path / "development-bundle",
        expected_readiness_audit_sha256=audit_sha256,
    )
    promotion = assess_tracklet_model_promotion(audit, report)

    assert report["admission_status"] == "development_only_fail_closed"
    assert report["g1_assist_eligible"] is False
    assert report["test"]["truth_scope"] == "labeled_candidate_edges_only"
    assert report["test"]["metrics"]["precision"]["available"] is True
    assert report["test"]["metrics"]["false_merge_rate"] == {
        "available": False,
        "value": None,
        "reason": "incomplete_graph_truth",
    }
    assert scorer.manifest["admission"] == {
        "status": "development_only_fail_closed",
        "default_model": False,
        "g1_assist_eligible": False,
        "readiness_audit_sha256": audit_sha256,
    }
    assert scorer.manifest["code_provenance"]["implementation_sha256"] == report[
        "bundle"
    ]["implementation_sha256"]
    assert promotion["status"] == "fail_closed"
    assert promotion["g1_assist_eligible"] is False


def test_checkpoint_round_trip_preserves_calibrated_probabilities(tmp_path: Path) -> None:
    graph, _ = _anonymous_graph()
    model = _write_bundle(tmp_path)
    model.eval()
    expected = model.forward_graph(graph).detach().cpu().numpy()
    scorer = load_tracklet_model_bundle(tmp_path)
    actual = scorer.forward_graph(graph).detach().cpu().numpy()

    np.testing.assert_allclose(actual, expected, rtol=1.0e-6, atol=1.0e-7)
    assert scorer.decision_threshold == pytest.approx(0.6)


@pytest.mark.parametrize(
    ("update", "error_code"),
    [
        (
            lambda manifest: manifest.__setitem__("dataset_schema_version", "wrong-v9"),
            "dataset_schema_mismatch",
        ),
        (lambda manifest: manifest.__setitem__("graph_schema_version", "wrong-v9"), "graph_schema_mismatch"),
        (lambda manifest: manifest.__setitem__("model_semantic_version", "9.0.0"), "model_semantic_version_mismatch"),
        (
            lambda manifest: manifest.__setitem__(
                "node_feature_names", list(reversed(manifest["node_feature_names"]))
            ),
            "node_feature_order_mismatch",
        ),
        (lambda manifest: manifest.__setitem__("edge_feature_version", "wrong-v9"), "edge_feature_version_mismatch"),
    ],
)
def test_bundle_feature_and_version_mismatches_fail_closed(
    tmp_path: Path,
    update: Callable[[dict[str, Any]], None],
    error_code: str,
) -> None:
    _write_bundle(tmp_path)
    _rewrite_manifest_checksum(tmp_path, update)

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(tmp_path)
    assert exc_info.value.code == error_code


def test_bundle_sha_corruption_fails_closed_and_runtime_wrapper_stays_unavailable(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    weights = tmp_path / "weights.pt"
    weights.write_bytes(weights.read_bytes() + b"corruption")

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(tmp_path)
    assert exc_info.value.code == "weights_sha_mismatch"
    runtime = load_tracklet_model_bundle_for_runtime(tmp_path)
    assert runtime.available is False
    assert runtime.failure_reason == "bundle_weights_sha_mismatch"


def test_incomplete_truth_metrics_are_unavailable_not_zero(tmp_path: Path) -> None:
    for seed in range(1, 4):
        graph, labels = _anonymous_graph(seed)
        stage_tracklet_dataset_episode(
            tmp_path,
            graph,
            labels[:-1],
            scenario_version="incomplete-v1",
            seed=seed,
            episode_id="episode-a",
            generation_config={"graph": "v1"},
            labels_complete=False,
            candidate_recall_available=False,
        )
    finalize_tracklet_dataset(tmp_path, split_seed=3)
    dataset = load_tracklet_dataset(tmp_path)
    result = evaluate_tracklet_edge_model(
        dataset,
        NativeTrackletEdgeClassifier(hidden_dim=8, message_passing_steps=1),
        split="test",
        temperature=1.0,
        decision_threshold=0.5,
        latency_repeats=1,
    )

    for name in ("precision", "recall", "f1", "false_merge_rate", "candidate_recall", "brier_score", "ece"):
        assert result["metrics"][name] == {
            "available": False,
            "value": None,
            "reason": "incomplete_evaluator_truth",
        }


K = np.array([[540.0, 0.0, 640.0], [0.0, 540.0, 360.0], [0.0, 0.0, 1.0]])
R_CAMERA_FROM_NED = np.array(
    [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]],
    dtype=float,
)
TARGET_POINT = np.array([1000.0, 0.0, 0.0])


def _online_inputs() -> tuple[list[CameraLocalTracklet], list[TrackletCameraGeometry], list[GlobalTrack]]:
    tracklets: list[CameraLocalTracklet] = []
    geometries: list[TrackletCameraGeometry] = []
    for index, east in enumerate((-5.0, 5.0, 15.0)):
        center_ned = np.array([0.0, east, -20.0])
        camera = CameraModel(
            K=K,
            R=R_CAMERA_FROM_NED,
            t=-R_CAMERA_FROM_NED @ center_ned,
            image_size=(1280, 720),
            measurement_cov=np.eye(2),
        )
        geometry = TrackletCameraGeometry(
            resource_id=f"RESOURCE-{index}",
            camera_id="CAM-0",
            camera=camera,
            measurement_timestamp=10.0,
            position_covariance_ned=np.eye(3) * 0.04,
            attitude_covariance_rad2=np.eye(3) * np.deg2rad(0.05) ** 2,
        )
        camera_point = camera.R @ TARGET_POINT + camera.t
        pixel = np.array(
            [
                K[0, 0] * camera_point[0] / camera_point[2] + K[0, 2],
                K[1, 1] * camera_point[1] / camera_point[2] + K[1, 2],
            ]
        )
        geometries.append(geometry)
        tracklets.append(
            CameraLocalTracklet(
                resource_id=geometry.resource_id,
                camera_id=geometry.camera_id,
                local_track_id="trk-0001",
                measurement_timestamp=10.0,
                arrival_timestamp=10.01,
                center_px=pixel,
                covariance_px=np.eye(2),
                bbox_xyxy=(pixel[0] - 8.0, pixel[1] - 6.0, pixel[0] + 8.0, pixel[1] + 6.0),
                confidence=0.95,
            )
        )
    center_tracks = [
        GlobalTrack(
            global_track_id="GT-CENTER-0001",
            position=TARGET_POINT,
            covariance=np.eye(3) * 4.0,
            timestamp=10.0,
        )
    ]
    return tracklets, geometries, center_tracks


def test_non_finite_timeout_and_missing_models_use_geometry_fallback(tmp_path: Path) -> None:
    tracklets, geometries, center_tracks = _online_inputs()

    missing = run_scalable_3d_online_association(tracklets, geometries, center_tracks)

    class NonFiniteModel:
        def forward_graph(self, graph: SparseTrackletGraph) -> np.ndarray:
            return np.full(graph.edge_count, np.nan)

    non_finite = run_scalable_3d_online_association(
        tracklets,
        geometries,
        center_tracks,
        edge_model=NonFiniteModel(),
    )

    class SlowModel:
        def forward_graph(self, graph: SparseTrackletGraph) -> np.ndarray:
            time.sleep(0.005)
            return np.full(graph.edge_count, 0.99)

    timed_out = run_scalable_3d_online_association(
        tracklets,
        geometries,
        center_tracks,
        config=Scalable3DAdapterConfig(model_inference_timeout_ms=0.1),
        edge_model=SlowModel(),
    )
    unavailable = run_scalable_3d_online_association(
        tracklets,
        geometries,
        center_tracks,
        edge_model=load_tracklet_model_bundle_for_runtime(tmp_path / "missing-bundle"),
    )

    assert missing.scoring_status == "rule_fallback_model_missing"
    assert non_finite.scoring_status == "rule_fallback_model_invalid_output"
    assert non_finite.fallback_reason == "model_output_non_finite"
    assert timed_out.scoring_status == "rule_fallback_model_timeout"
    assert timed_out.fallback_reason == "model_inference_timeout"
    assert unavailable.scoring_status == "rule_fallback_model_unavailable"
    assert unavailable.fallback_reason == "bundle_missing"
    assert missing.probability_source == non_finite.probability_source == "deterministic_geometry_rule"


def test_loaded_edge_probabilities_keep_constrained_clusters_and_center_ids_unchanged() -> None:
    tracklets, geometries, center_tracks = _online_inputs()
    center_ids_before = tuple(track.global_track_id for track in center_tracks)

    class ConfidentEdgeModel:
        decision_threshold = 0.8

        def forward_graph(self, graph: SparseTrackletGraph) -> np.ndarray:
            return np.full(graph.edge_count, 0.99)

    result = run_scalable_3d_online_association(
        tracklets,
        geometries,
        center_tracks,
        edge_model=ConfidentEdgeModel(),
    )

    assert result.scoring_status == "model_scored"
    assert result.diagnostics["edge_probability_threshold"] == pytest.approx(0.8)
    assert all(len(cluster.camera_keys) == len(set(cluster.camera_keys)) for cluster in result.clusters)
    output_ids = {binding.global_track_id for binding in result.bindings if binding.global_track_id}
    assert output_ids.issubset(set(center_ids_before))
    assert tuple(track.global_track_id for track in center_tracks) == center_ids_before
