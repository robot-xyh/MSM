#!/usr/bin/env python3
"""Build all 60 faithful academic Chinese paper translations with embedded figures and LaTeX math."""

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


def get_detail_info(detail_path: Path) -> Dict[str, str]:
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


def extract_pdf_sections(pdf_path: Path):
    doc = pymupdf.open(str(pdf_path))
    captions = {}
    pages_text = []
    
    for pno in range(len(doc)):
        page = doc[pno]
        blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
        p_lines = []
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
                p_lines.append(txt)
        pages_text.append("\n\n".join(p_lines))
        
    return doc, captions, pages_text


def format_latex(text: str) -> str:
    # Convert unicode math symbols
    replacements = [
        ("∑", r"\sum "),
        ("∫", r"\int "),
        ("∂", r"\partial "),
        ("∇", r"\nabla "),
        ("∈", r" \in "),
        ("∉", r" \notin "),
        ("⊆", r" \subseteq "),
        ("⊂", r" \subset "),
        ("∪", r" \cup "),
        ("∩", r" \cap "),
        ("×", r" \times "),
        ("⊗", r" \otimes "),
        ("⊕", r" \oplus "),
        ("±", r" \pm "),
        ("≤", r" \le "),
        ("≥", r" \ge "),
        ("≠", r" \ne "),
        ("≈", r" \approx "),
        ("∼", r" \sim "),
        ("∝", r" \propto "),
        ("∞", r" \infty "),
        ("→", r" \to "),
        ("⇒", r" \implies "),
        ("∀", r" \forall "),
        ("∃", r" \exists "),
        ("α", r"\alpha"),
        ("β", r"\beta"),
        ("γ", r"\gamma"),
        ("δ", r"\delta"),
        ("Δ", r"\Delta"),
        ("ε", r"\varepsilon"),
        ("θ", r"\theta"),
        ("Θ", r"\Theta"),
        ("λ", r"\lambda"),
        ("Λ", r"\Lambda"),
        ("μ", r"\mu"),
        ("π", r"\pi"),
        ("σ", r"\sigma"),
        ("Σ", r"\Sigma"),
        ("τ", r"\tau"),
        ("ω", r"\omega"),
        ("Ω", r"\Omega"),
    ]
    for char, tex in replacements:
        text = text.replace(char, tex)
    return text


print("build_all_faithful_translations_pipeline loaded.")
