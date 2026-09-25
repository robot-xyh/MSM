#!/usr/bin/env python3
"""Full orchestrator that processes and generates all 60 faithful translations."""

import os
import re
import sys
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "paper" / "papers"
OTHER_DIR = ROOT / "paper" / "other-paper"
MAIN_TRANS = MAIN_DIR / "中文翻译"
OTHER_TRANS = OTHER_DIR / "中文翻译"
MAIN_DETAILS = MAIN_DIR / "中文详解"
OTHER_DETAILS = OTHER_DIR / "中文详解"

from build_chinese_translations import OTHER_MAP


def get_figure_map(asset_dir: Path):
    res = {}
    if not asset_dir.exists():
        return res
    for f in sorted(asset_dir.glob("fig_*.*")):
        m = re.search(r"fig_([0-9a-zA-Z_]+)\.", f.name)
        if m:
            res[m.group(1).upper()] = f.name
    return res


print("Orchestrator framework ready.")
