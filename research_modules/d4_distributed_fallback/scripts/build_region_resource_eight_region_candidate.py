#!/usr/bin/env python3
"""Build the frozen eight-region D4 development/shadow candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d4_distributed_fallback.region_resource_eight_region_candidate import (
    build_region_resource_eight_region_candidate,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dataset", type=Path, required=True)
    parser.add_argument("--action-dataset", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_region_resource_eight_region_candidate(
        args.runtime_dataset,
        args.action_dataset,
        repository_root=args.repository_root,
        output_dir=args.output_dir,
    )
    manifest = result["candidate_manifest"]
    print(
        json.dumps(
            {
                "candidate_id": manifest["candidate_id"],
                "candidate_manifest_content_sha256": manifest["content_sha256"],
                "model_state_sha256": manifest["model_state_sha256"],
                "composite_dataset_sha256": manifest[
                    "composite_dataset_sha256"
                ],
                "composite_split_sha256": manifest[
                    "composite_split_sha256"
                ],
                "runtime_preflight_completed": manifest[
                    "runtime_preflight_completed"
                ],
                "formal_evaluation_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
