"""Reproducible micro-profile for the scalable D3 learning export path."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import platform
from statistics import median
import sys
import tempfile
from time import perf_counter
import tracemalloc
from typing import Any, Callable, TypeVar

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d3_assignment_planner import (
    AssignmentPlanner,
    LearningFrameRecord,
    PlannerConfig,
    ResourceState,
    TargetTrack,
    build_latest_learning_frame_record,
    write_learning_dataset,
)


T = TypeVar("T")


def _tracks(count: int) -> tuple[TargetTrack, ...]:
    return tuple(
        TargetTrack(
            track_id=f"T-{index:03d}",
            threat_score=0.2 + 0.7 * ((index % 11) / 10.0),
            covariance=0.05,
            window_cost=(index % 5) / 5.0,
            position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
            velocity_ned=(-2.0, 0.25 * (index % 3), 0.0),
            position_covariance_ned=np.eye(3) * (1.0 + index * 0.01),
            region_id="ALL",
            candidate_resource_region_ids=("ALL",),
            identity_commitment_state="committed",
        )
        for index in range(count)
    )


def _resources(count: int) -> tuple[ResourceState, ...]:
    return tuple(
        ResourceState(
            resource_id=f"R-{(index * 7) % 211:03d}",
            health_score=0.8 + 0.01 * (index % 10),
            load_penalty=0.01 * (index % 4),
            fov_difficulty=0.02 * (index % 7),
            conflict_risk=0.01 * (index % 5),
            position_ned=(float(index * 20), float((index % 8) * 200), -100.0),
            velocity_ned=(0.0, 0.0, 0.0),
            position_covariance_ned=np.eye(3) * 0.25,
            max_speed_mps=14.0,
            max_intercept_range_m=5_000.0,
            region_id="ALL",
            reachable_target_region_ids=("ALL",),
        )
        for index in range(count)
    )


def _median_call(function: Callable[[], T], repeat: int) -> tuple[float, T]:
    runs: list[float] = []
    result: T | None = None
    for _ in range(repeat):
        started = perf_counter()
        result = function()
        runs.append(perf_counter() - started)
    assert result is not None
    return float(median(runs)), result


def run_profile(
    *,
    count: int = 200,
    max_candidate_edges: int = 32,
    frame_count: int = 6,
    repeat: int = 5,
) -> dict[str, Any]:
    if count < 1 or max_candidate_edges < 1 or frame_count < 3 or repeat < 1:
        raise ValueError("count/max edges/repeat must be positive and frame_count >= 3")

    tracks = _tracks(count)
    resources = _resources(count)
    planner = AssignmentPlanner(
        config=PlannerConfig.scalable_3d(
            enable_hysteresis=False,
            max_candidate_edges_per_target=max_candidate_edges,
            human_authorization_state="approved",
            unassigned_base_cost=50.0,
        )
    )
    started = perf_counter()
    planner.plan(tracks, resources, timestamp=0.0)
    planner_elapsed_s = perf_counter() - started

    def build_frame() -> LearningFrameRecord:
        return build_latest_learning_frame_record(
            planner,
            scenario_version="d3_learning_export_profile_200v200_v1",
            seed=0,
            episode="episode_000",
            frame_index=0,
        )

    frame_build_median_s, record = _median_call(build_frame, repeat)
    to_dict_median_s, _ = _median_call(record.to_dict, repeat)
    json_encode_median_s, line = _median_call(record.to_json_line, repeat)
    json_decode_median_s, _ = _median_call(
        lambda: LearningFrameRecord.from_json_line(line), repeat
    )

    records = tuple(
        replace(
            record,
            seed=index % 3,
            episode=f"episode_{index % 3}",
            frame_index=index // 3,
        )
        for index in range(frame_count)
    )

    def finalize_once() -> float:
        with tempfile.TemporaryDirectory() as temporary:
            started = perf_counter()
            write_learning_dataset(
                Path(temporary) / "dataset",
                iter(records),
                source_kind="profile_only",
                minimum_unseen_seed_count=1,
            )
            return perf_counter() - started

    finalize_runs_s = [finalize_once() for _ in range(repeat)]
    with tempfile.TemporaryDirectory() as temporary:
        tracemalloc.start()
        write_learning_dataset(
            Path(temporary) / "dataset",
            iter(records),
            source_kind="profile_only",
            minimum_unseen_seed_count=1,
        )
        _, finalize_peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    return {
        "schema": "d3_learning_export_microprofile_v1",
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "fixture": {
            "target_count": count,
            "resource_count": count,
            "max_candidate_edges_per_target": max_candidate_edges,
            "candidate_edge_count": len(record.candidate_edge_indices),
            "frame_count": frame_count,
            "canonical_bytes_per_frame": len(line.encode("ascii")),
        },
        "timings_s": {
            "planner_once": planner_elapsed_s,
            "frame_build_median": frame_build_median_s,
            "to_dict_median": to_dict_median_s,
            "canonical_json_encode_median": json_encode_median_s,
            "json_decode_and_validate_median": json_decode_median_s,
            "dataset_finalize_runs": finalize_runs_s,
            "dataset_finalize_median": float(median(finalize_runs_s)),
        },
        "memory": {"dataset_finalize_tracemalloc_peak_bytes": finalize_peak_bytes},
        "contract": {
            "dataset_schema": "d3_learning_dataset_v2",
            "split_policy": "d3_numeric_seed_atomic_split_v2",
            "timings_are_acceptance_thresholds": False,
            "truth_fields_allowed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--max-candidate-edges", type=int, default=32)
    parser.add_argument("--frame-count", type=int, default=6)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_profile(
        count=args.count,
        max_candidate_edges=args.max_candidate_edges,
        frame_count=args.frame_count,
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
