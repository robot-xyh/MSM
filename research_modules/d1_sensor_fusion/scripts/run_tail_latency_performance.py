from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.tail_latency_performance import (
    analyze_frozen_tail_latency,
    write_tail_latency_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attribute D1 frozen-replay tail latency and audit frame reuse."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--profile-directory", type=Path)
    parser.add_argument("--scan-input-repeat-count", type=int, default=5)
    parser.add_argument("--scan-input-benchmark-scan-count", type=int, default=256)
    args = parser.parse_args()

    report = analyze_frozen_tail_latency(
        args.input,
        scan_input_repeat_count=args.scan_input_repeat_count,
        scan_input_benchmark_scan_count=args.scan_input_benchmark_scan_count,
        profile_directory=args.profile_directory,
    )
    write_tail_latency_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(f"passed={report['scan_input_comparison']['passed']}")
    print(
        "scan_input_p50_speedup="
        f"{report['scan_input_comparison']['interleaved_distribution']['p50_speedup']:.3f}"
    )
    print(
        "claim_serialization_passed="
        f"{report['claim_serialization_comparison']['passed']}"
    )
    print(
        "claim_serialization_p50_speedup="
        f"{report['claim_serialization_comparison']['interleaved_distribution']['p50_speedup']:.3f}"
    )
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
