#!/usr/bin/env python3
"""Run the D6 independent audit for one explicit D5 paired-shadow bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d6_evaluation_metrics.d5_paired_shadow_audit import (
    D5PairedShadowAuditInputs,
    write_d5_paired_shadow_audit,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit D5 paired-shadow evidence without modifying producer inputs."
    )
    for name in (
        "paired-report",
        "paired-lineage",
        "heldout-corpus-dir",
        "heldout-report",
        "model-bundle-dir",
        "d5-source-dir",
        "superseded-report",
        "superseded-lineage",
        "output-dir",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in (
        "expected-paired-report-sha256",
        "expected-paired-report-content-sha256",
        "expected-paired-lineage-sha256",
        "expected-corpus-manifest-sha256",
        "expected-corpus-content-sha256",
        "expected-corpus-config-sha256",
        "expected-heldout-report-sha256",
        "expected-heldout-report-content-sha256",
        "expected-bundle-manifest-sha256",
        "expected-bundle-weights-sha256",
        "expected-bundle-checksums-sha256",
        "expected-superseded-report-sha256",
        "expected-superseded-lineage-sha256",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--audited-at-utc", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    inputs = D5PairedShadowAuditInputs(
        paired_report_path=args.paired_report,
        paired_lineage_path=args.paired_lineage,
        heldout_corpus_dir=args.heldout_corpus_dir,
        heldout_report_path=args.heldout_report,
        model_bundle_dir=args.model_bundle_dir,
        d5_source_dir=args.d5_source_dir,
        superseded_report_path=args.superseded_report,
        superseded_lineage_path=args.superseded_lineage,
        output_dir=args.output_dir,
        expected_paired_report_sha256=args.expected_paired_report_sha256,
        expected_paired_report_content_sha256=(
            args.expected_paired_report_content_sha256
        ),
        expected_paired_lineage_sha256=args.expected_paired_lineage_sha256,
        expected_corpus_manifest_sha256=args.expected_corpus_manifest_sha256,
        expected_corpus_content_sha256=args.expected_corpus_content_sha256,
        expected_corpus_config_sha256=args.expected_corpus_config_sha256,
        expected_heldout_report_sha256=args.expected_heldout_report_sha256,
        expected_heldout_report_content_sha256=(
            args.expected_heldout_report_content_sha256
        ),
        expected_bundle_manifest_sha256=args.expected_bundle_manifest_sha256,
        expected_bundle_weights_sha256=args.expected_bundle_weights_sha256,
        expected_bundle_checksums_sha256=args.expected_bundle_checksums_sha256,
        expected_superseded_report_sha256=(
            args.expected_superseded_report_sha256
        ),
        expected_superseded_lineage_sha256=(
            args.expected_superseded_lineage_sha256
        ),
        audited_at_utc=args.audited_at_utc,
    )
    report = write_d5_paired_shadow_audit(inputs)
    print(
        json.dumps(
            {
                "status": report["status"],
                "audit_passed": report["audit_passed"],
                "content_sha256": report["content_sha256"],
                "external_generalization": report["evidence_layers"][
                    "external_generalization"
                ],
                "authority": report["authority"],
                "output_dir": str(inputs.output_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
