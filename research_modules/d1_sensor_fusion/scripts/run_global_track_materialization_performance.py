from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.global_track_materialization_performance import (
    GLOBAL_TRACK_MATERIALIZATION_MINIMUM_PAIRED_RUN_COUNT,
    benchmark_global_track_materialization_candidate,
    write_global_track_materialization_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the D1 default-off GlobalTrack materialization candidate gate."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument(
        "--paired-run-count",
        type=int,
        default=GLOBAL_TRACK_MATERIALIZATION_MINIMUM_PAIRED_RUN_COUNT,
    )
    parser.add_argument("--skip-profiles", action="store_true")
    args = parser.parse_args()

    report = benchmark_global_track_materialization_candidate(
        args.input,
        paired_run_count=args.paired_run_count,
        include_profiles=not args.skip_profiles,
    )
    write_global_track_materialization_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    aggregate = report["aggregate"]
    print(f"passed={report['passed']}")
    print(f"decision={report['decision']}")
    print(
        "candidate_faster_fraction="
        f"{aggregate['candidate_faster_fraction']:.6f}"
    )
    print(
        "median_module_wall_improvement_percent="
        f"{aggregate['median_module_wall_improvement_percent']:.6f}"
    )
    print(
        "bootstrap_upper_s="
        f"{aggregate['paired_bootstrap_module_wall_difference_s_95_ci'][1]:.9f}"
    )
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
