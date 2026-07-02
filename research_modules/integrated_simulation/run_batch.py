#!/usr/bin/env python3
"""Run the standard integrated offline scenario batch."""

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
from integrated_simulation.reporting import write_batch_outputs


DEFAULT_SCENARIOS = [
    "nominal_5v5",
    "center_destroyed",
    "secondary_destroyed",
    "active_terminal_mismatch",
    "friend_overlap_hold",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--scenarios", nargs="*", default=DEFAULT_SCENARIOS)
    parser.add_argument(
        "--output",
        default="research_modules/integrated_simulation/outputs/batch",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output)
    results = []
    for offset, scenario_name in enumerate(args.scenarios):
        scenario_output = output_root / scenario_name
        config = make_standard_scenario(
            scenario_name,
            seed=args.seed + offset,
            duration_s=args.duration,
            output_root=scenario_output,
        )
        results.append(run_integrated_episode(config, output_dir=scenario_output))
    paths = write_batch_outputs(results, output_root)
    print(f"episodes={len(results)}")
    print(f"summary={paths['summary_csv'].resolve()}")
    print(f"report={paths['report_md'].resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
