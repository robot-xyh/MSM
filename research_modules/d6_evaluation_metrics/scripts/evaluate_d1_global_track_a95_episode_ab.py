#!/usr/bin/env python3
"""CLI wrapper for the read-only D1 GlobalTrack A95 episode A/B audit."""

from __future__ import annotations

from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d1_global_track_a95_episode_ab import main


if __name__ == "__main__":
    raise SystemExit(main())
