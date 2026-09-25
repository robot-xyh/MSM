#!/usr/bin/env python3
"""Automated builder for faithful academic translations of all 60 papers with embedded figures and LaTeX math."""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "paper" / "papers"
OTHER_DIR = ROOT / "paper" / "other-paper"
MAIN_TRANS = MAIN_DIR / "中文翻译"
OTHER_TRANS = OTHER_DIR / "中文翻译"
MAIN_DETAILS = MAIN_DIR / "中文详解"
OTHER_DETAILS = OTHER_DIR / "中文详解"

from build_chinese_translations import OTHER_MAP, TERM_REPLACEMENTS


def get_detail_meta(detail_path: Path) -> Dict[str, str]:
    if not detail_path.exists():
        return {"title_cn": detail_path.stem, "authors": "", "venue": ""}
    lines = detail_path.read_text(encoding="utf-8", errors="replace").splitlines()
    title_cn = detail_path.stem
    authors = ""
    venue = ""
    for line in lines:
        if line.startswith("# "):
            title_cn = line.replace("# ", "").replace("中文详解", "").replace("《", "").replace("》", "").strip()
        elif "中文题名：" in line or "题名：" in line:
            title_cn = line.split("：", 1)[1].strip()
        elif "作者：" in line:
            authors = line.split("：", 1)[1].strip()
        elif "版本：" in line or "发表：" in line:
            venue = line.split("：", 1)[1].strip()
    return {"title_cn": title_cn, "authors": authors, "venue": venue}


def get_asset_figures(asset_dir: Path) -> Dict[str, str]:
    if not asset_dir.exists():
        return {}
    res = {}
    for p in sorted(asset_dir.glob("fig_*.*")):
        m = re.search(r"fig_([0-9a-zA-Z_]+)\.", p.name)
        if m:
            res[m.group(1).upper()] = p.name
    return res


def extract_pdf_structure(pdf_path: Path) -> Dict[str, Any]:
    doc = pymupdf.open(str(pdf_path))
    pages_text = []
    figures_captions = []
    
    for pno in range(len(doc)):
        page = doc[pno]
        blocks = page.get_text("blocks")
        # sort blocks reading order: top-to-bottom, left-to-right
        blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
        p_lines = []
        for b in blocks:
            txt = b[4].strip()
            if not txt:
                continue
            # check figure captions
            m = re.match(r'^(?:Fig(?:ure|\.)?\s*(\d+[A-Za-z]?))\b[:\.]?\s*(.*)', txt, re.I | re.S)
            if m:
                fig_key = m.group(1).upper()
                figures_captions.append({
                    "fig_key": fig_key,
                    "caption": txt,
                    "pno": pno + 1
                })
            else:
                p_lines.append(txt)
        pages_text.append("\n\n".join(p_lines))
        
    return {
        "pages_text": pages_text,
        "figures_captions": figures_captions,
        "page_count": len(doc)
    }


print("Structure extractor initialized.")
