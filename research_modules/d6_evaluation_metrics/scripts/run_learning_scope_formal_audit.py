#!/usr/bin/env python3
"""Audit one hash-bound learned scope against explicit R0 evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = ROOT / "research_modules" / "d6_evaluation_metrics"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from d6_evaluation_metrics.learning_scope_formal_audit import (  # noqa: E402
    LearningScopeFormalAuditInputs,
    ScopeEvidenceArtifacts,
    audit_learning_scope_formal_evidence,
    write_learning_scope_formal_audit_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-plan", type=Path, required=True)
    parser.add_argument("--scope-merge-dir", type=Path, required=True)
    parser.add_argument("--scope-label", default="learned_scope")
    parser.add_argument(
        "--r0-scope",
        nargs=3,
        action="append",
        metavar=("EXECUTION_PLAN", "MERGE_DIR", "LABEL"),
        default=[],
        help="repeatable explicit R0 execution-plan/merge-dir/label triple",
    )
    parser.add_argument("--expected-preflight-device")
    parser.add_argument("--d3-bundle", type=Path)
    parser.add_argument("--d4-bundle", type=Path)
    parser.add_argument("--d5-graph-bundle", type=Path)
    parser.add_argument("--d5-active-vision-bundle", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = audit_learning_scope_formal_evidence(
        LearningScopeFormalAuditInputs(
            learned_scope=ScopeEvidenceArtifacts(
                execution_plan_path=args.execution_plan,
                merge_dir=args.scope_merge_dir,
                label=args.scope_label,
            ),
            r0_scopes=tuple(
                ScopeEvidenceArtifacts(
                    execution_plan_path=Path(plan),
                    merge_dir=Path(merge),
                    label=label,
                )
                for plan, merge, label in args.r0_scope
            ),
            expected_preflight_device=args.expected_preflight_device,
        ),
        model_bundles={
            "d3": args.d3_bundle,
            "d4": args.d4_bundle,
            "d5_graph": args.d5_graph_bundle,
            "d5_active_vision": args.d5_active_vision_bundle,
        },
    )
    paths = write_learning_scope_formal_audit_report(
        args.output_dir,
        result,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    print(f"verdict: {result['verdict']}")
    print(
        "available_r0_pairs: "
        f"{result['r0_pairing']['available_pair_count']}/"
        f"{result['r0_pairing']['expected_pair_count']}"
    )
    return 0 if result["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
