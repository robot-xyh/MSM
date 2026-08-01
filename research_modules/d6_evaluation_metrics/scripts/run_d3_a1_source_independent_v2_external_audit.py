#!/usr/bin/env python3
"""Run the independent D6 audit of the D3 A1 v2 result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d6_evaluation_metrics.d3_a1_source_independent_v2_audit import (
    D3A1V2ExternalAuditInputs,
    audit_d3_a1_source_independent_v2,
    write_d3_a1_source_independent_v2_audit,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Independently audit D3 A1 source-independent v2 evidence. "
            "The command never trains, selects, or grants authority."
        )
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--generation-root", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--evaluated-at-utc", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    inputs = D3A1V2ExternalAuditInputs(
        repository_root=args.repository_root,
        result_dir=args.result_dir,
        generation_root=args.generation_root,
        dataset_dir=args.dataset_dir,
        contract_path=args.contract,
        bundle_dir=args.bundle_dir,
        audit_id=args.audit_id,
        evaluated_at_utc=args.evaluated_at_utc,
    )
    result = audit_d3_a1_source_independent_v2(inputs)
    artifacts = write_d3_a1_source_independent_v2_audit(
        args.output_dir,
        result,
    )
    overall = result["independent_recomputation"]["overall_metrics"]
    print(
        json.dumps(
            {
                "schema_version": result["schema_version"],
                "status": result["status"],
                "audit_integrity_passed": result["audit_integrity_passed"],
                "preregistered_machine_gate_passed": result[
                    "preregistered_machine_gate"
                ]["passed"],
                "frame_count": overall["frame_count"],
                "positive_safe_binding_change": overall[
                    "positive_safe_binding_change"
                ],
                "positive_teacher_exact_match": overall[
                    "positive_teacher_exact_match"
                ],
                "negative_exact_r0": overall["negative_exact_r0"],
                "all_authorities_false": all(
                    value is False for value in result["authorities"].values()
                ),
                "json": str(artifacts["json"]),
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
