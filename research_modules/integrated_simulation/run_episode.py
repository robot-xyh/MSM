#!/usr/bin/env python3
"""Run one integrated offline D1-D6 episode."""

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

from integrated_simulation import make_standard_scenario, run_integrated_episode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="nominal_5v5")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument(
        "--output",
        default="research_modules/integrated_simulation/outputs/episode",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = make_standard_scenario(
        args.scenario,
        seed=args.seed,
        duration_s=args.duration,
        output_root=args.output,
    )
    result = run_integrated_episode(config, output_dir=args.output)
    print(f"scenario={result.scenario.name}")
    print(f"track_rmse={result.metrics.track_rmse:.3f}")
    print(f"terminal_accuracy={result.metrics.terminal_association_accuracy:.3f}")
    print(f"decision_count={len(result.decisions)}")
    print(f"output_dir={Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
