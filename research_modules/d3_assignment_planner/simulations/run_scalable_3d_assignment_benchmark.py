"""Reproducible structural benchmark for D3 scalable sparse assignment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

import numpy as np

from d3_assignment_planner import (
    AssignmentPlanner,
    PlannerConfig,
    ResourceState,
    TargetTrack,
)


def _tracks(count: int) -> tuple[TargetTrack, ...]:
    return tuple(
        TargetTrack(
            track_id=f"T-{index:03d}",
            threat_score=0.7,
            covariance=0.05,
            window_cost=0.0,
            position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
            velocity_ned=(-2.0, 0.0, 0.0),
            position_covariance_ned=np.eye(3) * (1.0 + index * 0.01),
            region_id="ALL",
        )
        for index in range(count)
    )


def _resources(count: int) -> tuple[ResourceState, ...]:
    return tuple(
        ResourceState(
            resource_id=f"R-{index:03d}",
            position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
            velocity_ned=(0.0, 0.0, 0.0),
            position_covariance_ned=np.eye(3) * 0.25,
            max_speed_mps=14.0,
            max_intercept_range_m=5_000.0,
            region_id="ALL",
        )
        for index in range(count)
    )


def _run(
    tracks: tuple[TargetTrack, ...],
    resources: tuple[ResourceState, ...],
    *,
    max_edges: int,
    repeat: int,
    vectorized: bool,
) -> dict[str, Any]:
    elapsed_ms: list[float] = []
    plan = None
    for _ in range(repeat):
        planner = AssignmentPlanner(
            config=PlannerConfig.scalable_3d(
                enable_vectorized_sparse_costs=vectorized,
                enable_hysteresis=False,
                max_candidate_edges_per_target=max_edges,
                human_authorization_state="approved",
                unassigned_base_cost=50.0,
            )
        )
        started = perf_counter()
        plan = planner.plan(tracks, resources, timestamp=0.0)
        elapsed_ms.append((perf_counter() - started) * 1_000.0)
    assert plan is not None
    return {
        "cost_build_path": plan.metadata["cost_build_path"],
        "runs_ms": [round(value, 3) for value in elapsed_ms],
        "median_ms": round(median(elapsed_ms), 3),
        "assignment_count": len(plan.assignments),
        "candidate_edge_count": plan.metadata["candidate_edge_count"],
        "candidate_full_edge_count": plan.metadata["candidate_full_edge_count"],
        "python_full_pair_cost_evaluation_count": plan.metadata[
            "python_full_pair_cost_evaluation_count"
        ],
        "candidate_breakdown_materialization_count": plan.metadata[
            "candidate_breakdown_materialization_count"
        ],
    }


def run_benchmark(*, count: int, max_edges: int, repeat: int) -> dict[str, Any]:
    tracks = _tracks(count)
    resources = _resources(count)
    reference = _run(
        tracks,
        resources,
        max_edges=max_edges,
        repeat=repeat,
        vectorized=False,
    )
    vectorized = _run(
        tracks,
        resources,
        max_edges=max_edges,
        repeat=repeat,
        vectorized=True,
    )
    return {
        "schema": "d3_scalable_assignment_benchmark_v1",
        "resource_count": count,
        "target_count": count,
        "max_candidate_edges_per_target": max_edges,
        "repeat": repeat,
        "reference": reference,
        "vectorized": vectorized,
        "median_speedup": round(
            float(reference["median_ms"]) / max(float(vectorized["median_ms"]), 1.0e-12),
            3,
        ),
        "semantic_contract": "same_rule_costs_hard_constraints_and_hungarian",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--max-edges", type=int, default=32)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.count <= 0 or args.max_edges <= 0 or args.repeat <= 0:
        parser.error("count, max-edges, and repeat must be positive")
    payload = run_benchmark(
        count=args.count,
        max_edges=args.max_edges,
        repeat=args.repeat,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
