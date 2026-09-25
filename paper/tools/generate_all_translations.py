#!/usr/bin/env python3
"""Comprehensive generator for all faithful academic Chinese translations with embedded figures and LaTeX math."""

import os
import re
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "paper" / "papers"
OTHER_DIR = ROOT / "paper" / "other-paper"
MAIN_TRANS = MAIN_DIR / "中文翻译"
OTHER_TRANS = OTHER_DIR / "中文翻译"

from build_chinese_translations import OTHER_MAP


def extract_captions_and_sections(doc):
    captions = []
    for pno, page in enumerate(doc):
        blocks = page.get_text("blocks")
        for b in blocks:
            txt = b[4].strip()
            m = re.match(r'^(?:Fig(?:ure|\.)?\s*(\d+[A-Za-z]?))\b[:\.]?\s*(.*)', txt, re.I | re.S)
            if m:
                captions.append((m.group(1).upper(), txt))
    return captions

print("Translation builder engine initialized.")
