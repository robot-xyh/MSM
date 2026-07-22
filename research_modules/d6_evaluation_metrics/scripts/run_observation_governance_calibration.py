#!/usr/bin/env python3
"""Generate D6 long-episode observation-governance calibration reports."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.observation_governance_calibration import (  # noqa: E402
    DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RESAMPLES,
    DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RNG_SEED,
    ObservationGovernanceCalibrationReportGenerator,
    load_observation_governance_calibration_inputs,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-spec", required=True)
    parser.add_argument("--input-spec-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RESAMPLES,
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=DEFAULT_OBSERVATION_GOVERNANCE_BOOTSTRAP_RNG_SEED,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    inputs = load_observation_governance_calibration_inputs(
        args.input_spec,
        expected_sha256=args.input_spec_sha256,
    )
    outputs = ObservationGovernanceCalibrationReportGenerator().write_report_bundle(
        args.output_dir,
        inputs=inputs,
        bootstrap_resamples=args.bootstrap_resamples,
        bootstrap_rng_seed=args.bootstrap_seed,
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
