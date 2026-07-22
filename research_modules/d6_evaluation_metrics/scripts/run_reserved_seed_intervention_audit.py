#!/usr/bin/env python3
"""Audit one D3/D4 reserved-seed execution bundle as a read-only consumer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d6_evaluation_metrics import (
    EXPECTED_CHECKSUMS_SHA256,
    EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
    EXPECTED_D3_BUNDLE_STATE_SHA256,
    EXPECTED_D4_BUNDLE_MANIFEST_SHA256,
    EXPECTED_D4_BUNDLE_STATE_SHA256,
    EXPECTED_SOURCE_COMMIT,
    EXPECTED_SOURCE_MANIFEST_SHA256,
    ReservedSeedInterventionAuditInputs,
    write_reserved_seed_intervention_audit,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = (
    MODULE_ROOT.parent
    / "scalable_3d_simulation"
    / "outputs"
    / "reserved_seed_interventions_nominal_5v5_1000_1019_formal_6d5bfea"
)
DEFAULT_OUTPUT_DIR = (
    MODULE_ROOT
    / "outputs"
    / "reserved_seed_interventions_nominal_5v5_1000_1019_d6_audit_20260721"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Independently audit D3/D4 reserved-seed execution receipts and "
            "write a detached outcome-availability sidecar."
        )
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--audited-at-utc", required=True)
    parser.add_argument(
        "--expected-source-commit",
        default=EXPECTED_SOURCE_COMMIT,
    )
    parser.add_argument(
        "--expected-checksums-sha256",
        default=EXPECTED_CHECKSUMS_SHA256,
    )
    parser.add_argument(
        "--expected-source-manifest-sha256",
        default=EXPECTED_SOURCE_MANIFEST_SHA256,
    )
    parser.add_argument(
        "--expected-d3-bundle-manifest-sha256",
        default=EXPECTED_D3_BUNDLE_MANIFEST_SHA256,
    )
    parser.add_argument(
        "--expected-d3-bundle-state-sha256",
        default=EXPECTED_D3_BUNDLE_STATE_SHA256,
    )
    parser.add_argument(
        "--expected-d4-bundle-manifest-sha256",
        default=EXPECTED_D4_BUNDLE_MANIFEST_SHA256,
    )
    parser.add_argument(
        "--expected-d4-bundle-state-sha256",
        default=EXPECTED_D4_BUNDLE_STATE_SHA256,
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    inputs = ReservedSeedInterventionAuditInputs(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        audited_at_utc=args.audited_at_utc,
        expected_source_commit=args.expected_source_commit,
        expected_checksums_sha256=args.expected_checksums_sha256,
        expected_source_manifest_sha256=args.expected_source_manifest_sha256,
        expected_d3_bundle_manifest_sha256=(
            args.expected_d3_bundle_manifest_sha256
        ),
        expected_d3_bundle_state_sha256=args.expected_d3_bundle_state_sha256,
        expected_d4_bundle_manifest_sha256=(
            args.expected_d4_bundle_manifest_sha256
        ),
        expected_d4_bundle_state_sha256=args.expected_d4_bundle_state_sha256,
    )
    paths = write_reserved_seed_intervention_audit(inputs)
    sidecar = json.loads(paths["sidecar"].read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "status": sidecar["status"],
                "audit_passed": sidecar["audit_passed"],
                "content_sha256": sidecar["content_sha256"],
                "evidence_availability": sidecar["evidence_availability"],
                "d3_treatment_applied_count": sidecar["d3"][
                    "treatment_applied_count"
                ],
                "d4_treatment_safe_adopted_count": sidecar["d4"][
                    "treatment_safe_adopted_count"
                ],
                "output_dir": str(inputs.output_dir),
                "artifacts": {
                    name: str(path) for name, path in sorted(paths.items())
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
