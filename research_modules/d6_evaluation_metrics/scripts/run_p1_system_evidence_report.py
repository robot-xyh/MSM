#!/usr/bin/env python3
"""Generate the passive D6 P1 system evidence report bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from d6_evaluation_metrics import (  # noqa: E402
    P1SystemEvidenceInputs,
    P1SystemEvidenceReportGenerator,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--d1-dense-crossing-summary", type=Path)
    parser.add_argument("--d2-difficulty-summary", type=Path)
    parser.add_argument(
        "--d3-churn-summary",
        "--d3-plan-history",
        dest="d3_churn_summary",
        type=Path,
        help="D3 summary or canonical d3_plan_history.json",
    )
    parser.add_argument("--d4-communication-summary", type=Path)
    parser.add_argument("--d5-per-primary-summary", type=Path)
    parser.add_argument("--d5-native-mot-summary", type=Path)
    parser.add_argument("--d7-per-primary-summary", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        args.output_dir,
        inputs=P1SystemEvidenceInputs(
            d1_dense_crossing=args.d1_dense_crossing_summary,
            d2_difficulty_profiles=args.d2_difficulty_summary,
            d3_assignment_churn=args.d3_churn_summary,
            d4_episode_communication=args.d4_communication_summary,
            d5_per_primary=args.d5_per_primary_summary,
            d5_native_mot=args.d5_native_mot_summary,
            d7_per_primary=args.d7_per_primary_summary,
        ),
    )
    for name, path in outputs.items():
        print(f"{name}={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
