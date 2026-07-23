from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.long_duration_performance import (
    compare_consistency_counter_refresh_sources,
    write_consistency_counter_refresh_performance_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark D1 validated consistency replay-counter refresh."
    )
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--profile-directory", type=Path)
    args = parser.parse_args()

    report = compare_consistency_counter_refresh_sources(
        args.input,
        profile_directory=args.profile_directory,
    )
    write_consistency_counter_refresh_performance_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    aggregate = report["aggregate"]
    print(f"passed={aggregate['passed']}")
    print(
        "aggregate_fusion_wall_time_speedup="
        f"{aggregate['aggregate_fusion_wall_time_speedup']:.3f}"
    )
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
