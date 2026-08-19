"""Train on complete train seeds, validate on complete validation seeds, then freeze."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path
import random
import time
from typing import Any, Mapping, Sequence

import numpy as np
import torch
from torch import nn

from .assignment import (
    HYBRID_GEOMETRY_WEIGHT,
    HYBRID_LEARNED_WEIGHT,
    effective_edge_probabilities,
    probability_threshold_to_unmatched_cost,
    solve_assignment,
)
from .dataset import (
    PROTOCOL_CAUSAL_ONLINE,
    PROTOCOL_EXPANDED_FORMAL,
    canonical_json_sha256,
    dataset_fingerprint,
    load_dataset_manifest,
    load_entry,
    sample_entries,
)
from dual_optical_online_benchmark.contracts import BenchmarkProtocol
from .loader import sha256_file
from .metrics import evaluate_assignment
from .model import (
    BipartiteEdgeGNN,
    FeatureNormalizer,
    graph_tensors,
    save_weights_only,
)
from .schema import (
    EDGE_FEATURE_NAMES,
    FEATURE_CONTRACT_VERSION,
    NODE_FEATURE_NAMES,
    VALIDATION_PROBABILITY_THRESHOLDS,
    GraphLabels,
    OnlineGraph,
)


@dataclass(frozen=True)
class TrainingConfig:
    hidden_dim: int = 64
    dropout: float = 0.1
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-4
    max_epochs: int = 80
    patience: int = 10
    random_seed: int = 20260820
    device: str = "auto"


CAUSAL_INITIALIZATION_SEEDS = (1103, 2207, 3301, 4409, 5501)
EDGE_SAMPLING_SEED = 7319


@dataclass(frozen=True)
class CausalTrainingConfig:
    hidden_dim: int = 64
    dropout: float = 0.1
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-4
    max_epochs: int = 200
    patience: int = 25
    initialization_seeds: tuple[int, ...] = CAUSAL_INITIALIZATION_SEEDS
    device: str = "auto"


@dataclass(frozen=True)
class EdgeSamplingConfig:
    hard_negatives_per_positive: int = 4
    random_negatives_per_positive: int = 4
    negative_only_graph_limit: int = 32
    random_seed: int = EDGE_SAMPLING_SEED


@dataclass(frozen=True)
class EdgeSamplingPlan:
    selected_indices: np.ndarray
    positive_count: int
    negative_count: int
    selected_positive_count: int
    selected_hard_negative_count: int
    selected_random_negative_count: int

    def to_dict(self) -> dict[str, int | float]:
        selected_negative = (
            self.selected_hard_negative_count + self.selected_random_negative_count
        )
        return {
            "available_positive_edge_count": self.positive_count,
            "available_negative_edge_count": self.negative_count,
            "selected_positive_edge_count": self.selected_positive_count,
            "selected_hard_negative_edge_count": self.selected_hard_negative_count,
            "selected_random_negative_edge_count": self.selected_random_negative_count,
            "selected_negative_edge_count": selected_negative,
            "positive_retention_ratio": (
                self.selected_positive_count / self.positive_count
                if self.positive_count
                else 0.0
            ),
            "negative_sampling_ratio": (
                selected_negative / self.negative_count if self.negative_count else 0.0
            ),
        }


@dataclass(frozen=True)
class PreparedCausalCalibration:
    """Main-owned calibration snapshots converted to route-owned graphs."""

    manifest: Mapping[str, Any]
    train_data: Sequence[tuple[OnlineGraph, GraphLabels]]
    validation_data: Sequence[tuple[OnlineGraph, GraphLabels]]
    train_entries: Sequence[Mapping[str, Any]]
    validation_entries: Sequence[Mapping[str, Any]]


def _calibration_input_fingerprint_record(
    item: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep legacy fingerprints stable while binding new scale/candidate fields."""

    record = {
        "seed": int(item["seed"]),
        "corruption_level": str(item["corruption_level"]),
        "revolution_index": int(item["revolution_index"]),
        "input_fingerprint_sha256": str(item["input_fingerprint_sha256"]),
        "online_sha256": str(item["online_sha256"]),
        "offline_label_sha256": str(item["offline_label_sha256"]),
    }
    if "target_count" in item:
        record["target_count"] = int(item["target_count"])
    if "candidate_graph_fingerprint_sha256" in item:
        record["candidate_graph_fingerprint_sha256"] = str(
            item["candidate_graph_fingerprint_sha256"]
        )
    return record


FREEZE_SCHEMA_VERSION = "dual-optical-edge-gnn-freeze-v4"
CAUSAL_FREEZE_SCHEMA_VERSION = "dual-optical-edge-gnn-freeze-v6"
PREVIOUS_CAUSAL_FREEZE_SCHEMA_VERSION = "dual-optical-edge-gnn-freeze-v5"
LEGACY_FREEZE_SCHEMA_VERSION = "dual-optical-edge-gnn-freeze-v2"
SUPPORTED_FREEZE_SCHEMA_VERSIONS = frozenset(
    {
        LEGACY_FREEZE_SCHEMA_VERSION,
        FREEZE_SCHEMA_VERSION,
        PREVIOUS_CAUSAL_FREEZE_SCHEMA_VERSION,
        CAUSAL_FREEZE_SCHEMA_VERSION,
    }
)
LEARNED_ROUTES = ("learned", "hybrid")
VALIDATION_MINIMUM_CONDITIONAL_PRECISION = 0.70
VALIDATION_MAXIMUM_FALSE_ASSOCIATION_RATE = 0.30
VALIDATION_MAXIMUM_ROUTE_P95_MS = 1000.0


def _validate_training_config(config: TrainingConfig) -> None:
    if config.hidden_dim <= 0:
        raise ValueError("hidden_dim must be positive")
    if not 0.0 <= config.dropout < 1.0:
        raise ValueError("dropout must be in [0, 1)")
    if config.learning_rate <= 0.0 or config.weight_decay < 0.0:
        raise ValueError("optimizer rates are invalid")
    if config.max_epochs <= 0 or config.patience <= 0:
        raise ValueError("max_epochs and patience must be positive")


def _validate_causal_training_config(config: CausalTrainingConfig) -> None:
    if config.hidden_dim != 64:
        raise ValueError("causal protocol fixes hidden_dim=64")
    if config.dropout != 0.1:
        raise ValueError("causal protocol fixes dropout=0.1")
    if config.learning_rate != 1.0e-3 or config.weight_decay != 1.0e-4:
        raise ValueError("causal protocol fixes optimizer hyperparameters")
    if config.max_epochs != 200:
        raise ValueError("causal protocol fixes max_epochs=200")
    if config.patience != 25:
        raise ValueError("causal protocol fixes patience=25")
    if len(config.initialization_seeds) != 5:
        raise ValueError("causal protocol requires five independent initializations")
    if len(set(config.initialization_seeds)) != 5:
        raise ValueError("causal initialization seeds must be distinct")


def _validate_expanded_formal_config(
    manifest: dict[str, Any], config: TrainingConfig
) -> None:
    if manifest.get("protocol_profile") != PROTOCOL_EXPANDED_FORMAL:
        return
    expected = TrainingConfig(device=config.device)
    for field_name in (
        "hidden_dim",
        "dropout",
        "learning_rate",
        "weight_decay",
        "max_epochs",
        "patience",
        "random_seed",
    ):
        if getattr(config, field_name) != getattr(expected, field_name):
            raise ValueError(
                f"expanded formal protocol fixes {field_name}="
                f"{getattr(expected, field_name)}"
            )


def _device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    return device


def _load_split(
    manifest: dict[str, Any],
    root: Path,
    split: str,
) -> list[tuple[OnlineGraph, GraphLabels]]:
    loaded = []
    for entry in sample_entries(manifest, split):
        graph, labels = load_entry(root, entry, include_labels=True)
        assert labels is not None
        loaded.append((graph, labels))
    return loaded


def build_edge_sampling_plan(
    graph: OnlineGraph,
    labels: GraphLabels,
    *,
    config: EdgeSamplingConfig | None = None,
    graph_index: int = 0,
) -> EdgeSamplingPlan:
    """Keep every positive, then hard and reproducible random negatives."""

    config = config or EdgeSamplingConfig()
    positive_indices = np.flatnonzero(labels.edge_labels > 0.5).astype(np.int64)
    negative_indices = np.flatnonzero(labels.edge_labels <= 0.5).astype(np.int64)
    hard: set[int] = set()
    if len(positive_indices):
        for positive_index in positive_indices:
            index_a = int(graph.edge_index[0, positive_index])
            index_b = int(graph.edge_index[1, positive_index])
            neighbors = [
                int(edge_index)
                for edge_index in negative_indices
                if int(graph.edge_index[0, edge_index]) == index_a
                or int(graph.edge_index[1, edge_index]) == index_b
            ]
            neighbors.sort(key=lambda edge_index: (float(graph.geometry_cost[edge_index]), edge_index))
            hard.update(neighbors[: config.hard_negatives_per_positive])
    remaining = np.asarray(
        [index for index in negative_indices if int(index) not in hard],
        dtype=np.int64,
    )
    random_limit = (
        config.random_negatives_per_positive * len(positive_indices)
        if len(positive_indices)
        else config.negative_only_graph_limit
    )
    rng = np.random.default_rng(config.random_seed + 1009 * int(graph_index))
    if len(remaining) > random_limit:
        random_indices = np.sort(
            rng.choice(remaining, size=random_limit, replace=False).astype(np.int64)
        )
    else:
        random_indices = remaining
    selected = np.asarray(
        sorted(
            set(int(value) for value in positive_indices)
            | hard
            | set(int(value) for value in random_indices)
        ),
        dtype=np.int64,
    )
    return EdgeSamplingPlan(
        selected_indices=selected,
        positive_count=len(positive_indices),
        negative_count=len(negative_indices),
        selected_positive_count=len(positive_indices),
        selected_hard_negative_count=len(hard),
        selected_random_negative_count=len(random_indices),
    )


def summarize_edge_sampling(plans: Sequence[EdgeSamplingPlan]) -> dict[str, Any]:
    totals: dict[str, float] = {}
    for plan in plans:
        for key, value in plan.to_dict().items():
            if key.endswith("ratio"):
                continue
            totals[key] = totals.get(key, 0.0) + float(value)
    available_positive = int(totals.get("available_positive_edge_count", 0))
    available_negative = int(totals.get("available_negative_edge_count", 0))
    selected_positive = int(totals.get("selected_positive_edge_count", 0))
    selected_negative = int(totals.get("selected_negative_edge_count", 0))
    return {
        "graph_count": len(plans),
        **{key: int(value) for key, value in totals.items()},
        "positive_retention_ratio": (
            selected_positive / available_positive if available_positive else 0.0
        ),
        "negative_sampling_ratio": (
            selected_negative / available_negative if available_negative else 0.0
        ),
    }


def _loss_for_graph(
    model: BipartiteEdgeGNN,
    graph: OnlineGraph,
    labels: GraphLabels,
    normalizer: FeatureNormalizer,
    criterion: nn.Module,
    device: torch.device,
    selected_indices: np.ndarray | None = None,
) -> torch.Tensor:
    if graph.edge_index.shape[1] == 0:
        return torch.zeros((), dtype=torch.float32, device=device, requires_grad=True)
    tensors = graph_tensors(graph, normalizer, device)
    logits = model(*tensors)
    target = torch.as_tensor(labels.edge_labels, dtype=torch.float32, device=device)
    if selected_indices is not None:
        indices = torch.as_tensor(selected_indices, dtype=torch.long, device=device)
        logits = logits[indices]
        target = target[indices]
    if target.numel() == 0:
        return torch.zeros((), dtype=torch.float32, device=device, requires_grad=True)
    return criterion(logits, target)


def _predict_probabilities(
    model: BipartiteEdgeGNN,
    graph: OnlineGraph,
    normalizer: FeatureNormalizer,
    device: torch.device,
) -> np.ndarray:
    if graph.edge_index.shape[1] == 0:
        return np.empty(0, dtype=np.float32)
    with torch.no_grad():
        logits = model(*graph_tensors(graph, normalizer, device))
    return torch.sigmoid(logits).detach().cpu().numpy().astype(np.float32)


def _aggregate_validation(rows: list[dict[str, float | int]]) -> dict[str, float | int]:
    if not rows:
        raise ValueError("validation policy has no samples")
    selected_count = sum(int(row["selected_assignment_count"]) for row in rows)
    correct_count = sum(int(row["correct_assignment_count"]) for row in rows)
    return {
        "sample_count": len(rows),
        "macro_precision": float(np.mean([float(row["precision"]) for row in rows])),
        "macro_recall": float(np.mean([float(row["recall"]) for row in rows])),
        "macro_f1": float(np.mean([float(row["f1"]) for row in rows])),
        "false_association_count": int(
            sum(int(row["false_association_count"]) for row in rows)
        ),
        "duplicate_identity_match_count": int(
            sum(int(row["duplicate_identity_match_count"]) for row in rows)
        ),
        "duplicate_track_assignment_count": int(
            sum(int(row["duplicate_track_assignment_count"]) for row in rows)
        ),
        "correct_assignment_count": int(correct_count),
        "selected_assignment_count": int(selected_count),
        "conditional_precision": float(correct_count / max(selected_count, 1)),
        "candidate_positive_edge_count": int(
            sum(int(row["candidate_positive_edge_count"]) for row in rows)
        ),
        "expected_identity_count": int(
            sum(int(row["expected_identity_count"]) for row in rows)
        ),
        "candidate_true_edge_identity_count": int(
            sum(int(row["candidate_true_edge_identity_count"]) for row in rows)
        ),
        "candidate_true_edge_retention": float(
            sum(int(row["candidate_true_edge_identity_count"]) for row in rows)
            / max(sum(int(row["expected_identity_count"]) for row in rows), 1)
        ),
        "false_association_rate": float(
            sum(int(row["false_association_count"]) for row in rows)
            / max(sum(int(row["selected_assignment_count"]) for row in rows), 1)
        ),
    }


def _validation_hard_gate(candidate: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if float(candidate.get("noise_conditional_precision", 0.0)) < VALIDATION_MINIMUM_CONDITIONAL_PRECISION:
        reasons.append("conditional_precision_below_0_70")
    if int(candidate.get("duplicate_track_assignment_count", 0)) != 0:
        reasons.append("one_to_one_assignment_violated")
    if int(candidate.get("duplicate_identity_match_count", 0)) != 0:
        reasons.append("duplicate_identity_match")
    if float(candidate.get("noise_false_association_rate", 1.0)) > VALIDATION_MAXIMUM_FALSE_ASSOCIATION_RATE:
        reasons.append("false_association_rate_above_0_30")
    route_p95 = float(
        candidate.get(
            "route_compute_latency_p95_ms",
            float(candidate.get("scoring_latency_p95_ms", float("inf")))
            + float(candidate.get("assignment_latency_p95_ms", float("inf"))),
        )
    )
    if route_p95 > VALIDATION_MAXIMUM_ROUTE_P95_MS:
        reasons.append("route_p95_above_1000_ms")
    if int(candidate.get("correct_assignment_count", 0)) <= 0:
        reasons.append("zero_correct_assignment")
    return not reasons, reasons


def _validation_selection_key(candidate: dict[str, Any]) -> tuple[float, float, float, int, float, int, float]:
    """After hard gating, prefer recall and use precision only as a tie-breaker."""

    legacy_score = float(candidate.get("macro_f1", 0.0))
    recall = float(candidate.get("macro_recall", legacy_score))
    precision = float(candidate.get("macro_precision", legacy_score))
    return (
        float(candidate.get("noise_macro_recall", recall)),
        recall,
        float(candidate.get("noise_conditional_precision", precision)),
        -int(candidate["false_association_count"]),
        -float(candidate.get("route_compute_latency_p95_ms", float("inf"))),
        1 if candidate["route"] == "hybrid" else 0,
        float(candidate["probability_threshold"]),
    )


def _best_validation_candidate(
    candidates: Sequence[dict[str, Any]],
    *,
    enforce_hard_gates: bool,
) -> dict[str, Any]:
    """Select one policy without allowing ranking to bypass a validation gate."""

    route_candidates = list(candidates)
    if not route_candidates:
        raise ValueError("validation route candidate set is empty")
    if enforce_hard_gates:
        eligible = [
            candidate
            for candidate in route_candidates
            if bool(candidate.get("hard_gate_eligible"))
        ]
        route_candidates = eligible or route_candidates
    return max(route_candidates, key=_validation_selection_key)


def select_validation_policy(
    model: BipartiteEdgeGNN,
    normalizer: FeatureNormalizer,
    val_data: list[tuple[OnlineGraph, GraphLabels]],
    device: torch.device,
) -> dict[str, Any]:
    model.eval()
    predictions = []
    scoring_latencies_ms = []
    for graph, _ in val_data:
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        start = time.perf_counter()
        predictions.append(_predict_probabilities(model, graph, normalizer, device))
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        scoring_latencies_ms.append((time.perf_counter() - start) * 1000.0)
    candidates: list[dict[str, Any]] = []
    for route in LEARNED_ROUTES:
        for probability_threshold in VALIDATION_PROBABILITY_THRESHOLDS:
            unmatched_cost = probability_threshold_to_unmatched_cost(
                probability_threshold
            )
            rows: list[dict[str, float | int]] = []
            assignment_latencies_ms = []
            route_latencies_ms = []
            for (graph, labels), probabilities in zip(val_data, predictions):
                assignment_start = time.perf_counter()
                assignment = solve_assignment(
                    graph,
                    probabilities,
                    route,  # type: ignore[arg-type]
                    unmatched_cost=unmatched_cost,
                )
                assignment_latencies_ms.append(
                    (time.perf_counter() - assignment_start) * 1000.0
                )
                route_latencies_ms.append(
                    scoring_latencies_ms[len(rows)] + assignment_latencies_ms[-1]
                )
                metrics = evaluate_assignment(graph, labels, assignment)
                positive_identities = {
                    labels.identity_a[int(index_a)]
                    for label, (index_a, index_b) in zip(
                        labels.edge_labels, graph.edge_index.T
                    )
                    if label > 0.5
                    and labels.identity_a[int(index_a)] is not None
                    and labels.identity_a[int(index_a)]
                    == labels.identity_b[int(index_b)]
                }
                rows.append(
                    {
                        "corruption_level": graph.corruption_level,
                        "precision": metrics.precision,
                        "recall": metrics.recall,
                        "f1": metrics.f1,
                        "false_association_count": metrics.false_association_count,
                        "duplicate_identity_match_count": metrics.duplicate_identity_match_count,
                        "duplicate_track_assignment_count": metrics.duplicate_track_assignment_count,
                        "correct_assignment_count": metrics.correct_count,
                        "selected_assignment_count": metrics.selected_count,
                        "candidate_positive_edge_count": int(np.sum(labels.edge_labels > 0.5)),
                        "expected_identity_count": len(labels.expected_identities),
                        "candidate_true_edge_identity_count": len(positive_identities),
                    }
                )
            noise_rows = [
                row
                for row in rows
                if str(row["corruption_level"]) in {"medium", "heavy"}
            ] or rows
            noise_summary = _aggregate_validation(noise_rows)
            candidate = {
                    "route": route,
                    "probability_threshold": probability_threshold,
                    "unmatched_cost": unmatched_cost,
                    **_aggregate_validation(rows),
                    "noise_levels": sorted(
                        {str(row["corruption_level"]) for row in noise_rows}
                    ),
                    "noise_macro_recall": noise_summary["macro_recall"],
                    "noise_conditional_precision": noise_summary[
                        "conditional_precision"
                    ],
                    "noise_false_association_rate": noise_summary[
                        "false_association_rate"
                    ],
                    "scoring_latency_p50_ms": float(np.percentile(scoring_latencies_ms, 50)),
                    "scoring_latency_p95_ms": float(np.percentile(scoring_latencies_ms, 95)),
                    "assignment_latency_p50_ms": float(np.percentile(assignment_latencies_ms, 50)),
                    "assignment_latency_p95_ms": float(np.percentile(assignment_latencies_ms, 95)),
                    "route_compute_latency_p50_ms": float(np.percentile(route_latencies_ms, 50)),
                    "route_compute_latency_p95_ms": float(np.percentile(route_latencies_ms, 95)),
                }
            eligible, reasons = _validation_hard_gate(candidate)
            candidate["hard_gate_eligible"] = eligible
            candidate["hard_gate_failure_reasons"] = reasons
            candidates.append(candidate)
    best_by_route = {}
    for route in LEARNED_ROUTES:
        route_candidates = [
            candidate for candidate in candidates if candidate["route"] == route
        ]
        best_by_route[route] = _best_validation_candidate(
            route_candidates,
            enforce_hard_gates=True,
        )
    candidate_positive_count = max(
        int(candidate["candidate_positive_edge_count"]) for candidate in candidates
    )
    route_status = {
        route: {
            "failed_closed": not bool(candidate["hard_gate_eligible"]),
            "reason": (
                "|".join(candidate["hard_gate_failure_reasons"])
                if not candidate["hard_gate_eligible"]
                else "validated"
            ),
        }
        for route, candidate in best_by_route.items()
    }
    valid_routes = [
        candidate
        for route, candidate in best_by_route.items()
        if not route_status[route]["failed_closed"]
    ]
    failure_reasons = []
    if candidate_positive_count == 0:
        failure_reasons.append("zero_positive_geometry_candidate")
    if not valid_routes:
        failure_reasons.append("all_routes_failed_validation_hard_gates")
    selected = max(
        valid_routes or list(best_by_route.values()),
        key=_validation_selection_key,
    )
    calibration = {
        route: probability_calibration_evidence(
            [
                effective_edge_probabilities(graph, values, route)  # type: ignore[arg-type]
                for (graph, _), values in zip(val_data, predictions)
            ],
            [labels.edge_labels for _, labels in val_data],
        )
        for route in LEARNED_ROUTES
    }
    selection = {
        "selection_basis": [
            "hard_gates_before_ranking",
            "validation_macro_recall_desc",
            "validation_macro_precision_desc",
            "false_association_count_asc",
            "route_compute_latency_p95_asc",
            "hybrid_preferred_on_exact_tie",
            "higher_probability_threshold_on_remaining_tie",
        ],
        "hard_gates": {
            "minimum_conditional_precision": VALIDATION_MINIMUM_CONDITIONAL_PRECISION,
            "maximum_false_association_rate": VALIDATION_MAXIMUM_FALSE_ASSOCIATION_RATE,
            "maximum_route_compute_p95_ms": VALIDATION_MAXIMUM_ROUTE_P95_MS,
            "duplicate_track_assignment_count": 0,
            "duplicate_identity_match_count": 0,
        },
        "fixed_probability_threshold_candidates": list(
            VALIDATION_PROBABILITY_THRESHOLDS
        ),
        "hybrid_weights": {
            "geometry": HYBRID_GEOMETRY_WEIGHT,
            "learned": HYBRID_LEARNED_WEIGHT,
        },
        "cost_contract": "negative_log_effective_probability_v2",
        "probability_calibration": calibration,
        "freeze_allowed": not bool(failure_reasons),
        "promotion_allowed": False,
        "promotion_status": (
            "pending_reserved_test_same_input_comparison"
            if not failure_reasons
            else "validation_failed_closed"
        ),
        "validation_failed_closed": bool(failure_reasons),
        "validation_failure_reasons": failure_reasons,
        "route_status": route_status,
        "selected_route": selected["route"],
        "selected_probability_threshold": selected["probability_threshold"],
        "selected_unmatched_cost": selected["unmatched_cost"],
        "best_by_route": best_by_route,
        "candidates": candidates,
    }
    _validate_validation_selection_contract(selection)
    return selection


def probability_calibration_evidence(
    predictions: Sequence[np.ndarray],
    labels: Sequence[np.ndarray],
    *,
    bin_count: int = 10,
) -> dict[str, Any]:
    nonempty_predictions = [values for values in predictions if len(values)]
    nonempty_labels = [values for values in labels if len(values)]
    if not nonempty_predictions or not nonempty_labels:
        raise ValueError("probability calibration requires non-empty aligned edges")
    probabilities = np.concatenate(nonempty_predictions)
    targets = np.concatenate(nonempty_labels)
    if len(probabilities) != len(targets) or not len(probabilities):
        raise ValueError("probability calibration requires non-empty aligned edges")
    bins = []
    expected_calibration_error = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        mask = (probabilities >= lower) & (
            probabilities <= upper if index == bin_count - 1 else probabilities < upper
        )
        count = int(np.sum(mask))
        mean_probability = float(np.mean(probabilities[mask])) if count else 0.0
        empirical_positive_rate = float(np.mean(targets[mask])) if count else 0.0
        expected_calibration_error += (
            count / len(probabilities)
        ) * abs(mean_probability - empirical_positive_rate)
        bins.append(
            {
                "lower_probability": lower,
                "upper_probability": upper,
                "edge_count": count,
                "mean_probability": mean_probability,
                "empirical_positive_rate": empirical_positive_rate,
            }
        )
    return {
        "edge_count": len(probabilities),
        "positive_edge_count": int(np.sum(targets > 0.5)),
        "negative_edge_count": int(np.sum(targets <= 0.5)),
        "brier_score": float(np.mean(np.square(probabilities - targets))),
        "expected_calibration_error": float(expected_calibration_error),
        "bins": bins,
    }


def _validate_probability_cost_pair(
    probability: float,
    cost: float,
    *,
    context: str,
) -> None:
    if probability not in VALIDATION_PROBABILITY_THRESHOLDS:
        raise ValueError(f"{context} probability threshold is outside the fixed grid")
    expected = probability_threshold_to_unmatched_cost(probability)
    if not math.isclose(cost, expected, rel_tol=1.0e-12, abs_tol=1.0e-12):
        raise ValueError(f"{context} probability threshold and unmatched cost disagree")


def _same_policy(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("route") == right.get("route")
        and float(left.get("probability_threshold"))
        == float(right.get("probability_threshold"))
        and math.isclose(
            float(left.get("unmatched_cost")),
            float(right.get("unmatched_cost")),
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    )


def _validate_validation_selection_contract(selection: dict[str, Any]) -> None:
    expected_thresholds = list(VALIDATION_PROBABILITY_THRESHOLDS)
    if selection.get("fixed_probability_threshold_candidates") != expected_thresholds:
        raise ValueError("validation probability threshold grid is invalid")
    if selection.get("hybrid_weights") != {"geometry": 0.4, "learned": 0.6}:
        raise ValueError("validation hybrid weights are invalid")
    modern_cost_contract = selection.get("cost_contract") == "negative_log_effective_probability_v2"
    if modern_cost_contract:
        failed_closed = bool(selection.get("validation_failed_closed"))
        reasons = list(selection.get("validation_failure_reasons", []))
        if failed_closed != bool(reasons):
            raise ValueError("validation failure-closed evidence is inconsistent")
        if "freeze_allowed" in selection and bool(
            selection["freeze_allowed"]
        ) == failed_closed:
            raise ValueError("validation freeze evidence is inconsistent")
        if selection.get("promotion_allowed") is True:
            raise ValueError("validation data cannot authorize scale promotion")
        expected_promotion_status = (
            "validation_failed_closed"
            if failed_closed
            else "pending_reserved_test_same_input_comparison"
        )
        if (
            "promotion_status" in selection
            and selection["promotion_status"] != expected_promotion_status
        ):
            raise ValueError("validation promotion status is inconsistent")
        if set(selection.get("probability_calibration", {})) != set(LEARNED_ROUTES):
            raise ValueError("validation probability calibration is incomplete")
        route_status = selection.get("route_status", {})
        if set(route_status) != set(LEARNED_ROUTES):
            raise ValueError("validation route status is incomplete")
    candidates = [dict(item) for item in selection.get("candidates", [])]
    if len(candidates) != len(LEARNED_ROUTES) * len(expected_thresholds):
        raise ValueError("validation candidate grid is incomplete")
    for route in LEARNED_ROUTES:
        route_candidates = [item for item in candidates if item.get("route") == route]
        if sorted(float(item["probability_threshold"]) for item in route_candidates) != expected_thresholds:
            raise ValueError(f"validation probability threshold grid is incomplete for {route}")
        for item in route_candidates:
            _validate_probability_cost_pair(
                float(item["probability_threshold"]),
                float(item["unmatched_cost"]),
                context=f"validation candidate {route}",
            )
        expected_best = _best_validation_candidate(
            route_candidates,
            enforce_hard_gates=modern_cost_contract,
        )
        recorded_best = dict(selection.get("best_by_route", {}).get(route, {}))
        if not _same_policy(expected_best, recorded_best):
            raise ValueError(f"validation best policy is inconsistent for {route}")
        if modern_cost_contract and all(
            "hard_gate_eligible" in item for item in route_candidates
        ):
            expected_failed_closed = not bool(
                expected_best.get("hard_gate_eligible")
            )
            recorded_status = selection["route_status"][route]
            if bool(recorded_status.get("failed_closed")) != expected_failed_closed:
                raise ValueError(
                    f"validation failure-closed status is inconsistent for {route}"
                )
    eligible_routes = [
        route
        for route in LEARNED_ROUTES
        if not modern_cost_contract
        or not selection["route_status"][route]["failed_closed"]
    ]
    expected_selected = max(
        (
            selection["best_by_route"][route]
            for route in (eligible_routes or list(LEARNED_ROUTES))
        ),
        key=_validation_selection_key,
    )
    recorded_selected = {
        "route": selection.get("selected_route"),
        "probability_threshold": selection.get("selected_probability_threshold"),
        "unmatched_cost": selection.get("selected_unmatched_cost"),
    }
    if not _same_policy(expected_selected, recorded_selected):
        raise ValueError("validation selected policy is inconsistent")


def _validation_failure_evidence(
    selection: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """Read the v2 failure contract or derive it from legacy validation stubs."""

    if "validation_failed_closed" in selection:
        failed_closed = bool(selection.get("validation_failed_closed"))
        reasons = [
            str(reason)
            for reason in selection.get("validation_failure_reasons", [])
        ]
        if failed_closed and not reasons:
            reasons = ["legacy_validation_failed_closed_without_reason"]
        return failed_closed, reasons

    candidates = [
        item
        for item in selection.get("candidates", [])
        if isinstance(item, Mapping)
    ]
    positive_candidate_count = max(
        (int(item.get("candidate_positive_edge_count", 0)) for item in candidates),
        default=0,
    )
    correct_assignment_count = max(
        (int(item.get("correct_assignment_count", 0)) for item in candidates),
        default=0,
    )
    reasons = []
    if positive_candidate_count == 0:
        reasons.append("zero_positive_geometry_candidate")
    if correct_assignment_count == 0:
        reasons.append("zero_correct_assignment_all_routes")
    return bool(reasons), reasons


def _fit_initialization(
    train_data: list[tuple[OnlineGraph, GraphLabels]],
    val_data: list[tuple[OnlineGraph, GraphLabels]],
    normalizer: FeatureNormalizer,
    config: CausalTrainingConfig,
    initialization_seed: int,
    device: torch.device,
) -> tuple[
    dict[str, torch.Tensor],
    list[dict[str, float | int]],
    dict[str, Any],
    float,
    float,
    dict[str, Any],
]:
    """Train one initialization and return only its in-memory best checkpoint."""

    random.seed(initialization_seed)
    np.random.seed(initialization_seed)
    torch.manual_seed(initialization_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(initialization_seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    model = BipartiteEdgeGNN(
        len(NODE_FEATURE_NAMES),
        len(EDGE_FEATURE_NAMES),
        hidden_dim=config.hidden_dim,
        dropout=config.dropout,
    ).to(device)

    sampling_config = EdgeSamplingConfig()
    sampling_plans = [
        build_edge_sampling_plan(
            graph,
            labels,
            config=sampling_config,
            graph_index=index,
        )
        for index, (graph, labels) in enumerate(train_data)
    ]
    sampling_summary = {
        "schema_version": "dual-optical-edge-sampling-evidence-v1",
        "policy": asdict(sampling_config),
        "selection": "all_positive_then_endpoint_hard_negative_then_seeded_random_negative",
        **summarize_edge_sampling(sampling_plans),
    }
    if sampling_summary["positive_retention_ratio"] != 1.0:
        raise RuntimeError("edge sampling did not retain every positive edge")
    selected_positive = int(sampling_summary["selected_positive_edge_count"])
    selected_negative = int(sampling_summary["selected_negative_edge_count"])
    if selected_positive == 0:
        raise ValueError("training split contains no positive candidate edge")
    positive_weight = max(1.0, selected_negative / selected_positive)
    sampling_summary["loss_positive_weight"] = positive_weight
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(positive_weight, dtype=torch.float32, device=device)
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    best_loss = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    no_improvement = 0
    history: list[dict[str, float | int]] = []
    order_rng = np.random.default_rng(initialization_seed)
    for epoch in range(1, config.max_epochs + 1):
        model.train()
        train_losses = []
        for index in order_rng.permutation(len(train_data)):
            graph, labels = train_data[int(index)]
            plan = sampling_plans[int(index)]
            if graph.edge_index.shape[1] == 0:
                continue
            optimizer.zero_grad(set_to_none=True)
            loss = _loss_for_graph(
                model,
                graph,
                labels,
                normalizer,
                criterion,
                device,
                plan.selected_indices,
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))
        if not train_losses:
            raise ValueError("training split contains no non-empty candidate graph")
        model.eval()
        val_losses = []
        with torch.no_grad():
            for graph, labels in val_data:
                if graph.edge_index.shape[1] == 0:
                    continue
                loss = _loss_for_graph(
                    model, graph, labels, normalizer, criterion, device
                )
                val_losses.append(float(loss.detach().cpu()))
        if not val_losses:
            raise ValueError("validation split contains no non-empty candidate graph")
        train_loss = float(np.mean(train_losses))
        val_loss = float(np.mean(val_losses))
        history.append(
            {"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss}
        )
        if val_loss < best_loss - 1.0e-6:
            best_loss = val_loss
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.state_dict().items()
            }
            no_improvement = 0
        else:
            no_improvement += 1
        if no_improvement >= config.patience:
            break
    if best_state is None:
        raise RuntimeError("training did not produce a checkpoint")
    model.load_state_dict(best_state)
    selection = select_validation_policy(model, normalizer, val_data, device)
    return best_state, history, selection, best_loss, positive_weight, sampling_summary


def _initialization_selection_key(candidate: dict[str, Any]) -> tuple[float, float, int, float, int, float, int]:
    """Apply the frozen validation ordering across independent initializations."""

    legacy_score = float(candidate.get("macro_f1", 0.0))
    recall = float(candidate.get("macro_recall", legacy_score))
    precision = float(candidate.get("macro_precision", legacy_score))
    return (
        float(candidate.get("noise_macro_recall", recall)),
        recall,
        -int(candidate["false_association_count"]),
        precision,
        1 if candidate["selected_route"] == "hybrid" else 0,
        float(candidate["selected_probability_threshold"]),
        -int(candidate["initialization_index"]),
    )


def train_causal_ensemble_and_freeze(
    dataset_manifest: str | Path,
    output_dir: str | Path,
    *,
    config: CausalTrainingConfig | None = None,
    prepared: PreparedCausalCalibration | None = None,
) -> Path:
    """Train five initializations, freeze one model, and never open the test split."""

    config = config or CausalTrainingConfig()
    _validate_causal_training_config(config)
    if prepared is None:
        manifest, dataset_root = load_dataset_manifest(dataset_manifest)
        if manifest.get("protocol_profile") != PROTOCOL_CAUSAL_ONLINE:
            raise ValueError(
                "five-initialization training requires the causal formal dataset"
            )
        train_data = _load_split(manifest, dataset_root, "train")
        val_data = _load_split(manifest, dataset_root, "val")
        train_entries = sample_entries(manifest, "train")
        validation_entries = sample_entries(manifest, "val")
    else:
        manifest = dict(prepared.manifest)
        train_data = list(prepared.train_data)
        val_data = list(prepared.validation_data)
        train_entries = [dict(item) for item in prepared.train_entries]
        validation_entries = [dict(item) for item in prepared.validation_entries]
        if manifest.get("protocol_profile") != PROTOCOL_CAUSAL_ONLINE:
            raise ValueError("prepared calibration has the wrong protocol profile")
    if not train_data or not val_data:
        raise ValueError("training and validation calibration data must be non-empty")
    train_input_fingerprint_sha256 = canonical_json_sha256(
        [_calibration_input_fingerprint_record(item) for item in train_entries]
    )
    validation_input_fingerprint_sha256 = canonical_json_sha256(
        [
            _calibration_input_fingerprint_record(item)
            for item in validation_entries
        ]
    )
    normalizer = FeatureNormalizer.fit(graph for graph, _ in train_data)
    device = _device(config.device)

    candidates: list[dict[str, Any]] = []
    retained: dict[
        int,
        tuple[
            dict[str, torch.Tensor],
            list[dict[str, float | int]],
            float,
            float,
            dict[str, Any],
        ],
    ] = {}
    for initialization_index, initialization_seed in enumerate(
        config.initialization_seeds, start=1
    ):
        (
            state,
            history,
            selection,
            best_loss,
            positive_weight,
            sampling_summary,
        ) = _fit_initialization(
            train_data,
            val_data,
            normalizer,
            config,
            initialization_seed,
            device,
        )
        selected = {
            "route": selection["selected_route"],
            "probability_threshold": selection["selected_probability_threshold"],
            "unmatched_cost": selection["selected_unmatched_cost"],
            **next(
                item
                for item in selection["candidates"]
                if item["route"] == selection["selected_route"]
                and item["probability_threshold"]
                == selection["selected_probability_threshold"]
            ),
        }
        validation_failed_closed, validation_failure_reasons = (
            _validation_failure_evidence(selection)
        )
        candidate = {
            "initialization_index": initialization_index,
            "initialization_seed": initialization_seed,
            "selected_route": selected["route"],
            "selected_probability_threshold": selected["probability_threshold"],
            "selected_unmatched_cost": selected["unmatched_cost"],
            "macro_precision": selected["macro_precision"],
            "macro_recall": selected["macro_recall"],
            "macro_f1": selected["macro_f1"],
            "noise_macro_recall": selected.get(
                "noise_macro_recall", selected["macro_recall"]
            ),
            "noise_conditional_precision": selected.get(
                "noise_conditional_precision", selected["macro_precision"]
            ),
            "false_association_count": selected["false_association_count"],
            "duplicate_identity_match_count": selected[
                "duplicate_identity_match_count"
            ],
            "epochs_completed": len(history),
            "best_validation_loss": best_loss,
            "validation_failed_closed": validation_failed_closed,
            "validation_failure_reasons": validation_failure_reasons,
            "validation_selection": selection,
        }
        candidates.append(candidate)
        retained[initialization_index] = (
            state,
            history,
            best_loss,
            positive_weight,
            sampling_summary,
        )

    valid_candidates = [
        candidate for candidate in candidates if not candidate["validation_failed_closed"]
    ]
    selected_candidate = max(
        valid_candidates or candidates,
        key=_initialization_selection_key,
    )
    selected_index = int(selected_candidate["initialization_index"])
    (
        selected_state,
        selected_history,
        selected_loss,
        positive_weight,
        selected_sampling_summary,
    ) = retained[selected_index]
    del retained

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    weights_path = output_dir / "edge_gnn_weights.pt"
    normalizer_path = output_dir / "feature_normalizer.json"
    config_path = output_dir / "model_config.json"
    history_path = output_dir / "training_history.csv"
    selection_path = output_dir / "validation_selection.json"
    initialization_path = output_dir / "initialization_selection.json"
    sampling_path = output_dir / "edge_sampling_evidence.json"
    validation_evidence_path = output_dir / "validation_evidence.json"
    failure_path = output_dir / "freeze_failure.json"
    freeze_path = output_dir / "freeze_manifest.json"

    selected_model = BipartiteEdgeGNN(
        len(NODE_FEATURE_NAMES),
        len(EDGE_FEATURE_NAMES),
        hidden_dim=config.hidden_dim,
        dropout=config.dropout,
    )
    selected_model.load_state_dict(selected_state)
    save_weights_only(selected_model, weights_path)
    normalizer.save(normalizer_path)
    model_config = {
        "node_feature_dim": len(NODE_FEATURE_NAMES),
        "edge_feature_dim": len(EDGE_FEATURE_NAMES),
        "hidden_dim": config.hidden_dim,
        "dropout": config.dropout,
        "message_passing_layers": 2,
        "training": asdict(config),
        "positive_weight": positive_weight,
        "best_validation_loss": selected_loss,
        "epochs_completed": len(selected_history),
        "selected_initialization_index": selected_index,
        "selected_initialization_seed": selected_candidate["initialization_seed"],
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
    }
    config_path.write_text(json.dumps(model_config, indent=2) + "\n", encoding="utf-8")
    with history_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["epoch", "train_loss", "val_loss"])
        writer.writeheader()
        writer.writerows(selected_history)
    selected_selection = dict(selected_candidate["validation_selection"])
    selection_path.write_text(
        json.dumps(selected_selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sampling_path.write_text(
        json.dumps(selected_sampling_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    validation_evidence = {
        "schema_version": "dual-optical-edge-gnn-validation-evidence-v1",
        "freeze_allowed": not bool(
            selected_candidate["validation_failed_closed"]
        ),
        "promotion_allowed": False,
        "promotion_status": (
            "pending_reserved_test_same_input_comparison"
            if not selected_candidate["validation_failed_closed"]
            else "validation_failed_closed"
        ),
        "validation_failed_closed": bool(
            selected_candidate["validation_failed_closed"]
        ),
        "validation_failure_reasons": list(
            selected_candidate["validation_failure_reasons"]
        ),
        "candidate_true_edge_retention": selected_selection["best_by_route"][
            selected_selection["selected_route"]
        ]["candidate_true_edge_retention"],
        "positive_edge_count": selected_selection["probability_calibration"][
            "learned"
        ]["positive_edge_count"],
        "negative_edge_count": selected_selection["probability_calibration"][
            "learned"
        ]["negative_edge_count"],
        "route_status": selected_selection["route_status"],
        "best_by_route": selected_selection["best_by_route"],
        "probability_calibration": selected_selection["probability_calibration"],
    }
    validation_evidence_path.write_text(
        json.dumps(validation_evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    public_candidates = []
    for candidate in candidates:
        item = dict(candidate)
        item.pop("validation_selection")
        item["selected"] = item["initialization_index"] == selected_index
        item["checkpoint_retained"] = item["selected"]
        public_candidates.append(item)
    initialization_summary = {
        "schema_version": "dual-optical-edge-gnn-initialization-selection-v1",
        "selection_basis": [
            "validation_macro_f1_desc",
            "false_association_count_asc",
            "duplicate_identity_match_count_asc",
            "hybrid_preferred_on_exact_tie",
            "higher_probability_threshold_on_remaining_tie",
            "lower_initialization_index_on_remaining_tie",
        ],
        "ensemble_used_for_test": False,
        "initialization_count": 5,
        "selected_initialization_index": selected_index,
        "selected_initialization_seed": selected_candidate["initialization_seed"],
        "candidates": public_candidates,
    }
    initialization_path.write_text(
        json.dumps(initialization_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not valid_candidates:
        failure = {
            "schema_version": "dual-optical-edge-gnn-freeze-failure-v1",
            "status": "failed_closed",
            "freeze_allowed": False,
            "promotion_allowed": False,
            "promotion_status": "validation_failed_closed",
            "reason": "all_initializations_failed_validation",
            "initialization_count": len(candidates),
            "test_accessed_before_failure": False,
            "validation_evidence": validation_evidence_path.name,
            "validation_evidence_sha256": sha256_file(validation_evidence_path),
            "initialization_selection": initialization_path.name,
            "initialization_selection_sha256": sha256_file(initialization_path),
        }
        failure_path.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for path in (weights_path, normalizer_path, config_path, history_path, selection_path, sampling_path):
            path.unlink(missing_ok=True)
        raise ValueError(
            "validation failed closed for all five initializations; "
            f"evidence={failure_path}"
        )
    artifacts = {
        "weights_sha256": sha256_file(weights_path),
        "normalizer_sha256": sha256_file(normalizer_path),
        "model_config_sha256": sha256_file(config_path),
        "training_history_sha256": sha256_file(history_path),
        "validation_selection_sha256": sha256_file(selection_path),
        "initialization_selection_sha256": sha256_file(initialization_path),
        "edge_sampling_evidence_sha256": sha256_file(sampling_path),
        "validation_evidence_sha256": sha256_file(validation_evidence_path),
    }
    freeze = {
        "schema_version": CAUSAL_FREEZE_SCHEMA_VERSION,
        "dataset_manifest": str(Path(dataset_manifest).resolve()),
        "dataset_manifest_sha256": sha256_file(Path(dataset_manifest).resolve()),
        "dataset_fingerprint_sha256": manifest["dataset_fingerprint_sha256"],
        "weights": weights_path.name,
        "normalizer": normalizer_path.name,
        "model_config": config_path.name,
        "training_history": history_path.name,
        "validation_selection": selection_path.name,
        "initialization_selection": initialization_path.name,
        "edge_sampling_evidence": sampling_path.name,
        "validation_evidence": validation_evidence_path.name,
        **artifacts,
        "train_seeds": list(manifest["splits"]["train"]),
        "validation_seeds": list(manifest["splits"]["val"]),
        "reserved_test_seeds": list(manifest["splits"]["test"]),
        "corruption_levels": list(manifest["corruption_levels"]),
        "formal_protocol": True,
        "expanded_formal_protocol": False,
        "causal_prefix_protocol": True,
        "protocol_profile": PROTOCOL_CAUSAL_ONLINE,
        "target_count": int(
            manifest.get("target_count", manifest.get("expected_target_count", 100))
        ),
        "protocol_fingerprint_sha256": str(
            manifest.get("protocol_fingerprint_sha256")
            or BenchmarkProtocol().fingerprint
        ),
        "train_input_fingerprint_sha256": train_input_fingerprint_sha256,
        "validation_input_fingerprint_sha256": validation_input_fingerprint_sha256,
        "geometry_gate": dict(manifest["geometry_gate"]),
        "revolutions_per_seed": int(manifest["revolutions_per_seed"]),
        "selected_initialization_index": selected_index,
        "selected_initialization_seed": selected_candidate["initialization_seed"],
        "selected_route": selected_candidate["selected_route"],
        "selected_probability_threshold": selected_candidate[
            "selected_probability_threshold"
        ],
        "selected_unmatched_cost": selected_candidate["selected_unmatched_cost"],
        "route_probability_thresholds": {
            route: selected_selection["best_by_route"][route]["probability_threshold"]
            for route in LEARNED_ROUTES
        },
        "route_unmatched_costs": {
            route: selected_selection["best_by_route"][route]["unmatched_cost"]
            for route in LEARNED_ROUTES
        },
        "initialization_count": 5,
        "ensemble_used_for_test": False,
        "test_graph_files_opened_before_freeze": False,
        "test_accessed_before_freeze": False,
        "checkpoint_payload": "selected_state_dict_only",
        "checkpoint_load_policy": "torch_load_weights_only_true",
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "snapshot_contract_version": str(
            manifest.get("snapshot_contract_version", "v1_fallback")
        ),
        "tracker_fingerprint": str(
            manifest.get("tracker_fingerprint", "legacy-unfrozen-tracker")
        ),
        "confirmation_policy": {
            "window_revolutions": 3,
            "required_hits": 2,
            "one_to_one_assignment": "hungarian",
        },
        "cost_contract": "negative_log_effective_probability_v2",
        "validation_failed_closed": False,
        "freeze_allowed": True,
        "promotion_allowed": False,
        "promotion_status": "pending_reserved_test_same_input_comparison",
    }
    for key in (
        "dataset_manifest_kind",
        "train_label_fingerprint_sha256",
        "validation_label_fingerprint_sha256",
        "offline_label_schema",
        "route_name",
        "candidate_graph_contract",
    ):
        if key in manifest:
            freeze[key] = manifest[key]
    if freeze.get("dataset_manifest_kind") == "main_shared_calibration_v1":
        freeze["model_sha256"] = freeze["weights_sha256"]
        freeze["test_snapshot_open_count"] = 0
        freeze["test_label_open_count"] = 0
        freeze["train_inputs"] = [dict(item) for item in train_entries]
        freeze["validation_inputs"] = [
            dict(item) for item in validation_entries
        ]
    fingerprint_payload = {
        "dataset_fingerprint_sha256": freeze["dataset_fingerprint_sha256"],
        "artifact_hashes": artifacts,
        "train_seeds": freeze["train_seeds"],
        "validation_seeds": freeze["validation_seeds"],
        "reserved_test_seeds": freeze["reserved_test_seeds"],
        "corruption_levels": freeze["corruption_levels"],
        "selected_route": freeze["selected_route"],
        "selected_probability_threshold": freeze["selected_probability_threshold"],
        "selected_unmatched_cost": freeze["selected_unmatched_cost"],
        "route_probability_thresholds": freeze["route_probability_thresholds"],
        "route_unmatched_costs": freeze["route_unmatched_costs"],
        "selected_initialization_index": freeze["selected_initialization_index"],
        "selected_initialization_seed": freeze["selected_initialization_seed"],
        "initialization_count": 5,
        "ensemble_used_for_test": False,
        "protocol_fingerprint_sha256": freeze["protocol_fingerprint_sha256"],
        "train_input_fingerprint_sha256": freeze[
            "train_input_fingerprint_sha256"
        ],
        "validation_input_fingerprint_sha256": freeze[
            "validation_input_fingerprint_sha256"
        ],
        "geometry_gate": freeze["geometry_gate"],
        "feature_contract_version": freeze["feature_contract_version"],
        "snapshot_contract_version": freeze["snapshot_contract_version"],
        "tracker_fingerprint": freeze["tracker_fingerprint"],
        "confirmation_policy": freeze["confirmation_policy"],
        "cost_contract": freeze["cost_contract"],
        "validation_failed_closed": freeze["validation_failed_closed"],
        "target_count": freeze["target_count"],
    }
    for key in (
        "dataset_manifest_kind",
        "train_label_fingerprint_sha256",
        "validation_label_fingerprint_sha256",
        "offline_label_schema",
        "route_name",
        "candidate_graph_contract",
    ):
        if key in freeze:
            fingerprint_payload[key] = freeze[key]
    freeze["model_fingerprint_sha256"] = canonical_json_sha256(fingerprint_payload)
    freeze_path.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    return freeze_path


def train_and_freeze(
    dataset_manifest: str | Path,
    output_dir: str | Path,
    *,
    config: TrainingConfig | None = None,
) -> Path:
    """Do not call load_entry for the test split before writing the freeze manifest."""

    config = config or TrainingConfig()
    _validate_training_config(config)
    manifest, dataset_root = load_dataset_manifest(dataset_manifest)
    _validate_expanded_formal_config(manifest, config)
    train_data = _load_split(manifest, dataset_root, "train")
    val_data = _load_split(manifest, dataset_root, "val")
    if not train_data or not val_data:
        raise ValueError("training and validation splits must be non-empty")
    normalizer = FeatureNormalizer.fit(graph for graph, _ in train_data)

    random.seed(config.random_seed)
    np.random.seed(config.random_seed)
    torch.manual_seed(config.random_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.random_seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    device = _device(config.device)
    model = BipartiteEdgeGNN(
        len(NODE_FEATURE_NAMES),
        len(EDGE_FEATURE_NAMES),
        hidden_dim=config.hidden_dim,
        dropout=config.dropout,
    ).to(device)

    label_arrays = [
        labels.edge_labels for _, labels in train_data if len(labels.edge_labels)
    ]
    if not label_arrays:
        raise ValueError("training split contains no candidate edges")
    all_train_labels = np.concatenate(label_arrays)
    positive = int(np.sum(all_train_labels > 0.5))
    negative = len(all_train_labels) - positive
    if positive == 0:
        raise ValueError("training split contains no positive candidate edge")
    positive_weight = max(1.0, negative / positive)
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(positive_weight, dtype=torch.float32, device=device)
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )

    best_loss = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    no_improvement = 0
    history: list[dict[str, float | int]] = []
    order_rng = np.random.default_rng(config.random_seed)
    for epoch in range(1, config.max_epochs + 1):
        model.train()
        order = order_rng.permutation(len(train_data))
        train_losses = []
        for index in order:
            graph, labels = train_data[int(index)]
            optimizer.zero_grad(set_to_none=True)
            loss = _loss_for_graph(model, graph, labels, normalizer, criterion, device)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))
        model.eval()
        val_losses = []
        with torch.no_grad():
            for graph, labels in val_data:
                loss = _loss_for_graph(model, graph, labels, normalizer, criterion, device)
                val_losses.append(float(loss.detach().cpu()))
        train_loss = float(np.mean(train_losses))
        val_loss = float(np.mean(val_losses))
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        if val_loss < best_loss - 1.0e-6:
            best_loss = val_loss
            best_state = {
                key: value.detach().cpu().clone() for key, value in model.state_dict().items()
            }
            no_improvement = 0
        else:
            no_improvement += 1
        if no_improvement >= config.patience:
            break
    if best_state is None:
        raise RuntimeError("training did not produce a checkpoint")
    model.load_state_dict(best_state)
    validation_selection = select_validation_policy(
        model,
        normalizer,
        val_data,
        device,
    )

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    weights_path = output_dir / "edge_gnn_weights.pt"
    normalizer_path = output_dir / "feature_normalizer.json"
    config_path = output_dir / "model_config.json"
    history_path = output_dir / "training_history.csv"
    selection_path = output_dir / "validation_selection.json"
    freeze_path = output_dir / "freeze_manifest.json"
    save_weights_only(model, weights_path)
    normalizer.save(normalizer_path)
    model_config = {
        "node_feature_dim": len(NODE_FEATURE_NAMES),
        "edge_feature_dim": len(EDGE_FEATURE_NAMES),
        "hidden_dim": config.hidden_dim,
        "dropout": config.dropout,
        "training": asdict(config),
        "positive_weight": positive_weight,
        "best_validation_loss": best_loss,
        "epochs_completed": len(history),
    }
    config_path.write_text(json.dumps(model_config, indent=2) + "\n", encoding="utf-8")
    with history_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["epoch", "train_loss", "val_loss"])
        writer.writeheader()
        writer.writerows(history)
    selection_path.write_text(
        json.dumps(validation_selection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifact_hashes = {
        "weights_sha256": sha256_file(weights_path),
        "normalizer_sha256": sha256_file(normalizer_path),
        "model_config_sha256": sha256_file(config_path),
        "training_history_sha256": sha256_file(history_path),
        "validation_selection_sha256": sha256_file(selection_path),
    }
    freeze_manifest = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "dataset_manifest": str(Path(dataset_manifest).resolve()),
        "dataset_manifest_sha256": sha256_file(Path(dataset_manifest).resolve()),
        "dataset_fingerprint_sha256": manifest["dataset_fingerprint_sha256"],
        "weights": weights_path.name,
        "normalizer": normalizer_path.name,
        "model_config": config_path.name,
        "training_history": history_path.name,
        "validation_selection": selection_path.name,
        **artifact_hashes,
        "train_seeds": list(manifest["splits"]["train"]),
        "validation_seeds": list(manifest["splits"]["val"]),
        "reserved_test_seeds": list(manifest["splits"]["test"]),
        "corruption_levels": list(manifest["corruption_levels"]),
        "formal_protocol": bool(manifest["formal_protocol"]),
        "expanded_formal_protocol": bool(
            manifest.get("expanded_formal_protocol", False)
        ),
        "protocol_profile": manifest.get("protocol_profile", "legacy_formal_2test_v1"),
        "selected_route": validation_selection["selected_route"],
        "selected_probability_threshold": validation_selection[
            "selected_probability_threshold"
        ],
        "selected_unmatched_cost": validation_selection["selected_unmatched_cost"],
        "route_probability_thresholds": {
            route: validation_selection["best_by_route"][route][
                "probability_threshold"
            ]
            for route in LEARNED_ROUTES
        },
        "route_unmatched_costs": {
            route: validation_selection["best_by_route"][route]["unmatched_cost"]
            for route in LEARNED_ROUTES
        },
        "test_graph_files_opened_before_freeze": False,
        "checkpoint_payload": "state_dict_only",
        "checkpoint_load_policy": "torch_load_weights_only_true",
    }
    freeze_manifest["model_fingerprint_sha256"] = canonical_json_sha256(
        {
            "dataset_fingerprint_sha256": freeze_manifest[
                "dataset_fingerprint_sha256"
            ],
            "artifact_hashes": artifact_hashes,
            "train_seeds": freeze_manifest["train_seeds"],
            "validation_seeds": freeze_manifest["validation_seeds"],
            "reserved_test_seeds": freeze_manifest["reserved_test_seeds"],
            "corruption_levels": freeze_manifest["corruption_levels"],
            "selected_route": freeze_manifest["selected_route"],
            "selected_probability_threshold": freeze_manifest[
                "selected_probability_threshold"
            ],
            "selected_unmatched_cost": freeze_manifest["selected_unmatched_cost"],
            "route_probability_thresholds": freeze_manifest[
                "route_probability_thresholds"
            ],
            "route_unmatched_costs": freeze_manifest["route_unmatched_costs"],
        }
    )
    freeze_path.write_text(json.dumps(freeze_manifest, indent=2) + "\n", encoding="utf-8")
    return freeze_path


def _expected_shared_revolutions(protocol: Mapping[str, Any]) -> int:
    association_round_period_s = float(
        protocol.get(
            "association_round_period_s",
            protocol["scan_period_s"],
        )
    )
    return int(round(float(protocol["duration_s"]) / association_round_period_s))


def verify_freeze_manifest(path: str | Path) -> tuple[dict[str, Any], Path]:
    path = Path(path).resolve()
    values = json.loads(path.read_text(encoding="utf-8"))
    schema_version = values.get("schema_version")
    if schema_version not in SUPPORTED_FREEZE_SCHEMA_VERSIONS:
        raise ValueError("unsupported freeze manifest")
    if values.get("test_graph_files_opened_before_freeze") is not False:
        raise ValueError("test split isolation was not preserved")
    causal_schema = schema_version in {
        PREVIOUS_CAUSAL_FREEZE_SCHEMA_VERSION,
        CAUSAL_FREEZE_SCHEMA_VERSION,
    }
    if causal_schema:
        if values.get("test_accessed_before_freeze") is not False:
            raise ValueError("causal test split isolation was not preserved")
        if values.get("initialization_count") != 5:
            raise ValueError("causal freeze must record five initializations")
        if values.get("ensemble_used_for_test") is not False:
            raise ValueError("causal freeze must contain one selected model")
    artifacts = [
        ("weights", "weights_sha256"),
        ("normalizer", "normalizer_sha256"),
        ("model_config", "model_config_sha256"),
        ("training_history", "training_history_sha256"),
    ]
    if schema_version != LEGACY_FREEZE_SCHEMA_VERSION:
        artifacts.append(("validation_selection", "validation_selection_sha256"))
    if causal_schema:
        artifacts.append(
            ("initialization_selection", "initialization_selection_sha256")
        )
    if schema_version == CAUSAL_FREEZE_SCHEMA_VERSION:
        artifacts.extend(
            [
                ("edge_sampling_evidence", "edge_sampling_evidence_sha256"),
                ("validation_evidence", "validation_evidence_sha256"),
            ]
        )
    for key, hash_key in artifacts:
        artifact = path.parent / values[key]
        if sha256_file(artifact) != values[hash_key]:
            raise ValueError(f"frozen artifact hash mismatch: {artifact}")
    dataset_path = Path(values["dataset_manifest"])
    if sha256_file(dataset_path) != values["dataset_manifest_sha256"]:
        raise ValueError("dataset manifest changed after model freeze")
    shared_calibration = (
        values.get("dataset_manifest_kind") == "main_shared_calibration_v1"
    )
    if shared_calibration:
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        if dataset.get("phase") != "calibration":
            raise ValueError("frozen shared dataset is not calibration-only")
        if dataset.get("test_access_allowed") is not False:
            raise ValueError("frozen shared dataset permits test access")
        if any(
            item.get("split") == "test" for item in dataset.get("entries", [])
        ):
            raise ValueError("frozen shared dataset contains a test entry")
        expected_dataset_fingerprint = canonical_json_sha256(
            {
                "protocol_fingerprint": dataset.get("protocol_fingerprint"),
                "train_inputs": values.get("train_inputs", []),
                "validation_inputs": values.get("validation_inputs", []),
            }
        )
        if expected_dataset_fingerprint != values.get(
            "dataset_fingerprint_sha256"
        ):
            raise ValueError("frozen shared dataset fingerprint mismatch")
    else:
        dataset, _ = load_dataset_manifest(dataset_path)
        if dataset_fingerprint(dataset) != values.get(
            "dataset_fingerprint_sha256"
        ):
            raise ValueError("frozen dataset fingerprint mismatch")
    split_contract = {
        "train": list(values.get("train_seeds", [])),
        "val": list(values.get("validation_seeds", [])),
        "test": list(values.get("reserved_test_seeds", [])),
    }
    if shared_calibration:
        protocol_values = dataset.get("protocol", {})
        shared_split_contract = {
            "train": list(protocol_values.get("train_seeds", [])),
            "val": list(protocol_values.get("validation_seeds", [])),
            "test": list(protocol_values.get("test_seeds", [])),
        }
        if split_contract != shared_split_contract:
            raise ValueError(
                "frozen split contract no longer matches the shared dataset"
            )
    else:
        if split_contract != dataset["splits"]:
            raise ValueError("frozen split contract no longer matches the dataset")
        if bool(values.get("formal_protocol")) != bool(dataset["formal_protocol"]):
            raise ValueError("frozen formal-protocol marker does not match the dataset")
    if schema_version != LEGACY_FREEZE_SCHEMA_VERSION and not shared_calibration:
        if bool(values.get("expanded_formal_protocol")) != bool(
            dataset.get("expanded_formal_protocol", False)
        ):
            raise ValueError("frozen expanded-formal marker does not match the dataset")
        if values.get("protocol_profile") != dataset.get("protocol_profile"):
            raise ValueError("frozen protocol profile does not match the dataset")
    if causal_schema:
        if values.get("causal_prefix_protocol") is not True:
            raise ValueError("causal freeze marker is invalid")
        if shared_calibration:
            expected_revolutions = _expected_shared_revolutions(
                dataset["protocol"]
            )
        else:
            expected_revolutions = int(dataset.get("revolutions_per_seed", 0))
        if int(values.get("revolutions_per_seed", 0)) != expected_revolutions:
            raise ValueError("causal revolution contract changed after freeze")
        dataset_protocol_fingerprint = (
            dataset.get("protocol_fingerprint")
            if shared_calibration
            else dataset.get("protocol_fingerprint_sha256")
        )
        if values.get("protocol_fingerprint_sha256") != dataset_protocol_fingerprint:
            raise ValueError("causal protocol fingerprint changed after freeze")
        if not shared_calibration and values.get("geometry_gate") != dataset.get(
            "geometry_gate"
        ):
            raise ValueError("causal geometry gate changed after freeze")
    dataset_corruption_levels = (
        dataset["protocol"]["corruption_levels"]
        if shared_calibration
        else dataset["corruption_levels"]
    )
    if list(values.get("corruption_levels", [])) != list(
        dataset_corruption_levels
    ):
        raise ValueError("frozen corruption contract no longer matches the dataset")
    artifact_hash_keys = [
        "weights_sha256",
        "normalizer_sha256",
        "model_config_sha256",
        "training_history_sha256",
    ]
    if schema_version != LEGACY_FREEZE_SCHEMA_VERSION:
        artifact_hash_keys.append("validation_selection_sha256")
    if causal_schema:
        artifact_hash_keys.append("initialization_selection_sha256")
    if schema_version == CAUSAL_FREEZE_SCHEMA_VERSION:
        artifact_hash_keys.extend(
            ["edge_sampling_evidence_sha256", "validation_evidence_sha256"]
        )
    artifact_hashes = {
        key: values[key]
        for key in artifact_hash_keys
    }
    fingerprint_payload = {
            "dataset_fingerprint_sha256": values["dataset_fingerprint_sha256"],
            "artifact_hashes": artifact_hashes,
            "train_seeds": values["train_seeds"],
            "validation_seeds": values["validation_seeds"],
            "reserved_test_seeds": values["reserved_test_seeds"],
            "corruption_levels": values["corruption_levels"],
    }
    if schema_version != LEGACY_FREEZE_SCHEMA_VERSION:
        selection = json.loads(
            (path.parent / values["validation_selection"]).read_text(encoding="utf-8")
        )
        _validate_validation_selection_contract(selection)
        if values.get("selected_route") != selection.get("selected_route"):
            raise ValueError("frozen selected route does not match validation selection")
        selected_probability = float(values.get("selected_probability_threshold"))
        selected_cost = float(values.get("selected_unmatched_cost"))
        if selected_probability != float(
            selection.get("selected_probability_threshold")
        ):
            raise ValueError(
                "frozen probability threshold does not match validation selection"
            )
        if not math.isclose(
            selected_cost,
            float(selection.get("selected_unmatched_cost")),
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise ValueError("frozen unmatched cost does not match validation selection")
        if values.get("selected_route") not in LEARNED_ROUTES:
            raise ValueError("frozen selected route is invalid")
        _validate_probability_cost_pair(
            selected_probability,
            selected_cost,
            context="frozen selected policy",
        )
        route_probabilities = values.get("route_probability_thresholds")
        route_costs = values.get("route_unmatched_costs")
        if set(route_probabilities or {}) != set(LEARNED_ROUTES):
            raise ValueError("frozen route probability thresholds are incomplete")
        if set(route_costs or {}) != set(LEARNED_ROUTES):
            raise ValueError("frozen route unmatched costs are incomplete")
        for route in LEARNED_ROUTES:
            probability = float(route_probabilities[route])
            cost = float(route_costs[route])
            selected_route_policy = selection.get("best_by_route", {}).get(route, {})
            if probability != float(
                selected_route_policy.get("probability_threshold")
            ):
                raise ValueError(
                    f"frozen probability threshold does not match validation selection for {route}"
                )
            if not math.isclose(
                cost,
                float(selected_route_policy.get("unmatched_cost")),
                rel_tol=1.0e-12,
                abs_tol=1.0e-12,
            ):
                raise ValueError(
                    f"frozen unmatched cost does not match validation selection for {route}"
                )
            _validate_probability_cost_pair(
                probability,
                cost,
                context=f"frozen route {route}",
            )
        fingerprint_payload.update(
            {
                "selected_route": values["selected_route"],
                "selected_probability_threshold": values[
                    "selected_probability_threshold"
                ],
                "selected_unmatched_cost": values["selected_unmatched_cost"],
                "route_probability_thresholds": values[
                    "route_probability_thresholds"
                ],
                "route_unmatched_costs": values["route_unmatched_costs"],
            }
        )
    if causal_schema:
        summary = json.loads(
            (path.parent / values["initialization_selection"]).read_text(
                encoding="utf-8"
            )
        )
        if summary.get("initialization_count") != 5:
            raise ValueError("initialization selection is incomplete")
        candidates = list(summary.get("candidates", []))
        if len(candidates) != 5:
            raise ValueError("initialization selection must contain five candidates")
        selected = [item for item in candidates if item.get("selected")]
        retained = [item for item in candidates if item.get("checkpoint_retained")]
        if len(selected) != 1 or len(retained) != 1 or selected != retained:
            raise ValueError("exactly one initialization checkpoint may be retained")
        if int(selected[0]["initialization_index"]) != int(
            values["selected_initialization_index"]
        ):
            raise ValueError("selected initialization index is inconsistent")
        fingerprint_payload.update(
            {
                "selected_initialization_index": values[
                    "selected_initialization_index"
                ],
                "selected_initialization_seed": values[
                    "selected_initialization_seed"
                ],
                "initialization_count": values["initialization_count"],
                "ensemble_used_for_test": values["ensemble_used_for_test"],
                "protocol_fingerprint_sha256": values[
                    "protocol_fingerprint_sha256"
                ],
                "train_input_fingerprint_sha256": values[
                    "train_input_fingerprint_sha256"
                ],
                "validation_input_fingerprint_sha256": values[
                    "validation_input_fingerprint_sha256"
                ],
                "geometry_gate": values["geometry_gate"],
            }
        )
        for key in (
            "dataset_manifest_kind",
            "train_label_fingerprint_sha256",
            "validation_label_fingerprint_sha256",
            "offline_label_schema",
            "route_name",
            "candidate_graph_contract",
            "target_count",
        ):
            if key in values:
                fingerprint_payload[key] = values[key]
        if shared_calibration:
            if values.get("route_name") != "gnn":
                raise ValueError("shared freeze route name is invalid")
            if values.get("offline_label_schema") != "track_truth_counts_v1":
                raise ValueError("shared freeze offline label schema is invalid")
            if values.get("model_sha256") != values.get("weights_sha256"):
                raise ValueError("shared freeze model hash is inconsistent")
            if values.get("test_snapshot_open_count") != 0:
                raise ValueError("shared freeze opened a test snapshot")
            if values.get("test_label_open_count") != 0:
                raise ValueError("shared freeze opened a test label")
            if canonical_json_sha256(values.get("train_inputs", [])) != values.get(
                "train_input_fingerprint_sha256"
            ):
                raise ValueError("shared training input fingerprint mismatch")
            if canonical_json_sha256(
                values.get("validation_inputs", [])
            ) != values.get("validation_input_fingerprint_sha256"):
                raise ValueError("shared validation input fingerprint mismatch")
    if schema_version == CAUSAL_FREEZE_SCHEMA_VERSION:
        if values.get("feature_contract_version") != FEATURE_CONTRACT_VERSION:
            raise ValueError("frozen feature contract is invalid")
        if values.get("cost_contract") != "negative_log_effective_probability_v2":
            raise ValueError("frozen cost contract is invalid")
        if values.get("validation_failed_closed") is not False:
            raise ValueError("a failed validation cannot produce a freeze manifest")
        if "freeze_allowed" in values and values.get("freeze_allowed") is not True:
            raise ValueError("a causal freeze must explicitly allow freezing")
        if values.get("promotion_allowed") is True:
            raise ValueError("a validation freeze cannot authorize scale promotion")
        if (
            "promotion_status" in values
            and values.get("promotion_status")
            != "pending_reserved_test_same_input_comparison"
        ):
            raise ValueError("frozen promotion status is invalid")
        if values.get("confirmation_policy") != {
            "window_revolutions": 3,
            "required_hits": 2,
            "one_to_one_assignment": "hungarian",
        }:
            raise ValueError("frozen confirmation policy is invalid")
        sampling = json.loads(
            (path.parent / values["edge_sampling_evidence"]).read_text(
                encoding="utf-8"
            )
        )
        if sampling.get("positive_retention_ratio") != 1.0:
            raise ValueError("frozen edge sampling dropped a positive edge")
        validation = json.loads(
            (path.parent / values["validation_evidence"]).read_text(
                encoding="utf-8"
            )
        )
        if validation.get("validation_failed_closed") is not False:
            raise ValueError("frozen validation evidence is failed closed")
        if (
            "freeze_allowed" in validation
            and validation.get("freeze_allowed") is not True
        ):
            raise ValueError("frozen validation evidence does not allow freezing")
        if validation.get("promotion_allowed") is True:
            raise ValueError("validation evidence cannot authorize scale promotion")
        fingerprint_payload.update(
            {
                "feature_contract_version": values["feature_contract_version"],
                "snapshot_contract_version": values[
                    "snapshot_contract_version"
                ],
                "tracker_fingerprint": values["tracker_fingerprint"],
                "confirmation_policy": values["confirmation_policy"],
                "cost_contract": values["cost_contract"],
                "validation_failed_closed": values[
                    "validation_failed_closed"
                ],
            }
        )
    expected_model_fingerprint = canonical_json_sha256(fingerprint_payload)
    if values.get("model_fingerprint_sha256") != expected_model_fingerprint:
        raise ValueError("frozen model fingerprint mismatch")
    return values, path.parent
