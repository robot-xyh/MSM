#!/usr/bin/env python3
"""Read-only CLI for the D4 v8 main seed-allocation binding."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from d4_distributed_fallback.region_resource_v8_main_allocation_readiness import (
    RegionResourceV8MainAllocationError,
    default_v8_main_allocation_binding_path,
    default_v8_source_generation_request_path,
    validate_v8_main_allocation_pre_generation_readiness,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the exact main global seed allocation against the frozen "
            "D4 A2 v8 TRAIN-only request. This command only reports generation "
            "prerequisites; it never generates data, trains, registers, or grants "
            "runtime authority."
        )
    )
    parser.add_argument(
        "--binding",
        type=Path,
        default=default_v8_main_allocation_binding_path(),
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_REPOSITORY_ROOT,
    )
    parser.add_argument(
        "--source-generation-request",
        type=Path,
        default=default_v8_source_generation_request_path(),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        readiness = validate_v8_main_allocation_pre_generation_readiness(
            binding_path=args.binding,
            source_generation_request_path=args.source_generation_request,
            repository_root=args.repository_root,
        )
    except RegionResourceV8MainAllocationError as exc:
        print(
            json.dumps(
                {
                    "schema": "d4-region-resource-v8-main-seed-allocation-readiness-error-v1",
                    "status": "failed_closed",
                    "generation_prerequisites_ready": False,
                    "source_generation_request_ready": False,
                    "error_code": exc.code,
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
        )
        return 2
    print(
        json.dumps(
            readiness.to_dict(),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
