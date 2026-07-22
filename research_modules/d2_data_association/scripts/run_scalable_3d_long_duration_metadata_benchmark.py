#!/usr/bin/env python3
"""Run the D2 long-duration metadata scaling benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from d2_data_association.scalable_3d_long_duration import (
    run_scalable_3d_long_duration_metadata_benchmark,
    write_scalable_3d_long_duration_metadata_benchmark,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track-count", type=int, default=200)
    parser.add_argument("--cycle-count", type=int, default=48)
    parser.add_argument("--sensor-count-start", type=int, default=20)
    parser.add_argument("--sensor-count-end", type=int, default=181)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = run_scalable_3d_long_duration_metadata_benchmark(
        track_count=args.track_count,
        cycle_count=args.cycle_count,
        sensor_count_start=args.sensor_count_start,
        sensor_count_end=args.sensor_count_end,
    )
    digest = write_scalable_3d_long_duration_metadata_benchmark(
        str(args.output),
        report,
    )
    print(f"semantic_equal={report.cycle_semantic_hashes_equal}")
    print(f"baseline_seconds={report.baseline_total_seconds:.6f}")
    print(f"candidate_seconds={report.candidate_total_seconds:.6f}")
    print(f"speedup={report.speedup:.3f}")
    print(f"sha256={digest}")


if __name__ == "__main__":
    main()
