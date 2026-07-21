#!/usr/bin/env python3
"""Audit explicit D5 clean graph artifacts without promoting a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d5_clean_graph_evidence import (  # noqa: E402
    D5CleanGraphEvidenceError,
    load_d5_clean_graph_evidence_inputs,
    write_d5_clean_graph_evidence_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs-json",
        type=Path,
        required=True,
        help="explicit D5 artifact paths and caller-supplied SHA-256 values",
    )
    parser.add_argument(
        "--inputs-sha256",
        required=True,
        help="out-of-band SHA-256 of the input specification",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="independent D6 report directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        inputs = load_d5_clean_graph_evidence_inputs(
            args.inputs_json,
            expected_sha256=args.inputs_sha256,
        )
        paths = write_d5_clean_graph_evidence_report(inputs, args.output_dir)
    except (D5CleanGraphEvidenceError, ValueError, TypeError) as exc:
        reason = getattr(exc, "code", "invalid_input_specification")
        print(
            json.dumps(
                {"status": "failed", "reason": reason},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "json": str(paths["json"]),
                "markdown": str(paths["markdown"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
