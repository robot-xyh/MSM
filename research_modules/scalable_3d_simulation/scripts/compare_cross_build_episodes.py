#!/usr/bin/env python3
"""Audit semantic equivalence of same-input episodes from two clean builds."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.cross_build_equivalence import (
    compare_cross_build_episodes,
    write_cross_build_equivalence_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-episode", type=Path, required=True)
    parser.add_argument("--candidate-episode", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mismatch-limit", type=int, default=20)
    args = parser.parse_args()
    report = compare_cross_build_episodes(
        args.reference_episode,
        args.candidate_episode,
        mismatch_limit=args.mismatch_limit,
    )
    outputs = write_cross_build_equivalence_bundle(args.output_dir, report)
    print(f"passed={report['passed']}")
    print(
        "normalized_online_payloads_equal="
        f"{report['online_bus']['normalized_online_payloads_equal']}"
    )
    for name, path in outputs.items():
        print(f"{name}={path.resolve()}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
