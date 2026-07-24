from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.scan_input_performance import (
    benchmark_scan_input_implementations,
    write_scan_input_performance_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark D1 scan-input reference and candidate paths."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--repeat-count", type=int, default=5)
    parser.add_argument("--benchmark-scan-count", type=int)
    args = parser.parse_args()

    report = benchmark_scan_input_implementations(
        args.input,
        repeat_count=args.repeat_count,
        benchmark_scan_count=args.benchmark_scan_count,
    )
    write_scan_input_performance_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(f"passed={report['passed']}")
    print(
        "p50_speedup="
        f"{report['interleaved_wall_time']['p50_speedup']:.3f}"
    )
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
