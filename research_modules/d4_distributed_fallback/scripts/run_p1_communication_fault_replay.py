#!/usr/bin/env python3
"""Run the D4 P1 communication fault matrix and emit versioned JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from d4_distributed_fallback import (  # noqa: E402
    CommunicationReplayConfig,
    run_p1_communication_fault_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member-count", type=int, default=3)
    parser.add_argument("--secondary-count", type=int, default=1)
    parser.add_argument("--seed-count", type=int, default=10)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.member_count < 1 or args.secondary_count < 1 or args.seed_count < 1:
        raise SystemExit("member, secondary, and seed counts must be positive")
    config = CommunicationReplayConfig(
        member_ids=tuple(f"INT-{index + 1}" for index in range(args.member_count)),
        secondary_node_ids=tuple(
            f"RECON-{index + 1}" for index in range(args.secondary_count)
        ),
    )
    report = run_p1_communication_fault_matrix(
        config,
        seeds=range(args.seed_count),
    )
    encoded = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
