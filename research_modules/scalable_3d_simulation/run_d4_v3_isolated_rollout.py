#!/usr/bin/env python3
"""Run development-only D4 readiness-v3 isolated control/treatment pairs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    REGION_RESOURCE_V3_DEVELOPMENT_SEEDS,
)
from research_modules.scalable_3d_simulation.d4_v3_isolated_rollout import (
    D4V3IsolatedRolloutOptions,
    execute_d4_v3_isolated_rollouts,
    write_d4_v3_isolated_rollout_execution,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-root",
        type=Path,
        required=True,
        help="audited D4 readiness-v3 candidate root",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", default="nominal")
    parser.add_argument("--scale", type=int, default=20)
    parser.add_argument("--target-count", type=int, default=20)
    parser.add_argument("--resource-count", type=int, default=20)
    parser.add_argument("--recon-count", type=int, default=2)
    parser.add_argument("--region-count", type=int, default=8)
    parser.add_argument("--duration", type=float, default=3.2)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[REGION_RESOURCE_V3_DEVELOPMENT_SEEDS[0]],
        help="subset of fixed D4 development seeds 2003-2012",
    )
    parser.add_argument("--intervention-frame-index", type=int, default=0)
    parser.add_argument(
        "--created-at-utc",
        default="2026-07-29T00:00:00Z",
        help="explicit evidence timestamp for reproducible manifests",
    )
    parser.add_argument(
        "--no-episode-outputs",
        action="store_true",
        help="write paired evidence without full control/treatment artifacts",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    execution = execute_d4_v3_isolated_rollouts(
        D4V3IsolatedRolloutOptions(
            scenario=args.scenario,
            scale=args.scale,
            target_count=args.target_count,
            resource_count=args.resource_count,
            recon_count=args.recon_count,
            region_count=args.region_count,
            duration_s=args.duration,
            seeds=tuple(args.seeds),
            intervention_frame_index=args.intervention_frame_index,
            created_at_utc=args.created_at_utc,
        ),
        candidate_root=args.candidate_root,
    )
    paths = write_d4_v3_isolated_rollout_execution(
        args.output,
        execution,
        persist_episode_outputs=not args.no_episode_outputs,
    )
    print(f"manifest={paths['manifest']}")
    print(f"paired_evidence={paths['paired_evidence']}")
    print(f"report={paths['report_cn']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
