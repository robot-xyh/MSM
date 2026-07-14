#!/usr/bin/env python3
"""Run the governed D2 P1 identity-continuity calibration matrix."""

from __future__ import annotations

import argparse
from pathlib import Path

from d2_data_association import (
    load_identity_calibration_manifest,
    run_p1_identity_calibration,
    write_p1_identity_calibration_report,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screening-manifest", type=Path, required=True)
    parser.add_argument("--confirmation-manifest", type=Path)
    parser.add_argument(
        "--p95-loop-latency-budget-s",
        type=float,
        help=(
            "Frozen p95 budget. If omitted, it must be present in the "
            "screening manifest."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    screening_cases, manifest_budget = load_identity_calibration_manifest(
        args.screening_manifest
    )
    confirmation_cases = None
    if args.confirmation_manifest is not None:
        confirmation_cases, _ = load_identity_calibration_manifest(
            args.confirmation_manifest
        )
    latency_budget = (
        args.p95_loop_latency_budget_s
        if args.p95_loop_latency_budget_s is not None
        else manifest_budget
    )
    if latency_budget is None:
        parser.error(
            "p95 loop latency budget is required by CLI or screening manifest"
        )

    report = run_p1_identity_calibration(
        screening_cases,
        confirmation_cases=confirmation_cases,
        frozen_p95_loop_latency_budget_s=latency_budget,
    )
    write_p1_identity_calibration_report(args.output, report)


if __name__ == "__main__":
    main()
