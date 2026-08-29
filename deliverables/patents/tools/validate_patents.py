#!/usr/bin/env python3
"""Run structural checks over the two Chinese patent drafts."""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATENT_DIR = ROOT / "deliverables" / "patents"
PATENTS = (
    PATENT_DIR / "基于多智能体决策的集群无人机协同反无人机系统_CN.md",
    PATENT_DIR / "基于图神经网络的双光电多目标轨迹配准与交会定位方法_CN.md",
)
REQUIRED = ("摘要", "权利要求书", "技术领域", "背景技术", "发明内容", "附图说明", "具体实施方式")


def abstract_text(text: str) -> str:
    match = re.search(r"^##?\s+摘要\s*$([\s\S]*?)(?=^##?\s+)", text, flags=re.MULTILINE)
    if not match:
        return ""
    body = re.sub(r"!\[[^]]*]\([^)]+\)", "", match.group(1))
    body = re.sub(r"[`*_>#\s]", "", body)
    return body


def claim_numbers(text: str) -> list[int]:
    match = re.search(r"^##?\s+权利要求书\s*$([\s\S]*?)(?=^##?\s+(?:说明书|技术领域))", text, flags=re.MULTILINE)
    if not match:
        return []
    return [int(value) for value in re.findall(r"^\s*(\d+)\.\s*", match.group(1), flags=re.MULTILINE)]


def validate(md_path: Path) -> list[str]:
    errors: list[str] = []
    text = md_path.read_text(encoding="utf-8")
    for heading in REQUIRED:
        if not re.search(rf"^#+\s+{re.escape(heading)}\s*$", text, flags=re.MULTILINE):
            errors.append(f"缺少章节：{heading}")
    abstract = abstract_text(text)
    if not abstract:
        errors.append("未提取到摘要")
    elif len(abstract) > 300:
        errors.append(f"摘要超过300字：{len(abstract)}")
    claims = claim_numbers(text)
    if claims != list(range(1, 16)):
        errors.append(f"权利要求编号应为1-15，实际为{claims}")
    for alt, relative in re.findall(r"!\[([^]]*)]\(([^)]+)\)", text):
        if not (md_path.parent / relative).exists():
            errors.append(f"附图缺失：{relative}（{alt}）")
    docx_path = md_path.with_suffix(".docx")
    if not docx_path.exists():
        errors.append("Word文件缺失")
    else:
        try:
            with zipfile.ZipFile(docx_path) as archive:
                names = set(archive.namelist())
                if "word/document.xml" not in names:
                    errors.append("Word主文档关系缺失")
                if not any(name.startswith("word/media/") for name in names):
                    errors.append("Word未嵌入附图")
        except zipfile.BadZipFile:
            errors.append("Word文件不是有效OOXML压缩包")
    return errors


def main() -> int:
    failed = False
    for md_path in PATENTS:
        errors = validate(md_path)
        if errors:
            failed = True
            print(f"FAIL {md_path.name}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {md_path.name}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
