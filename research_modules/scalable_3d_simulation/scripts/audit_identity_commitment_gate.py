#!/usr/bin/env python3
"""Audit clean paired episodes for D2 commitment withdrawal enforcement."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.identity_commitment_gate import (
    compare_identity_commitment_gate,
    write_identity_commitment_gate_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-episode", type=Path, required=True)
    parser.add_argument("--candidate-episode", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    report = compare_identity_commitment_gate(
        args.control_episode,
        args.candidate_episode,
    )
    outputs = write_identity_commitment_gate_bundle(args.output_dir, report)
    print(f"passed={report['passed']}")
    print(f"status={report['status']}")
    print(
        "algorithm_promotion_allowed="
        f"{report['algorithm_promotion_allowed']}"
    )
    for name, path in outputs.items():
        print(f"{name}={path.resolve()}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
