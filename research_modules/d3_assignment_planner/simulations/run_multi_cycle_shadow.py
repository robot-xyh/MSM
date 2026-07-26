#!/usr/bin/env python3
"""Run the fixed reserved-seed D3 multi-cycle BC shadow evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d3_assignment_planner.multi_cycle_shadow import (  # noqa: E402
    run_reserved_seed_multi_cycle_shadow,
    write_multi_cycle_shadow_artifacts,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run isolated rule/control versus frozen BC residual/treatment "
            "across reserved seeds 1000-1019."
        )
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        required=True,
        help="Frozen D3 development/shadow-only model bundle.",
    )
    parser.add_argument(
        "--training-seed-registry",
        type=Path,
        required=True,
        help="Frozen main-owned training/reserved seed registry.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for JSON, CSV, and Chinese Markdown artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_reserved_seed_multi_cycle_shadow(
        bundle_dir=args.bundle_dir,
        training_seed_registry_path=args.training_seed_registry,
    )
    artifacts = write_multi_cycle_shadow_artifacts(args.output_dir, result)
    print(
        json.dumps(
            {
                "summary": result.summary,
                "artifacts": {
                    key: str(value) for key, value in artifacts.items()
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
