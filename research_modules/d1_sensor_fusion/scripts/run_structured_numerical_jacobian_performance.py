from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.structured_numerical_jacobian_performance import (
    DEFAULT_BENCHMARK_CONFIG_PATH,
    compare_structured_numerical_jacobian_variants,
    write_structured_numerical_jacobian_performance_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark D1's structured numerical Jacobian candidate."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_BENCHMARK_CONFIG_PATH,
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--warmup-count", type=int)
    parser.add_argument("--sample-count", type=int)
    parser.add_argument("--round-count", type=int)
    args = parser.parse_args()

    report = compare_structured_numerical_jacobian_variants(
        args.config,
        repetitions=args.repetitions,
        warmup_count=args.warmup_count,
        sample_count=args.sample_count,
        round_count=args.round_count,
    )
    write_structured_numerical_jacobian_performance_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    comparison = report["comparison"]
    print(f"semantic_passed={comparison['semantic_passed']}")
    print(
        "median_improvement_fraction="
        f"{comparison['median_improvement_fraction']:.6f}"
    )
    print(
        "integration_recommendation="
        f"{comparison['integration_recommendation']}"
    )
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
