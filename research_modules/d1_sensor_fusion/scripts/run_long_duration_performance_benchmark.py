from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.long_duration_performance import (
    audit_fused_track_publications,
    compare_long_duration_variants,
    write_long_duration_performance_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare D1 long-duration fixed-lag replay paths."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--profile-directory", type=Path)
    parser.add_argument("--skip-publication-audit", action="store_true")
    args = parser.parse_args()

    report = compare_long_duration_variants(
        args.input,
        profile_directory=args.profile_directory,
    )
    audit = (
        None
        if args.skip_publication_audit
        else audit_fused_track_publications(args.input)
    )
    write_long_duration_performance_report(
        report,
        publication_audit=audit,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(f"passed={report['comparison']['passed']}")
    print(
        "fusion_wall_time_speedup="
        f"{report['comparison']['fusion_wall_time_speedup']:.3f}"
    )
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
