#!/usr/bin/env python3
"""Generate the offline D6 P1 unified acceptance report bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from d6_evaluation_metrics import (  # noqa: E402
    P1AcceptanceInputs,
    P1AcceptanceReportGenerator,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--main-summary", type=Path)
    parser.add_argument("--d1-summary", type=Path)
    parser.add_argument("--d2-summary", type=Path)
    parser.add_argument("--d3-summary", type=Path)
    parser.add_argument("--d4-summary", type=Path)
    parser.add_argument("--d5-summary", type=Path)
    parser.add_argument("--d7-dropout-summary", type=Path)
    parser.add_argument("--d7-png-ttc-summary", type=Path)
    parser.add_argument("--d7-trend-summary", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    outputs = P1AcceptanceReportGenerator().write_report_bundle(
        args.output_dir,
        inputs=P1AcceptanceInputs(
            main_terminal_closure=args.main_summary,
            d1_long_replay=args.d1_summary,
            d2_long_replay=args.d2_summary,
            d3_assignment_calibration=args.d3_summary,
            d4_failover_matrix=args.d4_summary,
            d5_visual_calibration=args.d5_summary,
            d7_locked_dropout=args.d7_dropout_summary,
            d7_png_ttc=args.d7_png_ttc_summary,
            d7_trend_coast=args.d7_trend_summary,
        ),
    )
    for name, path in outputs.items():
        print(f"{name}={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
