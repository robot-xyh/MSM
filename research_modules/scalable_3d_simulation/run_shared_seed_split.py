#!/usr/bin/env python3
"""Build a detached cross-module numeric-seed split registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.shared_seed_split import (  # noqa: E402
    DEFAULT_MINIMUM_TEST_SEED_COUNT,
    DEFAULT_SPLIT_SEED,
    DEFAULT_TEST_FRACTION,
    DEFAULT_VALIDATION_FRACTION,
    SharedSeedSplitError,
    write_shared_seed_split_registry,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("training_seed_registry", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--split-seed", type=int, default=DEFAULT_SPLIT_SEED)
    parser.add_argument(
        "--validation-fraction", type=float, default=DEFAULT_VALIDATION_FRACTION
    )
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    parser.add_argument(
        "--minimum-test-seeds", type=int, default=DEFAULT_MINIMUM_TEST_SEED_COUNT
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = write_shared_seed_split_registry(
            args.training_seed_registry,
            args.output,
            split_seed=args.split_seed,
            validation_fraction=args.validation_fraction,
            test_fraction=args.test_fraction,
            minimum_test_seed_count=args.minimum_test_seeds,
        )
    except SharedSeedSplitError as exc:
        print(json.dumps({"status": "failed", "reason": exc.code}, sort_keys=True))
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "ok",
                "schema_version": payload["schema_version"],
                "content_sha256": payload["content_sha256"],
                "output": str(args.output.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
