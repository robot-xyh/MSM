#!/usr/bin/env python3
"""Run the dependency-free phase-1 AirSim dry-run pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
for rel in (
    "research_modules",
    "research_modules/d1_sensor_fusion/src",
    "research_modules/d2_data_association",
    "research_modules/d3_assignment_planner/src",
    "research_modules/d4_distributed_fallback",
    "research_modules/d5_terminal_association/src",
    "research_modules/d6_evaluation_metrics",
    "research_modules/d7_proportional_guidance",
):
    path = str(ROOT / rel)
    if path not in sys.path:
        sys.path.insert(0, path)

from airsim_dryrun import AirSimEpisodeConfig, run_airsim_dry_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="nominal_5v5")
    parser.add_argument("--episode-id", default="episode_001")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--dt", type=float, default=0.5)
    parser.add_argument("--output", default="research_modules/airsim_dryrun/outputs/episode_001")
    parser.add_argument("--no-lidar", action="store_true")
    parser.add_argument("--no-acoustic", action="store_true")
    parser.add_argument("--no-eo", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AirSimEpisodeConfig(
        scenario_name=args.scenario,
        episode_id=args.episode_id,
        seed=args.seed,
        duration_s=args.duration,
        dt_s=args.dt,
        include_lidar=not args.no_lidar,
        include_acoustic=not args.no_acoustic,
        include_eo=not args.no_eo,
    )
    result = run_airsim_dry_run(config, output_dir=args.output)
    print(f"episode_id={result.episode_id}")
    print(f"scenario={result.scenario_name}")
    print(f"frame_count={result.frame_count}")
    print(f"real_airsim_used={result.metadata['real_airsim_used']}")
    print(f"track_rmse={result.metrics['track_rmse']:.3f}")
    print(f"output_dir={Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
