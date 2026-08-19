"""One-to-one assignment after geometry gating."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np
from scipy.optimize import linear_sum_assignment

from .schema import OnlineGraph


AssignmentMode = Literal["geometry", "learned", "hybrid"]
HYBRID_GEOMETRY_WEIGHT = 0.4
HYBRID_LEARNED_WEIGHT = 0.6


def probability_threshold_to_unmatched_cost(probability_threshold: float) -> float:
    """Convert a probability acceptance threshold to negative-log cost space."""

    value = float(probability_threshold)
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise ValueError("probability_threshold must be finite and in (0, 1)")
    return -math.log(value)


@dataclass(frozen=True)
class SelectedPair:
    index_a: int
    index_b: int
    edge_index: int
    cost: float


@dataclass(frozen=True)
class AssignmentResult:
    mode: AssignmentMode
    selected_pairs: tuple[SelectedPair, ...]
    unmatched_a: tuple[int, ...]
    unmatched_b: tuple[int, ...]
    duplicate_track_assignment_count: int


def edge_costs(
    graph: OnlineGraph,
    probabilities: np.ndarray | None,
    mode: AssignmentMode,
) -> np.ndarray:
    if mode == "geometry":
        return graph.geometry_cost.astype(np.float64)
    if probabilities is None or probabilities.shape != graph.geometry_cost.shape:
        raise ValueError(f"{mode} assignment requires one probability per candidate edge")
    if not np.all(np.isfinite(probabilities)):
        raise ValueError("assignment probabilities must be finite")
    if np.any(probabilities < 0.0) or np.any(probabilities > 1.0):
        raise ValueError("assignment probabilities must be in [0, 1]")
    effective = effective_edge_probabilities(graph, probabilities, mode)
    learned = -np.log(np.clip(effective, 1e-6, 1.0))
    if mode == "learned":
        return learned
    if mode == "hybrid":
        return learned
    raise ValueError(f"unknown assignment mode: {mode}")


def effective_edge_probabilities(
    graph: OnlineGraph,
    probabilities: np.ndarray | None,
    mode: AssignmentMode,
) -> np.ndarray:
    """Put learned and hybrid acceptance on one calibrated probability scale."""

    if mode == "geometry":
        # Geometry cost is treated as a normalized residual for diagnostics.
        return np.exp(-0.5 * np.square(np.clip(graph.geometry_cost, 0.0, 8.0)))
    if probabilities is None or probabilities.shape != graph.geometry_cost.shape:
        raise ValueError(f"{mode} assignment requires one probability per candidate edge")
    values = probabilities.astype(np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("assignment probabilities must be finite")
    if np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError("assignment probabilities must be in [0, 1]")
    learned_probability = np.clip(values, 1.0e-6, 1.0)
    if mode == "learned":
        return learned_probability
    if mode == "hybrid":
        geometry_probability = np.exp(
            -0.5 * np.square(np.clip(graph.geometry_cost.astype(np.float64), 0.0, 8.0))
        )
        return np.power(geometry_probability, HYBRID_GEOMETRY_WEIGHT) * np.power(
            learned_probability, HYBRID_LEARNED_WEIGHT
        )
    raise ValueError(f"unknown assignment mode: {mode}")


def solve_assignment(
    graph: OnlineGraph,
    probabilities: np.ndarray | None,
    mode: AssignmentMode,
    *,
    unmatched_cost: float = 1.20,
) -> AssignmentResult:
    if not math.isfinite(unmatched_cost) or unmatched_cost <= 0.0:
        raise ValueError("unmatched_cost must be finite and positive")
    costs = edge_costs(graph, probabilities, mode)
    count_a = len(graph.track_ids_a)
    count_b = len(graph.track_ids_b)
    size = count_a + count_b
    blocked = 1.0e6
    matrix = np.full((size, size), blocked, dtype=np.float64)
    edge_lookup: dict[tuple[int, int], tuple[int, float]] = {}
    for edge_id, ((index_a, index_b), cost) in enumerate(
        zip(graph.edge_index.T, costs)
    ):
        key = (int(index_a), int(index_b))
        if key in edge_lookup:
            raise ValueError(f"duplicate candidate edge: {key}")
        if not math.isfinite(float(cost)):
            raise ValueError("assignment costs must be finite")
        edge_lookup[key] = (edge_id, float(cost))
        # A rejected edge must not affect the global optimum. If it remains in
        # the matrix and is filtered only after solving, it can displace a
        # legal low-cost edge that shares one endpoint.
        if float(cost) >= unmatched_cost:
            continue
        matrix[key] = float(cost)
    for index_a in range(count_a):
        matrix[index_a, count_b + index_a] = unmatched_cost
    for index_b in range(count_b):
        matrix[count_a + index_b, index_b] = unmatched_cost
    matrix[count_a:, count_b:] = 0.0
    rows, columns = linear_sum_assignment(matrix)
    selected: list[SelectedPair] = []
    matched_a: set[int] = set()
    matched_b: set[int] = set()
    for row, column in zip(rows, columns):
        if row >= count_a or column >= count_b:
            continue
        value = matrix[row, column]
        if not math.isfinite(value) or value >= unmatched_cost:
            continue
        edge_id, cost = edge_lookup[(int(row), int(column))]
        selected.append(SelectedPair(int(row), int(column), edge_id, cost))
        matched_a.add(int(row))
        matched_b.add(int(column))
    duplicate_count = len(selected) - len({item.index_a for item in selected})
    duplicate_count += len(selected) - len({item.index_b for item in selected})
    return AssignmentResult(
        mode=mode,
        selected_pairs=tuple(sorted(selected, key=lambda item: (item.index_a, item.index_b))),
        unmatched_a=tuple(index for index in range(count_a) if index not in matched_a),
        unmatched_b=tuple(index for index in range(count_b) if index not in matched_b),
        duplicate_track_assignment_count=duplicate_count,
    )
