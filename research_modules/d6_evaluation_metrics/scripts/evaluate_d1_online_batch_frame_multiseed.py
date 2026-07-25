#!/usr/bin/env python3
"""Evaluate the frozen D1 online batch-frame handoff matrix."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.d6_evaluation_metrics.d6_evaluation_metrics.d1_online_batch_frame_multiseed import (  # noqa: E402
    main,
)


if __name__ == "__main__":
    raise SystemExit(main())
