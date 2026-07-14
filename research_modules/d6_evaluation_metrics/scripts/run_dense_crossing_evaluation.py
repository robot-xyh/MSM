#!/usr/bin/env python3
"""Generate the offline D1/D2 dense-crossing calibration report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.dense_crossing_evaluation import (  # noqa: E402
    DenseCrossingEvaluationInputs,
    DenseCrossingEvaluationReportGenerator,
)


def _optional_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the D1/D2 dense-crossing offline evaluation bundle"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--d1-manifest")
    parser.add_argument("--d1-offline-truth-summary")
    parser.add_argument("--d2-screening")
    parser.add_argument("--d2-confirmation")
    parser.add_argument("--p95-loop-latency-budget-s", type=float)
    args = parser.parse_args()

    outputs = DenseCrossingEvaluationReportGenerator().write_report_bundle(
        args.output_dir,
        inputs=DenseCrossingEvaluationInputs(
            d1_governed_manifest=_optional_path(args.d1_manifest),
            d1_offline_truth_summary=_optional_path(
                args.d1_offline_truth_summary
            ),
            d2_screening=_optional_path(args.d2_screening),
            d2_confirmation=_optional_path(args.d2_confirmation),
            p95_loop_latency_budget_s=args.p95_loop_latency_budget_s,
        ),
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
