#!/usr/bin/env python3
"""Run the D6 metadata-only preflight for D3/D4/D5 generation sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.learning_source_generation_preflight import (  # noqa: E402
    LearningSourceGenerationPreflightError,
    evaluate_learning_source_generation_preflight,
    load_learning_source_generation_preflight_inputs,
    write_learning_source_generation_preflight_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate only D3/D4/D5 source-generation metadata. "
            "This command has no full-audit or payload-reading mode."
        )
    )
    parser.add_argument("--input-contract", type=Path, required=True)
    parser.add_argument("--input-contract-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        inputs = load_learning_source_generation_preflight_inputs(
            args.input_contract,
            expected_sha256=args.input_contract_sha256,
        )
        result = evaluate_learning_source_generation_preflight(inputs)
        output_hashes = write_learning_source_generation_preflight_report(
            args.output_dir,
            result,
        )
    except LearningSourceGenerationPreflightError as exc:
        print(
            json.dumps(
                {"status": "failed_closed", "error_code": exc.code, "detail": exc.detail},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "metadata_preflight_passed": result["metadata_preflight_passed"],
                "full_payload_audit_performed": False,
                "formal_source_data_read": False,
                "output_hashes": output_hashes,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["metadata_preflight_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
