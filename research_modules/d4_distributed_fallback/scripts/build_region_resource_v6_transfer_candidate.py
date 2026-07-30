#!/usr/bin/env python3
"""Build the unregistered D4 v6 edge-transfer development candidate."""

from __future__ import annotations

import argparse
import json

from d4_distributed_fallback.region_resource_v6_transfer_candidate import (
    build_region_resource_v6_transfer_candidate,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-v4-candidate-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    manifest = build_region_resource_v6_transfer_candidate(
        args.frozen_v4_candidate_root,
        args.output_root,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
