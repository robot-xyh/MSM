#!/usr/bin/env python3
"""Run the read-only D6 audit of the frozen D4 v7 external evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d4_v7_source_independent_external_audit import (  # noqa: E402
    audit_d4_v7_source_independent_external,
    load_d4_v7_external_audit_inputs,
    write_d4_v7_external_audit_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-spec", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    inputs = load_d4_v7_external_audit_inputs(
        args.input_spec,
        repository_root=args.repository_root,
    )
    result = audit_d4_v7_source_independent_external(inputs)
    outputs = write_d4_v7_external_audit_report(args.output_dir, result)
    aggregate = result["independent_recomputation"]["aggregate"]
    print(
        json.dumps(
            {
                "status": result["status"],
                "evaluation_disposition": result["evaluation_disposition"],
                "audit_execution_passed": result["audit_execution_passed"],
                "rule_positive_exact_action": (
                    f"{aggregate['projected_exact_positive_action_count']}/"
                    f"{aggregate['rule_positive_count']}"
                ),
                "actor_derived_positive_denominator": aggregate[
                    "actor_derived_positive_denominator_count"
                ],
                "confidence_calibration_allowed": result[
                    "admission_conclusion"
                ]["confidence_calibration_allowed"],
                "d4_d6_jsonl_sha256": result[
                    "d4_artifact_reconciliation"
                ]["d6_jsonl_byte_sha256"],
                "content_sha256": result["content_sha256"],
                "json": str(outputs["json"]),
                "csv": str(outputs["csv"]),
                "records_jsonl": str(outputs["records_jsonl"]),
                "markdown": str(outputs["markdown"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
