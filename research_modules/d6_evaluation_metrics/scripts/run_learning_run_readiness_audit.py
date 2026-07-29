#!/usr/bin/env python3
"""Run the small, read-only formal learning readiness audit."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT / "research_modules" / "d6_evaluation_metrics"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from d6_evaluation_metrics.learning_run_readiness import (  # noqa: E402
    audit_learning_run_readiness,
    load_learning_run_readiness_input,
    write_learning_run_readiness_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit G1/A1/A2/A3/C1/F1 formal run readiness."
    )
    parser.add_argument("input", type=Path, help="Explicit readiness manifest")
    parser.add_argument("output_dir", type=Path, help="Small report directory")
    args = parser.parse_args()
    input_path = args.input.expanduser().resolve()
    result = audit_learning_run_readiness(
        load_learning_run_readiness_input(input_path),
        artifact_root=input_path.parent,
    )
    paths = write_learning_run_readiness_report(args.output_dir, result)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
