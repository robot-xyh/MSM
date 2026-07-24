from __future__ import annotations

import argparse
from pathlib import Path

from d1_sensor_fusion.publication_metadata_performance import (
    analyze_frozen_publication_metadata,
    write_publication_metadata_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare D1 reference and immutable shared publication metadata."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--profile-directory", type=Path)
    parser.add_argument("--repeat-count", type=int, default=1)
    args = parser.parse_args()

    report = analyze_frozen_publication_metadata(
        args.input,
        repeat_count=args.repeat_count,
        profile_directory=args.profile_directory,
    )
    write_publication_metadata_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    comparison = report["comparison"]
    print(f"passed={comparison['passed']}")
    print(
        "p50_speedup="
        f"{float(comparison['timing']['p50_speedup'] or 0.0):.3f}"
    )
    print(f"json={args.json_output}")
    print(f"markdown={args.markdown_output}")


if __name__ == "__main__":
    main()
