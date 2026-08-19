from __future__ import annotations

from docx import Document

from dual_optical_100target_gnn.build_word_report import (
    DEFAULT_DOCUMENT_TITLE,
    build_word_report,
)


def _word_title(tmp_path, markdown: str) -> str:
    source = tmp_path / "report.md"
    output = tmp_path / "report.docx"
    source.write_text(markdown, encoding="utf-8")
    build_word_report(source, output)
    return Document(output).core_properties.title


def test_original_gnn_report_keeps_its_markdown_title(tmp_path):
    title = _word_title(
        tmp_path,
        "# 双站光电100目标图网络关联试验\n\n## 结论\n\n正文。\n",
    )
    assert title == "双站光电100目标图网络关联试验"


def test_summary_report_uses_its_own_first_level_one_title(tmp_path):
    title = _word_title(
        tmp_path,
        "## 编制说明\n\n# 双站光电40与100目标轨迹配准实验汇总 ###\n\n正文。\n",
    )
    assert title == "双站光电40与100目标轨迹配准实验汇总"


def test_missing_level_one_title_uses_safe_default_and_ignores_code_fence(tmp_path):
    title = _word_title(
        tmp_path,
        "## 说明\n\n```markdown\n# 代码示例标题\n```\n\n正文。\n",
    )
    assert title == DEFAULT_DOCUMENT_TITLE
