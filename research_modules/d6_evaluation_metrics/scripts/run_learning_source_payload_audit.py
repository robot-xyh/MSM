#!/usr/bin/env python3
"""Run the authorized D6 full-payload source-integrity audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.learning_source_payload_audit import (  # noqa: E402
    LearningSourcePayloadAuditError,
    LearningSourcePayloadAuditInputs,
    audit_learning_source_payloads,
    write_learning_source_payload_audit_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-contract", type=Path, required=True)
    parser.add_argument("--input-contract-sha256", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--preflight-sha256", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = LearningSourcePayloadAuditInputs(
        input_contract_path=args.input_contract,
        input_contract_sha256=args.input_contract_sha256,
        preflight_path=args.preflight,
        preflight_sha256=args.preflight_sha256,
        authorization_path=args.authorization,
        authorization_sha256=args.authorization_sha256,
    )
    try:
        result = audit_learning_source_payloads(inputs)
        hashes = write_learning_source_payload_audit_report(args.output_dir, result)
    except (LearningSourcePayloadAuditError, OSError) as exc:
        code = getattr(exc, "code", "source_audit_io_error")
        detail = getattr(exc, "detail", str(exc))
        print(
            json.dumps(
                {"status": "failed_closed", "blocker_code": code, "detail": detail},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "audit_passed": result["audit_passed"],
                "output_dir": str(args.output_dir.absolute()),
                "output_sha256": hashes,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result.get("audit_passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
