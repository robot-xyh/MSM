#!/usr/bin/env python3
"""Run the deterministic D3 P1 full/incremental calibration matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d3_assignment_planner import run_p1_assignment_calibration_matrix  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deterministic D3 P1 assignment calibration matrix."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path; the same JSON is always printed to stdout.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary = run_p1_assignment_calibration_matrix()
    payload = json.dumps(summary.as_dict(), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{payload}\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
