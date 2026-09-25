#!/usr/bin/env python3
"""Update indexes for Chinese translations."""

import os
import re
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


def update_main_readme():
    index_path = MAIN_TRANS / "README.md"
    lines = [
        "# 主论文中文翻译索引",
        "",
        "> 本目录收录 MSM 项目主论文库（25 篇）的高质量忠实中文学术翻译。",
        "> 每篇译文均已重构：",
        "> 1. **插入论文原始高清插图**（保存在各 `assets/` 目录中的 `fig_X.png`，不再使用整页 PDF 截图）；",
        "> 2. **标准 LaTeX 公式排版**（修复公式断裂问题，保留严谨数学符号与编号）；",
        "> 3. **完整忠实学术翻译**（涵盖摘要、引言、相关工作、系统架构、方法推导、实验对比与结论）。",
        "",
        "| 序号 | 英文原始论文 | 中文忠实译文 | 对应中文详解 | 页数 | 插图数 |",
        "|---:|---|---|---|---:|---:|",
    ]
    
    pdfs = sorted(MAIN_DIR.glob("*.pdf"))
    count = 0
    for pdf in pdfs:
        m = re.match(r"(\d+)_", pdf.name)
        if not m:
            continue
        num = m.group(1)
        details = list(MAIN_DETAILS.glob(f"{num}_*.md"))
        if not details:
            continue
        detail = details[0]
        count += 1
        doc = pymupdf.open(str(pdf))
        pcount = len(doc)
        trans_file = MAIN_TRANS / f"{detail.stem}_原文翻译.md"
        asset_dir = MAIN_TRANS / "assets" / detail.stem
        fig_count = len(list(asset_dir.glob("fig_*.*"))) if asset_dir.exists() else 0
        
        trans_link = f"[{trans_file.name}]({trans_file.name})" if trans_file.exists() else "待处理"
        pdf_link = f"[{pdf.name}](../{pdf.name})"
        detail_link = f"[{detail.name}](../中文详解/{detail.name})"
        
        lines.append(f"| {count} | {pdf_link} | {trans_link} | {detail_link} | {pcount} | {fig_count} |")
        
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Updated {index_path.name} ({count} papers)")


def update_other_readme():
    index_path = OTHER_TRANS / "README.md"
    lines = [
        "# 扩展论文中文翻译索引",
        "",
        "> 本目录收录 MSM 项目扩展论文库（35 篇）的高质量忠实中文学术翻译。",
        "> 每篇译文均已重构：",
        "> 1. **插入论文原始插图与矢量图裁剪**（保存在各 `assets/` 目录中的 `fig_X.png`，不再使用整页 PDF 截图）；",
        "> 2. **标准 LaTeX 公式排版**（修复公式断裂问题，保留严谨数学符号与编号）；",
        "> 3. **完整忠实学术翻译**（涵盖摘要、引言、相关工作、方法推导、实验对比与结论）。",
        "",
        "| 序号 | 英文原始论文 | 中文忠实译文 | 对应中文详解 | 页数 | 插图数 |",
        "|---:|---|---|---|---:|---:|",
    ]
    
    pdfs = sorted(OTHER_DIR.glob("*.pdf"))
    count = 0
    for pdf in pdfs:
        detail_name = OTHER_MAP.get(pdf.name)
        if not detail_name:
            continue
        detail = OTHER_DETAILS / detail_name
        if not detail.exists():
            continue
        count += 1
        doc = pymupdf.open(str(pdf))
        pcount = len(doc)
        trans_file = OTHER_TRANS / f"{detail.stem}_原文翻译.md"
        asset_dir = OTHER_TRANS / "assets" / detail.stem
        fig_count = len(list(asset_dir.glob("fig_*.*"))) if asset_dir.exists() else 0
        
        trans_link = f"[{trans_file.name}]({trans_file.name})" if trans_file.exists() else "待处理"
        pdf_link = f"[{pdf.name}](../{pdf.name})"
        detail_link = f"[{detail.name}](../中文详解/{detail.name})"
        
        lines.append(f"| {count} | {pdf_link} | {trans_link} | {detail_link} | {pcount} | {fig_count} |")
        
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Updated {index_path.name} ({count} papers)")


if __name__ == "__main__":
    update_main_readme()
    update_other_readme()
