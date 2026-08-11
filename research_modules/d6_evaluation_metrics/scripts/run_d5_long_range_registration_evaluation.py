#!/usr/bin/env python3
"""Generate the offline D5 long-range visual-registration report bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d5_long_range_registration import (  # noqa: E402
    D5LongRangeRegistrationThresholds,
    evaluate_d5_long_range_registration,
    load_d5_long_range_registration_episodes,
    write_d5_long_range_registration_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episode-dir",
        action="append",
        type=Path,
        required=True,
        help="repeatable AirSim episode directory or root containing coverage_safe",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--association-min-accuracy", type=float, default=0.95)
    parser.add_argument("--crossing-min-evaluable-count", type=int, default=10)
    parser.add_argument("--crossing-min-availability-ratio", type=float, default=0.30)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    thresholds = D5LongRangeRegistrationThresholds(
        association_min_accuracy=args.association_min_accuracy,
        crossing_min_evaluable_count=args.crossing_min_evaluable_count,
        crossing_min_availability_ratio=args.crossing_min_availability_ratio,
    )
    try:
        episodes = load_d5_long_range_registration_episodes(args.episode_dir)
        result = evaluate_d5_long_range_registration(
            episodes,
            thresholds=thresholds,
        )
        paths = write_d5_long_range_registration_report(args.output_dir, result)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "failed", "reason": type(exc).__name__},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        print(str(exc), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": result["status"],
                "episode_count": result["episode_count"],
                "aggregate_json": str(paths["aggregate_json"]),
                "per_episode_csv": str(paths["per_episode_csv"]),
                "markdown": str(paths["markdown"]),
                "plot": str(paths["plot"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
