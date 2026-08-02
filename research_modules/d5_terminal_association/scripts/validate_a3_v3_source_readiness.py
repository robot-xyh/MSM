#!/usr/bin/env python3
"""Print D5 A3 v3 metadata-only pre-generation readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
SRC = MODULE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d5_terminal_association.active_vision_a3_v3_source_readiness import (  # noqa: E402
    validate_a3_v3_pre_generation_readiness,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate frozen D5 A3 v3 allocation and source schedule metadata; "
            "no episode payload is opened and no output artifact is written."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=MODULE_ROOT / "configs/a3_v3_minority_intent_protocol_20260801.json",
    )
    parser.add_argument(
        "--allocation-binding",
        type=Path,
        default=(
            MODULE_ROOT
            / "configs/a3_v3_global_seed_allocation_binding_20260801.json"
        ),
    )
    parser.add_argument(
        "--source-schedule",
        type=Path,
        default=MODULE_ROOT / "configs/a3_v3_source_collection_schedule_20260801.json",
    )
    parser.add_argument(
        "--global-seed-registry",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "research_modules/scalable_3d_simulation/configs/"
            "scalable_learning_global_seed_registry_v1.json"
        ),
    )
    parser.add_argument(
        "--source-generation-request",
        type=Path,
        default=(
            MODULE_ROOT
            / "configs/a3_v3_source_generation_request_20260801.json"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    readiness = validate_a3_v3_pre_generation_readiness(
        repository_root=args.repository_root,
        protocol_path=args.protocol,
        allocation_binding_path=args.allocation_binding,
        source_schedule_path=args.source_schedule,
        global_registry_path=args.global_seed_registry,
        source_generation_request_path=args.source_generation_request,
    )
    print(json.dumps(readiness.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
