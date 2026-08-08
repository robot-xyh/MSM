#!/usr/bin/env python3
"""Prepare D6 source-audit metadata bindings or an explicit audit-only grant."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.learning_source_audit_gate import (  # noqa: E402
    SOURCE_AUDIT_CONFIRMATION,
    build_learning_source_audit_authorization,
    build_learning_source_preflight_input,
    canonical_json_sha256,
    write_learning_source_audit_authorization,
    write_learning_source_preflight_input,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser(
        "prepare-input",
        help="bind only D3/D4/D5 generation metadata for D6 preflight",
    )
    prepare.add_argument("--contract-id", required=True)
    prepare.add_argument("--d3-root", type=Path, required=True)
    prepare.add_argument("--d4-root", type=Path, required=True)
    prepare.add_argument("--d5-root", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)

    approve = commands.add_parser(
        "approve-audit",
        help="write an audit-only grant after an independently produced preflight",
    )
    approve.add_argument("--preflight-result", type=Path, required=True)
    approve.add_argument("--preflight-result-sha256", required=True)
    approve.add_argument("--authorization-id", required=True)
    approve.add_argument("--approver-id", required=True)
    approve.add_argument("--approval-reason", required=True)
    approve.add_argument("--confirmation", required=True)
    approve.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "prepare-input":
        payload = build_learning_source_preflight_input(
            contract_id=args.contract_id,
            source_roots={
                "D3": args.d3_root,
                "D4": args.d4_root,
                "D5": args.d5_root,
            },
        )
        path, digest = write_learning_source_preflight_input(args.output, payload)
        print(f"preflight_input={path}")
        print(f"preflight_input_sha256={digest}")
        print("formal_source_payload_read=false")
        print("audit_authorized=false")
        return 0

    content = args.preflight_result.read_bytes()
    actual = sha256(content).hexdigest()
    if actual != args.preflight_result_sha256:
        raise ValueError("preflight result SHA-256 mismatch")
    preflight = json.loads(content.decode("utf-8"))
    payload = build_learning_source_audit_authorization(
        preflight,
        authorization_id=args.authorization_id,
        approver_id=args.approver_id,
        approval_reason=args.approval_reason,
        confirmation=args.confirmation,
        preflight_report_file_sha256=actual,
    )
    path, digest = write_learning_source_audit_authorization(args.output, payload)
    print(f"audit_authorization={path}")
    print(f"audit_authorization_sha256={digest}")
    print(f"preflight_result_canonical_sha256={canonical_json_sha256(preflight)}")
    print("training=false")
    print("model_inference=false")
    print("runtime_authority=false")
    print(f"required_confirmation={SOURCE_AUDIT_CONFIRMATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
