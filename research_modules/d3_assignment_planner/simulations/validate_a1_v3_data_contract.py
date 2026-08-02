#!/usr/bin/env python3
"""Validate A1 v3 source-generation request readiness or dataset artifacts."""

from __future__ import annotations

from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d3_assignment_planner.a1_v3_data_contract import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
