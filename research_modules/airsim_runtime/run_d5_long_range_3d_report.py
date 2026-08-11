#!/usr/bin/env python3
"""Render 3D positions and trajectories from a completed long-range episode."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
for candidate in (
    ROOT,
    *(
        ROOT / relative
        for relative in (
            "research_modules",
            "research_modules/d1_sensor_fusion/src",
            "research_modules/d2_data_association",
            "research_modules/d3_assignment_planner/src",
            "research_modules/d4_distributed_fallback",
            "research_modules/d5_terminal_association/src",
            "research_modules/d6_evaluation_metrics",
            "research_modules/d7_proportional_guidance",
        )
    ),
):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from airsim_runtime.long_range_3d_reporting import (  # noqa: E402
    write_long_range_3d_trajectory_figures,
)


DEFAULT_EPISODE = Path(
    "research_modules/airsim_runtime/outputs/"
    "d5_cv_long_range_20target_visual_evidence_20260810/coverage_safe"
)
DEFAULT_OUTPUT = Path(
    "subagent_reviews/assets/d5_20_target_long_range_20260810"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-dir", type=Path, default=DEFAULT_EPISODE)
    parser.add_argument("--scenario-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenario_path = args.scenario_json or args.episode_dir.parent / "scenario.json"
    paths, summary = write_long_range_3d_trajectory_figures(
        args.episode_dir,
        scenario_path=scenario_path,
        output_dir=args.output_dir,
    )
    print(
        f"target_count={summary['target_count']} duration_s={summary['duration_s']:.2f} "
        f"interceptor_path_m={summary['interceptor_path_length_m']:.2f}"
    )
    for name, path in paths.items():
        print(f"{name}={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
