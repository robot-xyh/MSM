#!/usr/bin/env python3
"""Compare D5 operation growth on frozen short and long online logs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
for path in (MODULE_ROOT / "src", REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from d5_terminal_association.scalable_3d_performance import (
    run_scalable_3d_d5_duration_comparison,
    write_scalable_3d_d5_duration_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--short-online-log", type=Path, required=True)
    parser.add_argument("--long-online-log", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--repeat-count", type=int, default=3)
    args = parser.parse_args()

    report = run_scalable_3d_d5_duration_comparison(
        args.short_online_log,
        args.long_online_log,
        repeat_count=args.repeat_count,
    )
    write_scalable_3d_d5_duration_comparison(
        report,
        json_path=args.output_json,
        markdown_path=args.output_markdown,
    )
    comparison = report["comparison"]
    print(
        "short_business_hash_equivalent="
        f"{comparison['short_business_hash_equivalent']}"
    )
    print(
        "long_business_hash_equivalent="
        f"{comparison['long_business_hash_equivalent']}"
    )
    print(
        "mean_call_cost_growth="
        f"{comparison['mean_call_ms']['growth']:.6f}"
    )
    print(f"output_json={args.output_json.resolve()}")
    print(f"output_markdown={args.output_markdown.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
