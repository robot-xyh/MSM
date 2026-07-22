#!/usr/bin/env python3
"""Compare same-source short and long scalable 3D episodes."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.long_duration_performance import (
    compare_long_duration_episodes,
    write_long_duration_comparison_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--short-episode", type=Path, required=True)
    parser.add_argument("--long-episode", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--superlinear-threshold", type=float, default=1.25)
    args = parser.parse_args()
    report = compare_long_duration_episodes(
        args.short_episode,
        args.long_episode,
        superlinear_threshold=args.superlinear_threshold,
    )
    outputs = write_long_duration_comparison_bundle(args.output_dir, report)
    comparison = report["comparison"]
    print(f"passed_safety_contracts={comparison['passed_safety_contracts']}")
    print(
        "superlinear_stage_names="
        + ",".join(comparison["superlinear_stage_names"])
    )
    for name, path in outputs.items():
        print(f"{name}={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
