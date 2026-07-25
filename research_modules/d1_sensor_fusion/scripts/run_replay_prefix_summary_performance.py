from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.replay_prefix_summary_performance import (
    DEFAULT_REPLAY_PREFIX_SUMMARY_FIXTURE,
    benchmark_replay_prefix_summary,
    write_replay_prefix_summary_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen D1 fixed-lag replay prefix-summary microbenchmark."
        )
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_REPLAY_PREFIX_SUMMARY_FIXTURE,
    )
    parser.add_argument("--paired-runs", type=int, default=7)
    parser.add_argument("--warmup-pairs", type=int, default=1)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(
            "research_modules/d1_sensor_fusion/reports/"
            "d1_replay_prefix_summary_performance_20260725.json"
        ),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path(
            "research_modules/d1_sensor_fusion/reports/"
            "D1_REPLAY_PREFIX_SUMMARY_PERFORMANCE_20260725_CN.md"
        ),
    )
    args = parser.parse_args()
    report = benchmark_replay_prefix_summary(
        fixture_path=args.fixture,
        paired_run_count=args.paired_runs,
        warmup_pair_count=args.warmup_pairs,
    )
    write_replay_prefix_summary_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(args.json_output)
    print(args.markdown_output)
    print(
        "module_microbenchmark_passed="
        f"{report['module_microbenchmark_passed']}"
    )
    print(f"recommendation={report['recommendation']}")


if __name__ == "__main__":
    main()
