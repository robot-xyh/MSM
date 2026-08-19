"""Model-free Hungarian assignment and temporal confirmation primitives."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from .contracts import TargetTrackGraph, TargetTrackPublication


AssignmentRoute = Literal["deterministic", "gnn_assisted"]


@dataclass(frozen=True)
class SelectedTargetTrack:
    hypothesis_index: int
    track_index: int
    edge_index: int
    rule_cost: float
    cost_correction: float
    final_cost: float


@dataclass(frozen=True)
class TargetTrackAssignment:
    seed: int
    revolution_index: int
    camera_id: str
    route: AssignmentRoute
    selected_pairs: tuple[SelectedTargetTrack, ...]
    unmatched_hypothesis_indices: tuple[int, ...]
    unmatched_track_indices: tuple[int, ...]
    whitelist_fingerprint: str
    duplicate_assignment_count: int


def solve_assignment_from_costs(
    graph: TargetTrackGraph,
    route: AssignmentRoute,
    *,
    corrections: np.ndarray,
    final_costs: np.ndarray,
    unmatched_cost: float = 1.0,
) -> TargetTrackAssignment:
    """Solve one hard-whitelisted graph with explicit unmatched alternatives."""

    graph.validate()
    if route not in {"deterministic", "gnn_assisted"}:
        raise ValueError(f"unsupported target-track assignment route: {route}")
    if not math.isfinite(unmatched_cost) or unmatched_cost <= 0.0:
        raise ValueError("unmatched_cost must be finite and positive")
    corrections = np.asarray(corrections, dtype=np.float32)
    final_costs = np.asarray(final_costs, dtype=np.float64)
    edge_count = graph.edge_index.shape[1]
    if corrections.shape != (edge_count,) or final_costs.shape != (edge_count,):
        raise ValueError("target-track costs do not match the hard whitelist")
    if not np.all(np.isfinite(corrections)) or not np.all(np.isfinite(final_costs)):
        raise ValueError("target-track costs must be finite")

    hypothesis_count = len(graph.hypothesis_ids)
    track_count = len(graph.track_ids)
    if hypothesis_count + track_count == 0:
        return TargetTrackAssignment(
            seed=graph.seed,
            revolution_index=graph.revolution_index,
            camera_id=graph.camera_id,
            route=route,
            selected_pairs=(),
            unmatched_hypothesis_indices=(),
            unmatched_track_indices=(),
            whitelist_fingerprint=graph.whitelist_fingerprint,
            duplicate_assignment_count=0,
        )

    size = hypothesis_count + track_count
    matrix = np.full((size, size), 1.0e9, dtype=np.float64)
    edge_lookup: dict[tuple[int, int], int] = {}
    for edge_id, ((hypothesis_index, track_index), cost) in enumerate(
        zip(graph.edge_index.T, final_costs)
    ):
        key = (int(hypothesis_index), int(track_index))
        if key in edge_lookup:
            raise ValueError("hard whitelist contains a duplicate candidate edge")
        edge_lookup[key] = edge_id
        if float(cost) < unmatched_cost:
            matrix[key] = float(cost)
    for hypothesis_index in range(hypothesis_count):
        matrix[hypothesis_index, track_count + hypothesis_index] = unmatched_cost
    for track_index in range(track_count):
        matrix[hypothesis_count + track_index, track_index] = unmatched_cost
    matrix[hypothesis_count:, track_count:] = 0.0

    rows, columns = linear_sum_assignment(matrix)
    selected: list[SelectedTargetTrack] = []
    matched_hypotheses: set[int] = set()
    matched_tracks: set[int] = set()
    for row, column in zip(rows, columns):
        if row >= hypothesis_count or column >= track_count:
            continue
        if matrix[row, column] >= unmatched_cost:
            continue
        edge_id = edge_lookup[(int(row), int(column))]
        selected.append(
            SelectedTargetTrack(
                hypothesis_index=int(row),
                track_index=int(column),
                edge_index=edge_id,
                rule_cost=float(graph.rule_cost[edge_id]),
                cost_correction=float(corrections[edge_id]),
                final_cost=float(final_costs[edge_id]),
            )
        )
        matched_hypotheses.add(int(row))
        matched_tracks.add(int(column))
    duplicate_count = len(selected) - len(
        {item.hypothesis_index for item in selected}
    )
    duplicate_count += len(selected) - len({item.track_index for item in selected})
    return TargetTrackAssignment(
        seed=graph.seed,
        revolution_index=graph.revolution_index,
        camera_id=graph.camera_id,
        route=route,
        selected_pairs=tuple(
            sorted(selected, key=lambda item: (item.hypothesis_index, item.track_index))
        ),
        unmatched_hypothesis_indices=tuple(
            index
            for index in range(hypothesis_count)
            if index not in matched_hypotheses
        ),
        unmatched_track_indices=tuple(
            index for index in range(track_count) if index not in matched_tracks
        ),
        whitelist_fingerprint=graph.whitelist_fingerprint,
        duplicate_assignment_count=duplicate_count,
    )


def solve_deterministic_assignment(
    graph: TargetTrackGraph,
    *,
    unmatched_cost: float = 1.0,
) -> TargetTrackAssignment:
    """Run rule-cost assignment without importing or loading a learned model."""

    corrections = np.zeros_like(graph.rule_cost, dtype=np.float32)
    return solve_assignment_from_costs(
        graph,
        "deterministic",
        corrections=corrections,
        final_costs=graph.rule_cost.astype(np.float64),
        unmatched_cost=unmatched_cost,
    )


def publish_with_confirmation(
    graph: TargetTrackGraph,
    assignment: TargetTrackAssignment,
    prior_publications: Sequence[TargetTrackPublication] = (),
) -> tuple[TargetTrackPublication, ...]:
    """Require the same local pairing in two of the latest three revolutions."""

    graph.validate()
    if (
        assignment.seed != graph.seed
        or assignment.revolution_index != graph.revolution_index
        or assignment.camera_id != graph.camera_id
        or assignment.whitelist_fingerprint != graph.whitelist_fingerprint
    ):
        raise ValueError("assignment does not belong to the supplied hard-whitelist graph")
    selected_by_hypothesis = {
        item.hypothesis_index: item for item in assignment.selected_pairs
    }
    publications = []
    for hypothesis_index, hypothesis_id in enumerate(graph.hypothesis_ids):
        selected = selected_by_hypothesis.get(hypothesis_index)
        local_track_id = (
            graph.track_ids[selected.track_index] if selected is not None else None
        )
        history_by_revolution: dict[int, str | None] = {}
        for publication in prior_publications:
            if (
                publication.seed == graph.seed
                and publication.camera_id == graph.camera_id
                and publication.hypothesis_id == hypothesis_id
                and publication.route == assignment.route
                and graph.revolution_index - 2
                <= publication.revolution_index
                < graph.revolution_index
            ):
                if publication.revolution_index in history_by_revolution:
                    raise ValueError("duplicate prior publication for one revolution")
                history_by_revolution[publication.revolution_index] = (
                    publication.local_track_id
                )
        history_by_revolution[graph.revolution_index] = local_track_id
        recent = [
            history_by_revolution[index]
            for index in range(
                max(1, graph.revolution_index - 2), graph.revolution_index + 1
            )
            if index in history_by_revolution
        ]
        agreement_count = (
            sum(value == local_track_id for value in recent)
            if local_track_id is not None
            else 0
        )
        if local_track_id is None:
            decision_state = "unmatched"
        elif agreement_count >= 2:
            decision_state = "confirmed"
        else:
            decision_state = "tentative"
        publications.append(
            TargetTrackPublication(
                seed=graph.seed,
                revolution_index=graph.revolution_index,
                camera_id=graph.camera_id,
                hypothesis_id=hypothesis_id,
                local_track_id=local_track_id,
                route=assignment.route,
                decision_state=decision_state,
                agreement_count=agreement_count,
                window_size=len(recent),
                final_cost=(None if selected is None else selected.final_cost),
                whitelist_fingerprint=graph.whitelist_fingerprint,
            )
        )
    return tuple(publications)


def solve_deterministic_camera_graphs(
    graphs: Mapping[str, TargetTrackGraph],
    *,
    unmatched_cost: float = 1.0,
) -> Mapping[str, TargetTrackAssignment]:
    return {
        camera_id: solve_deterministic_assignment(
            graph, unmatched_cost=unmatched_cost
        )
        for camera_id, graph in graphs.items()
    }
