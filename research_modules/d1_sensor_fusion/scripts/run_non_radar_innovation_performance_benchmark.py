#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from d1_sensor_fusion.non_radar_performance import (
    benchmark_batched_non_radar_innovation,
    render_non_radar_innovation_benchmark_cn,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark scalar and batched D1 non-radar innovation solves."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--repeat-count", type=int, default=5)
    parser.add_argument("--warmup-count", type=int, default=1)
    parser.add_argument("--maximum-scan-count", type=int)
    parser.add_argument("--warmup-scan-count", type=int, default=128)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    report = benchmark_batched_non_radar_innovation(
        args.source,
        repeat_count=args.repeat_count,
        warmup_count=args.warmup_count,
        maximum_scan_count=args.maximum_scan_count,
        warmup_scan_count=args.warmup_scan_count,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.report_output.write_text(
        render_non_radar_innovation_benchmark_cn(report),
        encoding="utf-8",
    )
    print(
        "passed="
        f"{report['comparison']['passed']} "
        "p50_speedup="
        f"{report['comparison']['p50_speedup']:.3f}"
    )
    return 0 if report["comparison"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
