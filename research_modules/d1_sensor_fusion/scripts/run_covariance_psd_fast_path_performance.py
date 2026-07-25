from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.covariance_psd_fast_path_performance import (
    compare_covariance_psd_fast_path_variants,
    write_covariance_psd_fast_path_performance_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark D1's explicit 6x6 Cholesky PSD-check candidate."
        )
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=9)
    parser.add_argument("--warmup-count", type=int, default=2)
    parser.add_argument("--matrix-count", type=int, default=2_000)
    parser.add_argument("--round-count", type=int, default=10)
    parser.add_argument("--fallback-every", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260724)
    args = parser.parse_args()

    report = compare_covariance_psd_fast_path_variants(
        repetitions=args.repetitions,
        warmup_count=args.warmup_count,
        matrix_count=args.matrix_count,
        round_count=args.round_count,
        fallback_every=args.fallback_every,
        seed=args.seed,
    )
    write_covariance_psd_fast_path_performance_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    comparison = report["comparison"]
    print(f"semantic_passed={comparison['semantic_passed']}")
    print(f"median_speedup={comparison['median_speedup']:.3f}")
    print(
        "integration_recommendation="
        f"{comparison['integration_recommendation']}"
    )
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
