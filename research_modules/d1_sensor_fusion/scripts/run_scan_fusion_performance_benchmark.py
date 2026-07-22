from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.scan_fusion_performance import (
    compare_scan_fusion_variants,
    write_scan_fusion_performance_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare uncached and incremental D1 scan fusion on frozen input."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--profile-directory", type=Path)
    args = parser.parse_args()

    report = compare_scan_fusion_variants(
        args.input,
        profile_directory=args.profile_directory,
    )
    write_scan_fusion_performance_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(f"passed={report['comparison']['passed']}")
    print(f"speedup={report['comparison']['wall_time_speedup']:.3f}")
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
