#!/usr/bin/env python3
"""Run the main-owned D4 runtime-distribution compatibility preflight."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.d4_runtime_compatibility import (
    D4RuntimeCompatibilityOptions,
    D4RuntimeCompatibilityThresholds,
    run_d4_runtime_compatibility_preflight,
)


DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--d4-model-bundle",
        type=Path,
        required=True,
        help="raw D4 bundle directory or audited candidate root",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[2_000])
    parser.add_argument("--duration", type=float, default=2.2)
    parser.add_argument("--target-count", type=int, default=5)
    parser.add_argument("--resource-count", type=int, default=5)
    parser.add_argument("--recon-count", type=int, default=2)
    parser.add_argument("--region-count", type=int, default=2)
    parser.add_argument("--minimum-frame-count", type=int, default=2)
    parser.add_argument(
        "--minimum-in-distribution-fraction",
        type=float,
        default=0.80,
    )
    parser.add_argument(
        "--minimum-model-evaluated-frame-count",
        type=int,
        default=1,
    )
    parser.add_argument("--ood-margin", type=float, default=0.05)
    parser.add_argument(
        "--allow-reserved-evaluation-seeds",
        action="store_true",
        help="explicitly allow development probing of formal seed IDs",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = run_d4_runtime_compatibility_preflight(
        D4RuntimeCompatibilityOptions(
            config_path=args.config,
            bundle_dir=args.d4_model_bundle,
            output_dir=args.output,
            seeds=tuple(args.seeds),
            duration_s=args.duration,
            target_count=args.target_count,
            resource_count=args.resource_count,
            recon_count=args.recon_count,
            region_count=args.region_count,
            thresholds=D4RuntimeCompatibilityThresholds(
                minimum_frame_count=args.minimum_frame_count,
                minimum_in_distribution_fraction=(
                    args.minimum_in_distribution_fraction
                ),
                minimum_model_evaluated_frame_count=(
                    args.minimum_model_evaluated_frame_count
                ),
                ood_margin=args.ood_margin,
            ),
            allow_reserved_evaluation_seeds=(
                args.allow_reserved_evaluation_seeds
            ),
        )
    )
    print(f"preflight={paths['preflight_json']}")
    print(f"report={paths['report']}")
    import json

    payload = json.loads(paths["preflight_json"].read_text(encoding="utf-8"))
    return (
        0
        if payload["compatibility"]["paired_development_rollout_allowed"]
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
