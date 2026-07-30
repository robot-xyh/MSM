#!/usr/bin/env python3
"""Generate the D4 v6 transfer source-independent development dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.d4_v6_transfer_independent_development import (
    DEFAULT_CONFIG,
    DEFAULT_SCENARIO_FAMILIES,
    DEFAULT_SEED_REGISTRY,
    DEFAULT_SEEDS,
    D4V6TransferIndependentDevelopmentOptions,
    run_d4_v6_transfer_independent_development,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--seed-registry",
        type=Path,
        default=DEFAULT_SEED_REGISTRY,
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=list(DEFAULT_SEEDS),
    )
    parser.add_argument(
        "--scenario-families",
        nargs="+",
        default=list(DEFAULT_SCENARIO_FAMILIES),
    )
    parser.add_argument("--target-count", type=int, default=16)
    parser.add_argument("--resource-count", type=int, default=24)
    parser.add_argument("--recon-count", type=int, default=2)
    parser.add_argument("--region-count", type=int, default=8)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="smoke only; independent evidence requires a clean source",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = run_d4_v6_transfer_independent_development(
        D4V6TransferIndependentDevelopmentOptions(
            output_dir=args.output,
            config_path=args.config,
            seed_registry_path=args.seed_registry,
            seeds=tuple(args.seeds),
            scenario_families=tuple(args.scenario_families),
            target_count=args.target_count,
            resource_count=args.resource_count,
            recon_count=args.recon_count,
            region_count=args.region_count,
            duration_s=args.duration,
            allow_dirty=args.allow_dirty,
        )
    )
    print(f"summary={paths['summary']}")
    print(f"d4_dataset={paths['d4_dataset']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
