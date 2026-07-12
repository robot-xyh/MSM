#!/usr/bin/env python3
"""Run D2's governed N-target, multi-seed offline calibration."""

from __future__ import annotations

import argparse
from pathlib import Path

from d2_data_association import (
    run_dense_crossing_calibration,
    write_dense_crossing_calibration_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-count", type=int, default=5)
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument(
        "--seeds",
        default=",".join(str(seed) for seed in range(10)),
        help="Comma-separated unique seeds; at least 10 are required.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    report = run_dense_crossing_calibration(
        seeds=seeds,
        target_count=args.target_count,
        steps=args.steps,
        truth_output_directory=args.output / "offline_truth",
    )
    write_dense_crossing_calibration_report(
        args.output / "calibration_summary.json",
        report,
    )


if __name__ == "__main__":
    main()
