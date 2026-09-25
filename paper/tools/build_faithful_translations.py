#!/usr/bin/env python3
"""Build faithful, academic Chinese translations for paper PDFs with embedded figures and LaTeX formulas.

Key enhancements over legacy translation:
1. Extracted Paper Figures: Extracts original embedded images and vector diagram crops into assets/<stem>/fig_X.png,
   embedded at caption locations. Removes old whole-page screenshots (page-*.jpg).
2. Professional LaTeX Mathematics: Restores broken equations into standard LaTeX format ($...$, $$...$$) with equation numbers.
3. Academic Paper Structure: Preserves Section hierarchy (# Title, ## Abstract, ## I. Introduction, ## II. Related Work, etc.),
   tables, algorithms, figure captions, and references.
4. Faithful Full Translation: Translates the full paper faithfully into rigorous academic Chinese.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf
from extract_paper_figures import extract_figures_for_doc

ROOT = Path(__file__).resolve().parents[2]
PAPER_DIR = ROOT / "paper"
MAIN_DIR = PAPER_DIR / "papers"
OTHER_DIR = PAPER_DIR / "other-paper"
MAIN_DETAILS = MAIN_DIR / "中文详解"
OTHER_DETAILS = OTHER_DIR / "中文详解"
MAIN_TRANS = MAIN_DIR / "中文翻译"
OTHER_TRANS = OTHER_DIR / "中文翻译"

from build_chinese_translations import OTHER_MAP


@dataclass(frozen=True)
class PaperRecord:
    source_pdf: Path
    detail_md: Path
    trans_dir: Path
    group: str  # "main" or "other"

    @property
    def stem(self) -> str:
        return self.detail_md.stem

    @property
    def output_md(self) -> Path:
        return self.trans_dir / f"{self.stem}_原文翻译.md"

    @property
    def asset_dir(self) -> Path:
        return self.trans_dir / "assets" / self.stem


def get_all_records() -> List[PaperRecord]:
    records: List[PaperRecord] = []
    
    # 1. Main papers
    for pdf in sorted(MAIN_DIR.glob("*.pdf")):
        m = re.match(r"(\d+)_", pdf.name)
        if not m:
            continue
        num = m.group(1)
        details = list(MAIN_DETAILS.glob(f"{num}_*.md"))
        if details:
            records.append(PaperRecord(
                source_pdf=pdf,
                detail_md=details[0],
                trans_dir=MAIN_TRANS,
                group="main"
            ))
            
    # 2. Other papers
    for pdf in sorted(OTHER_DIR.glob("*.pdf")):
        detail_name = OTHER_MAP.get(pdf.name)
        if detail_name:
            detail_path = OTHER_DETAILS / detail_name
            if detail_path.exists():
                records.append(PaperRecord(
                    source_pdf=pdf,
                    detail_md=detail_path,
                    trans_dir=OTHER_TRANS,
                    group="other"
                ))
                
    return records


def get_pdf_metadata(doc: pymupdf.Document) -> Dict[str, str]:
    meta = doc.metadata or {}
    title = meta.get("title", "").strip()
    author = meta.get("author", "").strip()
    if not title or len(title) < 5:
        # read first page text
        first_page = doc[0].get_text("blocks")
        for b in first_page:
            t = b[4].strip()
            if len(t) > 10 and not t.startswith(("IEEE", "arXiv", "Vol", "http")):
                title = t.split("\n")[0]
                break
    return {"title": title, "author": author}


def clean_math_text(text: str) -> str:
    """Helper to detect and convert formula-like patterns to LaTeX."""
    # Convert common unicode Greek and operators
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
        ("∓", r" \mp "),
        ("≤", r" \le "),
        ("≥", r" \ge "),
        ("≠", r" \ne "),
        ("≈", r" \approx "),
        ("∼", r" \sim "),
        ("∝", r" \propto "),
        ("∞", r" \infty "),
        ("→", r" \to "),
        ("⇒", r" \implies "),
        ("⇔", r" \iff "),
        ("∀", r" \forall "),
        ("∃", r" \exists "),
        ("α", r"\alpha"),
        ("β", r"\beta"),
        ("γ", r"\gamma"),
        ("Γ", r"\Gamma"),
        ("δ", r"\delta"),
        ("Δ", r"\Delta"),
        ("ε", r"\varepsilon"),
        ("ϵ", r"\epsilon"),
        ("ζ", r"\zeta"),
        ("η", r"\eta"),
        ("θ", r"\theta"),
        ("Θ", r"\Theta"),
        ("κ", r"\kappa"),
        ("λ", r"\lambda"),
        ("Λ", r"\Lambda"),
        ("μ", r"\mu"),
        ("ν", r"\nu"),
        ("ξ", r"\xi"),
        ("π", r"\pi"),
        ("Π", r"\Pi"),
        ("ρ", r"\rho"),
        ("σ", r"\sigma"),
        ("Σ", r"\Sigma"),
        ("τ", r"\tau"),
        ("υ", r"\upsilon"),
        ("φ", r"\phi"),
        ("ϕ", r"\phi"),
        ("Φ", r"\Phi"),
        ("χ", r"\chi"),
        ("ψ", r"\psi"),
        ("Ψ", r"\Psi"),
        ("ω", r"\omega"),
        ("Ω", r"\Omega"),
    ]
    for char, tex in replacements:
        text = text.replace(char, tex)
    return text


print("build_faithful_translations module loaded successfully.")
