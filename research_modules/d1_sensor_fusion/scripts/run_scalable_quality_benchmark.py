from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d1_sensor_fusion.scalable_quality_benchmark import (  # noqa: E402
    D1QualityBenchmarkConfig,
    run_d1_quality_benchmark_batch,
    write_d1_quality_benchmark_outputs,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the truth-isolated D1 multi-seed quality benchmark.",
    )
    parser.add_argument(
        "--target-counts",
        default="200",
        help="Comma-separated target counts, for example 5,20,50,100,200.",
    )
    parser.add_argument("--seed-start", type=int, default=1000)
    parser.add_argument("--seed-count", type=int, default=20)
    parser.add_argument("--duration-s", type=float, default=8.0)
    parser.add_argument("--scan-period-s", type=float, default=0.5)
    parser.add_argument("--warmup-s", type=float, default=1.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=MODULE_ROOT / "outputs" / "scalable_quality_benchmark",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    target_counts = tuple(
        int(value.strip())
        for value in str(args.target_counts).split(",")
        if value.strip()
    )
    if args.seed_count < 1:
        raise ValueError("--seed-count must be positive")
    base = replace(
        D1QualityBenchmarkConfig(),
        duration_s=args.duration_s,
        scan_period_s=args.scan_period_s,
        warmup_s=args.warmup_s,
    )
    result = run_d1_quality_benchmark_batch(
        target_counts=target_counts,
        seeds=range(args.seed_start, args.seed_start + args.seed_count),
        base_config=base,
    )
    json_path, report_path = write_d1_quality_benchmark_outputs(
        result,
        args.output_dir,
    )
    print(f"runs={len(result.seed_results)}")
    print(f"json={json_path}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
