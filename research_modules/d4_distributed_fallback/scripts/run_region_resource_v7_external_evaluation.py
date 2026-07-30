#!/usr/bin/env python3
"""Run the frozen-by-hash D4 v7 read-only external evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from d4_distributed_fallback.region_resource_v7_external_evaluation import (
    evaluate_region_resource_v7_external_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the exact D4 v7 R0-node plus transfer-residual actor "
            "against the exact source-independent M16N24 export. The command "
            "does not fit, tune, calibrate, register, admit, or grant "
            "authority."
        )
    )
    parser.add_argument("--v7-candidate-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--labeled-dataset-root", type=Path, required=True)
    parser.add_argument("--external-evidence", type=Path, required=True)
    parser.add_argument("--derivation-manifest", type=Path, required=True)
    parser.add_argument("--export-summary", type=Path, required=True)
    parser.add_argument(
        "--frozen-v4-candidate-root",
        type=Path,
        required=True,
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--replace-output", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = evaluate_region_resource_v7_external_dataset(
        args.v7_candidate_root,
        args.source_root,
        args.labeled_dataset_root,
        args.external_evidence,
        args.derivation_manifest,
        args.export_summary,
        args.frozen_v4_candidate_root,
        args.output_root,
        replace_output=args.replace_output,
    )
    summary = result["summary"]
    print(
        json.dumps(
            {
                "output_root": result["output_root"],
                "metrics_by_split": summary["metrics_by_split"],
                "candidate_status": summary["candidate_status"],
                "input_mutation_count": 0,
                "candidate_mutation_count": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
