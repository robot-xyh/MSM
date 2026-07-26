#!/usr/bin/env python3
"""Run a clean D5 cross-view R0 or admitted-G1 calibration batch."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.d5_crossview_calibration_batch import (
    D5_CROSSVIEW_RESERVED_SEEDS,
    D5CrossviewCalibrationBatchOptions,
    run_d5_crossview_calibration_batch,
)


DEFAULT_CONFIG = (
    Path(__file__).with_name("configs")
    / "d5_crossview_visibility_calibration_v1.json"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("R0", "G1"), default="R0")
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--d5-model-bundle", type=Path)
    parser.add_argument(
        "--evaluated-at-utc",
        default="2026-07-26T00:00:00Z",
    )
    parser.add_argument("--formal", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = run_d5_crossview_calibration_batch(
        D5CrossviewCalibrationBatchOptions(
            config_path=args.config,
            output_dir=args.output,
            variant=args.variant,
            seeds=(
                D5_CROSSVIEW_RESERVED_SEEDS
                if args.seeds is None
                else tuple(args.seeds)
            ),
            evaluated_at_utc=args.evaluated_at_utc,
            d5_bundle_dir=args.d5_model_bundle,
            formal=args.formal,
        )
    )
    print(f"manifest={paths['manifest']}")
    print(f"dataset_manifest={paths['dataset_manifest']}")
    print(f"frame_index_sidecar={paths['frame_index_sidecar']}")
    print(f"report={paths['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
