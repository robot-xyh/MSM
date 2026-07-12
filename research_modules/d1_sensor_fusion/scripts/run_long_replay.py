#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = MODULE_ROOT / "src"
DEFAULT_OUTPUT = MODULE_ROOT / "reports" / "long_replay_summary.json"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d1_sensor_fusion import (  # noqa: E402
    LongReplayConfig,
    build_long_replay_scenario,
    summarize_long_replay,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the governed D1 long crossing/occlusion/OOSM replay."
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--duration", type=float, default=60.0, metavar="SECONDS")
    parser.add_argument("--target-count", type=int, default=3, metavar="N")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the LongReplaySummary JSON output.",
    )
    args = parser.parse_args(argv)
    if args.duration <= 0.0:
        parser.error("--duration must be positive")
    if args.target_count < 1:
        parser.error("--target-count must be at least 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    scenario = build_long_replay_scenario(
        LongReplayConfig(
            seed=args.seed,
            duration_s=args.duration,
            target_count=args.target_count,
        )
    )
    summary = summarize_long_replay(scenario)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"D1 long replay summary: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
