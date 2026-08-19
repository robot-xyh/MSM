"""Per-camera Hungarian assignment and temporal confirmation."""

from __future__ import annotations

import math
from typing import Literal, Mapping

import numpy as np

from .contracts import TargetTrackGraph
from .deterministic import (
    TargetTrackAssignment,
    publish_with_confirmation,
    solve_assignment_from_costs,
)
from .model import FeatureNormalizer, TargetTrackCostGNN, predict_cost_corrections


AssignmentRoute = Literal["deterministic", "gnn_assisted"]


def route_costs(
    graph: TargetTrackGraph,
    route: AssignmentRoute,
    *,
    model: TargetTrackCostGNN | None = None,
    normalizer: FeatureNormalizer | None = None,
    correction_weight: float = 0.5,
    device: str = "cpu",
) -> tuple[np.ndarray, np.ndarray]:
    """Score only hard-whitelisted edges; neither route can create an edge."""

    graph.validate()
    if not math.isfinite(correction_weight) or correction_weight < 0.0:
        raise ValueError("correction_weight must be finite and non-negative")
    if route == "deterministic":
        corrections = np.zeros_like(graph.rule_cost, dtype=np.float32)
    elif route == "gnn_assisted":
        if model is None or normalizer is None:
            raise ValueError("GNN-assisted assignment requires model and normalizer")
        corrections = predict_cost_corrections(
            model, graph, normalizer, device=device
        )
    else:
        raise ValueError(f"unsupported target-track assignment route: {route}")
    final = graph.rule_cost.astype(np.float64) + correction_weight * corrections.astype(
        np.float64
    )
    if final.shape != graph.rule_cost.shape or not np.all(np.isfinite(final)):
        raise ValueError("target-track final costs are invalid")
    return corrections.astype(np.float32), final


def solve_target_track_assignment(
    graph: TargetTrackGraph,
    route: AssignmentRoute,
    *,
    model: TargetTrackCostGNN | None = None,
    normalizer: FeatureNormalizer | None = None,
    correction_weight: float = 0.5,
    unmatched_cost: float = 1.0,
    device: str = "cpu",
) -> TargetTrackAssignment:
    """Solve one camera independently with explicit unmatched alternatives."""

    corrections, final_costs = route_costs(
        graph,
        route,
        model=model,
        normalizer=normalizer,
        correction_weight=correction_weight,
        device=device,
    )
    return solve_assignment_from_costs(
        graph,
        route,
        corrections=corrections,
        final_costs=final_costs,
        unmatched_cost=unmatched_cost,
    )


def solve_camera_graphs(
    graphs: Mapping[str, TargetTrackGraph],
    route: AssignmentRoute,
    **kwargs: object,
) -> Mapping[str, TargetTrackAssignment]:
    """Keep A and B assignments independent while sharing one scoring route."""

    return {
        camera_id: solve_target_track_assignment(graph, route, **kwargs)
        for camera_id, graph in graphs.items()
    }
