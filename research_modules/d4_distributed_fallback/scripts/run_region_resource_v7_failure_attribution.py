#!/usr/bin/env python3
"""Run the frozen D4 v7 failure diagnostic and freeze the v8 request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from d4_distributed_fallback.region_resource_v7_failure_attribution import (
    diagnose_v7_and_freeze_v8_development_request,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reload the exact frozen D4 v7 external-evaluation artifacts, "
            "attribute failures from exported online-observable fields, and "
            "write a request-only v8 development-source contract. The command "
            "does not train, tune, calibrate, register, or connect runtime."
        )
    )
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--v7-candidate-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--replace-output", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = diagnose_v7_and_freeze_v8_development_request(
        args.evaluation_root,
        args.v7_candidate_root,
        args.output_root,
        replace_output=args.replace_output,
    )
    attribution = result["failure_attribution"]
    registry = result["v8_seed_registry"]
    print(
        json.dumps(
            {
                "output_root": result["output_root"],
                "v7_disposition": attribution["v7_history"][
                    "evaluation_disposition"
                ],
                "behavior_failure_frames": attribution[
                    "attribution_denominators"
                ]["behavior_failure_frame_count"],
                "pipeline_attribution_available": attribution[
                    "attribution_denominators"
                ]["pipeline_stage_attribution_available_count"],
                "feature_causal_attribution_available": attribution[
                    "attribution_denominators"
                ]["feature_level_causal_attribution_available_count"],
                "v8_requested_seed_count": registry["requested_seed_count"],
                "v8_data_generation_count": 0,
                "permissions": attribution["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
