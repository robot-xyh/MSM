#!/usr/bin/env python3
"""Run the isolated D3 P2 capacity benchmark and print JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d3_assignment_planner.p2_benchmark import run_p2_capacity_benchmark  # noqa: E402


def main() -> None:
    print(json.dumps(run_p2_capacity_benchmark().to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
