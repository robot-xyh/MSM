#!/usr/bin/env python3
"""Run the D4 development-only actual-policy calibration diagnostic."""

from __future__ import annotations

import argparse
from pathlib import Path

from d4_distributed_fallback.region_resource_actual_policy_diagnostic import (
    run_region_resource_actual_policy_calibration,
    write_region_resource_actual_policy_diagnostic,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument(
        "--expected-candidate-manifest-sha256",
        required=True,
        help="trusted SHA-256 anchor for development_candidate_manifest.json",
    )
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--include-all-samples",
        action="store_true",
        help="persist every per-action sample instead of a compact audit",
    )
    args = parser.parse_args()

    report = run_region_resource_actual_policy_calibration(
        args.candidate_root,
        expected_candidate_manifest_sha256=(
            args.expected_candidate_manifest_sha256
        ),
        dataset_root=args.dataset_root,
    )
    json_path, markdown_path = (
        write_region_resource_actual_policy_diagnostic(
            report,
            args.output_dir,
            include_all_samples=args.include_all_samples,
        )
    )
    print(
        f"samples={report.sample_count} "
        f"safe_nonzero={report.safe_nonzero_actual_model_count} "
        f"formal_evidence=false permissions=false"
    )
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
