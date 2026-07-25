#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.online_batch_frame_performance import (
    MINIMUM_MEASUREMENT_COUNT,
    MINIMUM_REPETITIONS,
    compare_online_batch_frame_handoff_variants,
    write_online_batch_frame_handoff_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the D1 online-batch-to-frame handoff microbenchmark."
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=MINIMUM_REPETITIONS,
    )
    parser.add_argument(
        "--measurement-count",
        type=int,
        default=MINIMUM_MEASUREMENT_COUNT,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "research_modules/d1_sensor_fusion/outputs/"
            "online_batch_frame_handoff_20260725"
        ),
    )
    args = parser.parse_args()

    report = compare_online_batch_frame_handoff_variants(
        repetitions=args.repetitions,
        measurement_count=args.measurement_count,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_online_batch_frame_handoff_report(
        report,
        json_path=args.output_dir / "online_batch_frame_handoff_benchmark.json",
        markdown_path=(
            args.output_dir / "ONLINE_BATCH_FRAME_HANDOFF_BENCHMARK_CN.md"
        ),
    )
    print(
        "module_threshold_met="
        f"{report['comparison']['module_threshold_met']}"
    )
    print(
        "median_improvement_pct="
        f"{100.0 * report['comparison']['median_improvement_fraction']:.6f}"
    )
    print(
        "candidate_faster="
        f"{report['comparison']['candidate_faster_count']}/"
        f"{report['configuration']['repetitions']}"
    )
    print(f"output_dir={args.output_dir}")
    return 0 if report["comparison"]["module_threshold_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
