#!/usr/bin/env python3
"""Build the content-addressed D4 v4 development/shadow candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d4_distributed_fallback.region_resource_v4_shadow_candidate import (
    RegionResourceV4BuildConfig,
    build_region_resource_v4_development_candidate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--input-dataset-dir", type=Path, required=True)
    parser.add_argument("--source-evidence", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=240)
    parser.add_argument("--confidence-epochs", type=int, default=180)
    parser.add_argument("--hidden-dim", type=int, default=24)
    parser.add_argument("--torch-num-threads", type=int, default=1)
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = RegionResourceV4BuildConfig(
        epochs=args.epochs,
        confidence_epochs=args.confidence_epochs,
        hidden_dim=args.hidden_dim,
        torch_num_threads=args.torch_num_threads,
    )
    result = build_region_resource_v4_development_candidate(
        args.output_dir,
        repository_root=args.repository_root,
        input_dataset_dir=args.input_dataset_dir,
        source_evidence_path=args.source_evidence,
        config=config,
    )
    print(json.dumps(result["candidate_manifest"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
