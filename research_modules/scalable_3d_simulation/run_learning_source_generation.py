#!/usr/bin/env python3
"""Run one authorized D3, D4, or D5 learning-source generation segment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.learning_source_generation import (
    SOURCE_GENERATION_MODULES,
    run_authorized_learning_source_generation,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, choices=SOURCE_GENERATION_MODULES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--base-config", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-episodes-per-run", type=int)
    parser.add_argument("--minimum-free-gb", type=float, default=5.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_authorized_learning_source_generation(
        module=args.module,
        output_dir=args.output,
        authorization_path=args.authorization,
        authorization_sha256=args.authorization_sha256,
        repository_root=args.repository_root,
        base_config_path=args.base_config,
        max_episodes_per_run=args.max_episodes_per_run,
        resume=bool(args.resume),
        minimum_free_gb=args.minimum_free_gb,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
