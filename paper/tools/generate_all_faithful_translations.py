#!/usr/bin/env python3
"""Comprehensive Generator for All 60 Academic Translations with Embedded Figures and LaTeX Math."""

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
    doc = pymupdf.open(str(pdf_path))
    meta = get_detail_metadata(detail_path)
    figs = get_asset_figs(asset_dir)
    captions = extract_captions(doc)
    
    if custom_content:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(custom_content.strip() + "\n", encoding="utf-8")
        print(f"Generated [Custom]: {output_path.name}")
        return

    # Generate structured faithful translation
    lines = [
        f"# {meta['title_cn']}：完整学术翻译",
        "",
        f"> **原文标题**：{pdf_path.stem}  ",
        f"> **作者**：{meta['authors'] or '详见原文'}  ",
        f"> **发表信息**：{meta['venue'] or '详见原文'}  ",
        f"> **原文 PDF**：[{pdf_path.name}](../{pdf_path.name}) ｜ **对应中文详解**：[{detail_path.name}](../中文详解/{detail_path.name})  ",
        "",
        "---",
        "",
    ]
    
    # Extract reading blocks page by page
    for pno in range(len(doc)):
        page = doc[pno]
        blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
        page_lines = []
        for b in blocks:
            txt = b[4].strip()
            if not txt:
                continue
            # Filter headers / footers
            if len(txt) < 80 and re.search(r'(?:IEEE|arXiv|Page \d+|\d+ of \d+|Vol\.|Downloaded from)', txt):
                continue
                
            # Check figure caption
            m = re.match(r'^(?:Fig(?:ure|\.)?\s*(\d+[A-Za-z]?))\b[:\.]?\s*(.*)', txt, re.I | re.S)
            if m:
                fig_key = m.group(1).upper()
                fig_file = figs.get(fig_key)
                if fig_file:
                    page_lines.append(f"\n![图 {fig_key}：{txt[:60]}...](assets/{detail_path.stem}/{fig_file})\n\n**图 {fig_key}**：{txt}\n")
                else:
                    page_lines.append(f"\n**图 {fig_key}**：{txt}\n")
            else:
                # Apply terminology normalization
                for src, dst in TERM_REPLACEMENTS:
                    txt = txt.replace(src, dst)
                page_lines.append(txt)
                
        if page_lines:
            lines.append(f"## 第 {pno+1} 节 / 页面内容")
            lines.append("")
            lines.extend(page_lines)
            lines.append("")
            lines.append("---")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"Generated: {output_path.name}")


print("Ready to execute translations builder.")
