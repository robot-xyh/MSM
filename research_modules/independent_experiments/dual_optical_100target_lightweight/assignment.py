"""Joint probability filtering and one-to-one Hungarian assignment."""

from __future__ import annotations

import math

import numpy as np

from dual_optical_100target_gnn.assignment import AssignmentResult, solve_assignment
from dual_optical_100target_gnn.schema import OnlineGraph


def probability_threshold_to_unmatched_cost(threshold: float) -> float:
    if not math.isfinite(threshold) or not 0.0 < threshold < 1.0:
        raise ValueError("probability threshold must be in (0, 1)")
    return -math.log(threshold)


def solve_probability_assignment(
    graph: OnlineGraph,
    probabilities: np.ndarray,
    threshold: float,
    unmatched_cost: float | None = None,
) -> AssignmentResult:
    """Apply two independently frozen acceptance controls before assignment.

    ``threshold`` rejects weak candidate edges. ``unmatched_cost`` then lets the
    global solver prefer leaving a track unmatched when every remaining edge is
    too expensive.  Keeping the two values independent is important: deriving
    one from the other hides cost-scale failures during validation.

    ``unmatched_cost=None`` retains the V1 behaviour for legacy frozen models.
    """

    probabilities = np.asarray(probabilities, dtype=np.float64)
    if probabilities.shape != graph.geometry_cost.shape:
        raise ValueError("one probability is required for every candidate edge")
    if not np.all(np.isfinite(probabilities)):
        raise ValueError("assignment probabilities must be finite")
    if np.any(probabilities < 0.0) or np.any(probabilities > 1.0):
        raise ValueError("assignment probabilities must be in [0, 1]")
    effective_unmatched_cost = (
        probability_threshold_to_unmatched_cost(threshold)
        if unmatched_cost is None
        else float(unmatched_cost)
    )
    if not math.isfinite(effective_unmatched_cost) or effective_unmatched_cost <= 0.0:
        raise ValueError("unmatched_cost must be finite and positive")

    # The shared solver blocks costs at or above unmatched_cost.  Force edges
    # rejected by the separately frozen probability threshold above that cost
    # without changing the candidate graph or its geometry gate.
    filtered_probabilities = probabilities.copy()
    filtered_probabilities[probabilities <= threshold] = 0.0
    return solve_assignment(
        graph,
        filtered_probabilities,
        "learned",
        unmatched_cost=effective_unmatched_cost,
    )


def assignment_acceptance_mask(
    probabilities: np.ndarray,
    threshold: float,
    unmatched_cost: float,
) -> np.ndarray:
    """Return edges eligible immediately before the Hungarian conflict solve."""

    values = np.asarray(probabilities, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("assignment probabilities must be finite")
    if not 0.0 < threshold < 1.0:
        raise ValueError("probability threshold must be in (0, 1)")
    if not math.isfinite(unmatched_cost) or unmatched_cost <= 0.0:
        raise ValueError("unmatched_cost must be finite and positive")
    costs = -np.log(np.clip(values, 1.0e-6, 1.0))
    return (values > threshold) & (costs < unmatched_cost)
