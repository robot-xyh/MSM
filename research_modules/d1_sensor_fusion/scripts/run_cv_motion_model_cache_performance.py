from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.cv_motion_model_cache_performance import (
    compare_cv_motion_model_cache_variants,
    write_cv_motion_model_cache_performance_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the explicit D1 CV motion-model cache candidate."
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--state-count", type=int, default=200)
    parser.add_argument("--step-count", type=int, default=100)
    parser.add_argument("--dt-s", type=float, default=0.05)
    parser.add_argument("--cache-capacity", type=int, default=128)
    args = parser.parse_args()

    report = compare_cv_motion_model_cache_variants(
        repetitions=args.repetitions,
        state_count=args.state_count,
        step_count=args.step_count,
        dt_s=args.dt_s,
        cache_capacity=args.cache_capacity,
    )
    write_cv_motion_model_cache_performance_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(f"passed={report['comparison']['passed']}")
    print(f"median_speedup={report['comparison']['median_speedup']:.3f}")
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
