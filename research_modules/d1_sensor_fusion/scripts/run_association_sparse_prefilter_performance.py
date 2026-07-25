#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.association_sparse_prefilter_performance import (
    benchmark_association_sparse_prefilter,
    write_association_sparse_prefilter_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark the optional D1 modality-aware sparse prefilter."
    )
    parser.add_argument("--target-count", type=int, default=120)
    parser.add_argument("--repeat-count", type=int, default=7)
    parser.add_argument("--warmup-count", type=int, default=1)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    report = benchmark_association_sparse_prefilter(
        target_count=args.target_count,
        repeat_count=args.repeat_count,
        warmup_count=args.warmup_count,
    )
    write_association_sparse_prefilter_report(
        report,
        json_output=args.json_output,
        markdown_output=args.report_output,
    )
    print(
        "recommend_main_formal_ab="
        f"{report['acceptance']['recommend_main_formal_ab']} "
        "combined_non_radar_improvement="
        f"{report['combined_non_radar']['p50_wall_time_improvement_fraction']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
