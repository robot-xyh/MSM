"""Fit lightweight candidates on train, select on validation, then freeze."""

from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from dual_optical_100target_gnn.dataset import (
    canonical_json_sha256,
    load_dataset_manifest,
    load_entry,
    sample_entries,
)
from dual_optical_100target_gnn.loader import sha256_file
from dual_optical_100target_gnn.metrics import AssociationMetrics, evaluate_assignment
from dual_optical_100target_gnn.schema import EDGE_FEATURE_NAMES, GraphLabels, OnlineGraph

from .assignment import assignment_acceptance_mask, solve_probability_assignment
from .models import (
    GEOMETRY_COMPONENT_NAMES,
    LOGISTIC_C_GRID,
    PROBABILITY_THRESHOLD_GRID,
    UNMATCHED_COST_GRID,
    LightweightModel,
    fit_all_models,
    model_complexity_key,
)


FREEZE_SCHEMA_VERSION = "dual-optical-100target-lightweight-freeze-v1"
MINIMUM_CONDITIONAL_PRECISION = 0.70


class ValidationSelectionError(RuntimeError):
    """Expected fail-closed rejection of all validation configurations."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        validation_rows: Iterable[Mapping[str, Any]],
        best_validation_result: Mapping[str, Any] | None,
    ) -> None:
        super().__init__(message)
        self.reason_code = str(reason_code)
        self.validation_rows = tuple(dict(row) for row in validation_rows)
        self.best_validation_result = (
            None
            if best_validation_result is None
            else dict(best_validation_result)
        )


@dataclass(frozen=True)
class TrainingConfig:
    random_seed: int = 20260820


def _load_split(
    manifest: Mapping[str, Any],
    dataset_root: Path,
    split: str,
    *,
    freeze_already_written: bool,
    access_log: list[dict[str, Any]],
) -> list[tuple[OnlineGraph, GraphLabels]]:
    if split == "test" and not freeze_already_written:
        raise RuntimeError("test split cannot be opened before freeze_manifest.json exists")
    loaded: list[tuple[OnlineGraph, GraphLabels]] = []
    for entry in sample_entries(manifest, split):
        graph, labels = load_entry(dataset_root, entry, include_labels=True)
        if labels is None:
            raise AssertionError("offline labels are required for fitting and scoring")
        loaded.append((graph, labels))
        access_log.append(
            {
                "split": split,
                "seed": int(entry["seed"]),
                "corruption_level": str(entry["corruption_level"]),
            }
        )
    return loaded


def _aggregate_metrics(metrics: Iterable[AssociationMetrics]) -> dict[str, float | int]:
    values = list(metrics)
    if not values:
        raise ValueError("at least one validation sample is required")
    selected_count = int(sum(item.selected_count for item in values))
    correct_count = int(sum(item.correct_count for item in values))
    return {
        "sample_count": len(values),
        "macro_precision": float(np.mean([item.precision for item in values])),
        "macro_recall": float(np.mean([item.recall for item in values])),
        "macro_f1": float(np.mean([item.f1 for item in values])),
        "selected_count": selected_count,
        "correct_count": correct_count,
        "conditional_precision": (
            float(correct_count / selected_count) if selected_count else 0.0
        ),
        "false_association_count": int(
            sum(item.false_association_count for item in values)
        ),
        "duplicate_identity_match_count": int(
            sum(item.duplicate_identity_match_count for item in values)
        ),
        "duplicate_track_assignment_count": int(
            sum(item.duplicate_track_assignment_count for item in values)
        ),
    }


def _validation_rows(
    models: Iterable[LightweightModel],
    validation_data: Iterable[tuple[OnlineGraph, GraphLabels]],
    geometry_gate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    validation_data = list(validation_data)
    rows: list[dict[str, Any]] = []
    for model in models:
        probabilities = [
            model.predict_proba(graph, geometry_gate) for graph, _ in validation_data
        ]
        all_probabilities = np.concatenate(probabilities) if probabilities else np.empty(0)
        all_labels = np.concatenate(
            [labels.edge_labels for _, labels in validation_data]
        )
        positive_probabilities = all_probabilities[all_labels > 0.5]
        negative_probabilities = all_probabilities[all_labels <= 0.5]

        def quantile(values: np.ndarray, probability: float) -> float | str:
            return float(np.quantile(values, probability)) if len(values) else ""

        distribution = {
            "positive_probability_p05": quantile(positive_probabilities, 0.05),
            "positive_probability_p50": quantile(positive_probabilities, 0.50),
            "positive_probability_p95": quantile(positive_probabilities, 0.95),
            "negative_probability_p05": quantile(negative_probabilities, 0.05),
            "negative_probability_p50": quantile(negative_probabilities, 0.50),
            "negative_probability_p95": quantile(negative_probabilities, 0.95),
        }
        for threshold in PROBABILITY_THRESHOLD_GRID:
            for unmatched_cost in UNMATCHED_COST_GRID:
                sample_metrics = []
                pre_correct = 0
                pre_incorrect = 0
                for (graph, labels), scores in zip(validation_data, probabilities):
                    accepted = assignment_acceptance_mask(
                        scores, threshold, unmatched_cost
                    )
                    pre_correct += int(np.sum(labels.edge_labels[accepted] > 0.5))
                    pre_incorrect += int(np.sum(labels.edge_labels[accepted] <= 0.5))
                    result = solve_probability_assignment(
                        graph, scores, threshold, unmatched_cost
                    )
                    sample_metrics.append(evaluate_assignment(graph, labels, result))
                aggregate = _aggregate_metrics(sample_metrics)
                rows.append(
                    {
                        "model_id": model.model_id,
                        "model_kind": model.kind,
                        "C": model.parameters.get("C", ""),
                        "probability_threshold": threshold,
                        "unmatched_cost": unmatched_cost,
                        "parameter_count": model.parameter_count,
                        "candidate_positive_edge_count": int(
                            np.sum(all_labels > 0.5)
                        ),
                        "candidate_negative_edge_count": int(
                            np.sum(all_labels <= 0.5)
                        ),
                        "pre_assignment_correct_edge_count": pre_correct,
                        "pre_assignment_incorrect_edge_count": pre_incorrect,
                        "post_assignment_correct_edge_count": int(
                            aggregate["correct_count"]
                        ),
                        "post_assignment_incorrect_edge_count": int(
                            aggregate["false_association_count"]
                        ),
                        **distribution,
                        **aggregate,
                    }
                )
    return rows


def _selection_key(
    row: Mapping[str, Any],
    model: LightweightModel,
) -> tuple[float | int, ...]:
    complexity = model_complexity_key(model)
    return (
        not bool(row["selection_eligible"]),
        -float(row["macro_recall"]),
        -float(row["macro_f1"]),
        -float(row["conditional_precision"]),
        int(row["false_association_count"]),
        int(row["duplicate_identity_match_count"]),
        *complexity,
        abs(float(row["probability_threshold"]) - 0.5),
        abs(float(row["unmatched_cost"]) - 0.6),
        float(row["probability_threshold"]),
        float(row["unmatched_cost"]),
    )


def _rank_validation_rows(
    rows: list[dict[str, Any]],
    models: Iterable[LightweightModel],
) -> list[dict[str, Any]]:
    model_by_id = {model.model_id: model for model in models}
    if not rows:
        raise ValidationSelectionError(
            "validation produced no candidate configurations",
            reason_code="no_validation_configurations",
            validation_rows=(),
            best_validation_result=None,
        )
    for row in rows:
        row["minimum_conditional_precision"] = MINIMUM_CONDITIONAL_PRECISION
        row["selection_eligible"] = bool(
            int(row["selected_count"]) > 0
            and float(row["conditional_precision"])
            >= MINIMUM_CONDITIONAL_PRECISION
        )
    nonzero_rows = [row for row in rows if int(row["selected_count"]) > 0]
    best_failed = (
        sorted(
            nonzero_rows,
            key=lambda row: (
                -float(row["conditional_precision"]),
                -float(row["macro_recall"]),
                -float(row["macro_f1"]),
                int(row["false_association_count"]),
                int(row["duplicate_identity_match_count"]),
                str(row["model_id"]),
                float(row["probability_threshold"]),
                float(row["unmatched_cost"]),
            ),
        )[0]
        if nonzero_rows
        else None
    )
    if not nonzero_rows:
        raise ValidationSelectionError(
            "validation produced zero assignments for every probability/unmatched policy",
            reason_code="zero_validation_assignments",
            validation_rows=rows,
            best_validation_result=None,
        )
    if not any(bool(row["selection_eligible"]) for row in rows):
        raise ValidationSelectionError(
            "validation produced no candidate meeting conditional precision >= 0.70",
            reason_code="conditional_precision_floor_not_met",
            validation_rows=rows,
            best_validation_result=best_failed,
        )
    ranked = sorted(rows, key=lambda row: _selection_key(row, model_by_id[row["model_id"]]))
    return [{"rank": rank, **row} for rank, row in enumerate(ranked, start=1)]


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty validation leaderboard")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def train_validate_and_freeze(
    dataset_manifest: str | Path,
    output_dir: str | Path,
    *,
    config: TrainingConfig | None = None,
) -> Path:
    """Fit and select without opening any reserved test graph or label file."""

    config = config or TrainingConfig()
    manifest_path = Path(dataset_manifest).resolve()
    manifest, dataset_root = load_dataset_manifest(manifest_path)
    access_log: list[dict[str, Any]] = []
    train_data = _load_split(
        manifest,
        dataset_root,
        "train",
        freeze_already_written=False,
        access_log=access_log,
    )
    validation_data = _load_split(
        manifest,
        dataset_root,
        "val",
        freeze_already_written=False,
        access_log=access_log,
    )
    if not train_data or not validation_data:
        raise ValueError("train and validation splits must both be non-empty")

    geometry_gate = dict(manifest["geometry_gate"])
    target_count = int(manifest["expected_target_count"])
    if target_count <= 0:
        raise ValueError("dataset manifest expected_target_count must be positive")
    models = fit_all_models(
        train_data,
        geometry_gate,
        random_seed=config.random_seed,
    )
    rows = _rank_validation_rows(
        _validation_rows(models, validation_data, geometry_gate), models
    )
    selected_row = rows[0]
    selected_model = next(
        model for model in models if model.model_id == selected_row["model_id"]
    )

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "selected_model.json"
    leaderboard_path = output_dir / "validation_leaderboard.csv"
    summary_path = output_dir / "training_summary.json"
    freeze_path = output_dir / "freeze_manifest.json"
    model_payload = selected_model.to_dict()
    model_path.write_text(
        json.dumps(model_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(leaderboard_path, rows)
    summary = {
        "schema_version": "dual-optical-lightweight-training-summary-v1",
        "training_seed": config.random_seed,
        "candidate_model_count": len(models),
        "candidate_configuration_count": len(rows),
        "logistic_c_grid": list(LOGISTIC_C_GRID),
        "probability_threshold_grid": list(PROBABILITY_THRESHOLD_GRID),
        "unmatched_cost_grid": list(UNMATCHED_COST_GRID),
        "selection_order": [
            "conditional_precision_at_least_0.70",
            "validation_macro_recall_descending",
            "validation_macro_f1_descending",
            "false_association_count_ascending",
            "duplicate_identity_match_count_ascending",
            "parameter_count_ascending",
        ],
        "selected_validation_row": selected_row,
        "target_count_from_dataset_manifest": target_count,
        "opened_before_freeze": access_log,
        "test_graph_files_opened_before_freeze": False,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    artifact_hashes = {
        "selected_model_sha256": sha256_file(model_path),
        "validation_leaderboard_sha256": sha256_file(leaderboard_path),
        "training_summary_sha256": sha256_file(summary_path),
    }
    freeze = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "dataset_manifest": str(manifest_path),
        "dataset_manifest_sha256": sha256_file(manifest_path),
        "dataset_fingerprint_sha256": manifest["dataset_fingerprint_sha256"],
        "expected_target_count": target_count,
        "selected_model": model_path.name,
        "validation_leaderboard": leaderboard_path.name,
        "training_summary": summary_path.name,
        **artifact_hashes,
        "selected_model_id": selected_model.model_id,
        "selected_model_kind": selected_model.kind,
        "selected_probability_threshold": float(
            selected_row["probability_threshold"]
        ),
        "selected_unmatched_cost": float(selected_row["unmatched_cost"]),
        "selected_model_parameters": dict(selected_model.parameters),
        "selected_model_parameter_count": selected_model.parameter_count,
        "train_seeds": list(manifest["splits"]["train"]),
        "validation_seeds": list(manifest["splits"]["val"]),
        "reserved_test_seeds": list(manifest["splits"]["test"]),
        "corruption_levels": list(manifest["corruption_levels"]),
        "selection_policy": {
            "primary_metric": "validation_macro_recall",
            "minimum_conditional_precision": MINIMUM_CONDITIONAL_PRECISION,
            "reserved_test_threshold_selection": False,
        },
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "geometry_component_names": list(GEOMETRY_COMPONENT_NAMES),
        "geometry_gate": geometry_gate,
        "test_graph_files_opened_before_freeze": False,
        "truth_policy": {
            "training_labels_only": True,
            "offline_scoring_only": True,
            "truth_fields_in_online_features": False,
        },
    }
    freeze["model_fingerprint_sha256"] = canonical_json_sha256(
        {
            "dataset_fingerprint_sha256": freeze["dataset_fingerprint_sha256"],
            "expected_target_count": freeze["expected_target_count"],
            "selected_model_sha256": freeze["selected_model_sha256"],
            "selected_model_id": freeze["selected_model_id"],
            "selected_probability_threshold": freeze[
                "selected_probability_threshold"
            ],
            "selected_unmatched_cost": freeze["selected_unmatched_cost"],
            "train_seeds": freeze["train_seeds"],
            "validation_seeds": freeze["validation_seeds"],
            "reserved_test_seeds": freeze["reserved_test_seeds"],
            "edge_feature_names": freeze["edge_feature_names"],
            "selection_policy": freeze["selection_policy"],
        }
    )
    freeze_path.write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return freeze_path


def verify_freeze_manifest(
    path: str | Path,
) -> tuple[dict[str, Any], Path, LightweightModel, dict[str, Any], Path]:
    path = Path(path).resolve()
    freeze = json.loads(path.read_text(encoding="utf-8"))
    if freeze.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise ValueError("unsupported lightweight freeze manifest")
    if freeze.get("test_graph_files_opened_before_freeze") is not False:
        raise ValueError("freeze manifest does not prove reserved-test isolation")
    root = path.parent
    artifacts = {
        "selected_model": "selected_model_sha256",
        "validation_leaderboard": "validation_leaderboard_sha256",
        "training_summary": "training_summary_sha256",
    }
    for path_key, hash_key in artifacts.items():
        artifact = root / freeze[path_key]
        if sha256_file(artifact) != freeze[hash_key]:
            raise ValueError(f"frozen artifact hash mismatch: {artifact}")

    manifest_path = Path(freeze["dataset_manifest"]).resolve()
    if sha256_file(manifest_path) != freeze["dataset_manifest_sha256"]:
        raise ValueError("frozen dataset manifest hash mismatch")
    manifest, dataset_root = load_dataset_manifest(manifest_path)
    expected_contract = {
        "dataset_fingerprint_sha256": manifest["dataset_fingerprint_sha256"],
        "train_seeds": list(manifest["splits"]["train"]),
        "validation_seeds": list(manifest["splits"]["val"]),
        "reserved_test_seeds": list(manifest["splits"]["test"]),
        "corruption_levels": list(manifest["corruption_levels"]),
        "expected_target_count": int(manifest["expected_target_count"]),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "geometry_gate": dict(manifest["geometry_gate"]),
    }
    for key, expected in expected_contract.items():
        if freeze.get(key) != expected:
            raise ValueError(f"frozen dataset contract mismatch: {key}")
    if float(freeze["selected_probability_threshold"]) not in PROBABILITY_THRESHOLD_GRID:
        raise ValueError("frozen probability threshold is outside the approved grid")
    if float(freeze["selected_unmatched_cost"]) not in UNMATCHED_COST_GRID:
        raise ValueError("frozen unmatched cost is outside the approved grid")
    selection_policy = freeze.get("selection_policy", {})
    if selection_policy != {
        "primary_metric": "validation_macro_recall",
        "minimum_conditional_precision": MINIMUM_CONDITIONAL_PRECISION,
        "reserved_test_threshold_selection": False,
    }:
        raise ValueError("frozen lightweight selection policy is invalid")
    model_values = json.loads((root / freeze["selected_model"]).read_text(encoding="utf-8"))
    model = LightweightModel.from_dict(model_values)
    if model.model_id != freeze["selected_model_id"]:
        raise ValueError("frozen model ID mismatch")
    expected_fingerprint = canonical_json_sha256(
        {
            "dataset_fingerprint_sha256": freeze["dataset_fingerprint_sha256"],
            "expected_target_count": freeze["expected_target_count"],
            "selected_model_sha256": freeze["selected_model_sha256"],
            "selected_model_id": freeze["selected_model_id"],
            "selected_probability_threshold": freeze[
                "selected_probability_threshold"
            ],
            "selected_unmatched_cost": freeze["selected_unmatched_cost"],
            "train_seeds": freeze["train_seeds"],
            "validation_seeds": freeze["validation_seeds"],
            "reserved_test_seeds": freeze["reserved_test_seeds"],
            "edge_feature_names": freeze["edge_feature_names"],
            "selection_policy": freeze["selection_policy"],
        }
    )
    if freeze.get("model_fingerprint_sha256") != expected_fingerprint:
        raise ValueError("frozen model fingerprint mismatch")
    return freeze, root, model, manifest, dataset_root
