#!/usr/bin/env python3
"""Generate D6 reports from main-owned scalable 3D episode directories."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.scalable_3d_offline import (  # noqa: E402
    DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES,
    DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED,
    Scalable3DOfflineEvaluationInputs,
    Scalable3DOfflineReportGenerator,
    discover_scalable_3d_episode_dirs,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episode-dir",
        action="append",
        default=[],
        help="one episode directory; repeat for multiple episodes",
    )
    parser.add_argument(
        "--episode-root",
        action="append",
        default=[],
        help="recursively discover directories with the scalable 3D episode core",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES,
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    episode_dirs = discover_scalable_3d_episode_dirs(
        episode_dirs=args.episode_dir,
        episode_roots=args.episode_root,
    )
    outputs = Scalable3DOfflineReportGenerator().write_report_bundle(
        args.output_dir,
        inputs=Scalable3DOfflineEvaluationInputs(episode_dirs=episode_dirs),
        bootstrap_resamples=args.bootstrap_resamples,
        bootstrap_rng_seed=args.bootstrap_seed,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
