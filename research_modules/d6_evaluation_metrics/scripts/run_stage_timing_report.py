#!/usr/bin/env python3
"""Generate an offline D6 stage timing report from persisted AirSim JSONL."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from d6_evaluation_metrics import (  # noqa: E402
    StageTimingInputs,
    StageTimingReportGenerator,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--main-stage-timings", type=Path)
    parser.add_argument("--control-tick-stage-timings", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    outputs = StageTimingReportGenerator().write_report_bundle(
        args.output_dir,
        inputs=StageTimingInputs(
            main_bus=args.main_stage_timings,
            control_tick=args.control_tick_stage_timings,
        ),
    )
    for name, path in outputs.items():
        print(f"{name}={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
