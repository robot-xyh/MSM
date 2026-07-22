from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import pytest

import d5_terminal_association.tracklet_composite_training as composite
from d5_terminal_association.sparse_tracklet_graph import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
)
from d5_terminal_association.tracklet_dataset import (
    LoadedEvaluatorLabels,
    LoadedTrackletDataset,
    LoadedTrackletEpisode,
    LoadedTrackletGraph,
)
from d5_terminal_association.tracklet_gnn import OfflineTrackletTruthLabel
from d5_terminal_association.tracklet_supplemental_admission import (
    LoadedTrackletCompositeAdmission,
)
from d5_terminal_association.tracklet_supplemental_curriculum import (
    FORMAL_SCENARIO_CELLS,
)


@pytest.fixture(scope="module")
def valid_dataset() -> tuple[LoadedTrackletDataset, dict[int, str]]:
    assignment = _assignment()
    episodes = [
        _episode(seed, split, *FORMAL_SCENARIO_CELLS[0])
        for seed, split in assignment.items()
    ]
    representative_seed = {"train": 0, "validation": 60, "test": 80}
    for split, seed in representative_seed.items():
        episodes.extend(
            _episode(seed, split, scenario, scale)
            for scenario, scale in FORMAL_SCENARIO_CELLS[1:]
        )
    return _dataset(tuple(episodes)), assignment


def test_minimal_complete_composite_preflight_passes_without_model_artifacts(
    valid_dataset: tuple[LoadedTrackletDataset, dict[int, str]],
    tmp_path: Path,
) -> None:
    dataset, assignment = valid_dataset
    corpus = _corpus(dataset, assignment, tmp_path)

    report = composite.build_composite_training_preflight(
        corpus,
        implementation_git_commit="a" * 40,
        implementation_repository_dirty=True,
    )

    assert report["status"] == "ready_for_clean_internal_training"
    assert report["corpus_audit"]["seed_count_by_split"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert report["corpus_audit"]["scenario_scale_cell_count_by_split"] == {
        "train": 45,
        "validation": 45,
        "test": 45,
    }
    assert report["model_artifacts"] == {
        "model_training_performed": False,
        "pt_generated": False,
        "weights_sha256": None,
    }
    assert report["layers"]["g1_assist"]["authority_enabled"] is False


def test_admission_report_hash_and_view_binding_fail_closed(
    valid_dataset: tuple[LoadedTrackletDataset, dict[int, str]],
    tmp_path: Path,
) -> None:
    dataset, assignment = valid_dataset
    corpus = _corpus(dataset, assignment, tmp_path)
    expected = dict(corpus.admission.readiness)
    expected["view_manifest_sha256"] = corpus.admission.view_manifest_sha256
    expected["view_content_sha256"] = corpus.admission.view_manifest["content_sha256"]
    expected["content_sha256"] = composite._sha256_json(expected)
    report_path = tmp_path / "admission.json"
    _write_json(report_path, expected)
    assert composite._load_bound_admission_report(
        report_path, corpus.admission
    )["content_sha256"] == expected["content_sha256"]

    broken_hash = json.loads(json.dumps(expected))
    broken_hash["sources"]["formal_manifest_sha256"] = "f" * 64
    _write_json(report_path, broken_hash)
    with pytest.raises(composite.CompositeInternalTrainingError) as error:
        composite._load_bound_admission_report(report_path, corpus.admission)
    assert error.value.code == "admission_report_content_hash_mismatch"

    broken_hash["content_sha256"] = composite._sha256_json(
        {key: value for key, value in broken_hash.items() if key != "content_sha256"}
    )
    _write_json(report_path, broken_hash)
    with pytest.raises(composite.CompositeInternalTrainingError) as error:
        composite._load_bound_admission_report(report_path, corpus.admission)
    assert error.value.code == "admission_report_view_mismatch"


def test_reserved_seed_leakage_fails_closed() -> None:
    assignment = _assignment(reserved_last=True)
    episodes = [
        _episode(seed, split, *FORMAL_SCENARIO_CELLS[0])
        for seed, split in assignment.items()
    ]
    dataset = _dataset(tuple(episodes))
    with pytest.raises(composite.CompositeInternalTrainingError) as error:
        composite.audit_composite_training_dataset(
            dataset,
            expected_seed_assignment=assignment,
            expected_scenario_cells=(FORMAL_SCENARIO_CELLS[0],),
            reserved_evaluation_seeds=composite.RESERVED_EVALUATION_SEEDS,
        )
    assert error.value.code == "reserved_seed_leakage"


def test_registry_split_binding_fails_closed(
    valid_dataset: tuple[LoadedTrackletDataset, dict[int, str]],
) -> None:
    dataset, assignment = valid_dataset
    broken = dict(assignment)
    broken[0] = "validation"
    with pytest.raises(composite.CompositeInternalTrainingError) as error:
        composite.audit_composite_training_dataset(
            dataset,
            expected_seed_assignment=broken,
            expected_scenario_cells=FORMAL_SCENARIO_CELLS,
            reserved_evaluation_seeds=composite.RESERVED_EVALUATION_SEEDS,
        )
    assert error.value.code == "seed_split_leakage"


def test_same_camera_candidate_edge_fails_closed(
    valid_dataset: tuple[LoadedTrackletDataset, dict[int, str]],
) -> None:
    dataset, assignment = valid_dataset
    first = dataset.episodes[0]
    graph = replace(
        first.graph,
        camera_keys=(first.graph.camera_keys[0], first.graph.camera_keys[0], "RESOURCE-2/CAM-0"),
    )
    episodes = (replace(first, graph=graph), *dataset.episodes[1:])
    with pytest.raises(composite.CompositeInternalTrainingError) as error:
        composite.audit_composite_training_dataset(
            _dataset(episodes),
            expected_seed_assignment=assignment,
            expected_scenario_cells=FORMAL_SCENARIO_CELLS,
            reserved_evaluation_seeds=composite.RESERVED_EVALUATION_SEEDS,
        )
    assert error.value.code == "same_camera_candidate_edge"


def test_unlabeled_candidate_edge_fails_closed(
    valid_dataset: tuple[LoadedTrackletDataset, dict[int, str]],
) -> None:
    dataset, assignment = valid_dataset
    first = dataset.episodes[0]
    class_balance = dict(first.class_balance)
    class_balance["unlabeled_candidate_edges"] = 1
    episodes = (replace(first, class_balance=class_balance), *dataset.episodes[1:])
    with pytest.raises(composite.CompositeInternalTrainingError) as error:
        composite.audit_composite_training_dataset(
            _dataset(episodes),
            expected_seed_assignment=assignment,
            expected_scenario_cells=FORMAL_SCENARIO_CELLS,
            reserved_evaluation_seeds=composite.RESERVED_EVALUATION_SEEDS,
        )
    assert error.value.code == "label_completeness_failure"


def test_passing_internal_metrics_do_not_open_later_authority_layers() -> None:
    metrics = {
        "precision": _available(0.99),
        "recall": _available(0.98),
        "f1": _available(0.985),
        "false_merge_rate": _available(0.005),
        "candidate_recall": _available(0.99),
        "ece": _available(0.02),
        "p95_inference_latency_ms": _available(10.0),
    }
    internal = composite.assess_internal_model_test(
        metrics,
        same_camera_mutual_exclusion_preserved=True,
        audited_scenario_cell_count=45,
    )
    layers = composite._trained_layers(internal, smoke=False)

    assert internal["passed"] is True
    assert layers["held_out_1000_1019"]["status"] == "not_run"
    assert layers["paired_shadow"]["status"] == "not_run"
    assert layers["g1_assist"]["status"] == "fail_closed"
    assert layers["g1_assist"]["eligible"] is False
    assert layers["g1_assist"]["authority_enabled"] is False


def test_d6_model_evaluation_export_matches_exact_three_artifact_contract(
    tmp_path: Path,
) -> None:
    training_report, cells, bundle = _model_evidence_fixture(tmp_path)

    report = composite.build_d6_model_evaluation_report(
        training_report,
        cells,
        bundle_dir=bundle,
    )

    assert set(report) == {
        "schema_version",
        "content_sha256",
        "evaluation_date",
        "model_id",
        "weights_sha256",
        "config_sha256",
        "training_source_sha256",
        "test_seed_values",
        "test_metrics",
        "cell_metrics",
        "latency",
    }
    assert report["schema_version"] == composite.D6_MODEL_EVALUATION_SCHEMA_VERSION
    assert report["weights_sha256"] == composite.sha256_file(bundle / "weights.pt")
    assert report["config_sha256"] == composite.sha256_file(bundle / "manifest.json")
    unhashed = {key: value for key, value in report.items() if key != "content_sha256"}
    assert report["content_sha256"] == composite._sha256_json(unhashed)
    assert len(report["cell_metrics"]) == 45
    assert all(item["sample_count"] == 17 for item in report["cell_metrics"])
    assert not ({"g1_allowed", "assist_allowed", "authority_allowed"} & set(report))


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("weight_hash", "model_weight_hash_mismatch"),
        ("unavailable_metric", "model_metric_unavailable"),
        ("missing_cell", "model_cell_catalog_mismatch"),
        ("reserved_seed", "test_seed_partition_invalid"),
    ],
)
def test_d6_model_evaluation_export_fails_closed(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    training_report, cells, bundle = _model_evidence_fixture(tmp_path)
    if mutation == "weight_hash":
        training_report["bundle"]["weights_sha256"] = "0" * 64
    elif mutation == "unavailable_metric":
        training_report["test"]["metrics"]["f1"] = {
            "available": False,
            "value": None,
            "reason": "test_mutation",
        }
    elif mutation == "missing_cell":
        cells.pop()
    else:
        training_report["dataset"]["test_seed_values"][-1] = 1000

    with pytest.raises(composite.CompositeInternalTrainingError) as error:
        composite.build_d6_model_evaluation_report(
            training_report,
            cells,
            bundle_dir=bundle,
        )
    assert error.value.code == expected_code


def _assignment(*, reserved_last: bool = False) -> dict[int, str]:
    seeds = list(range(100))
    if reserved_last:
        seeds[-1] = 1000
    return {
        seed: "train" if index < 60 else "validation" if index < 80 else "test"
        for index, seed in enumerate(seeds)
    }


def _episode(
    seed: int,
    split: str,
    scenario: str,
    scale: int,
) -> LoadedTrackletEpisode:
    suffix = f"{seed}-{scenario}-{scale}"
    tracklet_keys = tuple(f"RESOURCE-{index}/CAM-0/trk-{suffix}-{index}" for index in range(3))
    camera_keys = tuple(f"RESOURCE-{index}/CAM-0" for index in range(3))
    timestamp = float(seed) + 0.1
    graph = LoadedTrackletGraph(
        episode_uid=f"episode-{suffix}",
        scenario_version=f"{scenario}-{scale}v{scale}-v1",
        seed=seed,
        episode_id=f"frame-{suffix}",
        node_features=np.zeros((3, len(NODE_FEATURE_NAMES)), dtype=np.float32),
        edge_index=np.asarray([[0, 0], [1, 2]], dtype=np.int64),
        edge_features=np.zeros((2, len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        tracklet_keys=tracklet_keys,
        camera_keys=camera_keys,
        measurement_timestamps=np.full(3, timestamp, dtype=np.float64),
        arrival_timestamps=np.full(3, timestamp + 0.01, dtype=np.float64),
        gate_scores=np.asarray([0.1, 0.2], dtype=np.float64),
        candidate_counts={"candidate_tracklet_edges": 2},
    )
    labels = LoadedEvaluatorLabels(
        episode_uid=graph.episode_uid,
        labels=(
            OfflineTrackletTruthLabel(tracklet_keys[0], "TARGET-A", timestamp),
            OfflineTrackletTruthLabel(tracklet_keys[1], "TARGET-A", timestamp),
            OfflineTrackletTruthLabel(tracklet_keys[2], "TARGET-B", timestamp),
        ),
        labels_complete=True,
        candidate_recall_available=True,
    )
    return LoadedTrackletEpisode(
        graph=graph,
        evaluator_labels=labels,
        split=split,
        graph_sha256="1" * 64,
        labels_sha256="2" * 64,
        class_balance={
            "positive_candidate_edges": 1,
            "negative_candidate_edges": 1,
            "unlabeled_candidate_edges": 0,
        },
        hard_negative_provenance={"source": "test_geometry_gate"},
    )


def _dataset(episodes: tuple[LoadedTrackletEpisode, ...]) -> LoadedTrackletDataset:
    manifest = MappingProxyType(
        {
            "config_sha256": "3" * 64,
            "split_sha256": "4" * 64,
            "training_set_sha256": "5" * 64,
        }
    )
    return LoadedTrackletDataset(
        root=Path("/detached/composite-view"),
        manifest=manifest,
        manifest_sha256="6" * 64,
        episodes=tuple(episodes),
    )


def _corpus(
    dataset: LoadedTrackletDataset,
    assignment: dict[int, str],
    root: Path,
) -> composite.LoadedCompositeTrainingCorpus:
    audit = composite.audit_composite_training_dataset(
        dataset,
        expected_seed_assignment=assignment,
        expected_scenario_cells=FORMAL_SCENARIO_CELLS,
        reserved_evaluation_seeds=composite.RESERVED_EVALUATION_SEEDS,
    )
    readiness: dict[str, Any] = {
        "sources": {
            "formal_manifest_sha256": "7" * 64,
            "supplemental_manifest_sha256": "8" * 64,
            "supplemental_source_repository_dirty": False,
        },
        "data_support_readiness": {"status": "pass", "passed": True},
        "training_readiness": {"status": "pass", "passed": True},
    }
    admission = LoadedTrackletCompositeAdmission(
        view_manifest_path=root / "view.json",
        view_manifest=MappingProxyType({"content_sha256": "9" * 64}),
        view_manifest_sha256="a" * 64,
        dataset=dataset,
        readiness=MappingProxyType(readiness),
    )
    return composite.LoadedCompositeTrainingCorpus(
        admission=admission,
        formal_dataset_root=root / "formal",
        supplemental_root=root / "supplemental",
        admission_report_path=root / "admission.json",
        admission_report=MappingProxyType({}),
        admission_report_sha256="b" * 64,
        corpus_audit=MappingProxyType(audit),
    )


def _available(value: float) -> dict[str, Any]:
    return {"available": True, "value": value}


def _model_evidence_fixture(
    root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    bundle = root / "model_bundle"
    bundle.mkdir()
    (bundle / "weights.pt").write_bytes(b"deterministic-test-weights")
    _write_json(bundle / "manifest.json", {"model": "internal-contract-test"})
    metrics = {
        "precision": _available(0.98),
        "recall": _available(0.96),
        "f1": _available(0.97),
        "candidate_recall": _available(0.99),
        "false_merge_rate": _available(0.005),
        "ece": _available(0.02),
    }
    latency = {
        "device": "cpu",
        "sample_count": 60,
        "p50_ms": 5.0,
        "p95_ms": 8.0,
        "max_ms": 12.0,
    }
    report = {
        "schema_version": composite.TRAINING_REPORT_SCHEMA_VERSION,
        "dataset": {
            "training_set_sha256": "c" * 64,
            "test_seed_values": list(range(80, 100)),
        },
        "bundle": {
            "weights_sha256": composite.sha256_file(bundle / "weights.pt"),
            "manifest_sha256": composite.sha256_file(bundle / "manifest.json"),
        },
        "test": {
            "complete_truth": True,
            "truth_scope": "complete_graph_truth",
            "metrics": json.loads(json.dumps(metrics)),
            "latency": dict(latency),
        },
    }
    cells = [
        {
            "scenario": scenario,
            "scale": scale,
            "episode_count": 2,
            "labeled_candidate_edge_count": 17,
            "complete_truth": True,
            "metrics": json.loads(json.dumps(metrics)),
        }
        for scenario, scale in FORMAL_SCENARIO_CELLS
    ]
    return report, cells, bundle


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
