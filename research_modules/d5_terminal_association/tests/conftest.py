from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC = MODULE_ROOT / "src"
sys.path.insert(0, str(SRC))
