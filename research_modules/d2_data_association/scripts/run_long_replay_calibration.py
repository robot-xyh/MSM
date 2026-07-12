#!/usr/bin/env python3
"""Run D2 long governed-replay calibration with offline truth scoring."""

from __future__ import annotations

import argparse
from pathlib import Path

from d2_data_association import (
    LongReplayCalibrationProfile,
    run_long_replay_calibration,
    write_dense_crossing_calibration_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-count", type=int, default=5)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--sample-period-s", type=float, default=0.2)
    parser.add_argument(
        "--seeds",
        default=",".join(str(seed) for seed in range(10)),
        help="Comma-separated unique seeds; at least 10 are required.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    profile = LongReplayCalibrationProfile(
        steps=args.steps,
        sample_period_s=args.sample_period_s,
    )
    report = run_long_replay_calibration(
        seeds=seeds,
        target_count=args.target_count,
        profile=profile,
        truth_output_directory=args.output / "offline_truth",
    )
    write_dense_crossing_calibration_report(
        args.output / "long_replay_calibration_summary.json",
        report,
    )


if __name__ == "__main__":
    main()
