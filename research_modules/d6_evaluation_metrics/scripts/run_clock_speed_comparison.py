#!/usr/bin/env python3
"""Generate the D6 M5N2 ClockSpeed comparison bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics import ClockSpeedComparisonReportGenerator


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and compare the same M5N2 baseline/candidate seed 1-10 "
            "suite at provenance ClockSpeed 1.0/0.2/0.1."
        )
    )
    parser.add_argument(
        "--suite",
        action="append",
        required=True,
        help=(
            "Suite root or p1_terminal_closure_summary.json; pass exactly three. "
            "Order is irrelevant because ClockSpeed comes from provenance."
        ),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--title",
        default="M5N2 三档 ClockSpeed 离线对比报告",
    )
    args = parser.parse_args()
    if len(args.suite) != 3:
        parser.error("--suite must be passed exactly three times")

    outputs = ClockSpeedComparisonReportGenerator().write_report_bundle(
        args.output_dir,
        suite_inputs=args.suite,
        title=args.title,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
