#!/usr/bin/env python3
"""Read-only validation entry point for the D4 v8 train-source contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from d4_distributed_fallback.region_resource_v8_development_contract import (
    validate_v8_pre_generation_readiness,
)


_MODULE_ROOT = Path(__file__).resolve().parents[1]
_FROZEN_REQUEST_ROOT = (
    _MODULE_ROOT
    / "reports"
    / "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Strictly load the frozen D4 v8 request and optionally validate a "
            "complete main schedule plus generated TRAIN episodes. The command "
            "never writes, trains, selects validation/test, or grants authority."
        )
    )
    parser.add_argument(
        "--request",
        type=Path,
        default=_FROZEN_REQUEST_ROOT / "v8_development_data_request.json",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=_FROZEN_REQUEST_ROOT / "v8_development_seed_registry.json",
    )
    parser.add_argument("--main-schedule", type=Path)
    parser.add_argument("--dataset-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    readiness = validate_v8_pre_generation_readiness(
        args.request,
        args.registry,
        main_schedule_path=args.main_schedule,
        dataset_root=args.dataset_root,
    )
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
