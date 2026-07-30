#!/usr/bin/env python3
"""Run the read-only D6 audit of the frozen D4 v5 external evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d4_v5_source_independent_external_audit import (  # noqa: E402
    audit_d4_v5_source_independent_external,
    load_d4_v5_external_audit_inputs,
    write_d4_v5_external_audit_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-spec", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    inputs = load_d4_v5_external_audit_inputs(
        args.input_spec,
        repository_root=args.repository_root,
    )
    result = audit_d4_v5_source_independent_external(inputs)
    outputs = write_d4_v5_external_audit_report(args.output_dir, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "audit_execution_passed": result["audit_execution_passed"],
                "admission_allowed": result["admission_conclusion"][
                    "admission_allowed"
                ],
                "formal_holdout_payload_read_count": result[
                    "seed_governance"
                ]["formal_holdout_payload_read_count"],
                "content_sha256": result["content_sha256"],
                "json": str(outputs["json"]),
                "csv": str(outputs["csv"]),
                "markdown": str(outputs["markdown"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
