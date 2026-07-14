#!/usr/bin/env python3
"""Generate the D6 report for persisted real AirSim native MOT evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from d6_evaluation_metrics import (  # noqa: E402
    NativeMotAirSimInputs,
    NativeMotAirSimReportGenerator,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--range-precheck", type=Path, required=True)
    parser.add_argument("--confirmation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    outputs = NativeMotAirSimReportGenerator().write_report_bundle(
        args.output_dir,
        inputs=NativeMotAirSimInputs(
            preflight_rows=args.preflight,
            range_precheck_rows=args.range_precheck,
            confirmation_rows=args.confirmation,
        ),
    )
    for name, path in outputs.items():
        print(f"{name}={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
