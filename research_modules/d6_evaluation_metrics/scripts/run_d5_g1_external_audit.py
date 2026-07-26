#!/usr/bin/env python3
"""Run the deterministic D6 audit for one D5 G1 evidence request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d6_evaluation_metrics.d5_g1_external_audit import (
    audit_d5_g1_external_evidence,
    load_d5_g1_external_audit_inputs,
    write_d5_g1_external_audit_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit frozen D5 G1 artifacts. The command writes a report even "
            "when the evidence fails closed."
        )
    )
    parser.add_argument("--input-spec", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    inputs = load_d5_g1_external_audit_inputs(
        args.input_spec,
        repository_root=args.repository_root,
    )
    result = audit_d5_g1_external_evidence(inputs)
    artifacts = write_d5_g1_external_audit_report(args.output_dir, result)
    print(
        json.dumps(
            {
                "schema_version": result["schema_version"],
                "status": result["status"],
                "audit_passed": result["audit_passed"],
                "blocker_codes": result["blocker_codes"],
                "content_sha256": result["content_sha256"],
                "json": str(artifacts["json"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
