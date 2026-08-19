"""Evaluate frozen models only on reserved complete test seeds."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import platform
import shutil
import time
from typing import Any

import numpy as np
import torch

from .assignment import solve_assignment
from .comparison import (
    DEFAULT_BOOTSTRAP_REPEATS,
    build_comparison_export,
    grouped_bootstrap,
    per_seed_summaries,
)
from .dataset import (
    PROTOCOL_EXPANDED_FORMAL,
    PROTOCOL_LEGACY_FORMAL,
    canonical_json_sha256,
    candidate_graph_fingerprint,
    load_dataset_manifest,
    load_entry,
    sample_entries,
)
from .loader import sha256_file
from .metrics import average_precision, evaluate_assignment
from .model import (
    BipartiteEdgeGNN,
    FeatureNormalizer,
    graph_tensors,
    load_weights_only,
)
from .schema import CORRUPTION_LEVELS, GraphLabels, OnlineGraph
from .training import verify_freeze_manifest


def _model_from_frozen(freeze: dict[str, Any], root: Path, device: torch.device) -> tuple[BipartiteEdgeGNN, FeatureNormalizer]:
    config = json.loads((root / freeze["model_config"]).read_text(encoding="utf-8"))
    model = BipartiteEdgeGNN(
        int(config["node_feature_dim"]),
        int(config["edge_feature_dim"]),
        hidden_dim=int(config["hidden_dim"]),
        dropout=float(config["dropout"]),
    ).to(device)
    load_weights_only(model, root / freeze["weights"], map_location=device)
    model.eval()
    return model, FeatureNormalizer.load(root / freeze["normalizer"])


def _predict(
    model: BipartiteEdgeGNN,
    normalizer: FeatureNormalizer,
    graph: OnlineGraph,
    device: torch.device,
) -> np.ndarray:
    if graph.edge_index.shape[1] == 0:
        return np.empty(0, dtype=np.float32)
    with torch.no_grad():
        logits = model(*graph_tensors(graph, normalizer, device))
        return torch.sigmoid(logits).detach().cpu().numpy().astype(np.float32)


def _latency(
    model: BipartiteEdgeGNN,
    normalizer: FeatureNormalizer,
    graphs: list[OnlineGraph],
    device: torch.device,
    repeats: int,
) -> dict[str, float | int | str]:
    samples = []
    with torch.no_grad():
        for graph in graphs:
            if graph.edge_index.shape[1] == 0:
                continue
            tensors = graph_tensors(graph, normalizer, device)
            for _ in range(2):
                model(*tensors)
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            for _ in range(repeats):
                start = time.perf_counter()
                model(*tensors)
                if device.type == "cuda":
                    torch.cuda.synchronize(device)
                samples.append((time.perf_counter() - start) * 1000.0)
    if not samples:
        return {"available": 0, "device": str(device), "sample_count": 0}
    return {
        "available": 1,
        "device": str(device),
        "sample_count": len(samples),
        "p50_ms": float(np.percentile(samples, 50)),
        "p95_ms": float(np.percentile(samples, 95)),
    }


def _aggregate_assignment(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot aggregate an empty assignment result")
    return {
        "sample_count": len(rows),
        "macro_precision": float(np.mean([row["precision"] for row in rows])),
        "macro_recall": float(np.mean([row["recall"] for row in rows])),
        "macro_f1": float(np.mean([row["f1"] for row in rows])),
        "false_association_count": int(
            sum(row["false_association_count"] for row in rows)
        ),
        "duplicate_track_assignment_count": int(
            sum(row["duplicate_track_assignment_count"] for row in rows)
        ),
        "duplicate_identity_match_count": int(
            sum(row["duplicate_identity_match_count"] for row in rows)
        ),
    }


def _promotion_decision(
    aggregate: dict[str, Any],
    latency: dict[str, Any],
    comparison_by_corruption: dict[str, Any],
    selected_route: str = "hybrid",
) -> dict[str, Any]:
    geometry = aggregate["geometry"]
    selected = aggregate[selected_route]
    f1_delta = float(selected["macro_f1"] - geometry["macro_f1"])
    f1_pass = f1_delta >= 0.02
    false_pass = (
        selected["false_association_count"]
        <= geometry["false_association_count"]
    )
    geometry_duplicate_identities = int(geometry["duplicate_identity_match_count"])
    selected_duplicate_identities = int(selected["duplicate_identity_match_count"])
    duplicate_identity_pass = (
        selected_duplicate_identities <= geometry_duplicate_identities
    )
    gpu = latency.get("gpu", {})
    gpu_available = bool(gpu.get("available"))
    gpu_pass = gpu_available and float(gpu.get("p95_ms", float("inf"))) <= 100.0
    return {
        "macro_f1_delta": f1_delta,
        "selected_route": selected_route,
        "f1_improvement_at_least_0_02": f1_pass,
        "false_association_non_increase": false_pass,
        "geometry_duplicate_identity_match_count": geometry_duplicate_identities,
        "selected_duplicate_identity_match_count": selected_duplicate_identities,
        "hybrid_duplicate_identity_match_count": int(
            aggregate["hybrid"]["duplicate_identity_match_count"]
        ),
        "duplicate_identity_non_increase": duplicate_identity_pass,
        "gpu_p95_at_most_100_ms": gpu_pass,
        "gpu_latency_available": gpu_available,
        "recommendation_scope": "next_isolated_engineering_validation_only",
        "recommend_continue_toward_mainline": bool(
            f1_pass and false_pass and duplicate_identity_pass and gpu_pass
        ),
        "by_corruption": comparison_by_corruption,
    }


def _write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def evaluate_frozen(
    freeze_manifest: str | Path,
    output_dir: str | Path,
    *,
    latency_repeats: int = 10,
    bootstrap_repeats: int = DEFAULT_BOOTSTRAP_REPEATS,
) -> Path:
    freeze, frozen_root = verify_freeze_manifest(freeze_manifest)
    dataset_manifest, dataset_root = load_dataset_manifest(freeze["dataset_manifest"])
    test_entries = sample_entries(dataset_manifest, "test")
    reserved = set(int(seed) for seed in freeze["reserved_test_seeds"])
    actual = {int(entry["seed"]) for entry in test_entries}
    if actual != reserved:
        raise ValueError(f"frozen test seeds {reserved} do not match dataset test seeds {actual}")
    train_val = set(int(seed) for seed in freeze["train_seeds"] + freeze["validation_seeds"])
    if train_val & actual:
        raise ValueError("test seed overlaps training or validation")

    loaded: list[tuple[OnlineGraph, GraphLabels]] = []
    candidate_manifest_entries: list[dict[str, Any]] = []
    for entry in test_entries:
        graph, labels = load_entry(dataset_root, entry, include_labels=True)
        assert labels is not None
        loaded.append((graph, labels))
        candidate_manifest_entries.append(
            {
                "seed": graph.seed,
                "corruption_level": graph.corruption_level,
                "candidate_fingerprint_sha256": candidate_graph_fingerprint(graph),
                "online_sha256": entry["online_sha256"],
            }
        )

    selected_route = str(freeze.get("selected_route", "hybrid"))
    if selected_route not in {"learned", "hybrid"}:
        raise ValueError(f"invalid frozen selected route: {selected_route}")
    route_unmatched_costs = {
        "learned": float(freeze.get("route_unmatched_costs", {}).get("learned", 1.20)),
        "hybrid": float(freeze.get("route_unmatched_costs", {}).get("hybrid", 1.20)),
    }
    route_probability_thresholds = {
        route: (
            float(freeze["route_probability_thresholds"][route])
            if "route_probability_thresholds" in freeze
            else None
        )
        for route in ("learned", "hybrid")
    }
    mode_unmatched_costs = {
        "geometry": 1.20,
        **route_unmatched_costs,
    }

    preferred_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, normalizer = _model_from_frozen(freeze, frozen_root, preferred_device)
    per_sample: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    for graph, labels in loaded:
        probabilities = _predict(model, normalizer, graph, preferred_device)
        graph_fingerprint = candidate_graph_fingerprint(graph)
        edge_auprc = average_precision(labels.edge_labels, probabilities)
        for edge_id, (label, probability) in enumerate(
            zip(labels.edge_labels, probabilities)
        ):
            candidate_rows.append(
                {
                    "seed": graph.seed,
                    "corruption_level": graph.corruption_level,
                    "edge_id": edge_id,
                    "offline_label": int(label > 0.5),
                    "probability": float(probability),
                    "candidate_fingerprint_sha256": graph_fingerprint,
                }
            )
        for mode in ("geometry", "learned", "hybrid"):
            start = time.perf_counter()
            assignment = solve_assignment(
                graph,
                probabilities if mode != "geometry" else None,
                mode,  # type: ignore[arg-type]
                unmatched_cost=mode_unmatched_costs[mode],
            )
            assignment_ms = (time.perf_counter() - start) * 1000.0
            metrics = evaluate_assignment(graph, labels, assignment)
            if metrics.duplicate_track_assignment_count:
                raise RuntimeError("global Hungarian assignment violated one-to-one output")
            row = {
                "seed": graph.seed,
                "corruption_level": graph.corruption_level,
                "mode": mode,
                "candidate_edge_auprc": edge_auprc,
                "candidate_edge_count": graph.edge_index.shape[1],
                "assignment_ms": assignment_ms,
                "unmatched_cost": mode_unmatched_costs[mode],
                "probability_threshold": (
                    route_probability_thresholds[mode]
                    if mode in route_probability_thresholds
                    else None
                ),
                "candidate_fingerprint_sha256": graph_fingerprint,
                **{key: value for key, value in metrics.to_dict().items() if key != "failure_reasons"},
            }
            per_sample.append(row)
            for reason, count in metrics.failure_reasons.items():
                failure_rows.append(
                    {
                        "seed": graph.seed,
                        "corruption_level": graph.corruption_level,
                        "mode": mode,
                        "reason": reason,
                        "count": count,
                    }
                )

    graphs = [graph for graph, _ in loaded]
    cpu_model, cpu_normalizer = _model_from_frozen(freeze, frozen_root, torch.device("cpu"))
    latency = {
        "cpu": _latency(cpu_model, cpu_normalizer, graphs, torch.device("cpu"), latency_repeats),
        "gpu": {"available": 0, "reason": "CUDA unavailable"},
    }
    if torch.cuda.is_available():
        gpu_model, gpu_normalizer = _model_from_frozen(
            freeze, frozen_root, torch.device("cuda")
        )
        latency["gpu"] = _latency(
            gpu_model,
            gpu_normalizer,
            graphs,
            torch.device("cuda"),
            latency_repeats,
        )

    aggregate: dict[str, Any] = {}
    for mode in ("geometry", "learned", "hybrid"):
        rows = [row for row in per_sample if row["mode"] == mode]
        aggregate[mode] = _aggregate_assignment(rows)
    aggregate_by_corruption: dict[str, Any] = {}
    comparison_by_corruption: dict[str, Any] = {}
    candidate_auprc_by_corruption: dict[str, float] = {}
    for level in CORRUPTION_LEVELS:
        level_rows = [row for row in per_sample if row["corruption_level"] == level]
        aggregate_by_corruption[level] = {
            mode: _aggregate_assignment(
                [row for row in level_rows if row["mode"] == mode]
            )
            for mode in ("geometry", "learned", "hybrid")
        }
        geometry = aggregate_by_corruption[level]["geometry"]
        selected = aggregate_by_corruption[level][selected_route]
        comparison_by_corruption[level] = {
            "selected_minus_geometry_macro_f1": float(
                selected["macro_f1"] - geometry["macro_f1"]
            ),
            "selected_minus_geometry_false_associations": int(
                selected["false_association_count"]
                - geometry["false_association_count"]
            ),
        }
        candidate_auprc_by_corruption[level] = float(
            np.mean(
                [
                    row["candidate_edge_auprc"]
                    for row in level_rows
                    if row["mode"] == "hybrid"
                ]
            )
        )
    candidate_auprc = float(
        np.mean(
            [
                row["candidate_edge_auprc"]
                for row in per_sample
                if row["mode"] == "hybrid"
            ]
        )
    )
    promotion = _promotion_decision(
        aggregate,
        latency,
        comparison_by_corruption,
        selected_route,
    )
    per_seed_summary = [
        {"mode": mode, **row}
        for mode in ("geometry", "learned", "hybrid")
        for row in per_seed_summaries(per_sample, mode, CORRUPTION_LEVELS)
    ]
    bootstrap = grouped_bootstrap(
        per_sample,
        ("geometry", "learned", "hybrid"),
        CORRUPTION_LEVELS,
        repeats=bootstrap_repeats,
    )
    profile = str(
        freeze.get(
            "protocol_profile",
            PROTOCOL_LEGACY_FORMAL if freeze.get("formal_protocol") else "nonformal_fixture_or_custom",
        )
    )
    if profile == PROTOCOL_EXPANDED_FORMAL:
        promotion["status"] = "pending_external_lightweight_comparison"
        promotion["final_decision_requires_external_baseline"] = True
        promotion["local_geometry_reference_passed"] = promotion[
            "recommend_continue_toward_mainline"
        ]
        promotion["recommend_continue_toward_mainline"] = False
    else:
        promotion["status"] = "local_geometry_reference_only"
        promotion["final_decision_requires_external_baseline"] = False

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    per_sample_path = output_dir / "per_sample_metrics.csv"
    failure_path = output_dir / "failure_reasons.csv"
    candidate_path = output_dir / "candidate_edge_scores.csv"
    per_seed_path = output_dir / "per_seed_metrics.csv"
    candidate_manifest_path = output_dir / "candidate_manifest.json"
    comparison_export_path = output_dir / "comparison_export.json"
    training_history_path = output_dir / "training_history.csv"
    _write_csv(per_sample_path, per_sample, list(per_sample[0]))
    _write_csv(per_seed_path, per_seed_summary, list(per_seed_summary[0]))
    _write_csv(
        failure_path,
        failure_rows,
        ["seed", "corruption_level", "mode", "reason", "count"],
    )
    _write_csv(
        candidate_path,
        candidate_rows,
        [
            "seed",
            "corruption_level",
            "edge_id",
            "offline_label",
            "probability",
            "candidate_fingerprint_sha256",
        ],
    )
    shutil.copy2(frozen_root / freeze["training_history"], training_history_path)
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
    evidence_status = {
        PROTOCOL_EXPANDED_FORMAL: "expanded_formal_reserved_test",
        PROTOCOL_LEGACY_FORMAL: "legacy_formal_reserved_test",
    }.get(profile, "nonformal_test_split")
    metrics = {
        "schema_version": "dual-optical-100target-gnn-evaluation-v3",
        "evidence_status": evidence_status,
        "protocol_profile": profile,
        "test_seeds": sorted(actual),
        "test_sample_count": len(graphs),
        "corruption_levels": list(CORRUPTION_LEVELS),
        "candidate_edge_auprc_macro": candidate_auprc,
        "candidate_edge_auprc_by_corruption": candidate_auprc_by_corruption,
        "assignment": aggregate,
        "assignment_by_corruption": aggregate_by_corruption,
        "per_seed_summary": per_seed_summary,
        "seed_grouped_bootstrap_95ci": bootstrap,
        "formal_selection": {
            "selected_route": selected_route,
            "selected_probability_threshold": freeze.get(
                "selected_probability_threshold"
            ),
            "selected_unmatched_cost": float(
                freeze.get("selected_unmatched_cost", route_unmatched_costs[selected_route])
            ),
            "route_probability_thresholds": route_probability_thresholds,
            "route_unmatched_costs": route_unmatched_costs,
            "geometry_unmatched_cost": 1.20,
            "selection_source": "validation_split_only",
        },
        "latency": latency,
        "promotion": promotion,
        "device": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cpu": platform.processor() or platform.machine(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        "truth_isolation": {
            "truth_used_for_training_labels": True,
            "truth_used_for_offline_evaluation": True,
            "truth_fields_in_model_features": False,
            "actor_fields_in_model_features": False,
            "world_truth_fields_in_model_features": False,
        },
        "reproducibility": {
            "dataset_manifest_sha256": freeze["dataset_manifest_sha256"],
            "dataset_fingerprint_sha256": freeze["dataset_fingerprint_sha256"],
            "freeze_manifest_sha256": sha256_file(Path(freeze_manifest).resolve()),
            "model_weights_sha256": freeze["weights_sha256"],
            "model_fingerprint_sha256": freeze["model_fingerprint_sha256"],
            "candidate_fingerprint_sha256": candidate_manifest[
                "candidate_fingerprint_sha256"
            ],
            "global_assignment": "hungarian_one_to_one",
            "test_entry_hashes": [
                {
                    "seed": int(entry["seed"]),
                    "corruption_level": str(entry["corruption_level"]),
                    "online_sha256": entry["online_sha256"],
                    "offline_label_sha256": entry["offline_label_sha256"],
                }
                for entry in test_entries
            ],
        },
        "artifacts": {
            "per_sample_metrics": per_sample_path.name,
            "per_seed_metrics": per_seed_path.name,
            "failure_reasons": failure_path.name,
            "candidate_edge_scores": candidate_path.name,
            "training_history": training_history_path.name,
            "candidate_manifest": candidate_manifest_path.name,
            "comparison_export": comparison_export_path.name,
        },
    }
    comparison_export = build_comparison_export(
        metrics,
        method_family="gnn",
        method_id=f"edge_gnn:{selected_route}",
        selected_route=selected_route,
    )
    comparison_export_path.write_text(
        json.dumps(comparison_export, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics_path = output_dir / "evaluation_metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metrics_path
