#!/usr/bin/env python3
"""Build the unregistered D4 v7 rule-node residual candidate."""

from __future__ import annotations

import argparse
import json

from d4_distributed_fallback.region_resource_v7_rule_node_residual_candidate import (
    build_region_resource_v7_rule_node_residual_candidate,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fit the D4 v7 transfer-only residual actor from frozen v4 and "
            "M16N24 TRAIN/VALIDATION sources. The output remains unregistered "
            "and carries no runtime authority."
        )
    )
    parser.add_argument("--frozen-v4-candidate-root", required=True)
    parser.add_argument("--m16n24-dataset-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    manifest = build_region_resource_v7_rule_node_residual_candidate(
        args.frozen_v4_candidate_root,
        args.m16n24_dataset_root,
        args.output_root,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
