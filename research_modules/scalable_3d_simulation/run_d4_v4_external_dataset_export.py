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
    parser.add_argument("--source-dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--split-seed", type=int, default=9)
    parser.add_argument(
        "--positive-frames-per-development-split",
        type=int,
        default=1,
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
            positive_frames_per_development_split=(
                args.positive_frames_per_development_split
            ),
        ),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
