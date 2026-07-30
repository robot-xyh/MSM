#!/usr/bin/env python3
"""Build the D4 v5 unregistered confidence-calibration candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d4_distributed_fallback.region_resource_v5_confidence_candidate import (
    build_region_resource_v5_confidence_candidate,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fit a TRAIN-only v5 confidence calibrator over the frozen v4 "
            "actor and audit VALIDATION without reading TEST payloads."
        )
    )
    parser.add_argument("--v4-candidate-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_region_resource_v5_confidence_candidate(
        args.v4_candidate_root,
        args.output_root,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
