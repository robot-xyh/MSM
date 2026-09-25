#!/usr/bin/env python3
"""Run structural and native-equation checks over the patent drafts."""

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
LATEX_RESIDUALS = ("$$", r"\frac", r"\boldsymbol", r"\operatorname", r"\begin{")


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


def markdown_formula_count(text: str) -> int:
    """Count display and inline TeX expressions represented in Markdown."""
    display_pattern = re.compile(r"(?<!\\)\$\$(.*?)(?<!\\)\$\$", flags=re.DOTALL)
    display_count = len(display_pattern.findall(text))
    without_display = display_pattern.sub("", text)
    inline_pattern = re.compile(
        r"(?<![\\$])\$(?!\$)(.+?)(?<!\\)\$(?!\$)",
        flags=re.DOTALL,
    )
    return display_count + len(inline_pattern.findall(without_display))


def inspect_docx(docx_path: Path) -> tuple[int, int, str]:
    with zipfile.ZipFile(docx_path) as archive:
        names = set(archive.namelist())
        if "word/document.xml" not in names:
            return 0, 0, ""
        document_xml = archive.read("word/document.xml").decode("utf-8")
        equation_count = len(re.findall(r"<m:oMath(?:\s|>)", document_xml))
        media_count = len(
            [
                name
                for name in names
                if name.startswith("word/media/") and not name.endswith("/")
            ]
        )
        return equation_count, media_count, document_xml


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
    image_references = re.findall(r"!\[([^]]*)]\(([^)]+)\)", text)
    for alt, relative in image_references:
        if not (md_path.parent / relative).exists():
            errors.append(f"附图缺失：{relative}（{alt}）")
    expected_equations = markdown_formula_count(text)
    expected_media = len(image_references)
    docx_path = md_path.with_suffix(".docx")
    if not docx_path.exists():
        errors.append("Word文件缺失")
    else:
        try:
            with zipfile.ZipFile(docx_path) as archive:
                names = set(archive.namelist())
                if "word/document.xml" not in names:
                    errors.append("Word主文档关系缺失")
                settings_xml = (
                    archive.read("word/settings.xml").decode("utf-8")
                    if "word/settings.xml" in names
                    else ""
                )
            equation_count, media_count, document_xml = inspect_docx(docx_path)
            if equation_count < expected_equations:
                errors.append(
                    "Word原生公式数量不足："
                    f"Markdown={expected_equations}，OMML={equation_count}"
                )
            if media_count != expected_media:
                errors.append(
                    f"Word嵌入附图数量不符：Markdown={expected_media}，Word={media_count}"
                )
            for residual in LATEX_RESIDUALS:
                if residual in document_xml:
                    errors.append(f"Word正文仍有未转换的LaTeX标记：{residual}")
            if "w:doNotExpandShiftReturn" not in settings_xml:
                errors.append("Word未设置手动换行行末禁止扩展字距")
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
            equations, media, _ = inspect_docx(md_path.with_suffix(".docx"))
            print(f"PASS {md_path.name}（OMML公式{equations}个，附图{media}幅）")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
