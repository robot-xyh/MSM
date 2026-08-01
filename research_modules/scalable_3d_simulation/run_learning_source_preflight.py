#!/usr/bin/env python3
"""Run the main-owned D3/D4/D5 learning-source preflight."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.learning_source_preflight import (
    evaluate_learning_source_preflight,
    write_learning_source_preflight_report,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return exit code 2 when producer execution is not ready",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = evaluate_learning_source_preflight(repository_root=ROOT)
    print(f"status={report['status']}")
    print(f"module_plans_ready={report['all_module_plans_ready']}")
    print(
        "producer_adapters_complete="
        f"{report['all_producer_adapters_complete']}"
    )
    print(f"execution_plan_ready={report['execution_plan_ready']}")
    print(f"execution_authorized={report['execution_authorized']}")
    if args.output_dir is not None:
        paths = write_learning_source_preflight_report(report, args.output_dir)
        for name, path in paths.items():
            print(f"{name}={path}")
    if args.require_ready and not report["execution_plan_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
