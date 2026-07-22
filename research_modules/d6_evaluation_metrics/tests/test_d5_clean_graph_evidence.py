from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

import pytest

from d6_evaluation_metrics import (
    D5_CLEAN_GRAPH_CRITERIA,
    D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION,
    D5_CLEAN_GRAPH_LEGACY_INPUT_SCHEMA_VERSION,
    D5_HELDOUT_CORPUS_SCHEMA_VERSION,
    D5_HELDOUT_EVALUATION_SCHEMA_VERSION,
    D5CleanGraphArtifact,
    D5CleanGraphEvidenceError,
    D5CleanGraphEvidenceInputs,
    audit_d5_clean_graph_evidence,
    load_d5_clean_graph_evidence_inputs,
    write_d5_clean_graph_evidence_report,
)


_SPLIT_SEEDS = {
    "train": list(range(60)),
    "validation": list(range(60, 80)),
    "test": list(range(80, 100)),
}
_SEED_COUNTS = {name: len(values) for name, values in _SPLIT_SEEDS.items()}
_HELDOUT_SEEDS = list(range(1000, 1020))
_HELDOUT_SCENARIOS = (
    "nominal",
    "dense_crossing",
    "formation_split",
    "evasive_multilevel",
    "delayed_noisy",
    "communication_degraded",
    "center_failure",
    "secondary_failure",
    "high_threat_m_to_n",
)
_HELDOUT_SCALES = (5, 20, 50, 100, 200)
_HELDOUT_CELLS = tuple(
    (scenario, scale)
    for scenario in _HELDOUT_SCENARIOS
    for scale in _HELDOUT_SCALES
)
_MODEL_NODE_FEATURE_NAMES = [
    "center_x_normalized",
    "center_y_normalized",
    "log_bbox_area_ratio",
    "log_bbox_aspect_ratio",
    "angular_velocity_x_rad_s",
    "angular_velocity_y_rad_s",
    "bbox_scale_rate_s",
    "confidence",
    "pixel_covariance_trace_normalized",
    "tracklet_age_s",
]
_MODEL_EDGE_FEATURE_NAMES = [
    "time_delta_s",
    "pixel_mahalanobis",
    "reprojection_error_px",
    "ray_closest_distance_m",
    "bbox_log_scale_delta",
    "bbox_scale_rate_delta_s",
    "angular_velocity_delta_rad_s",
    "baseline_m",
    "extrinsics_covariance_trace",
    "epipolar_error_px",
    "triangulation_angle_rad",
    "global_projection_mahalanobis",
    "confidence_product",
    "shared_global_track_count",
]
_HELDOUT_IMPLEMENTATION_FILES = (
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
    "tracklet_supplemental_curriculum.py",
    "tracklet_heldout_evaluation.py",
)
_MODEL_IMPLEMENTATION_FILES = (
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_HELDOUT_GATE_CONFIG = {
    "max_time_delta_s": 0.35,
    "max_arrival_time_delta_s": 1.0,
    "max_camera_geometry_age_s": 0.35,
    "fov_margin_px": 2.0,
    "max_epipolar_error_px": 8.0,
    "epipolar_covariance_sigma": 2.0,
    "max_ray_closest_distance_m": 25.0,
    "ray_covariance_sigma": 2.0,
    "min_triangulation_angle_deg": 0.2,
    "max_reprojection_error_px": 10.0,
    "reprojection_covariance_sigma": 2.0,
    "max_pixel_mahalanobis": 6.0,
    "max_global_projection_mahalanobis": 6.0,
    "global_process_noise_m2_s4": 1.0,
    "max_tracklet_covariance_trace_px2": 10_000.0,
    "max_extrinsics_covariance_trace": 1_000.0,
    "camera_overlap_near_m": 1.0,
    "camera_overlap_far_m": 3_000.0,
    "camera_index_cell_size_m": 1_000.0,
    "camera_pair_time_window_s": 0.35,
    "camera_pair_budget": 4_096,
    "camera_index_max_search_radius_cells": 8,
    "max_tracklet_candidate_edges_per_node": 24,
    "max_neighbors_per_node": 24,
    "covariance_regularization": 1.0e-6,
}


@dataclass(frozen=True)
class _Fixture:
    inputs: D5CleanGraphEvidenceInputs
    paths: dict[str, Path]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _d5_canonical_bytes(value: Any) -> bytes:
    return _canonical_bytes(value) + b"\n"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _with_content_sha(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _sha_bytes(_canonical_bytes(result))
    return result


def _with_d5_content_sha(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _sha_bytes(_d5_canonical_bytes(result))
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")


def _balance(episode_count: int) -> dict[str, int]:
    return {
        "candidate_edges": episode_count * 2,
        "positive_candidate_edges": episode_count,
        "negative_candidate_edges": episode_count,
        "unlabeled_candidate_edges": 0,
    }


def _dataset(prefix: str) -> dict[str, Any]:
    episodes = []
    for split, seeds in _SPLIT_SEEDS.items():
        for seed in seeds:
            episodes.append(
                {
                    "episode_uid": f"{prefix}-{seed}",
                    "seed": seed,
                    "split": split,
                    "labels_complete": True,
                    "candidate_recall_available": True,
                    "edge_count": 2,
                    "class_balance": _balance(1),
                }
            )
    return {
        "schema_version": "d5.tracklet-dataset.v2",
        "graph_schema_version": "d5.sparse-tracklet-graph.v1",
        "node_feature_version": "d5.tracklet-node-features.v1",
        "edge_feature_version": "d5.tracklet-edge-features.v1",
        "evaluator_label_schema_version": "d5.tracklet-evaluator-labels.v1",
        "split_policy": {
            "edge_level_random_split": False,
            "shared_seed_values_atomic_across_scenarios": True,
            "unit": "whole_episode_grouped_by_scenario_version_and_seed",
            "split_seed": 20260720,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
        },
        "episodes": episodes,
        "class_balance_by_split": {
            split: _balance(len(seeds)) for split, seeds in _SPLIT_SEEDS.items()
        },
        "candidate_recall_availability": {
            "status": "available",
            "available_episode_count": 100,
            "episode_count": 100,
        },
    }


def _canonical_view(source_sha256: str) -> dict[str, Any]:
    return _with_content_sha(
        {
            "schema_version": "d5.canonical-seed-split-view.v1",
            "consumer": "tracklet_graph",
            "source": {"manifest_sha256": source_sha256},
            "view_contract": {
                "source_manifest_modified": False,
                "source_artifacts_modified": False,
                "complete_episode_rebucket_only": True,
                "sample_copy_allowed": False,
                "online_offline_content_rewrite_allowed": False,
                "default_legacy_loader_unchanged": True,
            },
            "canonical_split": {
                "seed_counts": _SEED_COUNTS,
                "seed_values": _SPLIT_SEEDS,
                "reserved_evaluation_seed_overlap": [],
            },
        }
    )


def _admission_flags() -> dict[str, Any]:
    return {
        "full_sample_audit_required": True,
        "g1_assist_allowed": False,
        "global_track_id_created_or_rebound": False,
        "model_training_performed": False,
        "producer_complete": True,
        "pt_generated": False,
    }


def _readiness(training_sha256: str) -> dict[str, Any]:
    selected = {
        "episode_count": 200,
        "candidate_edge_count": 400,
        "unlabeled_candidate_edge_count": 0,
        "label_availability_ratio": 1.0,
        "seed_counts": _SEED_COUNTS,
        "reserved_evaluation_seed_overlap": [],
        "training_set_sha256": training_sha256,
    }
    return {
        "schema_version": "d5.tracklet-composite-admission-readiness.v1",
        "criteria": deepcopy(dict(D5_CLEAN_GRAPH_CRITERIA)),
        "data_support_readiness": {
            "existing_gate_results": [{"name": "clean_labels", "passed": True}],
            "passed": True,
            "status": "pass",
            "label_availability_100_percent": True,
        },
        "training_readiness": {
            "passed": True,
            "status": "pass",
            "failure_reasons": [],
        },
        "promotion_readiness": {
            "g1_assist_eligible": False,
            "model_training_performed": False,
            "pt_generated": False,
            "passed": False,
            "status": "awaiting_new_model_evidence",
        },
        "identity_safety": {
            "deterministic_rule_fallback_preserved": True,
            "geometry_gate_preserved": True,
            "global_track_id_rewrite_allowed": False,
            "same_camera_mutual_exclusion_preserved": True,
            "model_output": "same_target_probability_on_existing_candidate_edges_only",
        },
        "selected_corpus": selected,
        "split_summaries": {
            split: {
                "positive_candidate_edges": len(seeds) * 2,
                "negative_candidate_edges": len(seeds) * 2,
                "unlabeled_candidate_edges": 0,
            }
            for split, seeds in _SPLIT_SEEDS.items()
        },
    }


def _artifact(path: Path) -> D5CleanGraphArtifact:
    return D5CleanGraphArtifact(path=path, sha256=_sha_file(path))


def _build_fixture(root: Path) -> _Fixture:
    paths = {
        "supplemental_summary": root / "supplemental_summary.json",
        "composite_admission": root / "composite_admission.json",
        "composite_view": root / "composite_view.json",
        "formal_canonical_view": root / "formal_view.json",
        "supplemental_canonical_view": root / "supplemental_view.json",
        "supplemental_manifest": root / "supplemental_manifest.json",
        "supplemental_dataset_manifest": root / "supplemental_dataset.json",
        "formal_source_manifest": root / "formal_dataset.json",
    }
    _write_json(paths["formal_source_manifest"], _dataset("formal"))
    _write_json(paths["supplemental_dataset_manifest"], _dataset("supplemental"))
    formal_sha = _sha_file(paths["formal_source_manifest"])
    supplemental_dataset_sha = _sha_file(paths["supplemental_dataset_manifest"])

    _write_json(
        paths["formal_canonical_view"],
        _canonical_view(formal_sha),
    )
    _write_json(
        paths["supplemental_canonical_view"],
        _canonical_view(supplemental_dataset_sha),
    )

    supplemental_manifest = _with_content_sha(
        {
            "schema_version": "d5.tracklet-supplemental-manifest.v1",
            "source": {"git_commit": "1" * 40, "repository_dirty": False},
            "formal_source": {
                "manifest_sha256": formal_sha,
                "modified": False,
            },
            "dataset": {
                "manifest_sha256": supplemental_dataset_sha,
                "episode_count": 100,
                "candidate_edge_count": 200,
                "class_balance": _balance(100),
            },
            "admission": _admission_flags(),
            "seed_registries": {
                "canonical_seed_counts": _SEED_COUNTS,
                "reserved_evaluation_seeds": list(range(1000, 1020)),
                "reserved_seed_overlap": [],
            },
        }
    )
    _write_json(paths["supplemental_manifest"], supplemental_manifest)
    supplemental_manifest_sha = _sha_file(paths["supplemental_manifest"])

    training_sha = "a" * 64
    readiness = _readiness(training_sha)
    composite_view = _with_content_sha(
        {
            "schema_version": "d5.tracklet-composite-admission-view.v1",
            "selection_policy_version": "d5-tracklet-complete-label-source-selection-v1",
            "source_contract": {
                "complete_seed_atomic_split_required": True,
                "reserved_seed_allowed": False,
                "sample_copy_allowed": False,
                "source_artifact_modified": False,
                "source_label_backfill_allowed": False,
                "source_manifest_modified": False,
            },
            "sources": {
                "formal_source_modified": False,
                "supplemental_source_modified": False,
                "supplemental_source_repository_dirty": False,
                "formal_manifest_sha256": formal_sha,
                "supplemental_manifest_sha256": supplemental_manifest_sha,
            },
            "canonical_subviews": {
                "formal": {
                    "file": paths["formal_canonical_view"].name,
                    "file_sha256": _sha_file(paths["formal_canonical_view"]),
                    "content_sha256": json.loads(
                        paths["formal_canonical_view"].read_text(encoding="utf-8")
                    )["content_sha256"],
                },
                "supplemental": {
                    "file": paths["supplemental_canonical_view"].name,
                    "file_sha256": _sha_file(paths["supplemental_canonical_view"]),
                    "content_sha256": json.loads(
                        paths["supplemental_canonical_view"].read_text(
                            encoding="utf-8"
                        )
                    )["content_sha256"],
                },
            },
            "selection": deepcopy(readiness["selected_corpus"]),
            "readiness": readiness,
        }
    )
    _write_json(paths["composite_view"], composite_view)
    composite_view_sha = _sha_file(paths["composite_view"])

    composite_admission = deepcopy(readiness)
    composite_admission.update(
        {
            "view_manifest_sha256": composite_view_sha,
            "view_content_sha256": composite_view["content_sha256"],
            "sources": {
                "formal_manifest_sha256": formal_sha,
                "supplemental_manifest_sha256": supplemental_manifest_sha,
                "formal_source_modified": False,
                "supplemental_source_modified": False,
                "supplemental_source_repository_dirty": False,
            },
        }
    )
    _write_json(
        paths["composite_admission"],
        _with_content_sha(composite_admission),
    )

    summary = _with_content_sha(
        {
            "schema_version": "d5.tracklet-supplemental-summary.v1",
            "source_repository_dirty": False,
            "canonical_seed_counts": _SEED_COUNTS,
            "unique_seed_count": 100,
            "manifest_sha256": supplemental_manifest_sha,
            "dataset_manifest_sha256": supplemental_dataset_sha,
            "formal_manifest_sha256": formal_sha,
            "scenario_scale_cell_count": 45,
            "episode_count": 100,
            "candidate_edge_count": 200,
            "class_balance": _balance(100),
            "label_availability_ratio": 1.0,
            "admission": _admission_flags(),
        }
    )
    _write_json(paths["supplemental_summary"], summary)
    inputs = D5CleanGraphEvidenceInputs(
        **{name: _artifact(path) for name, path in paths.items()}
    )
    return _Fixture(inputs=inputs, paths=paths)


def _mutate_json_artifact(
    fixture: _Fixture,
    name: str,
    mutation: Callable[[dict[str, Any]], None],
) -> D5CleanGraphEvidenceInputs:
    path = fixture.paths[name]
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    if "content_sha256" in payload:
        payload = _with_content_sha(payload)
    _write_json(path, payload)
    return replace(fixture.inputs, **{name: _artifact(path)})


def _model_bundle_manifest(weights: Path) -> dict[str, Any]:
    source_files = {
        name: _sha_bytes(f"model-source:{name}".encode("ascii"))
        for name in _MODEL_IMPLEMENTATION_FILES
    }
    return {
        "schema_version": "d5.tracklet-model-bundle.v3",
        "model_semantic_version": "1.0.0",
        "dataset_schema_version": "d5.tracklet-dataset.v2",
        "graph_schema_version": "d5.sparse-tracklet-graph.v1",
        "node_feature_version": "d5.tracklet-node-features.v1",
        "edge_feature_version": "d5.tracklet-edge-features.v1",
        "node_feature_names": _MODEL_NODE_FEATURE_NAMES,
        "edge_feature_names": _MODEL_EDGE_FEATURE_NAMES,
        "architecture": {
            "class_name": "NativeTrackletEdgeClassifier",
            "node_feature_dim": len(_MODEL_NODE_FEATURE_NAMES),
            "edge_feature_dim": len(_MODEL_EDGE_FEATURE_NAMES),
            "hidden_dim": 8,
            "message_passing_steps": 1,
            "dropout": 0.0,
        },
        "training_dataset": {
            "dataset_manifest_sha256": "1" * 64,
            "split_sha256": "2" * 64,
            "training_set_sha256": "a" * 64,
            "training_config_sha256": "3" * 64,
        },
        "code_provenance": {
            "implementation_sha256": _sha_bytes(
                _d5_canonical_bytes(dict(sorted(source_files.items())))
            ),
            "source_files": source_files,
        },
        "calibration": {
            "method": "validation_only_scalar_temperature",
            "source_split": "validation",
            "temperature": 1.0,
            "decision_threshold": 0.6,
            "threshold_objective": "validation_f1",
        },
        "validation_results": {"f1": {"available": True, "value": 0.97}},
        "weights": {
            "filename": "weights.pt",
            "format": "pytorch_state_dict_weights_only",
            "sha256": _sha_file(weights),
            "size_bytes": weights.stat().st_size,
        },
        "admission": {
            "status": "development_only_fail_closed",
            "default_model": False,
            "g1_assist_eligible": False,
            "readiness_audit_sha256": "4" * 64,
        },
    }


def _attach_model_bundle(
    fixture: _Fixture,
    *,
    cell_count: int = 45,
    extra_report_field: bool = False,
) -> D5CleanGraphEvidenceInputs:
    weights = fixture.paths["supplemental_summary"].parent / "model.pt"
    config = fixture.paths["supplemental_summary"].parent / "model_config.json"
    report_path = fixture.paths["supplemental_summary"].parent / "model_report.json"
    weights.write_bytes(b"synthetic-contract-test-weights")
    _write_json(config, _model_bundle_manifest(weights))
    metrics = {
        "precision": 0.98,
        "recall": 0.96,
        "f1": 0.97,
        "candidate_recall": 0.99,
        "false_merge_rate": 0.005,
        "ece": 0.02,
    }
    report: dict[str, Any] = {
        "schema_version": "d5.tracklet-graph-model-evaluation.v1",
        "evaluation_date": "2026-07-21",
        "model_id": "synthetic-contract-test-only",
        "weights_sha256": _sha_file(weights),
        "config_sha256": _sha_file(config),
        "training_source_sha256": "a" * 64,
        "test_seed_values": _SPLIT_SEEDS["test"],
        "test_metrics": metrics,
        "cell_metrics": [
            {
                "cell_id": f"cell-{index:02d}",
                "scenario": "contract-test",
                "scale": index + 1,
                "sample_count": 10,
                **metrics,
            }
            for index in range(cell_count)
        ],
        "latency": {
            "device": "synthetic-test-device",
            "sample_count": 100,
            "p50_ms": 10.0,
            "p95_ms": 20.0,
            "max_ms": 30.0,
        },
    }
    if extra_report_field:
        report["g1_allowed"] = True
    _write_json(report_path, _with_content_sha(report))
    fixture.paths.update(
        {
            "model_report": report_path,
            "model_weights": weights,
            "model_config": config,
        }
    )
    return replace(
        fixture.inputs,
        model_report=_artifact(report_path),
        model_weights=_artifact(weights),
        model_config=_artifact(config),
    )


def _heldout_metric_values(*, passed: bool) -> dict[str, dict[str, Any]]:
    precision = 0.98 if passed else 0.5
    return {
        "precision": {"available": True, "value": precision},
        "recall": {"available": True, "value": 0.96},
        "f1": {"available": True, "value": 0.97 if passed else 0.65},
        "false_merge_rate": {"available": True, "value": 0.005},
        "candidate_recall": {"available": True, "value": 0.99},
        "brier_score": {"available": True, "value": 0.01},
        "ece": {"available": True, "value": 0.02},
        "p50_inference_latency_ms": {"available": True, "value": 10.0},
        "p95_inference_latency_ms": {"available": True, "value": 20.0},
    }


def _heldout_metric_gates(
    metrics: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    limits = (
        ("precision", ">=", 0.95),
        ("recall", ">=", 0.9),
        ("f1", ">=", 0.92),
        ("false_merge_rate", "<=", 0.01),
        ("candidate_recall", ">=", 0.95),
        ("ece", "<=", 0.05),
        ("p95_inference_latency_ms", "<=", 100.0),
    )
    result = []
    for name, operator, threshold in limits:
        item = metrics[name]
        value = item["value"] if item["available"] else None
        passed = bool(
            item["available"]
            and (
                float(value) >= threshold
                if operator == ">="
                else float(value) <= threshold
            )
        )
        result.append(
            {
                "name": name,
                "available": item["available"],
                "value": value,
                "operator": operator,
                "threshold": threshold,
                "passed": passed,
            }
        )
    return result


def _heldout_group(
    *,
    episode_count: int,
    edge_count: int,
    passed: bool,
) -> dict[str, Any]:
    return {
        "episode_count": episode_count,
        "complete_truth": True,
        "truth_scope": "complete_graph_truth_evaluator_only",
        "labeled_candidate_edge_count": edge_count,
        "decision_threshold": 0.6,
        "temperature": 1.0,
        "metrics": _heldout_metric_values(passed=passed),
        "latency": {
            "device": "synthetic-test-device",
            "sample_count": episode_count * 3,
            "p50_ms": 10.0,
            "p95_ms": 20.0,
            "max_ms": 30.0,
        },
    }


def _heldout_assessment(
    overall: dict[str, Any],
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    overall_gates = _heldout_metric_gates(overall["metrics"])
    cell_assessments = []
    for cell in cells:
        gates = _heldout_metric_gates(cell["metrics"])
        cell_assessments.append(
            {
                "cell_id": cell["cell_id"],
                "gates": gates,
                "passed": all(item["passed"] for item in gates),
            }
        )
    passed = all(item["passed"] for item in overall_gates) and all(
        item["passed"] for item in cell_assessments
    )
    reasons = [
        f"overall:{item['name']}" for item in overall_gates if not item["passed"]
    ]
    reasons.extend(
        f"cell:{item['cell_id']}"
        for item in cell_assessments
        if not item["passed"]
    )
    return {
        "status": "pass" if passed else "fail_closed",
        "passed": passed,
        "overall_gates": overall_gates,
        "cell_catalog_gate": {"actual": 45, "expected": 45, "passed": True},
        "cell_assessments": cell_assessments,
        "failure_reasons": reasons,
        "paired_shadow_satisfied": False,
        "g1_assist_eligible": False,
        "authority_enabled": False,
    }


def _build_heldout_manifest(path: Path) -> dict[str, Any]:
    gate_sha = _sha_bytes(_d5_canonical_bytes(_HELDOUT_GATE_CONFIG))
    generation_config_sha = "5" * 64
    episodes: list[dict[str, Any]] = []
    for seed in _HELDOUT_SEEDS:
        for scenario, scale in _HELDOUT_CELLS:
            uid = f"heldout-{scenario}-{scale}v{scale}-s{seed:04d}"
            episodes.append(
                {
                    "episode_uid": uid,
                    "scenario_version": f"{scenario}-{scale}v{scale}-v1",
                    "seed": seed,
                    "episode_id": f"d5-heldout-{scenario}-{scale}v{scale}-s{seed:04d}-frame-000000",
                    "graph_file": f"graphs/{uid}.graph.npz",
                    "graph_sha256": _sha_bytes(f"graph:{uid}".encode("ascii")),
                    "labels_file": f"labels/{uid}.labels.json",
                    "labels_sha256": _sha_bytes(f"labels:{uid}".encode("ascii")),
                    "config_sha256": generation_config_sha,
                    "node_count": 4,
                    "edge_count": 2,
                    "class_balance": _balance(1),
                    "labels_complete": True,
                    "candidate_recall_available": True,
                    "hard_negative_provenance": {
                        "source": "heldout_physical_projection_after_default_geometry_gates",
                        "truth_use": "offline_exact_observation_lineage_only",
                        "candidate_gate_config_sha256": gate_sha,
                        "evaluation_role": "held_out_evaluation",
                    },
                    "schema_version": "d5.tracklet-heldout-episode.v1",
                    "evaluation_role": "held_out_evaluation",
                    "split": "held_out_evaluation",
                    "scenario": scenario,
                    "scale": scale,
                }
            )
    config_sha = "6" * 64
    lineage_sha = "7" * 64
    inventory = [
        {
            "path": "heldout_dataset/heldout_config.json",
            "sha256": config_sha,
            "size_bytes": 100,
        },
        {
            "path": "evaluator/observation_lineage.json.gz",
            "sha256": lineage_sha,
            "size_bytes": 100,
        },
    ]
    for descriptor in episodes:
        inventory.extend(
            [
                {
                    "path": f"heldout_dataset/{descriptor['graph_file']}",
                    "sha256": descriptor["graph_sha256"],
                    "size_bytes": 100,
                },
                {
                    "path": f"heldout_dataset/{descriptor['labels_file']}",
                    "sha256": descriptor["labels_sha256"],
                    "size_bytes": 100,
                },
                {
                    "path": (
                        "heldout_dataset/episodes/"
                        f"{descriptor['episode_uid']}.episode.json"
                    ),
                    "sha256": _sha_bytes(_d5_canonical_bytes(descriptor)),
                    "size_bytes": 100,
                },
            ]
        )
    inventory.sort(key=lambda item: item["path"])
    implementation = {
        name: _sha_bytes(f"heldout-source:{name}".encode("ascii"))
        for name in _HELDOUT_IMPLEMENTATION_FILES
    }
    manifest = {
        "schema_version": D5_HELDOUT_CORPUS_SCHEMA_VERSION,
        "evaluation_role": "held_out_evaluation",
        "created_at_utc": "2026-07-21T12:00:00Z",
        "profile": {
            "profile_version": "d5-tracklet-heldout-1000-1019-full-v1",
            "evaluation_role": "held_out_evaluation",
            "seeds": _HELDOUT_SEEDS,
            "scenario_cells": [
                {"scenario": scenario, "scale": scale}
                for scenario, scale in _HELDOUT_CELLS
            ],
            "frames_per_seed_cell": 1,
            "expected_frame_count": 900,
            "training_split_registry_used": False,
        },
        "training_split_registry_used": False,
        "source": {
            "git_commit": "f" * 40,
            "repository_dirty": False,
            "implementation_sha256": implementation,
        },
        "read_only_training_sources": {
            "formal": {
                "manifest_file": "manifest.json",
                "manifest_sha256": "8" * 64,
                "modified": False,
            },
            "supplemental": {
                "manifest_file": "supplemental_manifest.json",
                "manifest_sha256": "9" * 64,
                "modified": False,
            },
            "samples_copied_or_rewritten": False,
        },
        "config": {
            "file": "heldout_dataset/heldout_config.json",
            "sha256": config_sha,
            "generation_config_sha256": generation_config_sha,
        },
        "candidate_gate": {
            "policy": "unchanged_sparse_tracklet_default",
            "config": _HELDOUT_GATE_CONFIG,
            "config_sha256": gate_sha,
            "aggregate_counts": {"retained_edges": 1800},
        },
        "evaluator_lineage": {
            "file": "evaluator/observation_lineage.json.gz",
            "sha256": lineage_sha,
            "record_count": 3600,
            "physically_separate_from_online_graph": True,
        },
        "episodes": episodes,
        "counts": {
            "episode_count": 900,
            "seed_count": 20,
            "scenario_scale_cell_count": 45,
            "node_count": 3600,
            "candidate_edge_count": 1800,
            "class_balance": _balance(900),
            "factor_counts": {"dual_class_frames": 900},
        },
        "identity_and_truth_safety": {
            "anonymous_online_tracklets": True,
            "online_truth_feature_count": 0,
            "same_camera_candidate_edge_count": 0,
            "global_track_id_created_or_rebound": False,
            "all_episodes_held_out_evaluation": True,
            "train_validation_test_assignment_count": 0,
        },
        "artifact_inventory": inventory,
        "artifact_inventory_sha256": _sha_bytes(
            _d5_canonical_bytes({"artifacts": inventory})
        ),
    }
    result = _with_d5_content_sha(manifest)
    _write_json(path, result)
    return result


def _build_heldout_report(
    path: Path,
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    model_config: Path,
    model_weights: Path,
    passed: bool,
) -> dict[str, Any]:
    overall = _heldout_group(episode_count=900, edge_count=1800, passed=passed)
    cells = [
        {
            "cell_id": f"{scenario}-{scale}v{scale}",
            "scenario": scenario,
            "scale": scale,
            **_heldout_group(episode_count=20, edge_count=40, passed=passed),
        }
        for scenario, scale in _HELDOUT_CELLS
    ]
    assessment = _heldout_assessment(overall, cells)
    blockers = ["paired_shadow_not_run", "internal_model_test_report_not_bound"]
    if not assessment["passed"]:
        blockers.insert(0, "held_out_1000_1019_not_passed")
    config_payload = json.loads(model_config.read_text(encoding="utf-8"))
    weights_sha = _sha_file(model_weights)
    report = {
        "schema_version": D5_HELDOUT_EVALUATION_SCHEMA_VERSION,
        "evaluated_at_utc": "2026-07-21T12:10:00Z",
        "evaluation_role": "held_out_evaluation",
        "heldout_corpus": {
            "manifest_sha256": _sha_file(manifest_path),
            "manifest_content_sha256": manifest["content_sha256"],
            "profile_version": "d5-tracklet-heldout-1000-1019-full-v1",
            "episode_count": 900,
            "seed_values": _HELDOUT_SEEDS,
            "scenario_scale_cell_count": 45,
        },
        "development_model": {
            "model_id": f"d5-tracklet-development-{weights_sha[:16]}",
            "bundle_manifest_sha256": _sha_file(model_config),
            "weights_sha256": weights_sha,
            "training_dataset": config_payload["training_dataset"],
            "admission_status": "development_only_fail_closed",
        },
        "frozen_decision": {
            "temperature": 1.0,
            "decision_threshold": 0.6,
            "source": "development_bundle_validation_calibration",
            "temperature_or_threshold_selection_performed": False,
            "weight_update_performed": False,
        },
        "overall": overall,
        "cell_metrics": cells,
        "heldout_assessment": assessment,
        "identity_and_truth_safety": {
            "online_truth_feature_count": 0,
            "same_camera_candidate_edge_count": 0,
            "unlabeled_candidate_edge_count": 0,
            "global_track_id_created_or_rebound": False,
            "truth_scope": "physically_separate_evaluator_only",
            "model_weights_unchanged": True,
            "model_config_unchanged": True,
            "heldout_corpus_unchanged": True,
        },
        "layers": {
            "data_support": {"status": "pass", "passed": True},
            "internal_model_test": {
                "status": "source_bundle_development_only",
                "passed": False,
                "authority": False,
            },
            "held_out_1000_1019": assessment,
            "paired_shadow": {"status": "not_run", "passed": False},
            "g1_assist_authority": {
                "status": "fail_closed",
                "passed": False,
                "g1_assist_eligible": False,
                "assist_enabled": False,
                "authority_enabled": False,
                "blockers": blockers,
            },
        },
        "implementation_sha256": {
            name: _sha_bytes(f"heldout-evaluator:{name}".encode("ascii"))
            for name in _HELDOUT_IMPLEMENTATION_FILES
        },
    }
    result = _with_d5_content_sha(report)
    _write_json(path, result)
    return result


def _attach_heldout_evidence(
    fixture: _Fixture,
    *,
    passed: bool = True,
) -> D5CleanGraphEvidenceInputs:
    inputs = _attach_model_bundle(fixture)
    root = fixture.paths["supplemental_summary"].parent
    manifest_path = root / "heldout_manifest.json"
    report_path = root / "heldout_evaluation.json"
    manifest = _build_heldout_manifest(manifest_path)
    assert inputs.model_config is not None
    assert inputs.model_weights is not None
    _build_heldout_report(
        report_path,
        manifest_path=manifest_path,
        manifest=manifest,
        model_config=inputs.model_config.path,
        model_weights=inputs.model_weights.path,
        passed=passed,
    )
    fixture.paths.update(
        {
            "heldout_manifest": manifest_path,
            "heldout_evaluation_report": report_path,
        }
    )
    return replace(
        inputs,
        heldout_manifest=_artifact(manifest_path),
        heldout_evaluation_report=_artifact(report_path),
    )


def _mutate_heldout_artifact(
    inputs: D5CleanGraphEvidenceInputs,
    *,
    name: str,
    mutation: Callable[[dict[str, Any]], None],
    refresh_content_sha: bool = True,
) -> D5CleanGraphEvidenceInputs:
    artifact = getattr(inputs, name)
    assert artifact is not None
    payload = json.loads(artifact.path.read_text(encoding="utf-8"))
    mutation(payload)
    if refresh_content_sha:
        payload = _with_d5_content_sha(payload)
    _write_json(artifact.path, payload)
    return replace(inputs, **{name: _artifact(artifact.path)})


def _assert_error(code: str, callable_: Callable[[], object]) -> None:
    with pytest.raises(D5CleanGraphEvidenceError) as caught:
        callable_()
    assert caught.value.code == code


def test_clean_data_is_complete_but_model_and_promotion_remain_closed(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    result = audit_d5_clean_graph_evidence(fixture.inputs)

    layers = result["evidence_layers"]
    assert layers["data_support"]["status"] == "complete"
    assert layers["training_source"]["status"] == "complete"
    assert layers["internal_model_test"]["status"] == "unavailable"
    assert layers["held_out_seed"]["status"] == "unavailable"
    assert layers["paired_shadow"]["status"] == "unavailable"
    assert result["data_summary"]["reserved_seed_overlap"] == []
    assert result["data_summary"]["unlabeled_candidate_edge_count"] == 0
    assert result["admission"] == {
        "clean_data_supported": True,
        "training_source_supported": True,
        "model_promotion_allowed": False,
        "g1_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "formal_ppo_reward_available": False,
        "causal_claim_available": False,
        "counterfactual_available": False,
        "status": "data_ready_model_admission_closed",
        "promotion_blockers": [
            "internal_model_test_unavailable",
            "held_out_seed_evaluation_unavailable",
            "same_seed_paired_shadow_unavailable",
            "g1_assist_authority_not_admitted",
        ],
    }


def test_input_spec_and_cli_are_hash_bound(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    spec = tmp_path / "inputs.json"
    _write_json(spec, fixture.inputs.to_dict())
    loaded = load_d5_clean_graph_evidence_inputs(
        spec,
        expected_sha256=_sha_file(spec),
    )
    assert loaded.resolved() == fixture.inputs.resolved()

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_d5_clean_graph_evidence.py"
    )
    output_dir = tmp_path / "report"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--inputs-json",
            str(spec),
            "--inputs-sha256",
            _sha_file(spec),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert (output_dir / "d5_clean_graph_evidence.json").is_file()
    assert (output_dir / "D5_CLEAN_GRAPH_EVIDENCE_CN.md").is_file()

    _assert_error(
        "input_specification_sha256_mismatch",
        lambda: load_d5_clean_graph_evidence_inputs(
            spec,
            expected_sha256="0" * 64,
        ),
    )


def test_artifact_file_hash_tamper_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    with fixture.paths["supplemental_summary"].open("ab") as stream:
        stream.write(b" ")
    _assert_error(
        "supplemental_summary_sha256_mismatch",
        lambda: audit_d5_clean_graph_evidence(fixture.inputs),
    )


def test_dirty_source_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _mutate_json_artifact(
        fixture,
        "supplemental_summary",
        lambda value: value.update(source_repository_dirty=True),
    )
    _assert_error(
        "dirty_training_source",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_source_rewrite_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    def mutate(value: dict[str, Any]) -> None:
        value["view_contract"]["source_manifest_modified"] = True

    inputs = _mutate_json_artifact(
        fixture,
        "formal_canonical_view",
        mutate,
    )
    _assert_error(
        "source_rewrite_detected",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_reserved_seed_leakage_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    def mutate(value: dict[str, Any]) -> None:
        value["canonical_split"]["seed_values"]["test"][0] = 1000

    inputs = _mutate_json_artifact(
        fixture,
        "formal_canonical_view",
        mutate,
    )
    _assert_error(
        "reserved_seed_leakage",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_unlabeled_edge_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    def mutate(value: dict[str, Any]) -> None:
        value["class_balance"]["positive_candidate_edges"] -= 1
        value["class_balance"]["unlabeled_candidate_edges"] = 1

    inputs = _mutate_json_artifact(
        fixture,
        "supplemental_summary",
        mutate,
    )
    _assert_error(
        "clean_edge_support_incomplete",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_lowered_admission_threshold_fails_closed(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")

    def mutate(value: dict[str, Any]) -> None:
        value["criteria"]["minimum_test_precision"] = 0.90

    inputs = _mutate_json_artifact(
        fixture,
        "composite_admission",
        mutate,
    )
    _assert_error(
        "admission_threshold_contract_mismatch",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_partial_model_bundle_is_rejected_before_audit(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    report = tmp_path / "model_report.json"
    _write_json(report, {})
    with pytest.raises(ValueError, match="must be supplied together"):
        replace(fixture.inputs, model_report=_artifact(report))


@pytest.mark.parametrize(
    ("cell_count", "extra_report_field", "expected_code"),
    [
        (44, False, "model_cell_count_mismatch"),
        (45, True, "object_keys_mismatch"),
    ],
)
def test_forged_or_incomplete_model_report_fails_closed(
    tmp_path: Path,
    cell_count: int,
    extra_report_field: bool,
    expected_code: str,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _attach_model_bundle(
        fixture,
        cell_count=cell_count,
        extra_report_field=extra_report_field,
    )
    _assert_error(
        expected_code,
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


def test_complete_synthetic_internal_test_does_not_open_external_gates(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    result = audit_d5_clean_graph_evidence(_attach_model_bundle(fixture))

    assert result["evidence_layers"]["internal_model_test"]["status"] == "complete"
    assert result["evidence_layers"]["held_out_seed"]["status"] == "unavailable"
    assert result["evidence_layers"]["paired_shadow"]["status"] == "unavailable"
    assert result["admission"]["model_promotion_allowed"] is False
    assert result["admission"]["g1_allowed"] is False
    assert result["admission"]["assist_allowed"] is False
    assert result["admission"]["authority_allowed"] is False
    assert result["admission"]["rule_fallback_required"] is True
    assert result["admission"]["formal_ppo_reward_available"] is False


def test_complete_synthetic_heldout_only_completes_heldout_layer(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    result = audit_d5_clean_graph_evidence(_attach_heldout_evidence(fixture))

    assert result["evidence_layers"]["internal_model_test"]["status"] == "complete"
    heldout = result["evidence_layers"]["held_out_seed"]
    assert heldout["status"] == "complete"
    assert heldout["producer_status"] == "pass"
    assert heldout["episode_count"] == 900
    assert heldout["seed_count"] == 20
    assert heldout["cell_count"] == 45
    assert result["evidence_layers"]["paired_shadow"]["status"] == "unavailable"
    assert result["admission"]["promotion_blockers"] == [
        "same_seed_paired_shadow_unavailable",
        "g1_assist_authority_not_admitted",
    ]
    assert result["admission"]["model_promotion_allowed"] is False
    assert result["admission"]["g1_allowed"] is False
    assert result["admission"]["assist_allowed"] is False
    assert result["admission"]["authority_allowed"] is False
    assert result["admission"]["rule_fallback_required"] is True


def test_synthetic_failed_heldout_metrics_are_failed_and_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    result = audit_d5_clean_graph_evidence(
        _attach_heldout_evidence(fixture, passed=False)
    )

    heldout = result["evidence_layers"]["held_out_seed"]
    assert heldout["status"] == "failed"
    assert heldout["producer_status"] == "fail_closed"
    assert heldout["thresholds_passed"] is False
    assert "held_out_seed_evaluation_failed" in result["admission"][
        "promotion_blockers"
    ]
    assert result["admission"]["g1_allowed"] is False
    assert result["admission"]["assist_allowed"] is False
    assert result["admission"]["authority_allowed"] is False
    assert result["admission"]["rule_fallback_required"] is True


def test_partial_or_unbound_heldout_pair_is_rejected(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    model_inputs = _attach_model_bundle(fixture)
    report = tmp_path / "heldout_evaluation.json"
    manifest = tmp_path / "heldout_manifest.json"
    _write_json(report, {})
    _write_json(manifest, {})

    with pytest.raises(ValueError, match="must be supplied together"):
        replace(
            model_inputs,
            heldout_evaluation_report=_artifact(report),
        )
    with pytest.raises(ValueError, match="requires the complete internal model bundle"):
        replace(
            fixture.inputs,
            heldout_evaluation_report=_artifact(report),
            heldout_manifest=_artifact(manifest),
        )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda value: value["profile"]["seeds"].pop(),
            "heldout_seed_catalog_mismatch",
        ),
        (
            lambda value: value["profile"]["scenario_cells"].pop(),
            "heldout_cell_catalog_mismatch",
        ),
        (
            lambda value: value["episodes"].pop(),
            "heldout_episode_count_mismatch",
        ),
    ],
)
def test_heldout_manifest_requires_exact_seed_cell_episode_catalog(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _attach_heldout_evidence(fixture)
    inputs = _mutate_heldout_artifact(
        inputs,
        name="heldout_manifest",
        mutation=mutation,
    )
    _assert_error(expected_code, lambda: audit_d5_clean_graph_evidence(inputs))


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda value: value["development_model"].update(
                weights_sha256="0" * 64
            ),
            "heldout_model_weight_hash_mismatch",
        ),
        (
            lambda value: value["development_model"].update(
                bundle_manifest_sha256="0" * 64
            ),
            "heldout_model_config_hash_mismatch",
        ),
        (
            lambda value: value["heldout_corpus"].update(
                manifest_sha256="0" * 64
            ),
            "heldout_manifest_hash_mismatch",
        ),
    ],
)
def test_heldout_report_rejects_weight_config_or_manifest_mismatch(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _attach_heldout_evidence(fixture)
    inputs = _mutate_heldout_artifact(
        inputs,
        name="heldout_evaluation_report",
        mutation=mutation,
    )
    _assert_error(expected_code, lambda: audit_d5_clean_graph_evidence(inputs))


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda value: value["frozen_decision"].update(
                temperature_or_threshold_selection_performed=True
            ),
            "heldout_threshold_reselection_detected",
        ),
        (
            lambda value: value["frozen_decision"].update(
                decision_threshold=0.4
            ),
            "heldout_threshold_reselection_detected",
        ),
        (
            lambda value: value["frozen_decision"].update(
                weight_update_performed=True
            ),
            "heldout_weight_update_detected",
        ),
    ],
)
def test_heldout_report_rejects_reselection_or_weight_update(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _attach_heldout_evidence(fixture)
    inputs = _mutate_heldout_artifact(
        inputs,
        name="heldout_evaluation_report",
        mutation=mutation,
    )
    _assert_error(expected_code, lambda: audit_d5_clean_graph_evidence(inputs))


def test_heldout_report_rejects_forged_authority(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _attach_heldout_evidence(fixture)

    def mutate(value: dict[str, Any]) -> None:
        value["layers"]["g1_assist_authority"]["authority_enabled"] = True

    inputs = _mutate_heldout_artifact(
        inputs,
        name="heldout_evaluation_report",
        mutation=mutate,
    )
    _assert_error(
        "heldout_authority_overstated",
        lambda: audit_d5_clean_graph_evidence(inputs),
    )


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_code"),
    [
        ("online_truth_feature_count", 1, "heldout_online_truth_leakage"),
        (
            "same_camera_candidate_edge_count",
            1,
            "heldout_same_camera_edge_leakage",
        ),
        ("unlabeled_candidate_edge_count", 1, "heldout_unlabeled_edge_leakage"),
        (
            "global_track_id_created_or_rebound",
            True,
            "heldout_global_track_id_rewrite",
        ),
    ],
)
def test_heldout_report_rejects_truth_edge_or_identity_leakage(
    tmp_path: Path,
    field: str,
    bad_value: object,
    expected_code: str,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _attach_heldout_evidence(fixture)

    def mutate(value: dict[str, Any]) -> None:
        value["identity_and_truth_safety"][field] = bad_value

    inputs = _mutate_heldout_artifact(
        inputs,
        name="heldout_evaluation_report",
        mutation=mutate,
    )
    _assert_error(expected_code, lambda: audit_d5_clean_graph_evidence(inputs))


def test_heldout_report_rejects_unknown_fields_and_content_hash_tamper(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "unknown")
    inputs = _attach_heldout_evidence(fixture)
    unknown = _mutate_heldout_artifact(
        inputs,
        name="heldout_evaluation_report",
        mutation=lambda value: value.update(authority_allowed=True),
    )
    _assert_error(
        "object_keys_mismatch",
        lambda: audit_d5_clean_graph_evidence(unknown),
    )

    fixture = _build_fixture(tmp_path / "content-hash")
    inputs = _attach_heldout_evidence(fixture)
    tampered = _mutate_heldout_artifact(
        inputs,
        name="heldout_evaluation_report",
        mutation=lambda value: value["heldout_corpus"].update(episode_count=899),
        refresh_content_sha=False,
    )
    _assert_error(
        "content_sha256_mismatch",
        lambda: audit_d5_clean_graph_evidence(tampered),
    )


def test_heldout_caller_sha_tamper_fails_before_json_consumption(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    inputs = _attach_heldout_evidence(fixture)
    assert inputs.heldout_manifest is not None
    tampered = replace(
        inputs,
        heldout_manifest=D5CleanGraphArtifact(
            inputs.heldout_manifest.path,
            "0" * 64,
        ),
    )
    _assert_error(
        "heldout_manifest_sha256_mismatch",
        lambda: audit_d5_clean_graph_evidence(tampered),
    )


def test_report_writer_does_not_mutate_inputs(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    before = {name: _sha_file(path) for name, path in fixture.paths.items()}
    outputs = write_d5_clean_graph_evidence_report(
        fixture.inputs,
        tmp_path / "output",
    )
    after = {name: _sha_file(path) for name, path in fixture.paths.items()}
    assert before == after
    assert set(outputs) == {"json", "markdown"}
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "模型内部测试" in markdown
    assert "unavailable" in markdown
    assert "G1、辅助模式和控制权限保持关闭" in markdown


def test_legacy_v1_input_spec_remains_read_only_unavailable(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path / "inputs")
    payload = fixture.inputs.to_dict()
    payload["schema_version"] = D5_CLEAN_GRAPH_LEGACY_INPUT_SCHEMA_VERSION
    payload.pop("heldout_evidence")
    loaded = D5CleanGraphEvidenceInputs.from_mapping(payload)

    assert loaded.schema_version == D5_CLEAN_GRAPH_LEGACY_INPUT_SCHEMA_VERSION
    assert loaded.to_dict() == payload
    result = audit_d5_clean_graph_evidence(loaded)
    assert result["evidence_layers"]["held_out_seed"]["status"] == "unavailable"

    payload["heldout_evidence"] = None
    _assert_error(
        "object_keys_mismatch",
        lambda: D5CleanGraphEvidenceInputs.from_mapping(payload),
    )


def test_input_spec_schema_upgrade_is_explicit() -> None:
    assert D5_CLEAN_GRAPH_LEGACY_INPUT_SCHEMA_VERSION == (
        "d6.d5-clean-graph-inputs.v1"
    )
    assert D5_CLEAN_GRAPH_INPUT_SCHEMA_VERSION == "d6.d5-clean-graph-inputs.v2"
