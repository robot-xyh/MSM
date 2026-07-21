#!/usr/bin/env python3
"""Audit or build detached D4/D5 learning-label sidecars."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.learning_label_backfill import (  # noqa: E402
    LearningLabelBackfillConfig,
    LearningLabelBackfillError,
    write_learning_label_readiness,
    write_learning_label_sidecars,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a frozen scalable-3D learning export and write either a "
            "compact readiness audit or detached D4/D5 label sidecars."
        )
    )
    parser.add_argument("learning_dataset_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="write one readiness JSON instead of the full sidecar bundle",
    )
    parser.add_argument(
        "--audit-date",
        default="2026-07-20",
        help="frozen evidence date written to deterministic outputs",
    )
    parser.add_argument(
        "--skip-source-hashes",
        action="store_true",
        help="development-only structural audit; never use for formal readiness",
    )
    parser.add_argument(
        "--shared-seed-split-registry",
        type=Path,
        default=None,
        help=(
            "optional detached scalable3d-shared-seed-split-registry-v1; "
            "enables read-only D3/D4/D5 canonical split readiness"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = LearningLabelBackfillConfig(
        audit_date=args.audit_date,
        verify_all_source_hashes=not args.skip_source_hashes,
    )
    try:
        if args.audit_only:
            payload = write_learning_label_readiness(
                args.learning_dataset_dir,
                args.output,
                config=config,
                shared_seed_split_registry_path=args.shared_seed_split_registry,
            )
        else:
            payload = write_learning_label_sidecars(
                args.learning_dataset_dir,
                args.output,
                config=config,
                shared_seed_split_registry_path=args.shared_seed_split_registry,
            )
    except LearningLabelBackfillError as exc:
        print(json.dumps({"status": "failed", "reason": exc.code}, sort_keys=True))
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "schema_version": payload["schema_version"],
                "output": str(args.output.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
