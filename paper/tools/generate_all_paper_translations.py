#!/usr/bin/env python3
"""Automated builder for all 60 academic Chinese paper translations with embedded figures and LaTeX math."""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
MAIN_DIR = ROOT / "paper" / "papers"
OTHER_DIR = ROOT / "paper" / "other-paper"
MAIN_TRANS = MAIN_DIR / "中文翻译"
OTHER_TRANS = OTHER_DIR / "中文翻译"
MAIN_DETAILS = MAIN_DIR / "中文详解"
OTHER_DETAILS = OTHER_DIR / "中文详解"

from build_chinese_translations import OTHER_MAP, TERM_REPLACEMENTS


def get_detail_metadata(detail_path: Path) -> Dict[str, str]:
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


def get_asset_figs(asset_dir: Path) -> Dict[str, str]:
    if not asset_dir.exists():
        return {}
    res = {}
    for p in sorted(asset_dir.glob("fig_*.*")):
        m = re.search(r"fig_([0-9a-zA-Z_]+)\.", p.name)
        if m:
            res[m.group(1).upper()] = p.name
    return res


def extract_pdf_info(pdf_path: Path) -> Dict[str, Any]:
    doc = pymupdf.open(str(pdf_path))
    captions = {}
    pages_text = []
    
    for pno in range(len(doc)):
        page = doc[pno]
        blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
        p_txt = []
        for b in blocks:
            txt = b[4].strip()
            if not txt:
                continue
            m = re.match(r'^(?:Fig(?:ure|\.)?\s*(\d+[A-Za-z]?))\b[:\.]?\s*(.*)', txt, re.I | re.S)
            if m:
                fig_key = m.group(1).upper()
                if fig_key not in captions or len(txt) > len(captions[fig_key]['text']):
                    captions[fig_key] = {
                        'text': txt,
                        'pno': pno + 1
                    }
            else:
                p_txt.append(txt)
        pages_text.append("\n\n".join(p_txt))
        
    return {
        "doc": doc,
        "captions": captions,
        "pages_text": pages_text,
        "page_count": len(doc)
    }


def clean_and_normalize(text: str) -> str:
    text = text.replace('\r', '').replace('\u00ad', '')
    text = re.sub(r'(?<=[A-Za-z])-[ \t]*\n[ \t]*(?=[a-z])', '', text)
    for src, dst in TERM_REPLACEMENTS:
        text = text.replace(src, dst)
    return text.strip()


print("generate_all_paper_translations loaded.")
