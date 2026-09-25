#!/usr/bin/env python3
"""Build faithful translations for all 25 main papers with embedded figures and LaTeX math."""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "paper" / "papers"
MAIN_TRANS = MAIN_DIR / "中文翻译"


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"Generated: {path.name} ({len(content)} chars)")


# We already generated 01_释放四旋翼特技飞行潜能_原文翻译.md.
# Let's generate 02 to 29.

print("Generating main papers...")
