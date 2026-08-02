#!/usr/bin/env python3
"""Issue one clean-commit, generation-only D3/D4/D5 source authorization."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.learning_source_generation_authorization import (
    SOURCE_GENERATION_CONFIRMATION,
    build_learning_source_generation_authorization,
    write_learning_source_generation_authorization,
)
from research_modules.scalable_3d_simulation.learning_source_preflight import (
    evaluate_learning_source_preflight,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--approver-id", required=True)
    parser.add_argument("--approval-reason", required=True)
    parser.add_argument(
        "--confirmation",
        required=True,
        help=f"must equal: {SOURCE_GENERATION_CONFIRMATION}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preflight = evaluate_learning_source_preflight(repository_root=ROOT)
    authorization = build_learning_source_generation_authorization(
        preflight,
        authorization_id=args.authorization_id,
        approver_id=args.approver_id,
        approval_reason=args.approval_reason,
        confirmation=args.confirmation,
    )
    path, digest = write_learning_source_generation_authorization(
        args.output, authorization
    )
    print(f"authorization={path}")
    print(f"authorization_sha256={digest}")
    print("dataset_generation=true")
    print("training=false")
    print("runtime_authority=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
