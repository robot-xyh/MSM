"""Frozen-test evaluation for the selected lightweight association model."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping

import numpy as np

from dual_optical_100target_gnn.assignment import solve_assignment
from dual_optical_100target_gnn import dataset as gnn_dataset
from dual_optical_100target_gnn.comparison import (
    build_comparison_export,
    per_seed_summaries,
    validate_comparison_export,
)
from dual_optical_100target_gnn.dataset import (
    canonical_json_sha256,
    load_entry,
    sample_entries,
)
from dual_optical_100target_gnn.loader import sha256_file
from dual_optical_100target_gnn.metrics import average_precision, evaluate_assignment

from .assignment import solve_probability_assignment
from .pipeline import verify_freeze_manifest


METHOD_LABELS = {
    "original_geometry": "原始几何代价",
    "selected_lightweight": "验证集选定轻量模型",
}


def _percentiles(values: Iterable[float]) -> dict[str, float | int]:
    array = np.asarray(list(values), dtype=np.float64)
    if len(array) == 0:
        return {"sample_count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "sample_count": len(array),
        "p50_ms": float(np.percentile(array, 50)),
        "p95_ms": float(np.percentile(array, 95)),
        "max_ms": float(np.max(array)),
    }


def _aggregate_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    if not rows:
        raise ValueError("cannot aggregate an empty evaluation set")
    failures: dict[str, int] = {}
    for row in rows:
        for name, count in row["failure_reasons"].items():
            failures[name] = failures.get(name, 0) + int(count)
    return {
        "sample_count": len(rows),
        "independent_seed_count": len({int(row["seed"]) for row in rows}),
        "macro_precision": float(np.mean([float(row["precision"]) for row in rows])),
        "macro_recall": float(np.mean([float(row["recall"]) for row in rows])),
        "macro_f1": float(np.mean([float(row["f1"]) for row in rows])),
        "candidate_edge_auprc_macro": float(
            np.mean([float(row["candidate_edge_auprc"]) for row in rows])
        ),
        "selected_count": int(sum(int(row["selected_count"]) for row in rows)),
        "correct_count": int(sum(int(row["correct_count"]) for row in rows)),
        "false_association_count": int(
            sum(int(row["false_association_count"]) for row in rows)
        ),
        "duplicate_track_assignment_count": int(
            sum(int(row["duplicate_track_assignment_count"]) for row in rows)
        ),
        "duplicate_identity_match_count": int(
            sum(int(row["duplicate_identity_match_count"]) for row in rows)
        ),
        "failure_reasons": failures,
    }


def _seed_level_metric(
    rows: Iterable[Mapping[str, Any]], metric: str
) -> dict[int, float]:
    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(int(row["seed"]), []).append(float(row[metric]))
    return {seed: float(np.mean(values)) for seed, values in grouped.items()}


def grouped_seed_bootstrap_ci(
    rows: Iterable[Mapping[str, Any]],
    *,
    metric: str,
    resamples: int,
    random_seed: int,
) -> dict[str, float | int | str]:
    if resamples <= 0:
        raise ValueError("bootstrap resamples must be positive")
    seed_values = _seed_level_metric(rows, metric)
    seeds = np.asarray(sorted(seed_values), dtype=np.int64)
    values = np.asarray([seed_values[int(seed)] for seed in seeds], dtype=np.float64)
    if len(values) == 0:
        raise ValueError("bootstrap requires at least one independent seed")
    rng = np.random.default_rng(random_seed)
    indices = rng.integers(0, len(values), size=(resamples, len(values)))
    estimates = np.mean(values[indices], axis=1)
    return {
        "sampling_unit": "seed",
        "independent_seed_count": len(values),
        "corruption_levels_grouped_with_seed": True,
        "resamples": resamples,
        "point": float(np.mean(values)),
        "lower": float(np.percentile(estimates, 2.5)),
        "upper": float(np.percentile(estimates, 97.5)),
    }


def grouped_paired_delta_ci(
    selected_rows: Iterable[Mapping[str, Any]],
    baseline_rows: Iterable[Mapping[str, Any]],
    *,
    metric: str,
    resamples: int,
    random_seed: int,
) -> dict[str, float | int | str]:
    selected = _seed_level_metric(selected_rows, metric)
    baseline = _seed_level_metric(baseline_rows, metric)
    if set(selected) != set(baseline):
        raise ValueError("paired bootstrap requires identical seed sets")
    seeds = sorted(selected)
    deltas = np.asarray([selected[seed] - baseline[seed] for seed in seeds])
    rng = np.random.default_rng(random_seed)
    indices = rng.integers(0, len(deltas), size=(resamples, len(deltas)))
    estimates = np.mean(deltas[indices], axis=1)
    return {
        "sampling_unit": "paired_seed",
        "independent_seed_count": len(deltas),
        "corruption_levels_grouped_with_seed": True,
        "resamples": resamples,
        "point": float(np.mean(deltas)),
        "lower": float(np.percentile(estimates, 2.5)),
        "upper": float(np.percentile(estimates, 97.5)),
    }


def _csv_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened = []
    for row in rows:
        values = {key: value for key, value in row.items() if key != "failure_reasons"}
        values["failure_reasons_json"] = json.dumps(
            row["failure_reasons"], ensure_ascii=False, sort_keys=True
        )
        flattened.append(values)
    return flattened


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write empty per-seed metrics")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def evaluate_frozen(
    freeze_manifest: str | Path,
    output_dir: str | Path,
    *,
    latency_repeats: int = 20,
    bootstrap_resamples: int = 2000,
    bootstrap_seed: int = 20260901,
) -> Path:
    if latency_repeats <= 0:
        raise ValueError("latency_repeats must be positive")
    freeze_path = Path(freeze_manifest).resolve()
    freeze, _, model, manifest, dataset_root = verify_freeze_manifest(freeze_path)
    threshold = float(freeze["selected_probability_threshold"])
    unmatched_cost = float(freeze["selected_unmatched_cost"])
    geometry_gate = dict(freeze["geometry_gate"])
    entries = sample_entries(manifest, "test")

    rows: list[dict[str, Any]] = []
    score_latency_ms: list[float] = []
    assignment_latency_ms: list[float] = []
    candidate_manifest_entries: list[dict[str, Any]] = []
    test_artifact_hashes: list[dict[str, Any]] = []
    for entry in entries:
        graph, labels = load_entry(dataset_root, entry, include_labels=True)
        if labels is None:
            raise AssertionError("test labels are required only for frozen offline scoring")
        fingerprint = gnn_dataset.candidate_graph_fingerprint(graph)
        candidate_manifest_entries.append(
            {
                "seed": graph.seed,
                "corruption_level": graph.corruption_level,
                "candidate_fingerprint_sha256": fingerprint,
                "online_sha256": entry["online_sha256"],
            }
        )
        test_artifact_hashes.append(
            {
                "seed": int(entry["seed"]),
                "corruption_level": str(entry["corruption_level"]),
                "online_sha256": str(entry["online_sha256"]),
                "offline_label_sha256": str(entry["offline_label_sha256"]),
            }
        )

        start = perf_counter()
        probabilities = model.predict_proba(graph, geometry_gate)
        score_latency_ms.append((perf_counter() - start) * 1000.0)
        start = perf_counter()
        selected_result = solve_probability_assignment(
            graph, probabilities, threshold, unmatched_cost
        )
        assignment_latency_ms.append((perf_counter() - start) * 1000.0)
        baseline_result = solve_assignment(graph, None, "geometry", unmatched_cost=1.20)

        for _ in range(latency_repeats - 1):
            start = perf_counter()
            repeated_probabilities = model.predict_proba(graph, geometry_gate)
            score_latency_ms.append((perf_counter() - start) * 1000.0)
            start = perf_counter()
            solve_probability_assignment(
                graph, repeated_probabilities, threshold, unmatched_cost
            )
            assignment_latency_ms.append((perf_counter() - start) * 1000.0)

        for method, result, scores in (
            ("original_geometry", baseline_result, np.exp(-graph.geometry_cost)),
            ("selected_lightweight", selected_result, probabilities),
        ):
            metrics = evaluate_assignment(graph, labels, result)
            rows.append(
                {
                    "seed": graph.seed,
                    "corruption_level": graph.corruption_level,
                    "method": method,
                    "method_cn": METHOD_LABELS[method],
                    "selected_model_id": model.model_id if method == "selected_lightweight" else "",
                    "probability_threshold": threshold if method == "selected_lightweight" else "",
                    "unmatched_cost": unmatched_cost if method == "selected_lightweight" else "",
                    "candidate_fingerprint_sha256": fingerprint,
                    "candidate_edge_count": int(graph.edge_index.shape[1]),
                    "candidate_edge_auprc": average_precision(labels.edge_labels, scores),
                    **metrics.to_dict(),
                }
            )

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_csv = output_dir / "per_seed_metrics.csv"
    candidate_manifest_path = output_dir / "candidate_manifest.json"
    comparison_export_path = output_dir / "comparison_export.json"
    _write_csv(metrics_csv, _csv_rows(rows))
    selected_rows = [row for row in rows if row["method"] == "selected_lightweight"]
    baseline_rows = [row for row in rows if row["method"] == "original_geometry"]
    by_method = {
        method: _aggregate_rows(row for row in rows if row["method"] == method)
        for method in METHOD_LABELS
    }
    by_corruption = {
        level: {
            method: _aggregate_rows(
                row
                for row in rows
                if row["method"] == method and row["corruption_level"] == level
            )
            for method in METHOD_LABELS
        }
        for level in manifest["corruption_levels"]
    }
    ci = {
        method: {
            metric: grouped_seed_bootstrap_ci(
                (row for row in rows if row["method"] == method),
                metric=metric,
                resamples=bootstrap_resamples,
                random_seed=bootstrap_seed,
            )
            for metric in ("precision", "recall", "f1")
        }
        for method in METHOD_LABELS
    }
    ci["selected_minus_geometry"] = {
        "f1": grouped_paired_delta_ci(
            selected_rows,
            baseline_rows,
            metric="f1",
            resamples=bootstrap_resamples,
            random_seed=bootstrap_seed,
        )
    }
    candidate_manifest = {
        "schema_version": "dual-optical-candidate-manifest-v1",
        "entries": sorted(
            candidate_manifest_entries,
            key=lambda item: (int(item["seed"]), str(item["corruption_level"])),
        ),
    }
    candidate_manifest["candidate_fingerprint_sha256"] = canonical_json_sha256(
        candidate_manifest["entries"]
    )
    candidate_manifest_path.write_text(
        json.dumps(candidate_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    contract_rows = [{"mode": row["method"], **row} for row in rows]
    per_seed_summary = [
        {"mode": mode, **summary}
        for mode in METHOD_LABELS
        for summary in per_seed_summaries(
            contract_rows, mode, manifest["corruption_levels"]
        )
    ]
    score_latency = _percentiles(score_latency_ms)
    assignment_latency = _percentiles(assignment_latency_ms)
    comparison_latency = {
        "cpu": {
            "available": 1,
            "device": "cpu",
            "sample_count": score_latency["sample_count"],
            "p50_ms": score_latency["p50_ms"],
            "p95_ms": score_latency["p95_ms"],
        },
        "gpu": {
            "available": 0,
            "reason": "lightweight route uses CPU inference",
        },
    }
    independent_seed_count = len({int(entry["seed"]) for entry in entries})
    evidence_status = (
        "expanded_reserved_100target_test"
        if int(manifest["expected_target_count"]) == 100 and independent_seed_count >= 20
        else "nonformal_fixture_or_limited_test"
    )
    evaluation = {
        "schema_version": "dual-optical-100target-lightweight-evaluation-v2",
        "evidence_status": evidence_status,
        "expected_target_count": int(manifest["expected_target_count"]),
        "test_seeds": sorted(int(seed) for seed in manifest["splits"]["test"]),
        "independent_seed_count": independent_seed_count,
        "test_sample_count": len(entries),
        "corruption_levels": list(manifest["corruption_levels"]),
        "selected_model_id": model.model_id,
        "selected_model_kind": model.kind,
        "selected_probability_threshold": threshold,
        "selected_unmatched_cost": unmatched_cost,
        "threshold_status": "selected_on_validation_not_universal_operating_limit",
        "assignment": by_method,
        "assignment_by_corruption": by_corruption,
        "per_seed_summary": per_seed_summary,
        "grouped_bootstrap_95ci": ci,
        "bootstrap_protocol": {
            "sampling_unit": "seed",
            "light_medium_heavy_are_not_independent_samples": True,
            "resamples": bootstrap_resamples,
            "random_seed": bootstrap_seed,
        },
        "latency": comparison_latency,
        "latency_detail": {
            "model_scoring": score_latency,
            "hungarian_assignment": assignment_latency,
            "measurement_scope": "process_wall_clock_on_this_host",
        },
        "candidate_fingerprints": {
            "aggregate_sha256": candidate_manifest[
                "candidate_fingerprint_sha256"
            ],
            "per_sample": candidate_manifest["entries"],
        },
        "test_artifact_hashes": test_artifact_hashes,
        "truth_isolation": {
            "truth_fields_in_model_features": False,
            "truth_used_for_training_labels": True,
            "truth_used_for_offline_test_scoring": True,
            "actor_name_in_model_features": False,
            "true_world_position_in_model_features": False,
        },
        "measurement_provenance": {
            "online_graphs": "saved_episode_measurements_and_geometry_fit",
            "corruption": "offline_reproducible_track_sample_corruption",
            "corruption_is_real_detector_distribution": False,
        },
        "reproducibility": {
            "dataset_fingerprint_sha256": freeze["dataset_fingerprint_sha256"],
            "model_fingerprint_sha256": freeze["model_fingerprint_sha256"],
            "freeze_manifest_sha256": sha256_file(freeze_path),
            "selected_model_sha256": freeze["selected_model_sha256"],
            "candidate_fingerprint_sha256": candidate_manifest[
                "candidate_fingerprint_sha256"
            ],
        },
        "artifacts": {
            "per_seed_metrics": metrics_csv.name,
            "freeze_manifest": str(freeze_path),
            "candidate_manifest": candidate_manifest_path.name,
            "comparison_export": comparison_export_path.name,
        },
    }
    comparison_export = build_comparison_export(
        evaluation,
        method_family="lightweight",
        method_id=freeze["selected_model_id"],
        selected_route="selected_lightweight",
    )
    validate_comparison_export(comparison_export)
    comparison_export_path.write_text(
        json.dumps(comparison_export, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics_path = output_dir / "evaluation_metrics.json"
    metrics_path.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metrics_path
