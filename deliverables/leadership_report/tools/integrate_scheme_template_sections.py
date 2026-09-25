#!/usr/bin/env python3
"""Integrate reviewed sections 4.1, 4.4 and 4.5 into the scheme template.

The script treats the current template as an in-place editing target. It backs up
the input first, replaces only the three requested body ranges, and verifies that
all other body nodes, headers, footers, package parts and existing media remain
unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / "deliverables/leadership_report"
DEFAULT_DOCUMENT = REPORT_DIR / "方案模板.docx"
DUAL_REPORT = REPORT_DIR / "双光电多目标轨迹配准与交汇定位试验报告_CN.md"
DUAL_EVIDENCE = REPORT_DIR / "双光电多目标轨迹配准与交汇定位试验报告_EVIDENCE.json"
SEARCH_REPORT = REPORT_DIR / "协同搜索试验报告_CN.md"
TERMINAL_REPORT = REPORT_DIR / "末端目标配准试验报告_CN.md"
DUAL_ASSETS = REPORT_DIR / "assets/dual_optical_registration_report"
TERMINAL_ASSETS = REPORT_DIR / "assets/center_terminal_split_reports"
SCHEME_ASSETS = REPORT_DIR / "assets/scheme_template_material"

EXPECTED_ORIGINAL_SHA256 = "977df2dc530d153dfd370744b5768e950ef27ea4884c2af5487f065b429d046d"
BACKUP_DIR = Path("/tmp/MSM_scheme_template_backups")

BODY_FONT = "仿宋"
HEADING_FONT = "黑体"
CAPTION_FONT = "楷体"

CONDITION_ORDER = {"clean": 0, "light": 1, "medium": 2, "heavy": 3}
CONDITION_LABEL = {
    "clean": "无附加漏检虚警",
    "light": "轻度干扰",
    "medium": "中度干扰",
    "heavy": "重度干扰",
}
ROUTE_ORDER = {"epipolar_mht": 0, "gnn": 1}
ROUTE_LABEL = {"epipolar_mht": "几何方法", "gnn": "图神经网络"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percent(value: float) -> str:
    return f"{100.0 * float(value):.1f}%"


def milliseconds(value: float) -> str:
    return f"{float(value):.1f}毫秒"


def find_paragraph(document: Document, prefix: str):
    matches = [p for p in document.paragraphs if p.text.strip().startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one paragraph starting with {prefix!r}, found {len(matches)}")
    return matches[0]


def find_numbered_heading(document: Document, number: str):
    matches = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text.strip() == number or paragraph.text.strip().startswith(number + " ")
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one heading numbered {number!r}, found {len(matches)}")
    return matches[0]


def target_boundaries(document: Document):
    return (
        (find_paragraph(document, "4.1 侦察的想法"), find_paragraph(document, "4.2 火指控的想法")),
        (find_paragraph(document, "4.4 拦截区域搜索"), find_paragraph(document, "4.5 群对群目标配准")),
        (find_paragraph(document, "4.5 群对群目标配准"), find_paragraph(document, "4.3.6 主动降级与分级目标分配")),
    )


def update_structural_digest(digest, element) -> None:
    """Hash XML structure without depending on namespace prefix serialization."""

    digest.update(b"<")
    digest.update(element.tag.encode("utf-8"))
    for name, value in sorted(element.attrib.items()):
        digest.update(b"|")
        digest.update(name.encode("utf-8"))
        digest.update(b"=")
        digest.update(value.encode("utf-8"))
    digest.update(b">")
    if element.text:
        digest.update(element.text.encode("utf-8"))
    for child in element:
        update_structural_digest(digest, child)
        if child.tail:
            digest.update(child.tail.encode("utf-8"))
    digest.update(b"</")
    digest.update(element.tag.encode("utf-8"))
    digest.update(b">")


def outside_target_hash(document: Document) -> str:
    """Hash every body node outside sections 4.1, 4.4 and 4.5."""

    body = document._element.body
    excluded: set[int] = set()
    for start, end in target_boundaries(document):
        start_index = body.index(start._p)
        end_index = body.index(end._p)
        excluded.update(range(start_index + 1, end_index))

    digest = hashlib.sha256()
    for index, element in enumerate(body.iterchildren()):
        if index not in excluded:
            update_structural_digest(digest, element)
    return digest.hexdigest()


def target_text(document: Document, start_prefix: str, end_prefix: str) -> str:
    start = find_paragraph(document, start_prefix)
    end = find_paragraph(document, end_prefix)
    body = document._element.body
    start_index = body.index(start._p)
    end_index = body.index(end._p)
    parts: list[str] = []
    for element in list(body.iterchildren())[start_index + 1 : end_index]:
        parts.extend(element.xpath(".//w:t/text()"))
    return "".join(parts)


def remove_between(start_paragraph, end_paragraph) -> None:
    node = start_paragraph._p.getnext()
    while node is not None and node is not end_paragraph._p:
        next_node = node.getnext()
        node.getparent().remove(node)
        node = next_node
    if node is None:
        raise RuntimeError("section boundary was not found in the document body")


def style_samples(document: Document):
    styles = {style.name: style for style in document.styles}
    required = ("Normal", "Heading 3", "Heading 4")
    missing = [name for name in required if name not in styles]
    if missing:
        raise RuntimeError(f"missing paragraph styles: {missing}")
    return styles


def package_hashes(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            result[name] = hashlib.sha256(archive.read(name)).hexdigest()
    return result


def verify_package_preservation(before: dict[str, str], after: dict[str, str]) -> dict[str, object]:
    """Allow document body/relationships and new media, but preserve all old parts."""

    allowed_changed = {
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "[Content_Types].xml",
        "docProps/core.xml",
    }
    preserved_parts = 0
    for name, old_hash in before.items():
        if name in allowed_changed:
            continue
        if name not in after:
            raise RuntimeError(f"package part disappeared: {name}")
        if after[name] != old_hash:
            raise RuntimeError(f"unrelated package part changed: {name}")
        preserved_parts += 1

    old_media = {name for name in before if name.startswith("word/media/")}
    new_media = {name for name in after if name.startswith("word/media/")}
    missing_media = sorted(old_media - new_media)
    if missing_media:
        raise RuntimeError(f"existing media disappeared: {missing_media}")
    changed_media = sorted(name for name in old_media if before[name] != after[name])
    if changed_media:
        raise RuntimeError(f"existing media changed: {changed_media}")

    header_footer = sorted(
        name
        for name in before
        if name.startswith("word/header") or name.startswith("word/footer")
    )
    return {
        "preserved_part_count": preserved_parts,
        "header_footer_count": len(header_footer),
        "existing_media_count": len(old_media),
        "new_media_count": len(new_media - old_media),
        "new_media_parts": sorted(new_media - old_media),
    }


def markdown_table(path: Path, header: Sequence[str]) -> list[list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    expected = "| " + " | ".join(header) + " |"
    starts = [index for index, line in enumerate(lines) if line.strip() == expected]
    if len(starts) != 1:
        raise RuntimeError(f"expected one table {header!r} in {path.name}, found {len(starts)}")
    rows: list[list[str]] = []
    for line in lines[starts[0] + 2 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != len(header):
            raise RuntimeError(f"malformed table row in {path.name}: {line}")
        rows.append(cells)
    if not rows:
        raise RuntimeError(f"table {header!r} in {path.name} is empty")
    return rows


def verify_reviewed_sources() -> dict[str, object]:
    required = {
        DUAL_REPORT: (
            "本次结果全部来自`report_replay_20260819_v2`确定性离线复算",
            "### 3.1 360度理想单站条件",
            "### 3.2 360度实际单站航迹",
            "### 3.3 180度扫描",
            "当前主要卡点是单站航迹连续性",
        ),
        SEARCH_REPORT: (
            "中心线索精度和召回率均设为100%",
            "不设置错误线索、重复线索、漏检目标和空白走廊",
            "3个规模×3个误差档×5个seed，共45组",
            "没有重新启动AirSim",
        ),
        TERMINAL_REPORT: (
            "p_C = R_C^G R_G^B R_B^N (p_N - o_C^N)",
            "### 2.2 图网络参数诊断",
            "### 2.3 五项评价",
            "当前证据不支持用同一组择优参数替换稀疏几何默认路径",
        ),
    }
    for path, markers in required.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        content = path.read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in content]
        if missing:
            raise RuntimeError(f"reviewed source changed: {path.name}; missing {missing}")

    with DUAL_EVIDENCE.open(encoding="utf-8") as stream:
        evidence = json.load(stream)
    if evidence.get("schema_version") != "dual-optical-leadership-report-evidence-v6":
        raise RuntimeError("unexpected dual-optical evidence schema")
    completeness = evidence.get("matrix_completeness", {})
    expected_counts = {
        "complete": True,
        "continuous_360_group_count": 24,
        "oracle_360_group_count": 6,
        "s180_group_count": 24,
        "seed_count_per_group": 5,
        "total_group_count": 54,
    }
    if any(completeness.get(key) != value for key, value in expected_counts.items()):
        raise RuntimeError(f"dual-optical evidence matrix is incomplete: {completeness}")
    if len(evidence.get("matrix_summary_rows", [])) != 54:
        raise RuntimeError("dual-optical evidence must contain 54 summary rows")
    return evidence


class SectionWriter:
    def __init__(self, document: Document, anchor, styles):
        self.document = document
        self.anchor = anchor
        self.styles = styles

    def _place(self, element) -> None:
        self.anchor._p.addprevious(element)

    def paragraph(
        self,
        text: str,
        *,
        style: str = "Normal",
        align: WD_ALIGN_PARAGRAPH | None = None,
        first_line: bool = True,
        keep_with_next: bool = False,
    ):
        paragraph = self.document.add_paragraph()
        paragraph.style = self.styles[style]
        paragraph.add_run(text)
        paragraph.alignment = align if align is not None else WD_ALIGN_PARAGRAPH.JUSTIFY
        paragraph.paragraph_format.line_spacing = Pt(25)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.first_line_indent = Pt(28) if first_line and style == "Normal" else Pt(0)
        paragraph.paragraph_format.keep_with_next = keep_with_next
        for run in paragraph.runs:
            font = HEADING_FONT if style.startswith("Heading") else BODY_FONT
            run.font.name = font
            run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), font)
            run.font.size = Pt(14)
        self._place(paragraph._p)
        return paragraph

    def heading(self, text: str, level: int = 3):
        style = "Heading 3" if level == 3 else "Heading 4"
        paragraph = self.paragraph(
            text,
            style=style,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            first_line=False,
            keep_with_next=True,
        )
        for run in paragraph.runs:
            run.bold = level == 3
        paragraph.paragraph_format.space_before = Pt(8 if level == 3 else 4)
        paragraph.paragraph_format.space_after = Pt(2)
        return paragraph

    def formula(self, text: str):
        paragraph = self.document.add_paragraph()
        paragraph.style = self.styles["Normal"]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.line_spacing = Pt(22)
        paragraph.paragraph_format.space_before = Pt(2)
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(text)
        run.font.name = "Cambria Math"
        run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Cambria Math")
        run.font.size = Pt(12)
        self._place(paragraph._p)
        return paragraph

    def image(self, path: Path, caption: str, *, width: float = 5.9) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        paragraph = self.document.add_paragraph()
        paragraph.style = self.styles["Normal"]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(4)
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.paragraph_format.keep_with_next = True
        paragraph.add_run().add_picture(str(path), width=Inches(width))
        self._place(paragraph._p)
        self.caption(caption)

    def caption(self, text: str) -> None:
        paragraph = self.document.add_paragraph()
        paragraph.style = self.styles["Normal"]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.line_spacing = Pt(19)
        paragraph.paragraph_format.space_after = Pt(4)
        paragraph.paragraph_format.first_line_indent = Pt(0)
        run = paragraph.add_run(text)
        run.font.name = CAPTION_FONT
        run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), CAPTION_FONT)
        run.font.size = Pt(10.5)
        self._place(paragraph._p)

    def table(
        self,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
        *,
        widths: Sequence[float] | None = None,
        font_size: float = 8.2,
    ):
        row_data = [list(map(str, row)) for row in rows]
        table = self.document.add_table(rows=1, cols=len(headers))
        table.autofit = False
        table.alignment = 1
        self._set_table_borders(table)
        for column, value in enumerate(headers):
            self._set_cell(table.rows[0].cells[column], value, header=True, font_size=font_size)
        for values in row_data:
            if len(values) != len(headers):
                raise ValueError(f"table row has {len(values)} cells, expected {len(headers)}")
            cells = table.add_row().cells
            for column, value in enumerate(values):
                self._set_cell(cells[column], value, header=False, font_size=font_size)
        if widths:
            for row in table.rows:
                for column, width in enumerate(widths):
                    row.cells[column].width = Inches(width)
        for row in table.rows:
            self._prevent_row_split(row)
        self._repeat_header(table.rows[0])
        self._place(table._tbl)
        spacer = self.document.add_paragraph()
        spacer.style = self.styles["Normal"]
        spacer.paragraph_format.space_after = Pt(2)
        spacer.paragraph_format.line_spacing = Pt(8)
        self._place(spacer._p)
        return table

    @staticmethod
    def _set_table_borders(table) -> None:
        properties = table._tbl.tblPr
        borders = properties.first_child_found_in("w:tblBorders")
        if borders is None:
            borders = OxmlElement("w:tblBorders")
            properties.append(borders)
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            element = OxmlElement(f"w:{edge}")
            element.set(qn("w:val"), "single")
            element.set(qn("w:sz"), "4")
            element.set(qn("w:space"), "0")
            element.set(qn("w:color"), "7F8C9A")
            borders.append(element)

    @staticmethod
    def _set_cell(cell, value: str, *, header: bool, font_size: float) -> None:
        cell.text = ""
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(1)
        paragraph.paragraph_format.space_after = Pt(1)
        paragraph.paragraph_format.line_spacing = Pt(14)
        run = paragraph.add_run(value)
        run.font.name = "黑体" if header else "宋体"
        run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "黑体" if header else "宋体")
        run.font.size = Pt(font_size)
        run.bold = header
        if header:
            run.font.color.rgb = RGBColor(255, 255, 255)
            shading = OxmlElement("w:shd")
            shading.set(qn("w:fill"), "274C77")
            cell._tc.get_or_add_tcPr().append(shading)

    @staticmethod
    def _repeat_header(row) -> None:
        properties = row._tr.get_or_add_trPr()
        repeat = OxmlElement("w:tblHeader")
        repeat.set(qn("w:val"), "true")
        properties.append(repeat)

    @staticmethod
    def _prevent_row_split(row) -> None:
        properties = row._tr.get_or_add_trPr()
        if properties.find(qn("w:cantSplit")) is None:
            properties.append(OxmlElement("w:cantSplit"))


def evidence_rows(evidence: dict[str, object], profile: str) -> list[dict[str, object]]:
    rows = [row for row in evidence["matrix_summary_rows"] if row["profile"] == profile]
    rows.sort(
        key=lambda row: (
            int(row["target_count"]),
            CONDITION_ORDER[str(row["condition"])],
            ROUTE_ORDER[str(row["route_name"])],
        )
    )
    return rows


def single_station_rows(evidence: dict[str, object], profile: str) -> list[tuple[str, ...]]:
    unique: dict[tuple[int, str], dict[str, object]] = {}
    for row in evidence_rows(evidence, profile):
        unique.setdefault((int(row["target_count"]), str(row["condition"])), row)
    return [
        (
            str(target_count),
            CONDITION_LABEL[condition],
            percent(row["single_station_precision"]),
            percent(row["single_station_coverage"]),
        )
        for (target_count, condition), row in sorted(
            unique.items(), key=lambda item: (item[0][0], CONDITION_ORDER[item[0][1]])
        )
    ]


def dual_station_rows(evidence: dict[str, object], profile: str) -> list[tuple[str, ...]]:
    return [
        (
            str(row["target_count"]),
            CONDITION_LABEL[str(row["condition"])],
            ROUTE_LABEL[str(row["route_name"])],
            percent(row["offline_completed_precision"]),
            percent(row["offline_completed_coverage"]),
            percent(row["on_time_coverage"]),
            milliseconds(row["latency_p95_ms"]),
            f"{row['timeout_count']}/{row['sample_count']}",
        )
        for row in evidence_rows(evidence, profile)
    ]


def write_section_41(writer: SectionWriter, evidence: dict[str, object]) -> None:
    writer.heading("4.1.1 场景与难点")
    writer.paragraph(
        "两台固定光电从不同位置连续扫描同一来袭空域。每台设备先看到目标在本机图像中的方向变化，不能仅凭单帧图像判断距离，也不能直接知道另一台设备中的哪条航迹与自己对应。目标数量增加、航迹交叉、扫描不同步和短时漏检会使一条航迹同时出现多个候选。双站一旦配错，后续交汇位置和速度都会随之错误。"
    )
    writer.paragraph(
        "处理难点集中在两个环节。第一，窄视场周扫使目标每圈只短时出现，单站需要把相邻帧和相邻扫描圈稳定接成同一条航迹。第二，两站局部编号彼此独立，必须在有限处理时间内完成候选筛选和整体一一配准。现有试验表明，双站方法在理想单站输入下可以贯通，实际链路的主要损失来自单站断轨、错误重接、重复建轨和混合航迹。"
    )

    writer.heading("4.1.2 方法流程")
    writer.paragraph(
        "处理顺序为单站成轨、共面候选筛选、跨站关系评分、匈牙利一一分配、多圈确认和交汇定位。共面筛选利用两站基线和两条空间视线应处于同一平面的关系，先排除明显不可能的组合。保留下来的候选可采用冻结权重的几何评分，也可由图神经网络综合多时刻运动和周边竞争关系给出评分。匈牙利算法从整批候选中选择不冲突的一一关系，证据不足的航迹允许保持未匹配。"
    )
    writer.image(
        DUAL_ASSETS / "01_algorithm_flow.png",
        "图4.1-1  双光电多目标轨迹配准与交汇定位流程",
    )

    writer.heading("4.1.3 单站航迹")
    writer.paragraph(
        "光电扫过目标时，连续检测先合并成一次扫描片段；下一圈重访时，再根据方位、俯仰、角速度、时间间隔和预测误差恢复原航迹。短时漏检期间保留休眠状态，目标交叉且关系不清时只保留少量候选，等待后续观测消解。单站若把一个目标拆成多条航迹，双站后端只能在这些碎片之间选择；若两目标被错误接成一条航迹，跨站多时刻关系也会被污染。"
    )
    writer.image(
        DUAL_ASSETS / "02_single_station_tracking.png",
        "图4.1-2  单站检测形成局部航迹及断轨风险",
    )

    writer.heading("4.1.4 双站候选与配准")
    writer.paragraph(
        "系统按照图像拍摄时刻校正设备位置、安装关系和云台姿态，把检测框中心转换为空间单位视线。设两站基线为b，两条视线为d_A和d_B，同一目标对应关系的归一化共面残差应接近零："
    )
    writer.formula("r = |bᵀ(d_A × d_B)| / (‖b‖·‖d_A × d_B‖ + ε)")
    writer.paragraph(
        "共面筛选只缩小候选范围。目标密集且运动方向接近时，多组航迹仍可能同时通过门限。几何方法比较多时刻共面残差、运动方向、角速度和交汇稳定性；图神经网络把A、B两站航迹作为两侧节点，把通过筛选的组合连成候选边，同时考虑每条候选与周边竞争候选的关系。网络评分不直接生成身份，仍需经过带空缺项的一一分配和连续多圈确认。"
    )
    writer.image(
        DUAL_ASSETS / "03_coplanarity_screening_3d.png",
        "图4.1-3  双站视线的三维共面候选筛选",
    )
    writer.image(
        DUAL_ASSETS / "04b_candidate_graph_gnn_assignment.png",
        "图4.1-4  图神经网络评分和一一分配后的航迹关系",
    )

    writer.heading("4.1.5 交汇定位")
    writer.paragraph(
        "双站关系确认后，系统把相邻时刻的两条视线配对。两条视线受离散采样和小幅误差影响，通常不会严格相交，取最近点连线的中点作为位置；多个时刻的位置再进行短时运动拟合，得到速度和拟合残差。交会角过小、两条视线分离过大或位置跳变时，结果保持待确认。配准回答两站是否看到同一目标，定位只处理已经确认的关系。"
    )
    writer.image(
        DUAL_ASSETS / "05_multitime_triangulation_3d.png",
        "图4.1-5  多时刻双视线交汇定位原理",
    )

    writer.heading("4.1.6 试验条件")
    writer.table(
        ("项目", "试验设置"),
        (
            ("光电布置", "两台固定光电，横向基线2千米，高度均为100米"),
            ("相机", "1280×1024，等效焦距300毫米，水平视场2.93度，垂直视场约2.344度"),
            ("采样", "检测和云台记录100赫兹；AirSim仿真时钟倍率0.1"),
            ("目标", "20、40、60个长度3米的无人机网格目标，速度50米/秒"),
            ("航向", "每组一半沿0度方向，一半沿负30度方向；前后位置和交叉关系随随机种子变化"),
            ("360度扫描", "2秒连续周扫一圈，12秒共6圈，统计第6圈"),
            ("180度扫描", "1秒单程扫过180度，2秒往返，12秒形成12轮，统计第12轮"),
            ("云台误差", "0.4毫弧度固定偏差和0.3毫弧度逐帧随机抖动"),
            ("样本", "每个目标规模、干扰等级和方法均为5个随机种子"),
        ),
        widths=(1.2, 5.0),
        font_size=8.7,
    )
    writer.table(
        ("干扰等级", "随机漏检率", "每台每秒瞬时虚警", "每台持续虚假航迹"),
        (
            ("无附加漏检虚警", "0", "0", "0"),
            ("轻度", "3%", "2个", "0"),
            ("中度", "7%", "4个", "1条"),
            ("重度", "12%", "8个", "2条"),
        ),
        widths=(1.7, 1.3, 1.6, 1.6),
        font_size=8.7,
    )
    writer.image(
        DUAL_ASSETS / "06_airsim_scene_40_targets_cn.png",
        "图4.1-6  双站光电与多方向运动目标仿真场景",
    )

    writer.heading("4.1.7 试验过程与评价口径")
    writer.paragraph(
        "本轮结果来自保存观测的确定性离线复算，共含360度理想单站6组、360度实际单站24组和180度扫描24组，每组5个随机种子。只统计最后一圈或最后一轮，不合并前期过渡数据。真实身份仅用于离线评分和理想单站诊断，不进入实际配准输入。"
    )
    writer.table(
        ("指标", "计算口径"),
        (
            ("单站精度", "两站各航迹的主导真实观测数÷全部有标签观测数"),
            ("单站覆盖度", "身份正确的单站航迹数÷两站目标机会总数"),
            ("双站质量精度", "正确双站关系数÷全部输出双站关系数"),
            ("双站质量覆盖度", "正确配准目标数÷目标总数"),
            ("按时覆盖度", "1000毫秒内正确配准目标数÷目标总数"),
            ("处理耗时P95", "5个随机种子最后窗口耗时的最近秩95%分位"),
        ),
        widths=(1.6, 4.6),
        font_size=8.7,
    )
    writer.paragraph(
        "超过1000毫秒后形成的关系仍保留其离线质量，用于判断算法是否配对正确；按时覆盖度记为0。这样可以把算法质量和在线处理能力分开，避免把超时后得到的正确关系写成实时结果。"
    )

    writer.heading("4.1.8 360度理想单站结果")
    writer.paragraph(
        "理想单站条件按离线真实身份把每个目标在每台光电的观测归成一条正确航迹，单站精度和覆盖度均为100%。该组只隔离检查双站候选、评分、一一分配和多圈确认，不代表实际单站航迹器已经达到完全正确。"
    )
    writer.table(
        ("目标数", "方法", "质量精度", "质量覆盖度", "按时覆盖度", "耗时P95", "超时"),
        [(row[0], *row[2:]) for row in dual_station_rows(evidence, "oracle_360")],
        widths=(0.55, 1.05, 0.85, 0.9, 0.9, 1.05, 0.7),
        font_size=7.9,
    )
    writer.image(
        DUAL_ASSETS / "13_v2_oracle_quality_timing.png",
        "图4.1-7  360度理想单站条件下的双站质量与耗时",
    )
    writer.paragraph(
        "六组均形成有效关系，说明双站链路在20至60目标范围内具备理论可行性。两种方法没有全面一致的质量排序：20和40目标的几何覆盖度较高；60目标图神经网络达到99.3%的质量精度和98.7%的质量覆盖度。时效差异明确，几何方法所有随机种子均超过1000毫秒，图神经网络全部按时。"
    )

    writer.heading("4.1.9 360度实际单站结果")
    writer.paragraph(
        "实际单站复算直接使用封存的匿名局部航迹，不按真实身份修复断轨、错误重接或重复建轨。两种跨站方法读取完全相同的单站输入。下表先列单站结果，再列对应的双站结果。"
    )
    writer.heading("单站航迹", level=4)
    writer.table(
        ("目标数", "干扰条件", "单站精度", "单站覆盖度"),
        single_station_rows(evidence, "continuous_360"),
        widths=(0.8, 2.1, 1.35, 1.35),
        font_size=8.4,
    )
    writer.image(
        DUAL_ASSETS / "14_v2_continuous_single_station.png",
        "图4.1-8  360度实际单站航迹精度和覆盖度",
    )
    writer.heading("双站配准", level=4)
    writer.table(
        ("目标数", "干扰", "方法", "质量精度", "质量覆盖", "按时覆盖", "耗时P95", "超时"),
        dual_station_rows(evidence, "continuous_360"),
        widths=(0.45, 0.85, 0.9, 0.75, 0.78, 0.78, 0.95, 0.55),
        font_size=7.0,
    )
    writer.image(
        DUAL_ASSETS / "15_v2_continuous_dual_matrix.png",
        "图4.1-9  360度实际单站条件下两种方法的最终质量",
    )
    writer.paragraph(
        "无附加漏检虚警时，单站覆盖度从20目标的91.5%下降到40目标的80.2%和60目标的73.2%。同条件下，几何方法双站覆盖度从理想输入的93.0%、87.5%、84.0%下降到66.0%、41.5%、36.7%；图神经网络由82.0%、79.5%、98.7%下降到56.0%、50.5%、41.7%。实际360度中，单站覆盖度与双站覆盖度的相关系数为0.903和0.613，说明前级航迹连续性是主要限制。"
    )
    writer.paragraph(
        "实际质量仍随场景变化。20目标四档条件下几何方法覆盖较高；40目标无附加和轻度条件下图神经网络较高；60目标两种方法随干扰等级交替占优。几何方法全部超时，图神经网络全部按时，因此当前应同时保留质量和时效两套判断，不能声称图神经网络在所有场景全面优于几何方法。"
    )

    writer.heading("4.1.10 180度扫描结果")
    writer.paragraph(
        "180度方案把目标来袭扇区作为已知范围，云台1秒扫过180度后反向返回，12秒形成12轮。无附加和轻度条件来自封存观测，中度和重度在同一匿名观测上按固定策略进行离线干扰复算。"
    )
    writer.heading("单站航迹", level=4)
    writer.table(
        ("目标数", "干扰条件", "单站精度", "单站覆盖度"),
        single_station_rows(evidence, "s180"),
        widths=(0.8, 2.1, 1.35, 1.35),
        font_size=8.4,
    )
    writer.image(
        DUAL_ASSETS / "16_v2_s180_single_station.png",
        "图4.1-10  180度扫描的单站航迹精度和覆盖度",
    )
    writer.heading("双站配准", level=4)
    writer.table(
        ("目标数", "干扰", "方法", "质量精度", "质量覆盖", "按时覆盖", "耗时P95", "超时"),
        dual_station_rows(evidence, "s180"),
        widths=(0.45, 0.85, 0.9, 0.75, 0.78, 0.78, 0.95, 0.55),
        font_size=7.0,
    )
    writer.image(
        DUAL_ASSETS / "16b_v2_s180_dual_matrix.png",
        "图4.1-11  180度扫描条件下两种方法的最终质量",
    )
    writer.paragraph(
        "缩小扫描扇区提高了目标方向的重访频率。60目标无附加漏检虚警时，图神经网络双站覆盖度由360度实际单站条件的41.7%提高到81.0%。几何方法12组全部超时，图神经网络12组全部按时。扇区扫描没有自动消除跨站损失，例如20目标中度干扰下单站覆盖度为100.0%，图神经网络双站覆盖度为61.0%，该部分仍需校准候选评分和连续确认。"
    )
    writer.image(
        DUAL_ASSETS / "17_v2_latency_deadline.png",
        "图4.1-12  三类复算耗时与1000毫秒处理期限",
    )

    writer.heading("4.1.11 结果判断")
    writer.paragraph(
        "双站配准在理想单站输入下已经形成20、40、60目标的完整结果，图神经网络在较大规模下兼顾质量和处理时限。实际周扫的首要问题仍是单站航迹连续性。下一步应先降低断轨、错误重接和混合航迹，再在相同匿名输入上比较几何与图神经网络。交汇定位的厘米级误差只来自理想位姿和理想时间的单次仿真演示，不能作为设备定位指标。"
    )


def write_section_44(writer: SectionWriter) -> None:
    search_rows = markdown_table(
        SEARCH_REPORT,
        (
            "场景",
            "位置误差σ",
            "发现率均值/最差",
            "连续确认均值/最差",
            "视锥概率覆盖",
            "重复确认",
            "未执行任务均值",
            "首次发现均值",
            "规划P95均值",
        ),
    )
    if len(search_rows) != 9:
        raise RuntimeError(f"expected 9 cooperative-search rows, found {len(search_rows)}")

    writer.heading("4.4.1 场景与难点")
    writer.paragraph(
        "本节限定中心已经正确识别全部目标，每个目标只有一条正确线索。中心不提供足以直接交战的精确位置，只给出粗位置、速度、信息时刻和协方差。拦截无人机需要在18秒预算内飞到合适观察位置，调整云台，逐步检查预测区域，并把一次看到目标转成连续两帧确认。"
    )
    writer.paragraph(
        "粗位置误差会扩大相机需要检查的范围。资源较少时，平台可能来不及覆盖全部高概率子单元；资源较多时，多机又可能重复观察相邻区域。分配需要同时考虑目标概率、平台飞行时间、云台转向、观察时间和重复占用。本轮不设置错误线索、重复线索、中心漏检目标或空白走廊，只验证正确线索存在较大位置误差时的责任区搜索。"
    )

    writer.heading("4.4.2 三倍标准差预测区域")
    writer.paragraph(
        "每条线索先按保存速度外推到规划时刻，再在北、东、地三个方向取三倍位置标准差，形成包含大部分位置概率的三维预测区域。误差标准差取30米、60米和100米，对应各轴半宽约90米、180米和300米。每条线索单独形成预测区域，线索之间不依靠真实目标编号合并。"
    )
    writer.paragraph(
        "相机分辨率为1920×1080，水平视场19度，垂直视场10.75度。在700米观察距离上，单视场覆盖约234.28米×131.78米，相邻视场保留20%重叠。预测区域横向和高度方向按实际视场足迹划分子单元，深度方向保留完整三倍标准差范围。误差越大，子单元数量越多，搜索任务随之增加。"
    )
    writer.image(
        TERMINAL_ASSETS / "search100_02_cells_3d.png",
        "图4.4-1  中心粗位置三倍标准差区域与实际视场子单元",
    )

    writer.heading("4.4.3 概率更新与云台扫描")
    writer.paragraph(
        "每个子单元的初始优先级由高斯分布在该范围内的概率质量确定，中心区域优先，边缘区域次之。无人机到达观察点后，云台指向子单元中心并稳定观察0.3秒，每0.1秒形成一帧，共采集3帧。平台飞行与云台转动可同时进行，离线模型采用97米/秒平台速度上限和200度/秒云台转速上限。"
    )
    writer.paragraph(
        "目标进入真实视锥且检测框最长边不小于10像素时，生成匿名检测；同一短航迹连续2帧满足门限后确认该目标。一次观察没有发现目标时，只把真实视锥已经覆盖的概率质量从待搜索集合中扣除，不把整条线索区域清空。确认目标后关闭该线索剩余子单元。由于本轮没有随机漏检和虚警，这一更新用于核对搜索几何和资源容量，不代表真实探测概率已经标定。"
    )

    writer.heading("4.4.4 滚动一一分配")
    writer.paragraph(
        "每次有无人机空闲时，系统重新建立无人机到候选子单元的收益矩阵。收益同时考虑子单元概率、预计完成时间和飞行距离："
    )
    writer.formula("U = 12p + 1.5/(1+T) − 0.018T − 0.00005D")
    writer.paragraph(
        "式中，p为子单元概率质量，T为飞行、转向和观察总时间，D为平台到观察点的距离。预计完成时间超过18秒的组合不下发。匈牙利算法一次处理整张收益矩阵，保证一架无人机同一轮只接一个子单元，一个子单元同一轮只分给一架无人机。完成观察后立即更新剩余概率和平台状态，再滚动计算下一项任务。"
    )
    writer.image(
        TERMINAL_ASSETS / "search100_01_flow.png",
        "图4.4-2  粗位置线索条件下的协同搜索与滚动分配流程",
    )

    writer.heading("4.4.5 试验条件")
    writer.table(
        ("项目", "设置"),
        (
            ("试验性质", "保存AirSim目标轨迹上的确定性离线搜索调度，未重新启动AirSim"),
            ("规模", "20目标/8机、20目标/30机、40目标/50机"),
            ("中心线索", "精度和召回率均为100%，每个目标恰有一条正确线索"),
            ("误差档", "北、东、地各轴位置标准差30米、60米、100米，截断在±3σ"),
            ("随机种子", "20260816至20260820，每档5个随机种子"),
            ("目标", "保存记录中的3米网格目标，速度约50米/秒；0.8秒后按保存速度外推"),
            ("机载相机", "1920×1080，水平视场19度，垂直视场10.75度，观察距离700米"),
            ("观察与预算", "每点0.3秒、3帧；10像素门限；连续2帧确认；总预算18秒"),
            ("检测干扰", "不额外注入随机漏检和虚警"),
        ),
        widths=(1.25, 4.95),
        font_size=8.6,
    )

    writer.heading("4.4.6 试验过程")
    writer.paragraph(
        "三种规模分别在30米、60米和100米误差档运行5个随机种子，共45组。每组先生成三倍标准差预测区域和视场子单元，再按平台运动、云台转向和观察时间滚动分配。任务获得分配不等于已经观察，只有平台完成运动、真实视锥覆盖相应空间并取得连续图像后，才计入发现和确认。"
    )
    writer.paragraph(
        "离线观测器使用保存的目标位置生成匿名检测。真实目标编号不参与子单元生成、收益计算、分配或关闭判断，45组在线记录的真实身份泄漏数为0。目标轨迹在保存记录结束后按恒速外推，平台和云台采用速度上限模型，因此本轮验证的是调度和几何可见性，不是新AirSim在线飞行试验。"
    )

    writer.heading("4.4.7 试验结果")
    writer.table(
        (
            "场景",
            "误差σ",
            "发现均值/最差",
            "连续确认均值/最差",
            "视锥概率覆盖",
            "重复确认",
            "未执行任务",
            "首次发现",
            "规划P95",
        ),
        search_rows,
        widths=(0.85, 0.5, 0.95, 1.15, 0.75, 0.7, 0.75, 0.7, 0.7),
        font_size=6.6,
    )
    writer.image(
        TERMINAL_ASSETS / "search100_03_results.png",
        "图4.4-3  三种粗位置误差下的目标发现与连续确认",
    )
    writer.paragraph(
        "20目标/8机是资源最紧张的场景。30米误差档连续确认率为100%；60米为97%，最差随机种子90%；100米为91%，最差随机种子80%，预算结束平均仍有24.6个有效子单元未执行。20目标/30机和40目标/50机在30、60、100米三档误差下均达到100%连续确认。"
    )
    writer.paragraph(
        "100米误差档中，20目标/30机和40目标/50机的视锥概率覆盖分别为61.3%和59.6%，目标仍全部确认。原因是目标一旦连续确认，其余子单元按规则关闭，视锥概率覆盖不是整片空域覆盖率。重复确认比例为71.1%至93.2%，说明相邻子单元和多机共同视场带来较多复核，也占用了部分搜索容量。"
    )
    writer.image(
        TERMINAL_ASSETS / "search100_04_coverage_budget.png",
        "图4.4-4  真实视锥覆盖与18秒预算内剩余任务",
    )
    writer.image(
        TERMINAL_ASSETS / "search100_05_timing.png",
        "图4.4-5  首次发现时间与滚动分配计算时间",
    )

    writer.heading("4.4.8 结果边界")
    writer.paragraph(
        "结果说明，在中心线索全部正确、目标尺寸3米、无随机漏检和虚警的限定条件下，滚动一一分配能够把粗位置和协方差转换为可执行搜索任务。30米误差下8架无人机完成20目标搜索；误差扩大后8机资源出现漏搜，30机搜索20目标和50机搜索40目标仍完成全部连续确认。"
    )
    writer.paragraph(
        "本轮45组均为保存AirSim轨迹上的离线复算，没有新启动AirSim。目标后续运动采用线性外推，平台和云台采用上限模型，尚未加入加速度、航迹冲突、导航误差、云台稳定时间、真实图像检测波动和通信延迟。上述结果只能作为搜索调度和几何覆盖证据。"
    )


def write_section_45(writer: SectionWriter) -> None:
    parameter_rows = markdown_table(
        TERMINAL_REPORT,
        ("参数", "搜索范围", "选定值"),
    )
    handover_rows = markdown_table(
        TERMINAL_REPORT,
        ("场景", "正确绑定", "错误绑定", "精度", "召回率", "原复算时间"),
    )
    metric_rows = markdown_table(
        TERMINAL_REPORT,
        (
            "场景",
            "方法",
            "机会目标",
            "关系精度",
            "等权纯度",
            "等权完整度",
            "独立纯净簇",
            "混合目标",
            "未完成目标",
        ),
    )
    runtime_rows = markdown_table(
        TERMINAL_REPORT,
        ("场景", "方法", "保留相机对", "候选边", "无缓存耗时"),
    )
    if (len(parameter_rows), len(handover_rows), len(metric_rows), len(runtime_rows)) != (3, 3, 6, 6):
        raise RuntimeError("unexpected terminal-association source table shape")

    writer.heading("4.5.1 场景与难点")
    writer.paragraph(
        "拦截无人机进入目标附近后，每架相机只能看到群目标的一部分。不同无人机为同一目标建立的本地编号互不相同，中心航迹位于北东地坐标系，机载检测位于图像坐标系。无人机在运动，云台也在转动，同一目标在不同图像中的位置和运动方向均会变化。姿态时刻、安装偏移或旋转方向处理错误，会使中心预测点整体偏离检测框；多机之间还可能把相邻目标错误合并。"
    )
    writer.paragraph(
        "末端按责任区和实际视场保持稀疏，只比较可能存在共同视场的相机对。没有足够几何证据时，航迹保持未匹配。中心交接解决“中心航迹与哪条机载航迹对应”，机间配准解决“多架无人机看到的局部航迹是否属于同一目标”，两条链路均使用拍摄时刻状态、硬几何门控、一一分配和连续多帧确认。"
    )
    writer.image(
        TERMINAL_ASSETS / "06_terminal_flow.png",
        "图4.5-1  中心航迹交接与拦截无人机之间的末端配准流程",
    )

    writer.heading("4.5.2 测量时刻状态")
    writer.paragraph(
        "中心位置、速度和协方差先外推到图像的测量时刻。机体位置、机体姿态和云台姿态也按同一测量时刻插值，插值必须同时具有拍摄时刻前后的姿态样本；任一侧缺失或时间间隔超限时停止建立关系。消息到达时刻只用于判断通信是否过期，不能替代图像拍摄时刻参与几何计算。"
    )
    writer.formula("x(t) = Fx₀，P(t) = FP₀Fᵀ + Q")
    writer.paragraph(
        "现有三组AirSim保存回放已经把拍摄时刻的最终相机光心和姿态写入观测，因此按合成相机位姿、安装偏移为零的兼容方式读取。完整安装偏移和姿态插值已经形成可测试计算链，但旧回放没有验证非零安装偏移。"
    )

    writer.heading("4.5.3 完整坐标转换")
    writer.paragraph(
        "旋转方向固定为：R_B^N把北东地坐标转到机体坐标，R_G^B把机体坐标转到云台坐标，R_C^G把云台坐标转到相机坐标。目标点从北东地坐标转入相机坐标的完整关系为："
    )
    writer.formula("p_C = R_C^G R_G^B R_B^N (p_N − o_C^N)")
    writer.paragraph(
        "相机光心不是机体参考点。视线起点同时包含机体位置、机体到云台转轴的偏移和云台转轴到相机光心的安装偏移："
    )
    writer.formula("o_C^N = p_B^N + R_N^B (r_fix^B + r_G^B + R_B^G r_C^G)")
    writer.paragraph(
        "相机采用前、右、下坐标。检测框中心先按相机内参反投影为相机系单位视线，再用同一旋转链转回北东地坐标。正投影和反投影必须使用同一光心、同一拍摄时刻和同一旋转方向。"
    )
    writer.image(
        TERMINAL_ASSETS / "07_terminal_pose_chain.png",
        "图4.5-2  机体、云台和相机之间的完整旋转链与安装偏移",
    )

    writer.heading("4.5.4 联合误差传播与中心交接")
    writer.paragraph(
        "像面预测范围同时考虑中心航迹位置误差、无人机导航位置误差、机体姿态误差、云台角误差、检测框中心误差和时间误差。把这些误差组成联合状态，通过投影函数的雅可比矩阵传播到图像平面，得到预测椭圆。线索时间越旧、姿态越不确定，预测椭圆越大。"
    )
    writer.formula("S_image = J_image Σ_x J_imageᵀ + R_projection")
    writer.formula("d² = (z − z_hat)ᵀ S_image⁻¹ (z − z_hat)")
    writer.paragraph(
        "外推后的中心状态投到机载图像后，先检查线索有效期、预测点是否位于图像内、检测框是否达到10像素、归一化像面残差和像面运动是否通过门限。通过硬门控的候选进入带未匹配项的匈牙利一一分配，最近3帧中至少2帧保持同一关系后正式交接。"
    )
    writer.image(
        SCHEME_ASSETS / "12_center_interceptor_direct_registration.png",
        "图4.5-3  中心源航迹向机载局部航迹的投影和一一交接",
    )
    writer.heading("中心交接保存回放结果", level=4)
    writer.table(
        ("场景", "正确绑定", "错误绑定", "精度", "召回率", "原复算时间"),
        handover_rows,
        widths=(1.2, 0.85, 0.85, 0.8, 0.8, 1.2),
        font_size=8.4,
    )
    writer.paragraph(
        "中心交接结果沿用三组已有匿名观测，与4.4的100%正确线索搜索矩阵属于不同专项，不混合统计。20目标/8机和20目标/30机没有错误绑定；40目标/50机形成31条正确绑定和1条错误绑定。旧回放没有保存导航、机体和云台误差序列，因此该表不能作为非零姿态误差条件下的稳定性结论。"
    )

    writer.heading("4.5.5 拦截无人机之间的配准")
    writer.paragraph(
        "各机先在本相机内把匿名检测连接成局部短航迹。两条航迹按测量时刻对齐后，将检测中心反投影为空间单位视线，计算多个时刻的双视线交会、重投影误差和运动一致性。硬门控检查时间差、交会角、视线分离、重投影、运动拟合和目标尺度。通过门控的候选使用几何代价，或由图神经网络给出同目标概率并修正代价；最终仍执行相机对内匈牙利一一分配、最近3帧至少2帧确认和同一相机唯一性约束。"
    )
    writer.image(
        TERMINAL_ASSETS / "10_crossview_rays.png",
        "图4.5-4  两机视线交会与多时刻运动核对",
    )
    writer.paragraph(
        "相机数量增加后，先按责任区和实际视场重叠构建稀疏相机关系。无共同视场的相机对不进入精细计算。确认的局部关系再合并为目标簇，同一目标簇不允许出现同一相机的两条航迹；成熟目标簇合并需要多个不同相机对共同支持，防止一条偶然错误关系扩散到整个目标簇。"
    )
    writer.image(
        SCHEME_ASSETS / "11_multicamera_subset_scenario.png",
        "图4.5-5  多架拦截无人机分别观察不同目标子集",
    )

    writer.heading("4.5.6 图网络诊断参数")
    writer.paragraph(
        "图网络只在通过硬门控的候选中调整排序，不读取真实目标编号，也不能恢复被时间或几何门限拒绝的关系。本轮只搜索图网络概率阈值、几何与图网络融合权重和未匹配代价，网络权重、硬门控、一一匹配和多帧确认均保持不变。"
    )
    writer.table(
        ("参数", "搜索范围", "选定值"),
        parameter_rows,
        widths=(1.7, 3.1, 1.2),
        font_size=8.6,
    )
    writer.paragraph(
        "选定值为图网络概率阈值0.05、图网络融合权重0.25、未匹配代价0.85。36组组合直接在三组随机种子20260816的单次保存回放上择优，属于同批诊断，不是独立留出验证。该参数只能用于说明图网络在已有歧义候选上的可能作用，不能据此替换默认方法。"
    )

    writer.heading("4.5.7 评价口径与结果")
    writer.paragraph(
        "评价分母只包含至少被两台相机看到、具备配准机会的真实目标。航迹关系精度统计输出关系中正确关系的比例。每目标等权纯度表示一个目标最佳目标簇中有多少成员确属该目标；每目标等权完整度表示该目标应合并的局部航迹有多少进入最佳目标簇。每个目标只计一次。独立纯净目标簇要求该目标全部可评分航迹进入同一簇且没有混入其他目标。另行统计身份混合目标数和未完成配准目标数。"
    )
    writer.image(
        TERMINAL_ASSETS / "15_terminal_target_metric.png",
        "图4.5-6  关系级与目标级配准评价口径",
    )
    writer.table(
        (
            "场景",
            "方法",
            "机会目标",
            "关系精度",
            "等权纯度",
            "等权完整度",
            "独立纯净簇比例",
            "混合目标",
            "未完成目标",
        ),
        metric_rows,
        widths=(0.75, 0.85, 0.55, 0.65, 0.65, 0.65, 0.75, 0.55, 0.65),
        font_size=6.7,
    )
    writer.table(
        ("场景", "方法", "保留相机对", "候选边", "无缓存耗时"),
        runtime_rows,
        widths=(1.15, 1.2, 1.15, 1.2, 1.25),
        font_size=8.2,
    )
    writer.image(
        TERMINAL_ASSETS / "12_terminal_metric_comparison.png",
        "图4.5-7  稀疏几何与同批择优图网络的目标级结果",
    )
    writer.paragraph(
        "20目标/30机中，图网络把关系精度由0.7402提高到0.9736，身份混合目标由7个降为0，等权完整度为0.9587，说明该场景的歧义候选排序获得了明显改善。20目标/8机中，图网络虽然保持关系精度1.0000，但等权完整度降至0.2500，并有15个目标未完成配准。40目标/50机中，图网络关系精度由0.9960小幅提高到0.9971，等权完整度却由0.9710降至0.5666。"
    )

    writer.heading("4.5.8 阶段判断")
    writer.paragraph(
        "完整旋转链、安装偏移、测量时刻状态和联合误差传播已经形成可测试计算关系。旧AirSim回放只验证合成相机位姿和零安装偏移兼容路径，导航误差、机体姿态误差、云台角误差和时间漂移仍需重新注入。"
    )
    writer.paragraph(
        "当前默认方法继续采用责任区与实际视场稀疏候选、硬几何门控、匈牙利一一分配和多帧确认。图网络在20目标/30机场景改善明显，在另外两个场景损失较多完整度；同批单随机种子择优也不具备独立验证效力。现有证据不支持图网络全面优于几何方法或替换默认路径。"
    )


def validate_integrated_content(document: Document) -> None:
    expected_headings = (
        *(f"4.1.{index}" for index in range(1, 12)),
        *(f"4.4.{index}" for index in range(1, 9)),
        *(f"4.5.{index}" for index in range(1, 9)),
    )
    for number in expected_headings:
        find_numbered_heading(document, number)

    section_41 = target_text(document, "4.1 侦察的想法", "4.2 火指控的想法")
    section_44 = target_text(document, "4.4 拦截区域搜索", "4.5 群对群目标配准")
    section_45 = target_text(document, "4.5 群对群目标配准", "4.3.6 主动降级与分级目标分配")

    required_41 = (
        "360度理想单站",
        "360度实际单站",
        "180度扫描",
        "最后一圈或最后一轮",
        "1000毫秒",
        "99.3%",
        "98.7%",
        "主要限制",
    )
    required_44 = (
        "精度和召回率均为100%",
        "每个目标恰有一条正确线索",
        "三倍标准差",
        "实际视场足迹",
        "45组",
        "真实身份泄漏数为0",
        "未重新启动AirSim",
    )
    required_45 = (
        "p_C = R_C^G R_G^B R_B^N (p_N − o_C^N)",
        "测量时刻",
        "安装偏移",
        "导航位置误差",
        "图网络概率阈值0.05",
        "融合权重0.25",
        "未匹配代价0.85",
        "不是独立留出验证",
        "默认方法继续采用",
    )
    for label, text, markers in (
        ("4.1", section_41, required_41),
        ("4.4", section_44, required_44),
        ("4.5", section_45, required_45),
    ):
        missing = [marker for marker in markers if marker not in text]
        if missing:
            raise RuntimeError(f"integrated section {label} is missing {missing}")

    forbidden = (
        "增强型图神经网络",
        "全相机",
        "中心线索精度和召回率固定为80%",
        "空白走廊单元",
    )
    combined = section_41 + section_44 + section_45
    present = [marker for marker in forbidden if marker in combined]
    if present:
        raise RuntimeError(f"integrated sections retain superseded wording: {present}")


def choose_backup_path(document_path: Path, before_sha: str, requested: Path | None) -> Path:
    if requested is not None:
        return requested.resolve()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR / f"{document_path.stem}.{before_sha[:16]}.docx"


def backup_document(document_path: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        if sha256(backup_path) != sha256(document_path):
            raise RuntimeError(f"backup path already contains a different document: {backup_path}")
        return
    shutil.copy2(document_path, backup_path)


def integrate(document_path: Path, output_path: Path, requested_backup: Path | None) -> dict[str, object]:
    if not document_path.is_file():
        raise FileNotFoundError(document_path)
    evidence = verify_reviewed_sources()

    before_sha = sha256(document_path)
    backup_path = choose_backup_path(document_path, before_sha, requested_backup)
    backup_document(document_path, backup_path)
    package_before = package_hashes(document_path)

    document = Document(document_path)
    styles = style_samples(document)
    outside_before = outside_target_hash(document)

    heading_41 = find_paragraph(document, "4.1 侦察的想法")
    heading_42 = find_paragraph(document, "4.2 火指控的想法")
    heading_44 = find_paragraph(document, "4.4 拦截区域搜索")
    heading_45 = find_paragraph(document, "4.5 群对群目标配准")
    heading_after_45 = find_paragraph(document, "4.3.6 主动降级与分级目标分配")

    remove_between(heading_41, heading_42)
    remove_between(heading_44, heading_45)
    remove_between(heading_45, heading_after_45)

    write_section_41(SectionWriter(document, heading_42, styles), evidence)
    write_section_44(SectionWriter(document, heading_45, styles))
    write_section_45(SectionWriter(document, heading_after_45, styles))
    validate_integrated_content(document)

    outside_after_in_memory = outside_target_hash(document)
    if outside_before != outside_after_in_memory:
        raise RuntimeError("content outside sections 4.1, 4.4 and 4.5 changed in memory")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp.docx")
    if temporary.exists():
        temporary.unlink()
    document.save(temporary)

    saved = Document(temporary)
    validate_integrated_content(saved)
    outside_after_saved = outside_target_hash(saved)
    if outside_before != outside_after_saved:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("saved document changed body content outside sections 4.1, 4.4 and 4.5")

    package_after = package_hashes(temporary)
    package_result = verify_package_preservation(package_before, package_after)
    os.replace(temporary, output_path)

    return {
        "document": str(output_path),
        "backup": str(backup_path),
        "sha256_before": before_sha,
        "sha256_after": sha256(output_path),
        "started_from_expected_original": before_sha == EXPECTED_ORIGINAL_SHA256,
        "outside_sha256_before": outside_before,
        "outside_sha256_after_in_memory": outside_after_in_memory,
        "outside_sha256_after_saved": outside_after_saved,
        "dual_matrix_groups": evidence["matrix_completeness"]["total_group_count"],
        **package_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()

    document_path = args.document.resolve()
    output_path = (args.output or document_path).resolve()
    result = integrate(document_path, output_path, args.backup)
    for key, value in result.items():
        if isinstance(value, list):
            print(f"{key}={','.join(map(str, value))}")
        else:
            print(f"{key}={value}")


if __name__ == "__main__":
    main()
