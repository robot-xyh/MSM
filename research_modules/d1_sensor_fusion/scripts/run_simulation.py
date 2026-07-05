#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d1_sensor_fusion.simulation import run_simulation  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run D1 offline sensor-fusion simulation.")
    parser.add_argument(
        "--drone-count",
        dest="target_count",
        type=int,
        default=3,
        metavar="N",
        help="Number of target truth tracks to generate.",
    )
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--dt", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--output",
        type=Path,
        default=MODULE_ROOT / "reports",
        help="Directory for plots and Markdown report.",
    )
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    if args.target_count < 1:
        parser.error("--drone-count must be at least 1")
    return args


def main() -> int:
    args = parse_args()
    result = run_simulation(
        target_count=args.target_count,
        duration_s=args.duration,
        dt=args.dt,
        seed=args.seed,
        output_dir=args.output,
        make_plots=not args.no_plots,
        write_report=True,
    )
    print("D1 offline fusion simulation complete")
    for key, value in result.metrics.items():
        print(f"{key}: {value:.4f}")
    if result.report_path:
        print(f"report: {result.report_path}")
    if result.figure_paths:
        for path in result.figure_paths:
            print(f"figure: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
