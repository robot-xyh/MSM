#!/usr/bin/env python3
"""Run the D6 low-level independent D5 A3 v2 BC model audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from d6_evaluation_metrics.d5_a3_v2_bc_model_audit import (
    AuditInputs,
    audit_d5_a3_v2_bc_candidate,
    write_report_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--frozen-config", type=Path, required=True)
    parser.add_argument("--candidate-evidence", type=Path, required=True)
    parser.add_argument("--generation-plan", type=Path, required=True)
    parser.add_argument("--generation-summary", type=Path, required=True)
    parser.add_argument("--training-seed-registry", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = audit_d5_a3_v2_bc_candidate(
        AuditInputs(
            repo_root=args.repo_root,
            candidate_root=args.candidate_root,
            frozen_config=args.frozen_config,
            candidate_evidence=args.candidate_evidence,
            generation_plan=args.generation_plan,
            generation_summary=args.generation_summary,
            training_seed_registry=args.training_seed_registry,
        )
    )
    write_report_bundle(result, args.output_dir)
    print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
