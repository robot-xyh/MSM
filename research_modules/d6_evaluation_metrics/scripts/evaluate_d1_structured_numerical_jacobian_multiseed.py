#!/usr/bin/env python3
"""Run the independent D6 structured numerical Jacobian evaluator."""

from __future__ import annotations

from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d1_structured_numerical_jacobian_multiseed import (
    main,
)


if __name__ == "__main__":
    raise SystemExit(main())
