from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable

import numpy as np
import pytest


D5_SRC = (
    Path(__file__).resolve().parents[2]
    / "d5_terminal_association"
    / "src"
)
if str(D5_SRC) not in sys.path:
    sys.path.insert(0, str(D5_SRC))

from d5_terminal_association.sparse_tracklet_graph import (  # noqa: E402
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CameraLocalTracklet,
    SparseCandidateEdge,
    SparseTrackletGraph,
)
from d5_terminal_association.tracklet_dataset import (  # noqa: E402
    finalize_tracklet_dataset,
    stage_tracklet_dataset_episode,
)
from d5_terminal_association.tracklet_gnn import (  # noqa: E402
    OfflineTrackletTruthLabel,
)
from d6_evaluation_metrics import (  # noqa: E402
    D5_CROSSVIEW_CALIBRATION_SCHEMA_VERSION,
    D5_CROSSVIEW_FRAME_INDEX_SCHEMA_VERSION,
    D5CrossviewCalibrationConfig,
    D5CrossviewDatasetInput,
    evaluate_d5_crossview_calibration,
    verify_d5_crossview_calibration_sha256sums,
    write_d5_crossview_calibration_report,
)


def _node(
    resource: str,
    camera: str,
    local: str,
    measurement: float,
    arrival: float,
) -> CameraLocalTracklet:
    return CameraLocalTracklet(
        resource_id=resource,
        camera_id=camera,
        local_track_id=local,
        measurement_timestamp=measurement,
        arrival_timestamp=arrival,
        center_px=np.asarray([640.0, 360.0], dtype=float),
        covariance_px=np.eye(2, dtype=float),
        bbox_xyxy=(630.0, 350.0, 650.0, 370.0),
        source_observation_id=f"obs-{resource}-{local}",
    )


def _graph(
    *,
    edge_mode: str,
    base_time: float,
    same_camera: bool = False,
    delayed_positive: bool = False,
) -> tuple[SparseTrackletGraph, tuple[OfflineTrackletTruthLabel, ...]]:
    second_measurement = base_time + (0.6 if delayed_positive else 0.2)
    second_arrival = base_time + (1.3 if delayed_positive else 0.8)
    nodes = (
        _node("camera-a", "0", "local-a", base_time, base_time + 0.1),
        _node(
            "camera-a" if same_camera else "camera-b",
            "0",
            "local-b",
            second_measurement,
            second_arrival,
        ),
        _node("camera-c", "0", "local-c", base_time + 0.1, base_time + 0.3),
    )
    pairs: tuple[tuple[int, int], ...]
    if edge_mode == "positive":
        pairs = ((0, 1),)
    elif edge_mode == "mixed":
        pairs = ((0, 1), (0, 2))
    elif edge_mode == "false":
        pairs = ((0, 2),)
    elif edge_mode == "none":
        pairs = ()
    else:
        raise ValueError(edge_mode)
    edges = tuple(
        SparseCandidateEdge(
            source_index=left,
            target_index=right,
            source_tracklet_key=nodes[left].tracklet_key,
            target_tracklet_key=nodes[right].tracklet_key,
            shared_global_track_ids=(),
            feature_values=tuple(0.0 for _ in EDGE_FEATURE_NAMES),
            gate_score=0.1,
        )
        for left, right in pairs
    )
    edge_index = (
        np.asarray(pairs, dtype=np.int64).T
        if pairs
        else np.empty((2, 0), dtype=np.int64)
    )
    graph = SparseTrackletGraph(
        nodes=nodes,
        node_features=np.zeros(
            (len(nodes), len(NODE_FEATURE_NAMES)),
            dtype=np.float32,
        ),
        edge_index=edge_index,
        edge_features=np.zeros(
            (len(edges), len(EDGE_FEATURE_NAMES)),
            dtype=np.float32,
        ),
        edges=edges,
        candidate_counts={"retained": len(edges)},
    )
    labels = (
        OfflineTrackletTruthLabel(nodes[0].tracklet_key, "truth-a", base_time),
        OfflineTrackletTruthLabel(
            nodes[1].tracklet_key,
            "truth-a",
            second_measurement,
        ),
        OfflineTrackletTruthLabel(
            nodes[2].tracklet_key,
            "truth-b",
            base_time + 0.1,
        ),
    )
    return graph, labels


def _dataset(
    root: Path,
    *,
    seeds: range | tuple[int, ...],
    edge_mode: str = "positive",
    complete_labels: bool = True,
    candidate_recall_available: bool | None = None,
    scenario_for_seed: Callable[[int], str] | None = None,
    same_camera: bool = False,
    delayed_positive: bool = False,
    distinct_truth: bool = False,
    episode_prefix: str = "frame",
) -> Path:
    scenario_selector = scenario_for_seed or (lambda _seed: "crossview-calibration-v1")
    for seed in seeds:
        graph, labels = _graph(
            edge_mode=edge_mode,
            base_time=float(seed * 10),
            same_camera=same_camera,
            delayed_positive=delayed_positive,
        )
        if distinct_truth:
            labels = (
                labels[0],
                OfflineTrackletTruthLabel(
                    labels[1].tracklet_key,
                    "truth-c",
                    labels[1].measurement_timestamp,
                ),
                labels[2],
            )
        selected_labels = labels if complete_labels else labels[:2]
        stage_tracklet_dataset_episode(
            root,
            graph,
            selected_labels,
            scenario_version=scenario_selector(int(seed)),
            seed=int(seed),
            episode_id=f"{episode_prefix}-{int(seed):04d}",
            generation_config={"fixture": "d6-crossview-calibration-v1"},
            labels_complete=complete_labels,
            candidate_recall_available=(
                complete_labels
                if candidate_recall_available is None
                else candidate_recall_available
            ),
        )
    finalize_tracklet_dataset(
        root,
        split_seed=20260726,
        validation_fraction=0.2,
        test_fraction=0.2,
    )
    return root


def _frame_sidecar(dataset: Path, path: Path) -> Path:
    manifest_path = dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = {
        "schema_version": D5_CROSSVIEW_FRAME_INDEX_SCHEMA_VERSION,
        "coordinate_semantics": "scenario_version_seed_frame_index",
        "dataset_manifest_sha256": hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest(),
        "records": [
            {
                "episode_uid": item["episode_uid"],
                "scenario_version": item["scenario_version"],
                "seed": item["seed"],
                "frame_index": item["seed"],
            }
            for item in manifest["episodes"]
        ],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _metric(result: dict, variant: str, name: str) -> dict:
    return result["variants"][variant]["aggregate"][name]


def test_formal_R0_G1_complete_mixed_edges_and_bootstrap(tmp_path: Path) -> None:
    seeds = tuple(range(1000, 1020))
    r0 = _dataset(
        tmp_path / "r0",
        seeds=seeds,
        edge_mode="positive",
        episode_prefix="runtime-r0-config-a",
    )
    g1 = _dataset(
        tmp_path / "g1",
        seeds=seeds,
        edge_mode="mixed",
        episode_prefix="runtime-g1-config-b",
    )
    r0_sidecar = _frame_sidecar(r0, tmp_path / "r0-frames.json")
    g1_sidecar = _frame_sidecar(g1, tmp_path / "g1-frames.json")

    result = evaluate_d5_crossview_calibration(
        (
            D5CrossviewDatasetInput("R0", r0, r0_sidecar),
            D5CrossviewDatasetInput("G1", g1, g1_sidecar),
        ),
        config=D5CrossviewCalibrationConfig(
            mode="formal",
            expected_seeds=seeds,
            bootstrap_resamples=100,
            bootstrap_rng_seed=7,
        ),
    )

    assert result["schema_version"] == D5_CROSSVIEW_CALIBRATION_SCHEMA_VERSION
    assert result["evaluation_scope"] == "candidate_graph_geometry_calibration"
    assert result["status"] == "pass"
    assert result["formal_acceptance"] is True
    assert result["authority"] == {
        "evaluation_only": True,
        "model_promotion": False,
        "default_path": False,
        "assignment": False,
        "failover": False,
        "control": False,
    }
    assert result["variants"]["R0"]["aggregate"][
        "time_eligible_true_pair_count"
    ] == 20
    assert _metric(result, "R0", "geometry_candidate_precision")["value"] == 1.0
    assert _metric(result, "R0", "geometry_candidate_recall")["value"] == 1.0
    assert _metric(result, "G1", "geometry_candidate_precision")["value"] == 0.5
    assert _metric(result, "G1", "geometry_false_edge_rate")["value"] == 0.5
    assert _metric(result, "G1", "geometry_candidate_recall")["value"] == 1.0
    assert _metric(result, "G1", "geometry_candidate_f1")["value"] == pytest.approx(
        2.0 / 3.0
    )
    comparison = result["candidate_graph_R0_G1_comparison"]
    assert comparison["comparable"] is True
    assert comparison["paired_frame_count"] == 20
    assert comparison["scope"] == "candidate_graph_geometry_only"
    assert comparison["metric_deltas_G1_minus_R0"][
        "geometry_candidate_precision"
    ]["value"] == -0.5
    assert comparison["model_scoring_benefit"]["availability"] == "unavailable"
    assert result["variants"]["G1"]["seed_statistics"][
        "geometry_candidate_precision"
    ][
        "bootstrap_availability"
    ] == "available"
    assert result["unsupported_metrics"]["G1_edge_scoring_benefit"][
        "availability"
    ] == "unavailable"
    assert result["unsupported_metrics"]["cluster_purity"]["availability"] == "unavailable"
    assert result["unsupported_metrics"]["global_track_id_binding_correctness"][
        "availability"
    ] == "unavailable"

    no_coordinate = evaluate_d5_crossview_calibration(
        (
            D5CrossviewDatasetInput("R0", r0),
            D5CrossviewDatasetInput("G1", g1),
        ),
        config=D5CrossviewCalibrationConfig(
            mode="formal",
            expected_seeds=seeds,
            bootstrap_resamples=25,
        ),
    )
    assert no_coordinate["status"] == "fail_closed"
    assert no_coordinate["candidate_graph_R0_G1_comparison"]["reason"] == (
        "stable_frame_coordinate_sidecar_missing_or_invalid"
    )
    assert no_coordinate["candidate_graph_R0_G1_comparison"][
        "paired_frame_count"
    ] is None


def test_no_denominator_is_unavailable_not_zero(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / "dataset",
        seeds=range(3),
        edge_mode="false",
        distinct_truth=True,
    )
    result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", dataset),),
    )

    assert result["status"] == "development_descriptive"
    assert _metric(result, "R0", "geometry_candidate_precision")["value"] == 0.0
    assert _metric(result, "R0", "geometry_candidate_recall") == {
        "availability": "unavailable",
        "value": None,
        "reason": "no_time_eligible_same_truth_cross_camera_pairs",
    }
    assert _metric(result, "R0", "geometry_candidate_f1")[
        "availability"
    ] == "unavailable"
    assert result["variants"]["R0"]["seed_statistics"][
        "geometry_candidate_precision"
    ][
        "bootstrap_unavailable_reason"
    ] == "fewer_than_20_available_seeds_descriptive_only"


def test_missing_labels_fail_closed_and_recall_stays_unavailable(
    tmp_path: Path,
) -> None:
    dataset = _dataset(
        tmp_path / "dataset",
        seeds=range(3),
        edge_mode="mixed",
        complete_labels=False,
        candidate_recall_available=False,
    )
    result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", dataset),),
    )

    assert result["status"] == "fail_closed"
    assert result["hard_violation_count"] == 3
    assert result["variants"]["R0"]["hard_violations"][
        "missing_label_node_count"
    ] == 3
    assert _metric(result, "R0", "geometry_candidate_recall")[
        "availability"
    ] == "unavailable"


def test_same_camera_edge_is_an_explicit_hard_violation(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / "dataset",
        seeds=range(3),
        edge_mode="positive",
        same_camera=True,
    )
    result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", dataset),),
    )

    assert result["status"] == "fail_closed"
    assert result["variants"]["R0"]["strict_loader"]["status"] == "pass"
    assert result["variants"]["R0"]["hard_violations"][
        "same_camera_edge_count"
    ] == 3
    assert _metric(result, "R0", "geometry_candidate_precision")[
        "availability"
    ] == "unavailable"


def test_time_ineligible_candidate_edge_fails_closed(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path / "dataset",
        seeds=range(3),
        edge_mode="positive",
        delayed_positive=True,
    )
    result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", dataset),),
    )

    assert result["status"] == "fail_closed"
    assert result["variants"]["R0"]["hard_violations"][
        "time_ineligible_candidate_edge_count"
    ] == 3
    assert _metric(result, "R0", "geometry_candidate_recall")[
        "availability"
    ] == "unavailable"


def test_formal_rejects_seed_shortage_and_mixed_scenario(tmp_path: Path) -> None:
    seeds = tuple(range(1000, 1020))
    mixed = _dataset(
        tmp_path / "mixed",
        seeds=seeds,
        scenario_for_seed=lambda seed: (
            "crossview-a-v1" if seed < 1010 else "crossview-b-v1"
        ),
    )
    result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", mixed),),
        config=D5CrossviewCalibrationConfig(
            mode="formal",
            expected_seeds=seeds,
            bootstrap_resamples=50,
        ),
    )
    assert result["status"] == "fail_closed"
    assert "formal_scenario_version_not_uniform" in result["blockers"]

    short = _dataset(tmp_path / "short", seeds=range(3))
    short_result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", short),),
        config=D5CrossviewCalibrationConfig(
            mode="formal",
            expected_seeds=tuple(range(20)),
            bootstrap_resamples=50,
        ),
    )
    assert short_result["status"] == "fail_closed"
    assert "formal_seed_set_mismatch:missing=[3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]:extra=[]" in short_result[
        "variants"
    ]["R0"]["blockers"]


def test_explicit_frame_sidecar_requires_exact_episode_coverage(
    tmp_path: Path,
) -> None:
    dataset = _dataset(tmp_path / "dataset", seeds=range(3))
    sidecar = _frame_sidecar(dataset, tmp_path / "frames.json")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["records"].pop()
    sidecar.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", dataset, sidecar),),
    )

    assert result["status"] == "fail_closed"
    assert result["variants"]["R0"]["frame_index_sidecar"]["status"] == "fail_closed"
    assert result["variants"]["R0"]["frame_index_sidecar"]["reason"] == (
        "frame_index_episode_coverage_mismatch"
    )


def _tamper_first_graph(
    dataset: Path,
    change: Callable[[dict[str, np.ndarray]], None],
) -> None:
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    graph_path = dataset / manifest["episodes"][0]["graph_file"]
    with np.load(graph_path, allow_pickle=False) as archive:
        arrays = {name: np.array(archive[name], copy=True) for name in archive.files}
    change(arrays)
    np.savez_compressed(graph_path, **arrays)


@pytest.mark.parametrize(
    ("change", "field"),
    (
        (
            lambda arrays: arrays.__setitem__(
                "edge_index",
                np.concatenate(
                    (arrays["edge_index"], arrays["edge_index"][:, :1]),
                    axis=1,
                ),
            ),
            "duplicate_undirected_edge_count",
        ),
        (
            lambda arrays: arrays["edge_index"].__setitem__(
                (1, 0),
                arrays["edge_index"][0, 0],
            ),
            "self_loop_count",
        ),
        (
            lambda arrays: arrays["node_features"].__setitem__((0, 0), np.nan),
            "non_finite_array_count",
        ),
        (
            lambda arrays: arrays["tracklet_keys"].__setitem__(
                1,
                arrays["tracklet_keys"][0],
            ),
            "duplicate_tracklet_key_count",
        ),
    ),
)
def test_tamper_duplicate_self_nonfinite_and_tracklet_key_fail_closed(
    tmp_path: Path,
    change: Callable[[dict[str, np.ndarray]], None],
    field: str,
) -> None:
    dataset = _dataset(tmp_path / field, seeds=range(3))
    _tamper_first_graph(dataset, change)

    result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", dataset),),
    )

    assert result["status"] == "fail_closed"
    assert result["variants"]["R0"]["strict_loader"]["status"] == "fail_closed"
    assert result["variants"]["R0"]["hard_violations"][field] >= 1
    assert result["variants"]["R0"]["hard_violations"][
        "loader_validation_failure_count"
    ] == 1


def test_writer_cli_and_sha_inventory(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "dataset", seeds=range(3), edge_mode="mixed")
    result = evaluate_d5_crossview_calibration(
        (D5CrossviewDatasetInput("R0", dataset),),
        config=D5CrossviewCalibrationConfig(
            bootstrap_resamples=25,
            bootstrap_rng_seed=9,
        ),
    )
    output = tmp_path / "direct-output"
    paths = write_d5_crossview_calibration_report(
        output,
        result,
        datasets=(D5CrossviewDatasetInput("R0", dataset),),
    )
    assert all(path.is_file() for path in paths.values())
    assert verify_d5_crossview_calibration_sha256sums(output) is True
    rows = list(csv.DictReader(paths["csv"].open(encoding="utf-8")))
    assert len(rows) == 3
    assert {row["variant"] for row in rows} == {"R0"}

    cli_output = tmp_path / "cli-output"
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_d5_crossview_calibration.py"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--dataset",
            f"R0={dataset}",
            "--mode",
            "development",
            "--bootstrap-resamples",
            "25",
            "--output-dir",
            str(cli_output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    stdout = json.loads(completed.stdout)
    assert stdout["status"] == "development_descriptive"
    assert verify_d5_crossview_calibration_sha256sums(cli_output) is True
    (cli_output / "D5_CROSSVIEW_CALIBRATION_CN.md").write_text(
        "tampered\n",
        encoding="utf-8",
    )
    assert verify_d5_crossview_calibration_sha256sums(cli_output) is False
