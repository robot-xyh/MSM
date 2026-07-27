#!/usr/bin/env python3
"""Assemble one D5 G1 v5 bundle from explicit, hashed evidence files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from d5_terminal_association.tracklet_g1_evidence_assembler import (
    TrackletG1EvidenceAssemblyError,
    TrackletG1EvidenceInputs,
    assemble_tracklet_g1_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a development bundle, held-out report, paired-shadow "
            "report, paired episode lineage, and D6 external audit before "
            "atomically writing v5."
        )
    )
    parser.add_argument("--development-bundle-dir", type=Path, required=True)
    parser.add_argument("--bundle-manifest-sha256", required=True)
    parser.add_argument("--bundle-weights-sha256", required=True)
    parser.add_argument("--bundle-checksums-sha256", required=True)
    parser.add_argument("--heldout-report", type=Path, required=True)
    parser.add_argument("--heldout-report-sha256", required=True)
    parser.add_argument("--paired-shadow-report", type=Path, required=True)
    parser.add_argument("--paired-shadow-report-sha256", required=True)
    parser.add_argument("--paired-shadow-lineage", type=Path, required=True)
    parser.add_argument("--paired-shadow-lineage-sha256", required=True)
    parser.add_argument("--d6-audit", type=Path, required=True)
    parser.add_argument("--d6-audit-sha256", required=True)
    parser.add_argument("--output-bundle-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        inputs = TrackletG1EvidenceInputs(
            development_bundle_dir=args.development_bundle_dir,
            expected_bundle_manifest_sha256=args.bundle_manifest_sha256,
            expected_bundle_weights_sha256=args.bundle_weights_sha256,
            expected_bundle_checksums_sha256=args.bundle_checksums_sha256,
            heldout_report_path=args.heldout_report,
            expected_heldout_report_sha256=args.heldout_report_sha256,
            paired_shadow_report_path=args.paired_shadow_report,
            expected_paired_shadow_report_sha256=(
                args.paired_shadow_report_sha256
            ),
            paired_shadow_lineage_path=args.paired_shadow_lineage,
            expected_paired_shadow_lineage_sha256=(
                args.paired_shadow_lineage_sha256
            ),
            d6_audit_path=args.d6_audit,
            expected_d6_audit_sha256=args.d6_audit_sha256,
        )
        result = assemble_tracklet_g1_bundle(
            args.output_bundle_dir,
            inputs,
        )
    except TrackletG1EvidenceAssemblyError as exc:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "code": exc.code,
                    "detail": exc.detail,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {"status": "assembled", **dict(result.to_dict())},
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
