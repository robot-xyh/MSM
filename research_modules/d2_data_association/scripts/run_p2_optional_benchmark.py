#!/usr/bin/env python3
"""Compare D2 baseline with isolated optional adapters on frozen replay files."""

from __future__ import annotations

import argparse
from pathlib import Path

from d2_data_association import (
    load_airsim_replay_frames,
    load_offline_truth_labels_jsonl,
    run_optional_framework_benchmark,
    write_p2_benchmark_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--offline-truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--frameworks",
        default="filterpy,stonesoup,jpda,mht",
        help=(
            "Comma-separated research adapters: filterpy,stonesoup,jpda,mht. "
            "The GNN/Hungarian baseline always runs."
        ),
    )
    args = parser.parse_args()
    frameworks = tuple(
        value.strip() for value in args.frameworks.split(",") if value.strip()
    )
    report = run_optional_framework_benchmark(
        load_airsim_replay_frames(args.replay),
        load_offline_truth_labels_jsonl(args.offline_truth),
        frameworks=frameworks,
    )
    write_p2_benchmark_report(args.output, report)


if __name__ == "__main__":
    main()
