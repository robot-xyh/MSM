#!/usr/bin/env python3
"""Build page-preserving Chinese translations for the local paper PDFs.

The source PDFs remain authoritative.  The generated Markdown keeps a rendered
image of every source page, preserves formula-like blocks, and translates the
remaining prose with a local NLLB model.  It is intentionally conservative:
references and uncertain PDF extraction are left visible for checking against
the page image.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
PAPER_DIR = ROOT / "paper"
MAIN_DIR = PAPER_DIR / "papers"
OTHER_DIR = PAPER_DIR / "other-paper"
MAIN_DETAILS = MAIN_DIR / "中文详解"
OTHER_DETAILS = OTHER_DIR / "中文详解"
MODEL_NAME = "facebook/nllb-200-distilled-600M"
CACHE_PATH = Path("/tmp/msm-paper-translation-cache.json")
GOOGLE_MOBILE_CACHE_PATH = Path("/tmp/msm-paper-translation-google-mobile-cache.json")


# NLLB is used for the first pass.  These replacements keep recurring robotics
# terminology consistent without changing numbers, identifiers, or equations.
TERM_REPLACEMENTS = (
    # Google and local MT models both translate these technical expressions too
    # literally.  Keep the project terminology consistent before applying more
    # general punctuation cleanup below.
    ("四旋翼飞行器", "四旋翼无人机"),
    ("固有的驱动不足", "固有的欠驱动特性"),
    ("固有的不足", "固有的欠驱动特性"),
    ("驱动不足", "欠驱动"),
    ("攻击性机动", "激进机动"),
    ("侵略性机动", "激进机动"),
    ("侵略性动作", "激进机动"),
    ("特技潜力", "特技飞行潜能"),
    ("特技任务", "特技飞行任务"),
    ("有氧任务", "特技飞行任务"),
    ("有氧机动", "特技机动"),
    ("特技点", "特技航路点"),
    ("零射", "零样本"),
    ("仿真到实际", "仿真到真实"),
    ("仿真到现实", "仿真到真实"),
    ("增强学习", "强化学习"),
    ("增强的学习", "强化学习"),
    ("近距离政策优化", "近端策略优化"),
    ("近端政策优化", "近端策略优化"),
    ("政策梯度", "策略梯度"),
    ("政策网络", "策略网络"),
    ("培训框架", "训练框架"),
    ("培训政策", "训练策略"),
    ("政策", "策略"),
    ("I. 引入", "I. 引言"),
    ("我们引言", "我们引入"),
    ("问题表达", "问题表述"),
    ("抽象", "摘要"),
    ("态度角", "姿态角"),
    ("态度误差", "姿态误差"),
    ("态度", "姿态"),
    ("反控制器", "反馈控制器"),
    ("反向控制器", "反馈控制器"),
    ("空操", "特技飞行"),
    ("空旋", "特技飞行"),
    ("空中操纵", "空中特技机动"),
    ("空动机", "特技机动"),
    ("空气动作", "特技机动"),
    ("空气路线点", "特技航路点"),
    ("动态空气点", "动态航路点"),
    ("空气点", "航路点"),
    ("轨道优化", "轨迹优化"),
    ("轨道跟踪", "轨迹跟踪"),
    ("轨道规划", "轨迹规划"),
    ("空中飞行轨道", "空中飞行轨迹"),
    ("真实传输", "仿真到真实迁移"),
    ("零射击", "零样本"),
    ("融合解决方案", "收敛解"),
    ("融合效率", "收敛效率"),
    ("政策", "策略"),
    ("培训", "训练"),
    ("低行径", "欠驱动特性"),
    ("低调", "欠驱动特性"),
    ("低活力", "欠驱动特性"),
    ("不切断性", "欠驱动特性"),
    ("未被激活", "欠驱动"),
    ("飞行机动作", "特技机动"),
    ("差异平率", "微分平坦性"),
    ("差分平率", "微分平坦性"),
    ("最佳性", "最优性"),
    ("加强学习", "强化学习"),
    ("大规模飞行飞行", "大规模特技飞行"),
    ("飞行飞行", "特技飞行"),
    ("空气路线", "航路"),
    ("飞行路线点", "航路点"),
    ("真实与真实", "仿真与真实"),
    ("仿真和现实", "仿真与现实"),
    ("动机速度", "电机转速"),
    ("直动动机速度", "直接电机转速"),
    ("图پل", "元组"),
    ("马科夫决策过程", "马尔可夫决策过程"),
    ("无限地平线", "无限时域"),
    ("无限视野", "无限时域"),
    ("网络融合", "网络收敛"),
    ("现实实", "真实"),
    ("侵略动作", "激进机动"),
    ("侵略性", "激进性"),
    ("分辨精度", "离散精度"),
    ("质量正常化", "质量归一化"),
    ("机器人体框架", "机器人机体坐标系"),
    ("自觉观测", "自状态观测"),
    ("批评网络", "价值网络"),
    ("批评家网络", "价值网络"),
    ("批次", "批次"),
    ("逐步的训练策略", "渐进式训练策略"),
    ("域名随机化", "域随机化"),
    ("寄生虫的空气阻力", "附加空气阻力"),
    ("模拟和现实之间的差异", "仿真与现实之间的差异"),
    ("Sim到真实", "仿真到真实"),
)


def normalize_translation(text: str) -> str:
    """Apply only conservative terminology corrections to model output."""
    text = text.strip()
    for source, target in TERM_REPLACEMENTS:
        text = text.replace(source, target)
    text = re.sub(r"\s+([，。；：！？、])", r"\1", text)
    text = re.sub(r"([（【])\s+", r"\1", text)
    text = re.sub(r"\s+([）】])", r"\1", text)
    return text


OTHER_MAP = {
    "Adaptive Tracking and Perching for Quadrotor in Dynamic Scenarios.pdf": "03_动态场景下四旋翼自适应跟踪与停泊.md",
    "A Decoupled and Linear Framework for Global Outlier Rejection over Planar Pose Graph.pdf": "01_平面位姿图全局外点剔除解耦线性框架.md",
    "Aggressive Collision-Inclusive Motion Planning.pdf": "04_包含碰撞的高动态机动运动规划.md",
    "A Linear and Exact Algorithm for Whole-Body Collision Evaluation via Scale Optimization.pdf": "02_基于尺度优化的全机身精确碰撞评估线性算法.md",
    "An Efficient Spatial-Temporal Trajectory Planner for Autonomous Vehicles in Unstructured Environments.pdf": "05_非结构化环境下自动驾驶车辆高效时空轨迹规划器.md",
    "Auto Filmer Autonomous Aerial Videography Under Human Interaction.pdf": "06_Auto_Filmer人机交互下的自主空中影视拍摄.md",
    "Autonomous Exploration With Terrestrial-Aerial Bimodal Vehicles.pdf": "07_空地双模态机器人自主环境探索.md",
    "Bearing-Based Relative Localization for Robotic Swarm With Partially Mutual Observations.pdf": "08_基于方位测量的部分相互观测机器人集群相对定位.md",
    "Collaborative Planning for Catching and Transporting Objects in Unstructured Environments.pdf": "09_非结构化环境下多机协同接力物体捕获与运输规划.md",
    "Cost-Effective Swarm Navigation System via Close Cooperation.pdf": "10_紧密协作下的高性价比无人机集群导航系统.md",
    "DPNet Doppler LiDAR Motion Planning for Highly-Dynamic Environments.pdf": "11_DPNet多普勒激光雷达高动态环境运动规划.md",
    "Dynamically Feasible Trajectory Generation With Optimization-Embedded Networks for Autonomous Flight.pdf": "12_嵌入优化神经网络的自主飞行可行动力学轨迹生成.md",
    "Efficient View Path Planning for Autonomous Implicit Reconstruction.pdf": "13_自主隐式神经重建的高效视点路径规划.md",
    "FACT Fast and Active Coordinate Initialization for Vision-Based Drone Swarms.pdf": "14_FACT视觉无人机集群快速主动坐标系初始化.md",
    "FAR-AVIO Fast and Robust Schur-Complement Based Acoustic-Visual-Inertial Fusion Odometry With Sensor Calibration.pdf": "15_FAR-AVIO基于舒尔补的声光惯融合里程计与在线标定.md",
    "FastSim A Modular and Plug-and-Play Simulator for Aerial Robots.pdf": "16_FastSim模块化即插即用空中机器人仿真平台.md",
    "Flying in Dynamic Scenes With Multitarget Velocimetry and Perception-Enhanced Planning.pdf": "17_动态场景多目标测速与感知增强规划飞行.md",
    "Global-State-Free Obstacle Avoidance for Quadrotor Control in Air-Ground Cooperation.pdf": "18_空地协同中无全局状态四旋翼避障控制.md",
    "Ground-Effect-Aware Modeling and Control for Multicopters.pdf": "19_多旋翼近地效应建模与自适应控制.md",
    "Hierarchically Depicting Vehicle Trajectory with Stability in Complex Environments.pdf": "20_复杂环境下兼顾稳定性的车辆分层轨迹表征.md",
    "Impact-Aware Planning and Control for Aerial Robots With Suspended Payloads.pdf": "21_考虑碰撞冲击的缆绳悬挂载荷无人机规划与控制.md",
    "LEMON-Mapping Loop-Enhanced Large-Scale Multi-Session Point Cloud Merging and Optimization for Globally Consistent Mapping.pdf": "22_LEMON-Mapping大规模多时序点云融合与回环增强优化.md",
    "LF-VISLAM A SLAM Framework for Large Field-of-View Cameras With Negative Imaging Plane on Mobile Agents.pdf": "23_LF-VISLAM负成像平面超大视场相机视觉惯导SLAM.md",
    "LiDAR-VGGT Cross-Modal Coarse-to-Fine Fusion for Globally Consistent and Metric-Scale Dense Mapping.pdf": "24_LiDAR-VGGT跨模态粗到精融合全局一致米制稠密建图.md",
    "Microsaccade-Inspired Event Camera for Robotics.pdf": "25_微跳视仿生事件相机机器人视觉感知系统.md",
    "NavDreamer Video Models as Zero-Shot 3D Navigators.pdf": "26_NavDreamer基于视频生成模型的零样本三维具身导航.md",
    "PredRecon A Prediction-boosted Planning Framework for Fast and High-quality Autonomous Aerial Reconstruction.pdf": "27_PredRecon基于预测增强的高效高质量自主空中三维重建.md",
    "Primitive-Swarm An Ultra-Lightweight and Scalable Planner for Large-Scale Aerial Swarms.pdf": "28_Primitive-Swarm超轻量高扩展大规模无人机集群规划器.md",
    "Real-Time Trajectory Planning for Aerial Perching.pdf": "29_实时空中停泊轨迹规划.md",
    "Rotor-Failure-Aware Quadrotors Flight in Unknown Environments.pdf": "30_旋翼故障感知四旋翼未知环境自主飞行.md",
    "STD-Trees Spatio-temporal Deformable Trees for Multirotors Kinodynamic Planning.pdf": "31_STD-Trees时空可变形搜索树运动动力学规划.md",
    "Skywalker A Compact and Agile Air-Ground Omnidirectional Vehicle.pdf": "32_Skywalker紧凑灵活空地全向移动机器人.md",
    "Star-Searcher A Complete and Efficient Aerial System for Autonomous Target Search in Complex Unknown Environments.pdf": "33_Star-Searcher复杂未知环境自主目标搜索系统.md",
    "The Forgotten Spectrum Reviving Ultrasound for Robust Autonomy.pdf": "34_复兴超声波传感构建鲁棒自主系统.md",
    "Universal Trajectory Optimization Framework for Differential Drive Robot Class.pdf": "35_差速驱动机器人族通用轨迹优化框架.md",
}


@dataclass(frozen=True)
class Record:
    source: Path
    detail: Path
    output_dir: Path

    @property
    def output(self) -> Path:
        return self.output_dir / f"{self.detail.stem}_原文翻译.md"

    @property
    def asset_dir(self) -> Path:
        return self.output_dir / "assets" / self.detail.stem


def root_pdfs(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.pdf") if p.is_file())


def records() -> list[Record]:
    result: list[Record] = []
    for source in root_pdfs(MAIN_DIR):
        match = re.match(r"(\d+)_", source.name)
        if not match:
            continue
        detail = MAIN_DETAILS / next(
            (p.name for p in MAIN_DETAILS.glob(f"{match.group(1)}_*.md") if p.name != "README.md"),
            "",
        )
        if detail.name:
            result.append(Record(source, detail, MAIN_DIR / "中文翻译"))
    for source in root_pdfs(OTHER_DIR):
        detail_name = OTHER_MAP.get(source.name)
        if detail_name:
            result.append(Record(source, OTHER_DETAILS / detail_name, OTHER_DIR / "中文翻译"))
    return result


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, encoding="utf-8", errors="replace")


def pdf_title(source: Path) -> str:
    info = run("pdfinfo", str(source))
    for line in info.splitlines():
        if line.startswith("Title:"):
            title = line.split(":", 1)[1].strip()
            if title:
                return title
    return source.stem


def pdf_pages(source: Path) -> list[str]:
    raw = run("pdftotext", "-raw", str(source), "-")
    pages = raw.split("\f")
    while pages and not pages[-1].strip():
        pages.pop()
    return pages


def clean_page(text: str) -> str:
    text = text.replace("\r", "")
    text = text.replace("\u00ad", "")
    # Join words split by a line-end hyphen, but leave minus signs and formulas.
    text = re.sub(r"(?<=[A-Za-z])-[ \t]*\n[ \t]*(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def is_formula_line(line: str) -> bool:
    """Recognize a likely displayed equation in pdftotext's line stream."""
    if len(line) > 260:
        return False
    if re.search(r"[∑∫√±×÷∞∂∼⊗πγμωτλ]|\\(?:dot|sum|mathbb|mathrm)", line):
        if not re.match(r"^[∑∫√±×∞∂∼⊗πγμωτλX]", line):
            return False
        return len(re.findall(r"[A-Za-z]{2,}", line)) <= 8
    if "=" not in line:
        return line.strip() in {"X", "Y", "Z", "∑"}
    prefix = line.split("=", 1)[0].strip()
    # A displayed equation normally begins with a variable or a function,
    # rather than a complete prose clause containing an inline equality.
    if prefix and not re.match(
        r"^(?:[A-Za-zπγμωτλ][A-Za-z0-9_]*\s*(?:\(|\*|[−+\-])?|[A-Za-zπγμωτλ](?:\s+[A-Za-zπγμωτλ])?)$",
        prefix,
    ):
        return False
    words = re.findall(r"[A-Za-z]{2,}", line)
    return len(words) <= 24 and not re.match(r"^(?:E-mail|Email|Available)\b", line, re.I)


def is_formula_continuation(line: str) -> bool:
    if len(line) > 180:
        return False
    if re.match(r"^\(?\d+[a-z]?\)?\s*$", line):
        return True
    if re.match(r"^[πγ∑XμωτλqprCFE⊗](?=[^A-Za-z]|$)", line):
        return len(re.findall(r"[A-Za-z]{2,}", line)) <= 12
    return bool(re.match(r"^[|()[\]{}.,;:+\-]", line))


def is_structure_line(line: str) -> bool:
    return bool(
        re.match(
            r"^(?:Abstract\s*[—-]|(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\.?\s+|"
            r"[A-H]\.\s+|\d+[.)]\s+|(?:Fig\.?|Figure|TABLE|Table|Algorithm|ALGORITHM)\s+|"
            r"Corresponding author:|E-mail:|(?:REFERENCES|REFERENCE|BIBLIOGRAPHY)\b)",
            line,
            re.I,
        )
    )


def blocks(text: str) -> list[str]:
    """Split the PDF text layer without losing displayed-equation boundaries."""
    result: list[str] = []
    prose: list[str] = []
    formula: list[str] = []

    def flush_prose() -> None:
        if prose:
            joined = " ".join(prose)
            joined = re.sub(r"\s{2,}", " ", joined)
            joined = re.sub(r"\s+([,.;:!?%)\]])", r"\1", joined)
            joined = re.sub(r"([(\[])\s+", r"\1", joined)
            result.append(joined)
            prose.clear()

    def flush_formula() -> None:
        if formula:
            joined = " ".join(formula)
            joined = re.sub(r"\s{2,}", " ", joined).strip()
            result.append(joined)
            formula.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_formula()
            flush_prose()
            continue
        if is_formula_line(line) or (formula and is_formula_continuation(line)):
            flush_prose()
            formula.append(line)
            continue
        flush_formula()
        if is_structure_line(line):
            flush_prose()
            result.append(line)
        else:
            prose.append(line)
    flush_formula()
    flush_prose()
    return result


def is_formula(block: str) -> bool:
    if is_structure_line(block) or is_caption(block):
        return False
    return len(block) <= 650 and is_formula_line(block)


def is_heading(block: str) -> bool:
    if len(block) > 140 or block.endswith((".", ",", ";", ":")):
        return False
    if re.match(r"^(?:[IVX]+\.?|[A-Z]\.?|\d+(?:\.\d+)*[.)]?)\s+", block):
        return True
    return block.isupper() and len(block.split()) <= 12


def is_reference_heading(block: str) -> bool:
    return bool(re.match(r"^(?:REFERENCES|REFERENCE|BIBLIOGRAPHY)\b", block, re.I))


def is_caption(block: str) -> bool:
    return bool(
        re.match(
            r"^(?:Fig\.?|Figure|TABLE|Table|Algorithm|ALGORITHM)\s*[A-Za-z0-9IVX.-]*",
            block,
            re.I,
        )
    )


def is_metadata_block(block: str) -> bool:
    return bool(
        re.match(
            r"^(?:arXiv:|\[cs\.|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)|"
            r"Corresponding author:|E-mail:)",
            block,
            re.I,
        )
    )


def split_for_model(text: str, limit: int = 300) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\[0-9])", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > limit:
            words = sentence.split()
            while words:
                part: list[str] = []
                size = 0
                while words and (not part or size + len(words[0]) + 1 <= limit):
                    word = words.pop(0)
                    part.append(word)
                    size += len(word) + 1
                chunks.append(" ".join(part))
            continue
        if not current:
            current = sentence
        elif len(current) + len(sentence) + 1 <= limit:
            current += " " + sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


class TextTranslator(Protocol):
    """Translation interface shared by local and network-backed engines."""

    chunk_limit: int

    def translate(self, texts: Iterable[str], cache: dict[str, str] | None = None) -> list[str]:
        ...


class Translator:
    chunk_limit = 300

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: str = "cuda",
        batch_size: int = 12,
    ) -> None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        import torch

        self.torch = torch
        self.device = device if device == "cuda" and torch.cuda.is_available() else "cpu"
        self.batch_size = max(1, batch_size)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, src_lang="eng_Latn")
        model_kwargs = {"dtype": torch.float16} if self.device == "cuda" else {}
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name, **model_kwargs)
        self.model.to(self.device)
        self.model.eval()
        self.target_id = self.tokenizer.convert_tokens_to_ids("zho_Hans")

    def translate(self, texts: Iterable[str], cache: dict[str, str] | None = None) -> list[str]:
        items = list(texts)
        if not items:
            return []
        cache = cache if cache is not None else {}
        missing = list(dict.fromkeys(item for item in items if item not in cache))
        for start in range(0, len(missing), self.batch_size):
            batch_text = missing[start : start + self.batch_size]
            encoded = self.tokenizer(
                batch_text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=384,
            ).to(self.device)
            with self.torch.inference_mode():
                generated = self.model.generate(
                    **encoded,
                    forced_bos_token_id=self.target_id,
                    max_new_tokens=320,
                    num_beams=4,
                )
            translated = [
                normalize_translation(item)
                for item in self.tokenizer.batch_decode(generated, skip_special_tokens=True)
            ]
            for source, target in zip(batch_text, translated):
                cache[source] = target
        for item in items:
            cache[item] = normalize_translation(cache[item])
        return [cache[item] for item in items]


class GoogleMobileTranslator:
    """Translate prose through Google Translate's public mobile page.

    The implementation deliberately sends one bounded paragraph at a time,
    retries only transient failures, and leaves formulas, citations, and
    references to the local parser.  It is selected explicitly through the
    command line; the original local NLLB path remains available for an
    offline-only rebuild.
    """

    chunk_limit = 1_600
    endpoint = "https://translate.google.com/m"

    def __init__(self, request_delay: float = 0.25, retries: int = 4) -> None:
        self.request_delay = max(0.0, request_delay)
        self.retries = max(0, retries)

    @staticmethod
    def _extract_translation(body: str) -> str:
        match = re.search(r'<div class="result-container">(.*?)</div>', body, re.S)
        if not match:
            raise RuntimeError("Google Translate response did not contain a translated result.")
        result = re.sub(r"<br\\s*/?>", "\\n", match.group(1), flags=re.I)
        result = re.sub(r"<[^>]+>", "", result)
        result = html.unescape(result).strip()
        if not result:
            raise RuntimeError("Google Translate returned an empty result.")
        return result

    def _translate_one(self, text: str) -> str:
        query = urlencode({"sl": "en", "tl": "zh-CN", "q": text})
        request = Request(
            f"{self.endpoint}?{query}",
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
        )
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8", errors="replace")
                if self.request_delay:
                    time.sleep(self.request_delay)
                return self._extract_translation(body)
            except (HTTPError, URLError, TimeoutError) as exc:
                if attempt >= self.retries:
                    raise RuntimeError(f"Translation request failed after retries: {exc}") from exc
                # Keep the pause short and bounded so an interrupted batch can
                # be resumed from its cache without losing completed pages.
                time.sleep(min(8.0, 0.75 * (2**attempt)))
        raise AssertionError("unreachable")

    def translate(self, texts: Iterable[str], cache: dict[str, str] | None = None) -> list[str]:
        items = list(texts)
        if not items:
            return []
        cache = cache if cache is not None else {}
        for item in dict.fromkeys(item for item in items if item not in cache):
            cache[item] = normalize_translation(self._translate_one(item))
        return [normalize_translation(cache[item]) for item in items]


def render_pages(record: Record, page_count: int) -> list[Path]:
    record.asset_dir.mkdir(parents=True, exist_ok=True)
    prefix = record.asset_dir / "page"
    order_marker = record.asset_dir / ".page-order-v2"
    expected = [record.asset_dir / f"page-{i:02d}.jpg" for i in range(1, page_count + 1)]
    if order_marker.exists() and all(path.exists() for path in expected):
        return expected
    for old in record.asset_dir.glob("page-*.jpg"):
        old.unlink()
    subprocess.run(
        [
            "pdftoppm",
            "-jpeg",
            "-r",
            "110",
            "-jpegopt",
            "quality=78",
            str(record.source),
            str(prefix),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    generated = sorted(
        record.asset_dir.glob("page-*.jpg"),
        key=lambda path: int(re.search(r"page-(\d+)\.jpg$", path.name).group(1)),
    )
    # pdftoppm writes page-1.jpg; normalize to the two-digit names used in MD.
    normalized: list[Path] = []
    for index, path in enumerate(generated, 1):
        target = record.asset_dir / f"page-{index:02d}.jpg"
        if path != target:
            path.rename(target)
        normalized.append(target)
    order_marker.write_text("natural numeric page order\n", encoding="utf-8")
    return normalized


def relpath(path: Path, start: Path) -> str:
    return Path(os.path.relpath(path, start)).as_posix()


def md_link(label: str, target: str) -> str:
    target = f"<{target}>" if " " in target else target
    return f"[{label}]({target})"


def formula_block(block: str) -> str:
    return "**公式（按原文提取）**\n\n```text\n" + block + "\n```"


def translate_page(
    page: str,
    translator: TextTranslator | None,
    reference_mode: bool,
    cache: dict[str, str] | None = None,
) -> tuple[str, bool]:
    page = clean_page(page)
    if not page:
        return "_（本页无可提取文字，请以页面图片为准。）_", reference_mode
    page_blocks = blocks(page)
    output: list[str | list[str]] = []
    pending: list[str] = []
    for block in page_blocks:
        if is_reference_heading(block):
            reference_mode = True
            output.append(block)
        elif reference_mode:
            output.append(block)
        elif is_metadata_block(block):
            output.append(block)
        elif is_formula(block):
            output.append(formula_block(block))
        else:
            chunks = split_for_model(block, limit=translator.chunk_limit if translator else 300)
            if translator is None:
                output.append(block)
            else:
                slots: list[str] = []
                for chunk in chunks:
                    marker = f"__TRANSLATION_{len(pending)}__"
                    pending.append(chunk)
                    slots.append(marker)
                output.append(slots)
    translated = translator.translate(pending, cache) if translator is not None else []
    translated_by_marker = {
        f"__TRANSLATION_{index}__": value
        for index, value in enumerate(translated)
    }
    rendered: list[str] = []
    for item in output:
        if isinstance(item, list):
            rendered.append(" ".join(translated_by_marker[marker] for marker in item))
        else:
            rendered.append(item)
    return "\n\n".join(rendered), reference_mode


def detail_title(detail: Path) -> str:
    lines = detail.read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            title = re.sub(r"^#\s*", "", line).strip()
            if title and title not in {"标题", "Title"}:
                return title
            for candidate in lines[index + 1 :]:
                candidate = candidate.strip()
                if candidate and not candidate.startswith(("#", ">", "-", "*")):
                    return candidate
    return detail.stem


def build(
    record: Record,
    translator: TextTranslator | None,
    force: bool,
    cache: dict[str, str] | None = None,
) -> Path:
    if record.output.exists() and not force:
        return record.output
    record.output_dir.mkdir(parents=True, exist_ok=True)
    pages = pdf_pages(record.source)
    image_paths = render_pages(record, len(pages))
    title = pdf_title(record.source)
    chinese_title = detail_title(record.detail) if record.detail.exists() else record.detail.stem
    pdf_rel = relpath(record.source, record.output.parent)
    detail_rel = relpath(record.detail, record.output.parent)
    lines = [
        f"# {chinese_title}：原文忠实翻译",
        "",
        f"> 原文标题：{title}",
        f"> 原文 PDF：{md_link(record.source.name, pdf_rel)}",
        f"> 对应中文详解：{md_link(record.detail.name, detail_rel)}",
        "> 翻译范围：按本地英文 PDF 逐页整理；图号、公式、表号和参考文献以原文页面为准。",
        "> 使用说明：页面图片是原文核对依据。PDF 文本层对双栏、公式和表格的提取可能不完整，遇到提取异常时以页面图片和原 PDF 为准。",
        "",
        "---",
        "",
    ]
    reference_mode = False
    for index, (page, image) in enumerate(zip(pages, image_paths), 1):
        translated_page, reference_mode = translate_page(
            page,
            translator,
            reference_mode,
            cache,
        )
        lines.extend(
            [
                f"## 原文第 {index} 页",
                "",
                f"![原文第 {index} 页（含图表与公式）]({relpath(image, record.output.parent)})",
                "",
                translated_page,
                "",
            ]
        )
    record.output.write_text("\n".join(lines), encoding="utf-8")
    return record.output


def write_indexes(all_records: list[Record]) -> None:
    """Write stable entry points so each source PDF has a visible translation link."""
    groups = (
        (MAIN_DIR, MAIN_DIR / "中文翻译" / "README.md", "主论文中文翻译"),
        (OTHER_DIR, OTHER_DIR / "中文翻译" / "README.md", "扩展论文中文翻译"),
    )
    for source_dir, index_path, title in groups:
        group = [record for record in all_records if record.source.parent == source_dir]
        index_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# {title}",
            "",
            f"> 共 {len(group)} 篇。每篇译文按英文 PDF 逐页整理，保留对应原文页面图，用于核对图表、公式和排版。",
            "> 参考文献段落保留英文原文；PDF 文本层若无法完整提取公式或表格，以页面图和原始 PDF 为准。",
            "",
            "| 序号 | 英文论文 | 中文译文 | 中文详解 | 页数 |",
            "|---:|---|---|---|---:|",
        ]
        for number, record in enumerate(group, 1):
            pages = len(pdf_pages(record.source))
            output = (
                md_link(record.output.name, relpath(record.output, index_path.parent))
                if record.output.exists()
                else "待生成"
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(number),
                        md_link(record.source.name, relpath(record.source, index_path.parent)),
                        output,
                        md_link(record.detail.name, relpath(record.detail, index_path.parent)),
                        str(pages),
                    ]
                )
                + " |"
            )
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def select(all_records: list[Record], args: argparse.Namespace) -> list[Record]:
    selected = all_records
    if args.group == "main":
        selected = [record for record in selected if record.source.parent == MAIN_DIR]
    elif args.group == "other":
        selected = [record for record in selected if record.source.parent == OTHER_DIR]
    if args.files:
        wanted = set(args.files)
        selected = [record for record in selected if record.source.name in wanted]
    if args.limit:
        selected = selected[: args.limit]
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=["main", "other", "all"], default="all")
    parser.add_argument("--files", nargs="*", help="Exact PDF basenames")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--engine",
        choices=("nllb", "google-mobile", "none"),
        default="nllb",
        help="Translation engine. google-mobile is higher quality but requires network access.",
    )
    parser.add_argument("--no-model", action="store_true", help="Keep extracted English text; useful for format tests")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--request-delay", type=float, default=0.25)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()

    all_records = records()
    selected = select(all_records, args)
    if not selected:
        raise SystemExit("No matching PDFs with a Chinese detail document were found.")
    cache_path = args.cache or (
        GOOGLE_MOBILE_CACHE_PATH if args.engine == "google-mobile" else CACHE_PATH
    )
    cache: dict[str, str] = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    if args.no_model or args.engine == "none":
        translator: TextTranslator | None = None
    elif args.engine == "google-mobile":
        translator = GoogleMobileTranslator(request_delay=args.request_delay)
    else:
        translator = Translator(device=args.device, batch_size=args.batch_size)
    for index, record in enumerate(selected, 1):
        print(f"[{index}/{len(selected)}] {record.source.name}", flush=True)
        started = time.monotonic()
        output = build(record, translator, args.force, cache)
        if translator is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"      -> {output}", flush=True)
        print(f"      elapsed={time.monotonic() - started:.1f}s cache={len(cache)}", flush=True)
    write_indexes(all_records)


if __name__ == "__main__":
    main()
