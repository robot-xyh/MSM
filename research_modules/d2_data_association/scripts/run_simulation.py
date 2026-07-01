#!/usr/bin/env python3
"""Run offline D2 data-association simulations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d2_data_association.simulation import (  # noqa: E402
    ASSOCIATOR_NAMES,
    SCENARIO_NAMES,
    format_markdown_table,
    run_benchmark,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("all", *SCENARIO_NAMES),
        default="all",
        help="Scenario to run.",
    )
    parser.add_argument(
        "--associator",
        choices=("all", *ASSOCIATOR_NAMES),
        default="all",
        help="Associator to run.",
    )
    parser.add_argument("--steps", type=int, default=36, help="Frames per scenario.")
    parser.add_argument("--seed", type=int, default=7, help="Base RNG seed.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional JSON path.")
    parser.add_argument(
        "--markdown-out", type=Path, default=None, help="Optional Markdown table path."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenarios = None if args.scenario == "all" else [args.scenario]
    associators = None if args.associator == "all" else [args.associator]
    results = run_benchmark(
        scenarios=scenarios,
        associators=associators,
        steps=args.steps,
        seed=args.seed,
    )
    table = format_markdown_table(results)
    print(table)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps([result.to_dict() for result in results], indent=2),
            encoding="utf-8",
        )
    if args.markdown_out is not None:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(table + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
