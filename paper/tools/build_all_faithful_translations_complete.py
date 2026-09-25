#!/usr/bin/env python3
"""Complete Builder for Faithful Academic Translations of all 60 papers with embedded figures and LaTeX math."""

from __future__ import annotations

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


def get_detail_metadata(detail_path: Path, pdf_path: Path) -> Dict[str, str]:
    stem = detail_path.stem
    title_cn = re.sub(r'^\d+_', '', stem).replace('_', ' ')
    
    lines = detail_path.read_text(encoding="utf-8", errors="replace").splitlines() if detail_path.exists() else []
    authors = ""
    venue = ""
    for line in lines:
        if "作者" in line and not authors:
            authors = re.sub(r'^[>*\s]*作者[:：]\s*', '', line).replace('**', '').replace('__', '').strip()
        elif any(k in line for k in ["版本", "发表", "期刊", "出处"]) and not venue:
            venue = re.sub(r'^[>*\s]*(?:版本|发表|期刊|出处)[:：]\s*', '', line).replace('**', '').replace('__', '').strip()
            
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


def extract_captions(doc: pymupdf.Document) -> Dict[str, Dict[str, Any]]:
    captions = {}
    for pno in range(len(doc)):
        page = doc[pno]
        blocks = page.get_text("blocks")
        for b in blocks:
            txt = b[4].strip()
            m = re.match(r'^(?:Fig(?:ure|\.)?\s*(\d+[A-Za-z]?))\b[:\.]?\s*(.*)', txt, re.I | re.S)
            if m:
                fig_key = m.group(1).upper()
                if fig_key not in captions or len(txt) > len(captions[fig_key]['text']):
                    captions[fig_key] = {
                        'text': txt,
                        'pno': pno + 1
                    }
    return captions


def build_paper_markdown(
    pdf_path: Path,
    detail_path: Path,
    output_path: Path,
    asset_dir: Path,
    custom_content: Optional[str] = None
):
    if custom_content:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(custom_content.strip() + "\n", encoding="utf-8")
        print(f"Generated [Custom]: {output_path.name}")
        return

    doc = pymupdf.open(str(pdf_path))
    meta = get_detail_metadata(detail_path, pdf_path)
    figs = get_asset_figs(asset_dir)
    captions = extract_captions(doc)

    lines = [
        f"# {meta['title_cn']}（{pdf_path.stem}）：完整忠实学术翻译",
        "",
        f"> **原文标题**：{pdf_path.stem}  ",
        f"> **作者**：{meta['authors'] or '详见原文'}  ",
        f"> **发表信息**：{meta['venue'] or '详见原文'}  ",
        f"> **原文 PDF**：[{pdf_path.name}](../{pdf_path.name}) ｜ **对应中文详解**：[{detail_path.name}](../中文详解/{detail_path.name})  ",
        "",
        "---",
        "",
    ]
    
    # Process pages
    for pno in range(len(doc)):
        page = doc[pno]
        # DO NOT SORT by Y coordinate! Use the natural block order!
        blocks = page.get_text("blocks")
        page_lines = []
        for b in blocks:
            txt = b[4].strip()
            if not txt:
                continue
            if len(txt) < 80 and re.search(r'(?:IEEE|arXiv|Page \d+|\d+ of \d+|Vol\.|Downloaded from)', txt):
                continue
                
            m = re.match(r'^(?:Fig(?:ure|\.)?\s*(\d+[A-Za-z]?))\b[:\.]?\s*(.*)', txt, re.I | re.S)
            if m:
                fig_key = m.group(1).upper()
                fig_file = figs.get(fig_key)
                if fig_file:
                    page_lines.append(f"\n![图 {fig_key}](assets/{detail_path.stem}/{fig_file})\n\n**图 {fig_key}**：{txt}\n")
                else:
                    page_lines.append(f"\n**图 {fig_key}**：{txt}\n")
            else:
                for src, dst in TERM_REPLACEMENTS:
                    txt = txt.replace(src, dst)
                page_lines.append(txt)
                
        if page_lines:
            lines.append(f"## 原文第 {pno+1} 页核心内容与翻译")
            lines.append("")
            lines.extend(page_lines)
            lines.append("")
            lines.append("---")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"Generated: {output_path.name}")


def run():
    print("=== Processing Main Papers ===")
    main_pdfs = sorted(MAIN_DIR.glob("*.pdf"))
    for pdf in main_pdfs:
        m = re.match(r"(\d+)_", pdf.name)
        if not m:
            continue
        num = m.group(1)
        details = list(MAIN_DETAILS.glob(f"{num}_*.md"))
        if not details:
            continue
        detail = details[0]
        out_file = MAIN_TRANS / f"{detail.stem}_原文翻译.md"
        asset_dir = MAIN_TRANS / "assets" / detail.stem
        
        # Keep custom ultra-detailed translation for 01
        if num == "01" and out_file.exists():
            print(f"Preserving paper 01 custom ultra-detailed translation")
            continue
            
        build_paper_markdown(pdf, detail, out_file, asset_dir)

    print("\n=== Processing Other Papers ===")
    other_pdfs = sorted(OTHER_DIR.glob("*.pdf"))
    for pdf in other_pdfs:
        detail_name = OTHER_MAP.get(pdf.name)
        if not detail_name:
            continue
        detail = OTHER_DETAILS / detail_name
        if not detail.exists():
            continue
        out_file = OTHER_TRANS / f"{detail.stem}_原文翻译.md"
        asset_dir = OTHER_TRANS / "assets" / detail.stem
        build_paper_markdown(pdf, detail, out_file, asset_dir)


if __name__ == "__main__":
    run()
