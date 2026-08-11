#!/usr/bin/env python3
"""Re-audit completed long-range MOT logs without launching AirSim."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
for candidate_path in (
    ROOT,
    *(
        ROOT / relative
        for relative in (
            "research_modules",
            "research_modules/d1_sensor_fusion/src",
            "research_modules/d2_data_association",
            "research_modules/d3_assignment_planner/src",
            "research_modules/d4_distributed_fallback",
            "research_modules/d5_terminal_association/src",
            "research_modules/d6_evaluation_metrics",
            "research_modules/d7_proportional_guidance",
        )
    ),
):
    candidate = str(candidate_path)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from airsim_runtime.long_range_mot_reaudit import reaudit_long_range_campaign  # noqa: E402


DEFAULT_SOURCE = Path(
    "research_modules/airsim_runtime/outputs/"
    "d5_cv_long_range_20target_50mps_2d_20260810"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or args.source_dir.with_name(
        f"{args.source_dir.name}_mot_reaudit"
    )
    result = reaudit_long_range_campaign(
        source_dir=args.source_dir,
        output_dir=output_dir,
    )
    for mode, profile in result["profiles"].items():
        comparison = profile["comparison"]
        print(
            "mode={mode} baseline_visible_idsw={baseline} corrected_visible_idsw={corrected} "
            "reacquisition={reacquisition} crossing_evaluable={crossing_count} "
            "crossing_idsw={crossing_idsw} gate={gate}".format(
                mode=mode,
                baseline=comparison["baseline_v2_id_switch_count"],
                corrected=comparison["motion_compensated_v2_id_switch_count"],
                reacquisition=comparison["motion_compensated_v2_reacquisition_count"],
                crossing_count=comparison[
                    "motion_compensated_v2_crossing_evaluable_window_count"
                ],
                crossing_idsw=comparison["motion_compensated_v2_crossing_id_switch_count"],
                gate=comparison["motion_compensated_v2_gate_passed"],
            )
        )
    print(f"output_dir={output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
