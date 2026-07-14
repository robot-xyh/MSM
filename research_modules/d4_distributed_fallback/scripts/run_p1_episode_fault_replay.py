#!/usr/bin/env python3
"""Emit the D4 P1 episode-time fault-injection matrix as JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from d4_distributed_fallback import (  # noqa: E402
    EpisodeCommunicationConfig,
    run_p1_episode_fault_validation_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member-count", type=int, default=3)
    parser.add_argument("--secondary-count", type=int, default=1)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.member_count < 1 or args.secondary_count < 1:
        raise SystemExit("member-count and secondary-count must be positive")
    config = EpisodeCommunicationConfig(
        member_ids=tuple(f"INT-{index + 1}" for index in range(args.member_count)),
        secondary_node_ids=tuple(
            f"RECON-{index + 1}" for index in range(args.secondary_count)
        ),
    )
    payload = run_p1_episode_fault_validation_matrix(config=config).to_dict()
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
