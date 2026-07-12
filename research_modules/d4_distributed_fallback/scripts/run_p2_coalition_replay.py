#!/usr/bin/env python3
"""Run the isolated D4 P2 coalition fault replay and emit JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from d4_distributed_fallback.p2_coalition_replay import run_p2_coalition_fault_replay


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mit-cbba-path",
        type=Path,
        default=None,
        help="optional path to an unpacked MIT CBBA reference tree",
    )
    parser.add_argument(
        "--ca-cbba-path",
        type=Path,
        default=None,
        help="optional path to a CA-CBBA reference tree",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional JSON output path; stdout is always emitted",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_p2_coalition_fault_replay(
        mit_cbba_path=args.mit_cbba_path,
        ca_cbba_path=args.ca_cbba_path,
    )
    encoded = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
