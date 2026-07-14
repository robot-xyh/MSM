#!/usr/bin/env python3
"""Generate the D6 cooperative-closure-v2 offline report bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.cooperative_closure import (  # noqa: E402
    CooperativeClosureInputs,
    CooperativeClosureReportGenerator,
)


def _optional_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an offline P1 cooperative-closure-v2 report"
    )
    parser.add_argument("--rows", required=True, help="main JSON/JSONL/CSV line records")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--d3-candidate")
    parser.add_argument("--d4-communication")
    parser.add_argument("--d5-visibility")
    parser.add_argument("--d7-guidance")
    args = parser.parse_args()

    outputs = CooperativeClosureReportGenerator().write_report_bundle(
        args.output_dir,
        inputs=CooperativeClosureInputs(
            rows=Path(args.rows),
            d3_candidate=_optional_path(args.d3_candidate),
            d4_communication=_optional_path(args.d4_communication),
            d5_visibility=_optional_path(args.d5_visibility),
            d7_guidance=_optional_path(args.d7_guidance),
        ),
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
