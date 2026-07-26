"""Command-line entry points for D4 A2 evidence assembly and validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .region_resource_a2_evidence import (
    RegionResourceA2EvidenceError,
    RegionResourceA2EvidenceInputs,
    assemble_region_resource_a2_evidence_bundle,
    load_region_resource_a2_evidence_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble or validate a D4 A2 assist-only evidence bundle. "
            "The command cannot grant default, PPO, failover, assignment, "
            "or control authority."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    assemble = subparsers.add_parser(
        "assemble", help="assemble one immutable evidence bundle"
    )
    assemble.add_argument("--development-bundle", type=Path, required=True)
    assemble.add_argument("--development-manifest-sha256", required=True)
    assemble.add_argument("--development-weights-sha256", required=True)
    assemble.add_argument(
        "--development-training-manifest-sha256", required=True
    )
    assemble.add_argument(
        "--implementation-evidence", type=Path, required=True
    )
    assemble.add_argument("--implementation-evidence-sha256", required=True)
    assemble.add_argument("--d6-external-audit", type=Path, required=True)
    assemble.add_argument("--d6-external-audit-sha256", required=True)
    assemble.add_argument("--formal-scope-audit", type=Path, required=True)
    assemble.add_argument("--formal-scope-audit-sha256", required=True)
    assemble.add_argument(
        "--formal-scope-checksums", type=Path, required=True
    )
    assemble.add_argument("--formal-scope-checksums-sha256", required=True)
    assemble.add_argument(
        "--runtime-chain-evidence", type=Path, required=True
    )
    assemble.add_argument("--runtime-chain-evidence-sha256", required=True)
    assemble.add_argument("--output-dir", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate", help="strictly load an assembled evidence bundle"
    )
    validate.add_argument("--bundle-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            loaded = load_region_resource_a2_evidence_bundle(args.bundle_dir)
            payload = {
                "status": "pass",
                "bundle_dir": str(loaded.bundle_dir),
                "candidate_fingerprint": loaded.candidate_fingerprint,
                "implementation_sha256": loaded.implementation_sha256,
                "unseen_seed_values": list(loaded.unseen_seed_values),
                "a2_assist_eligible": loaded.a2_assist_eligible,
                "default_model": loaded.default_model,
                "ppo_enabled": loaded.ppo_enabled,
                "failover_authority": loaded.failover_authority,
                "assignment_authority": loaded.assignment_authority,
                "control_authority": loaded.control_authority,
                "rule_fallback_required": loaded.rule_fallback_required,
            }
        else:
            inputs = RegionResourceA2EvidenceInputs(
                development_bundle_dir=args.development_bundle,
                expected_development_manifest_sha256=(
                    args.development_manifest_sha256
                ),
                expected_development_weights_sha256=(
                    args.development_weights_sha256
                ),
                expected_development_training_manifest_sha256=(
                    args.development_training_manifest_sha256
                ),
                implementation_evidence_path=args.implementation_evidence,
                expected_implementation_evidence_sha256=(
                    args.implementation_evidence_sha256
                ),
                d6_external_audit_path=args.d6_external_audit,
                expected_d6_external_audit_sha256=(
                    args.d6_external_audit_sha256
                ),
                formal_scope_audit_path=args.formal_scope_audit,
                expected_formal_scope_audit_sha256=(
                    args.formal_scope_audit_sha256
                ),
                formal_scope_checksums_path=args.formal_scope_checksums,
                expected_formal_scope_checksums_sha256=(
                    args.formal_scope_checksums_sha256
                ),
                runtime_chain_evidence_path=args.runtime_chain_evidence,
                expected_runtime_chain_evidence_sha256=(
                    args.runtime_chain_evidence_sha256
                ),
            )
            result = assemble_region_resource_a2_evidence_bundle(
                args.output_dir, inputs
            )
            payload = {"status": "pass", **dict(result.to_dict())}
    except RegionResourceA2EvidenceError as exc:
        print(
            json.dumps(
                {
                    "status": "fail_closed",
                    "code": exc.code,
                    "detail": exc.detail,
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
