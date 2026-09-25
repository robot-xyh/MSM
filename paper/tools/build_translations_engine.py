#!/usr/bin/env python3
"""Build faithful academic translations for papers with embedded figures and LaTeX formulas."""

import os
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "paper" / "papers"
OTHER_DIR = ROOT / "paper" / "other-paper"
MAIN_TRANS = MAIN_DIR / "中文翻译"
OTHER_TRANS = OTHER_DIR / "中文翻译"


def write_doc(target_path: Path, content: str):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"Successfully generated: {target_path.name}")

print("build_translations_engine module loaded.")
