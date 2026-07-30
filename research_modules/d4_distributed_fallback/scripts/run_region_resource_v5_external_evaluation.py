#!/usr/bin/env python3
"""Run the frozen D4 v5 source-independent read-only evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from d4_distributed_fallback.region_resource_v5_external_evaluation import (
    evaluate_region_resource_v5_external_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the frozen v4 actor and v5 confidence calibrator on "
            "the frozen M16N20 source-independent dataset. This command "
            "does not fit, register, admit, or run a candidate."
        )
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument(
        "--labeled-dataset-root",
        type=Path,
        required=True,
    )
    parser.add_argument("--v4-candidate-root", type=Path, required=True)
    parser.add_argument("--v5-candidate-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--replace-output", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = evaluate_region_resource_v5_external_dataset(
        args.source_root,
        args.labeled_dataset_root,
        args.v4_candidate_root,
        args.v5_candidate_root,
        args.output_root,
        replace_output=args.replace_output,
    )
    summary = result["summary"]
    print(
        json.dumps(
            {
                "output_root": result["output_root"],
                "sample_count": summary["metrics"]["sample_count"],
                "rule_safe_positive_action_count": summary["metrics"][
                    "rule_safe_positive_action_count"
                ],
                "actor_derived_positive_count": summary["metrics"][
                    "actor_derived_positive_count"
                ],
                "confidence_threshold_pass_count": summary["metrics"][
                    "confidence_threshold_pass_count"
                ],
                "negative_false_accept_count": summary["metrics"][
                    "negative_false_accept_count"
                ],
                "rule_fallback_count": summary["metrics"][
                    "rule_fallback_count"
                ],
                "positive_recall_status": summary["metrics"][
                    "positive_recall_status"
                ],
                "formal_holdout_payload_read_count": summary["data_usage"][
                    "formal_holdout_payload_read_count"
                ],
                "registered": summary["candidate_status"]["registered"],
                "admission_closed": summary["candidate_status"][
                    "admission_closed"
                ],
                "rule_fallback_required": summary["candidate_status"][
                    "rule_fallback_required"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
