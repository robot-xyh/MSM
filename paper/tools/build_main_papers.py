#!/usr/bin/env python3
"""Build faithful translations for all 25 main papers with embedded figures and LaTeX math."""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "paper" / "papers"
MAIN_TRANS = MAIN_DIR / "中文翻译"
MAIN_DETAILS = MAIN_DIR / "中文详解"


def get_figures_in_asset(asset_dir: Path):
    if not asset_dir.exists():
        return {}
    res = {}
    for p in asset_dir.glob("fig_*.*"):
        m = re.search(r"fig_([0-9a-zA-Z_]+)\.", p.name)
        if m:
            res[m.group(1).upper()] = p.name
    return res


print("Main papers translation builder ready.")
