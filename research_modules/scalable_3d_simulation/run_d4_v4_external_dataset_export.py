"""CLI for the main-owned D4 v4 external runtime-frame export."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .d4_v4_external_dataset import (
    D4V4ExternalDatasetExportConfig,
    export_d4_v4_external_runtime_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dataset-dir",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--split-seed", type=int, default=9)
    parser.add_argument(
        "--train-positive-frame-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--validation-positive-frame-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--test-positive-frame-count",
        type=int,
        default=0,
        help=(
            "evaluation labels only; defaults to zero to preserve the "
            "training-dataset export contract"
        ),
    )
    parser.add_argument(
        "--source-kind",
        choices=(
            "main_runtime_frames",
            "external_region_learning_dataset",
        ),
        default="main_runtime_frames",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = export_d4_v4_external_runtime_dataset(
        args.source_dataset_dir,
        args.output_dir,
        repository_root=args.repository_root,
        config=D4V4ExternalDatasetExportConfig(
            split_seed=args.split_seed,
            train_positive_frame_count=args.train_positive_frame_count,
            validation_positive_frame_count=(
                args.validation_positive_frame_count
            ),
            test_positive_frame_count=args.test_positive_frame_count,
            source_kind=args.source_kind,
        ),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
