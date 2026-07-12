#!/usr/bin/env python3
"""Write the D5 deterministic P1 visual robustness summary JSON."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d5_terminal_association import write_p1_visual_robustness_summary  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    path = write_p1_visual_robustness_summary(args.output)
    print(f"d5_summary={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
