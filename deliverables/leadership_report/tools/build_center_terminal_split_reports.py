#!/usr/bin/env python3
"""Build the cooperative-search and terminal-registration Chinese reports."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Sequence
import warnings

warnings.filterwarnings(
    "ignore",
    message="Unable to import Axes3D.*",
    category=UserWarning,
    module="matplotlib.projections",
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Polygon
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = (
    ROOT / "research_modules" / "independent_experiments" / "center_terminal_cv_campaign"
)
OUTPUTS_DIR = EXPERIMENT_ROOT / "outputs"
ASSET_DIR = ROOT / "deliverables" / "leadership_report" / "assets" / "center_terminal_split_reports"
REPORT_DIR = ROOT / "deliverables" / "leadership_report"
BENCHMARK_PATH = OUTPUTS_DIR / "gnn_offline_benchmark_20260816" / "benchmark_summary.json"
TERMINAL_SELECTION_ROOT = OUTPUTS_DIR / "terminal_gnn_diagnostic_selection_20260819_v2"
TERMINAL_SELECTION_PATH = TERMINAL_SELECTION_ROOT / "selection_summary.json"
SEARCH_MATRIX_ROOT = OUTPUTS_DIR / "offline_search_100pct_cues_20260819"
SEARCH_MATRIX_PATH = SEARCH_MATRIX_ROOT / "matrix_summary.json"
SEARCH_CELLS_PATH = (
    OUTPUTS_DIR
    / "airsim_n20_formal_v3_20260816"
    / "search"
    / "search_cells.json"
)

sys.path.insert(0, str(ROOT / "research_modules" / "independent_experiments"))

from center_terminal_cv_campaign.build_three_scale_report import (  # noqa: E402
    RUN_SPECS,
    BenchmarkEvidence,
    RunEvidence,
    fixture_counts,
    load_benchmark,
    load_evidence,
)


SEARCH_MD = REPORT_DIR / "协同搜索试验报告_CN.md"
SEARCH_DOCX = REPORT_DIR / "协同搜索试验报告_CN.docx"
TERMINAL_MD = REPORT_DIR / "末端目标配准试验报告_CN.md"
TERMINAL_DOCX = REPORT_DIR / "末端目标配准试验报告_CN.docx"


def _ratio(value: Any, digits: int = 4) -> str:
    return f"{float(value):.{digits}f}"


def _percent(value: Any, digits: int = 1) -> str:
    return f"{100.0 * float(value):.{digits}f}%"


def _table(headers: Sequence[Any], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(str(value) for value in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def _figure(name: str, caption: str) -> str:
    return f"![{caption}](assets/center_terminal_split_reports/{name})"


def _load_evidence() -> tuple[tuple[RunEvidence, ...], BenchmarkEvidence]:
    runs = tuple(load_evidence(OUTPUTS_DIR, spec) for spec in RUN_SPECS)
    return runs, load_benchmark(BENCHMARK_PATH)


def _load_search_matrix() -> dict[str, Any]:
    if not SEARCH_MATRIX_PATH.is_file():
        raise FileNotFoundError(SEARCH_MATRIX_PATH)
    payload = json.loads(SEARCH_MATRIX_PATH.read_text(encoding="utf-8"))
    if payload.get("matrix_status") != "complete":
        raise ValueError("offline search matrix is not complete")
    if int(payload.get("run_count", 0)) != int(payload.get("expected_run_count", -1)):
        raise ValueError("offline search matrix run count is incomplete")
    return payload


def _load_terminal_selection() -> dict[str, Any]:
    if not TERMINAL_SELECTION_PATH.is_file():
        raise FileNotFoundError(TERMINAL_SELECTION_PATH)
    payload = json.loads(TERMINAL_SELECTION_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "terminal-crossview-testset-diagnostic-selection-v1":
        raise ValueError("unsupported terminal selection evidence")
    if payload.get("diagnostic_testset_tuning") is not True:
        raise ValueError("terminal parameter evidence must disclose test-set tuning")
    scenarios = payload.get("selected_cold_scenario_metrics")
    if not isinstance(scenarios, list) or len(scenarios) != 3:
        raise ValueError("terminal selection evidence is incomplete")
    if int(payload.get("online_truth_leakage_count", -1)) != 0:
        raise ValueError("terminal selection evidence contains online truth leakage")
    return payload


def _configure_plotting() -> None:
    plt.rcParams.update(
        {
            "font.family": "Noto Sans CJK JP",
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _flow_box(
    axis: plt.Axes,
    center: tuple[float, float],
    text: str,
    color: str,
    *,
    width: float = 0.15,
    height: float = 0.27,
) -> None:
    x, y = center
    axis.add_patch(
        FancyBboxPatch(
            (x - width / 2.0, y - height / 2.0),
            width,
            height,
            boxstyle="round,pad=0.015,rounding_size=0.018",
            facecolor=color,
            edgecolor="#39434b",
            linewidth=1.2,
        )
    )
    axis.text(x, y, text, ha="center", va="center", fontsize=10, linespacing=1.4)


def _flow_arrow(axis: plt.Axes, left: float, right: float, y: float = 0.58) -> None:
    axis.add_patch(
        FancyArrowPatch(
            (left, y),
            (right, y),
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.35,
            color="#46515a",
        )
    )


def _build_search_flow(path: Path) -> None:
    _configure_plotting()
    fig, axis = plt.subplots(figsize=(15.8, 5.0))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    centers = (0.09, 0.255, 0.42, 0.585, 0.75, 0.915)
    labels = (
        "80%精度、80%召回率\n中心线索",
        "线索单元\n空白走廊单元",
        "搜索收益矩阵\n概率、视场、转向、复访",
        "匈牙利一一分配\n相机与单元不冲突",
        "连续读取3帧\n检测框最长边≥10像素",
        "连续2帧确认\n未确认单元进入后续复访",
    )
    colors = ("#dfeaf1", "#e8f0df", "#f5e9cb", "#eedfd9", "#dfe8ef", "#e5ece4")
    for center, label, color in zip(centers, labels, colors, strict=True):
        _flow_box(axis, (center, 0.58), label, color, width=0.14)
    for left, right in zip(centers[:-1], centers[1:], strict=True):
        _flow_arrow(axis, left + 0.072, right - 0.072)
    axis.text(
        0.5,
        0.18,
        "没有形成连续确认时，只记录该单元已观察；系统不生成目标身份，也不把一次未发现写成目标不存在。",
        ha="center",
        va="center",
        fontsize=11,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f5f6f7", "edgecolor": "#9aa2a8"},
    )
    axis.set_title("协同搜索计算流程", fontsize=15, pad=10)
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def _box_faces(cell: dict[str, Any]) -> list[list[tuple[float, float, float]]]:
    north, east, down = (float(value) for value in cell["center_ned_m"])
    north_half, east_half, down_half = (
        float(value) for value in cell["half_extent_ned_m"]
    )
    east_min, east_max = east - east_half, east + east_half
    north_min, north_max = north - north_half, north + north_half
    altitude = -down
    altitude_min, altitude_max = altitude - down_half, altitude + down_half
    vertices = (
        (east_min, north_min, altitude_min),
        (east_max, north_min, altitude_min),
        (east_max, north_max, altitude_min),
        (east_min, north_max, altitude_min),
        (east_min, north_min, altitude_max),
        (east_max, north_min, altitude_max),
        (east_max, north_max, altitude_max),
        (east_min, north_max, altitude_max),
    )
    return [
        [vertices[index] for index in face]
        for face in (
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        )
    ]


def _boxes_overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return all(
        abs(float(first["center_ned_m"][index]) - float(second["center_ned_m"][index]))
        <= float(first["half_extent_ned_m"][index])
        + float(second["half_extent_ned_m"][index])
        for index in range(3)
    )


def _project_3d(point: tuple[float, float, float]) -> tuple[float, float]:
    east, north, altitude = point
    east_scaled = east / 1300.0
    north_scaled = (north - 2500.0) / 1000.0
    altitude_scaled = altitude / 250.0
    return (
        0.95 * east_scaled - 0.68 * north_scaled,
        0.34 * east_scaled + 0.34 * north_scaled + 1.08 * altitude_scaled,
    )


def _draw_projected_box(
    axis: plt.Axes,
    cell: dict[str, Any],
    *,
    facecolor: str,
    edgecolor: str,
    alpha: float,
    linewidth: float,
) -> None:
    for face in _box_faces(cell):
        axis.add_patch(
            Polygon(
                [_project_3d(point) for point in face],
                closed=True,
                facecolor=facecolor,
                edgecolor=edgecolor,
                linewidth=linewidth,
                alpha=alpha,
            )
        )


def _build_search_cells_3d(path: Path) -> None:
    _configure_plotting()
    if not SEARCH_CELLS_PATH.is_file():
        raise FileNotFoundError(SEARCH_CELLS_PATH)
    cells = json.loads(SEARCH_CELLS_PATH.read_text(encoding="utf-8"))
    source_cells = [cell for cell in cells if cell["cell_kind"] == "source_directed"]
    gap_cells = [cell for cell in cells if cell["cell_kind"] == "unbound_gap"]
    overlap_count = sum(
        any(_boxes_overlap(source, gap) for gap in gap_cells) for source in source_cells
    )

    fig, axis = plt.subplots(figsize=(13.8, 8.6))
    for east in (-650.0, -325.0, 0.0, 325.0, 650.0):
        start = _project_3d((east, 2500.0, 0.0))
        end = _project_3d((east, 3500.0, 0.0))
        axis.plot((start[0], end[0]), (start[1], end[1]), color="#d9dde0", linewidth=0.7)
    for north in (2500.0, 2750.0, 3000.0, 3250.0, 3500.0):
        start = _project_3d((-650.0, north, 0.0))
        end = _project_3d((650.0, north, 0.0))
        axis.plot((start[0], end[0]), (start[1], end[1]), color="#d9dde0", linewidth=0.7)

    for index, cell in enumerate(gap_cells, start=1):
        _draw_projected_box(
            axis,
            cell,
            facecolor="#4f8fbf",
            edgecolor="#28658f",
            alpha=0.075,
            linewidth=0.9,
        )
        north, east, down = (float(value) for value in cell["center_ned_m"])
        altitude_top = -down + float(cell["half_extent_ned_m"][2])
        label = _project_3d((east, north, altitude_top + 8.0))
        axis.text(label[0], label[1], f"G{index:02d}", color="#1f5578", fontsize=8)

    for index, cell in enumerate(source_cells, start=1):
        _draw_projected_box(
            axis,
            cell,
            facecolor="#ef9b3d",
            edgecolor="#a95712",
            alpha=0.42,
            linewidth=0.8,
        )
        north, east, down = (float(value) for value in cell["center_ned_m"])
        center = _project_3d((east, north, -down))
        label = _project_3d((east, north, -down + 34.0))
        axis.scatter(center[0], center[1], color="#a33b20", s=13, zorder=5)
        axis.text(label[0], label[1], f"S{index:02d}", color="#7f2d18", fontsize=6.5)

    corridor = {
        "center_ned_m": (3000.0, 0.0, -145.0),
        "half_extent_ned_m": (500.0, 650.0, 75.0),
    }
    for face in _box_faces(corridor):
        projected = [_project_3d(point) for point in face]
        axis.add_patch(
            Polygon(
                projected,
                closed=True,
                fill=False,
                edgecolor="#5d666d",
                linewidth=1.15,
                linestyle="--",
            )
        )

    origin = _project_3d((-700.0, 2400.0, 0.0))
    directions = (
        ((-350.0, 2400.0, 0.0), "东", "#37688a"),
        ((-700.0, 2750.0, 0.0), "北", "#4e7954"),
        ((-700.0, 2400.0, 110.0), "高", "#8a5437"),
    )
    for endpoint_3d, label_text, color in directions:
        endpoint = _project_3d(endpoint_3d)
        axis.add_patch(
            FancyArrowPatch(
                origin,
                endpoint,
                arrowstyle="-|>",
                mutation_scale=12,
                linewidth=1.4,
                color=color,
            )
        )
        axis.text(endpoint[0], endpoint[1], label_text, color=color, fontsize=10, weight="bold")

    axis.relim()
    axis.autoscale_view()
    axis.margins(0.08)
    axis.set_aspect("equal", adjustable="datalim")
    axis.axis("off")
    axis.legend(
        handles=(
            Patch(facecolor="#ef9b3d", edgecolor="#a95712", label="中心线索单元（S）"),
            Patch(facecolor="#4f8fbf", edgecolor="#28658f", label="空白走廊单元（G）"),
            Patch(facecolor="white", edgecolor="#5d666d", linestyle="--", label="来袭走廊边界"),
        ),
        loc="upper left",
        framealpha=0.95,
    )
    axis.set_title("20目标场景的线索单元与空白走廊单元", fontsize=15, pad=18)
    fig.text(
        0.5,
        0.035,
        f"线索单元{len(source_cells)}个，空白单元{len(gap_cells)}个；"
        f"其中{overlap_count}个线索单元与至少一个空白单元发生几何重叠。",
        ha="center",
        fontsize=10.5,
        color="#343a40",
    )
    fig.savefig(path, dpi=210, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)


def _build_terminal_flow(path: Path) -> None:
    _configure_plotting()
    fig, axes = plt.subplots(2, 1, figsize=(15.8, 7.8))
    for axis in axes:
        axis.set_xlim(0.0, 1.0)
        axis.set_ylim(0.0, 1.0)
        axis.axis("off")
    top_centers = (0.09, 0.255, 0.42, 0.585, 0.75, 0.915)
    top_labels = (
        "中心线索\n位置、速度、协方差",
        "外推到图像测量时刻\n协方差同步增长",
        "机体、云台、相机\n完整旋转和安装偏移",
        "时间、像面、运动门控",
        "匈牙利一一匹配",
        "最近3帧至少2帧一致\n建立交接关系",
    )
    bottom_labels = (
        "各机匿名局部航迹",
        "0.16秒内时间对齐",
        "双视线交会\n恢复三维运动",
        "几何门控\n可选图网络修正代价",
        "相机对内匈牙利匹配",
        "视场区相机关系\n合并跨相机目标簇",
    )
    colors = ("#dfeaf1", "#e8f0df", "#f5e9cb", "#eedfd9", "#dfe8ef", "#e5ece4")
    for row, labels in enumerate((top_labels, bottom_labels)):
        axis = axes[row]
        for center, label, color in zip(top_centers, labels, colors, strict=True):
            _flow_box(axis, (center, 0.5), label, color, width=0.14, height=0.34)
        for left, right in zip(top_centers[:-1], top_centers[1:], strict=True):
            _flow_arrow(axis, left + 0.072, right - 0.072, y=0.5)
    axes[0].set_title("中心线索与机载局部航迹交接", fontsize=14, pad=8)
    axes[1].set_title("拦截无人机之间的跨视角关联", fontsize=14, pad=8)
    fig.suptitle("末端目标配准计算流程", fontsize=16, y=0.995)
    fig.tight_layout(h_pad=1.2)
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def build_search_assets() -> tuple[Path, ...]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    sources = {
        "search100_01_flow.png": SEARCH_MATRIX_ROOT / "figures" / "01_search_flow.png",
        "search100_02_cells_3d.png": SEARCH_MATRIX_ROOT / "figures" / "02_search_cells_3d.png",
        "search100_03_results.png": SEARCH_MATRIX_ROOT / "figures" / "03_search_results.png",
        "search100_04_coverage_budget.png": SEARCH_MATRIX_ROOT
        / "figures"
        / "04_search_coverage_budget.png",
        "search100_05_timing.png": SEARCH_MATRIX_ROOT / "figures" / "05_search_timing.png",
    }
    copied: list[Path] = []
    for destination_name, source in sources.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = ASSET_DIR / destination_name
        shutil.copy2(source, destination)
        copied.append(destination)
    return tuple(copied)


def build_assets() -> tuple[Path, ...]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    build_search_assets()
    terminal_flow = ASSET_DIR / "06_terminal_flow.png"
    _build_terminal_flow(terminal_flow)

    sources = {
        "07_handover_geometry.png": OUTPUTS_DIR / "three_scale_report_figures" / "04_handover_geometry.png",
        "08_handover_results.png": OUTPUTS_DIR / "three_scale_report_figures" / "05_handover_results.png",
        "09_projection_ellipse_matching.png": OUTPUTS_DIR / "airsim_n20_formal_v3_20260816" / "center_handover" / "figures" / "projection_ellipse_matching.png",
        "10_crossview_rays.png": OUTPUTS_DIR / "three_scale_report_figures" / "06_crossview_rays.png",
        "11_crossview_funnel.png": OUTPUTS_DIR / "three_scale_report_figures" / "07_crossview_funnel.png",
        "12_crossview_results.png": OUTPUTS_DIR / "three_scale_report_figures" / "08_scaling_results.png",
        "13_local_pixel_tracks.png": OUTPUTS_DIR / "airsim_n20_formal_v3_20260816" / "crossview" / "figures" / "02_local_pixel_tracks.png",
        "14_crossview_relation_graph.png": OUTPUTS_DIR / "airsim_n20_formal_v3_20260816" / "crossview" / "figures" / "03_crossview_relation_graph.png",
    }
    for destination_name, source in sources.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, ASSET_DIR / destination_name)
    return tuple(sorted(ASSET_DIR.glob("*.png")))


def _build_terminal_pose_chain(path: Path) -> None:
    _configure_plotting()
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.0))
    left, right = axes
    for axis in axes:
        axis.set_xlim(0.0, 1.0)
        axis.set_ylim(0.0, 1.0)
        axis.axis("off")
    centers = ((0.12, "北东地坐标", "#dfeaf1"), (0.39, "机体坐标", "#e8f0df"), (0.66, "云台坐标", "#f5e9cb"), (0.90, "相机坐标", "#eedfd9"))
    for x, label, color in centers:
        _flow_box(left, (x, 0.64), label, color, width=0.17, height=0.20)
    for x1, x2, label in ((0.21, 0.30, "R_B^N"), (0.48, 0.57, "R_G^B"), (0.75, 0.81, "R_C^G")):
        _flow_arrow(left, x1, x2, y=0.64)
        left.text((x1 + x2) / 2.0, 0.75, label, ha="center", fontsize=11)
    left.text(0.50, 0.34, "p_C = R_C^G R_G^B R_B^N (p_N - o_C^N)", ha="center", fontsize=13)
    left.text(0.50, 0.16, "旋转方向逐级固定，不能用消息到达时刻的姿态替代图像拍摄时刻姿态", ha="center", fontsize=10.5)
    left.set_title("坐标旋转链", fontsize=14)

    right.plot((0.12, 0.38), (0.62, 0.62), color="#46515a", linewidth=3)
    right.plot((0.38, 0.70), (0.62, 0.48), color="#46515a", linewidth=3)
    right.scatter((0.12, 0.38, 0.70), (0.62, 0.62, 0.48), s=(110, 90, 90), color=("#567b9a", "#d3a249", "#b66a5e"), zorder=3)
    right.text(0.12, 0.72, "机体参考点", ha="center", fontsize=11)
    right.text(0.38, 0.72, "云台转轴", ha="center", fontsize=11)
    right.text(0.70, 0.58, "相机光心", ha="center", fontsize=11)
    right.add_patch(FancyArrowPatch((0.70, 0.48), (0.92, 0.34), arrowstyle="-|>", mutation_scale=14, color="#2c7f54", linewidth=1.8))
    right.text(0.86, 0.46, "反投影视线", color="#2c7f54", fontsize=11)
    right.text(0.50, 0.20, "光心位置同时计入机体至云台转轴、云台转轴至光心两段安装偏移", ha="center", fontsize=10.5)
    right.set_title("视线起点与安装偏移", fontsize=14)
    fig.suptitle("末端相机位姿计算", fontsize=16)
    fig.tight_layout()
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def _build_center_handover_principle(path: Path) -> None:
    _configure_plotting()
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.2))
    left, right = axes
    for axis in axes:
        axis.set_xlim(0.0, 1.0)
        axis.set_ylim(0.0, 1.0)
        axis.axis("off")

    left_nodes = (
        (0.12, 0.72, "中心航迹\n位置、速度、协方差", "#dfeaf1"),
        (0.12, 0.28, "机载局部航迹\n像点、运动、质量", "#e8f0df"),
        (0.50, 0.50, "拍摄时刻对齐\n投影与不确定范围", "#f5e9cb"),
        (0.84, 0.50, "候选关系\n允许未匹配", "#eedfd9"),
    )
    for x, y, label, color in left_nodes:
        _flow_box(left, (x, y), label, color, width=0.23, height=0.24)
    for start in ((0.235, 0.72), (0.235, 0.28)):
        left.add_patch(
            FancyArrowPatch(
                start,
                (0.375, 0.50),
                arrowstyle="-|>",
                mutation_scale=13,
                color="#46515a",
                linewidth=1.4,
            )
        )
    _flow_arrow(left, 0.62, 0.72, y=0.50)
    left.text(
        0.50,
        0.10,
        "先用识别、时效、像面距离和运动连续性形成候选白名单",
        ha="center",
        fontsize=10.5,
        color="#343a40",
    )
    left.set_title("中心航迹投到机载图像", fontsize=14)

    right_nodes = (
        (0.12, 0.72, "几何代价\n像面残差和运动残差", "#dfeaf1"),
        (0.12, 0.28, "可选图神经网络\n输出同目标概率", "#e8f0df"),
        (0.50, 0.50, "形成分配代价矩阵", "#f5e9cb"),
        (0.82, 0.70, "匈牙利一一匹配", "#eedfd9"),
        (0.82, 0.30, "3帧中至少2帧一致\n建立交接", "#e5ece4"),
    )
    for x, y, label, color in right_nodes:
        _flow_box(right, (x, y), label, color, width=0.23, height=0.22)
    for start in ((0.235, 0.72), (0.235, 0.28)):
        right.add_patch(
            FancyArrowPatch(
                start,
                (0.375, 0.50),
                arrowstyle="-|>",
                mutation_scale=13,
                color="#46515a",
                linewidth=1.4,
            )
        )
    right.add_patch(
        FancyArrowPatch(
            (0.615, 0.50),
            (0.705, 0.70),
            arrowstyle="-|>",
            mutation_scale=13,
            color="#46515a",
            linewidth=1.4,
        )
    )
    right.add_patch(
        FancyArrowPatch(
            (0.82, 0.59),
            (0.82, 0.41),
            arrowstyle="-|>",
            mutation_scale=13,
            color="#46515a",
            linewidth=1.4,
        )
    )
    right.text(
        0.50,
        0.10,
        "图神经网络只调整已通过几何门控的候选，不能绕过硬门控",
        ha="center",
        fontsize=10.5,
        color="#343a40",
    )
    right.set_title("两条评分路线共用同一分配与确认过程", fontsize=14)
    fig.suptitle("中心航迹与无人机局部航迹交接原理", fontsize=16)
    fig.tight_layout()
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def _build_crossview_hard_gates(path: Path) -> None:
    _configure_plotting()
    fig, axis = plt.subplots(figsize=(15.5, 8.0))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    gates = (
        (0.18, 0.72, "时间对齐", "单点偏差≤0.16秒\n末端时差≤0.65秒\n有效样本≥3", "#dfeaf1"),
        (0.50, 0.72, "交会角", "多时刻中位数≥0.35°\n角度过小则距离不稳定", "#e8f0df"),
        (0.82, 0.72, "视线分离", "两条视线最近点距离\n多时刻中位数≤2米", "#f5e9cb"),
        (0.18, 0.32, "重投影", "交会点投回两台相机\n较大误差中位数≤8像素", "#eedfd9"),
        (0.50, 0.32, "运动拟合", "恒速拟合均方根≤5米\n局部转角≤55°", "#dfe8ef"),
        (0.82, 0.32, "目标尺度", "检测框最长边≥10像素\n估计尺度比约≤1.32", "#e5ece4"),
    )
    for x, y, title, detail, color in gates:
        _flow_box(axis, (x, y), f"{title}\n{detail}", color, width=0.27, height=0.27)
    axis.text(
        0.50,
        0.93,
        "同一候选必须同时通过六项检查；任一项失败，候选不进入图网络和匈牙利匹配",
        ha="center",
        fontsize=12,
        weight="bold",
        color="#2e3439",
    )
    axis.text(
        0.50,
        0.08,
        "阈值来自本轮保存回放配置，用于说明当前试验口径，尚需用导航误差、云台误差和真实检测误差重新标定",
        ha="center",
        fontsize=10.5,
        color="#4a535a",
    )
    axis.set_title("机间配准六类硬门控", fontsize=16, pad=14)
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def _build_crossview_assignment_principle(path: Path) -> None:
    _configure_plotting()
    fig, axis = plt.subplots(figsize=(15.5, 6.2))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    centers = (0.08, 0.245, 0.41, 0.575, 0.74, 0.91)
    labels = (
        "视场区重合\n确定相机对",
        "局部航迹两两组合",
        "六项硬门控",
        "几何代价\n或图网络修正",
        "匈牙利一一匹配\n保留未匹配",
        "多帧确认与\n跨相机目标簇",
    )
    colors = ("#dfeaf1", "#e8f0df", "#f5e9cb", "#eedfd9", "#dfe8ef", "#e5ece4")
    for center, label, color in zip(centers, labels, colors, strict=True):
        _flow_box(axis, (center, 0.56), label, color, width=0.14, height=0.28)
    for left, right in zip(centers[:-1], centers[1:], strict=True):
        _flow_arrow(axis, left + 0.072, right - 0.072, y=0.56)
    axis.text(
        0.575,
        0.25,
        "图网络输入：时间、视线交会、重投影、运动、尺度和相机可信度等候选特征",
        ha="center",
        fontsize=10.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f4f5f6", "edgecolor": "#9aa2a8"},
    )
    axis.text(
        0.50,
        0.09,
        "真实目标编号只用于试验结束后的评分，不参与候选生成、网络计算和输出身份",
        ha="center",
        fontsize=10.5,
        color="#343a40",
    )
    axis.set_title("视场区内的机间目标配准流程", fontsize=16, pad=14)
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def _build_terminal_metric_definition(path: Path) -> None:
    _configure_plotting()
    fig, axis = plt.subplots(figsize=(14.5, 4.2))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    nodes = ((0.12, 0.68, "相机A\n局部航迹"), (0.12, 0.32, "相机B/C\n局部航迹"), (0.45, 0.50, "视场区候选边\n几何或图网络评分"), (0.76, 0.50, "跨相机目标簇"))
    for index, (x, y, label) in enumerate(nodes):
        _flow_box(axis, (x, y), label, ("#dfeaf1", "#e8f0df", "#f5e9cb", "#e5ece4")[index], width=0.20, height=0.22)
    for start in ((0.22, 0.68), (0.22, 0.32)):
        axis.add_patch(FancyArrowPatch(start, (0.34, 0.50), arrowstyle="-|>", mutation_scale=13, color="#46515a", linewidth=1.4))
    _flow_arrow(axis, 0.56, 0.65, y=0.50)
    axis.text(0.76, 0.18, "每个真实目标等权评分：纯度、完整度、独立纯净簇、身份混合、未完成配准", ha="center", fontsize=11, bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f4f5f6", "edgecolor": "#9aa2a8"})
    axis.text(0.45, 0.83, "真实编号只在关联结束后进入离线评分，不进入候选、图网络特征和输出身份", ha="center", fontsize=10.5)
    axis.set_title("机间配准与目标等权评价", fontsize=15)
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def _build_terminal_result_comparison(path: Path, summary: Mapping[str, Any]) -> None:
    _configure_plotting()
    geometry = {item["scenario_id"]: item for item in summary["geometry_scenario_metrics"]}
    gnn = {item["scenario_id"]: item for item in summary["selected_cold_scenario_metrics"]}
    scenario_ids = ("n20_m8", "n20_m30", "n40_m50")
    labels = ("20目标/8机", "20目标/30机", "40目标/50机")
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.3), sharey=True)
    metrics = (
        ("关系精度", "association_precision"),
        ("等权纯度", "target_equal_mean_purity"),
        ("等权完整度", "target_equal_mean_completeness"),
        ("独立纯净簇", "independently_correct_target_rate"),
    )
    positions = list(range(len(metrics)))
    for axis, scenario_id, label in zip(axes, scenario_ids, labels, strict=True):
        axis.bar([value - 0.18 for value in positions], [geometry[scenario_id][key] for _, key in metrics], width=0.36, label="视场区几何", color="#567b9a")
        axis.bar([value + 0.18 for value in positions], [gnn[scenario_id][key] for _, key in metrics], width=0.36, label="视场区图网络", color="#5f9e6e")
        axis.set_xticks(positions, [name for name, _ in metrics], rotation=20)
        axis.set_ylim(0.0, 1.08)
        axis.set_title(label)
        axis.grid(axis="y", alpha=0.22)
    axes[0].set_ylabel("比例")
    axes[-1].legend(loc="lower right")
    fig.suptitle("视场区几何与同批回放图网络结果", fontsize=15)
    fig.tight_layout()
    fig.savefig(path, dpi=190, bbox_inches="tight")
    plt.close(fig)


def build_terminal_assets(selection: Mapping[str, Any]) -> tuple[Path, ...]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    generated = {
        "06_terminal_flow.png": _build_terminal_flow,
        "07_terminal_pose_chain.png": _build_terminal_pose_chain,
        "07b_center_handover_principle.png": _build_center_handover_principle,
        "10b_crossview_hard_gates.png": _build_crossview_hard_gates,
        "11b_crossview_assignment_principle.png": _build_crossview_assignment_principle,
        "12_terminal_metric_comparison.png": lambda path: _build_terminal_result_comparison(path, selection),
        "15_terminal_target_metric.png": _build_terminal_metric_definition,
    }
    for name, builder in generated.items():
        builder(ASSET_DIR / name)
    sources = {
        "08_handover_results.png": OUTPUTS_DIR / "three_scale_report_figures" / "05_handover_results.png",
        "09_projection_ellipse_matching.png": OUTPUTS_DIR / "airsim_n20_formal_v3_20260816" / "center_handover" / "figures" / "projection_ellipse_matching.png",
        "10_crossview_rays.png": OUTPUTS_DIR / "three_scale_report_figures" / "06_crossview_rays.png",
        "13_local_pixel_tracks.png": TERMINAL_SELECTION_ROOT / "selected" / "n20_m30" / "gnn" / "figures" / "02_local_pixel_tracks.png",
        "14_crossview_relation_graph.png": TERMINAL_SELECTION_ROOT / "selected" / "n20_m30" / "gnn" / "figures" / "03_crossview_relation_graph.png",
    }
    copied = []
    for name, source in sources.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = ASSET_DIR / name
        shutil.copy2(source, destination)
        copied.append(destination)
    return tuple(ASSET_DIR / name for name in (*generated, *sources))


def build_search_markdown(runs: Sequence[RunEvidence]) -> str:
    lines = [
        "# 协同搜索试验报告",
        "",
        "本报告说明中心线索不完整时，拦截无人机如何把有限相机资源分配到搜索区域，并把一次检测逐步确认成可交接的匿名局部航迹。结论来自20目标/8机、20目标/30机和40目标/50机三组AirSim单次试验，只用于说明算法流程和规模变化。",
        "",
        "## 一、问题、难点与方法",
        "",
        "### 1.1 当前问题与难点",
        "",
        "中心线索按精度80%、召回率80%构造。以20个真实目标为例，中心给出20条线索，其中16条指向真实目标，4条是错误线索，同时还有4个真实目标没有线索。拦截无人机无法事先判断哪条线索错误，也不能只沿中心线索搜索，否则中心漏掉的目标不会进入机载视场。",
        "",
        "搜索还受到相机容量限制。窄视场相机一次只能观察一个有限区域，同一轮内多架无人机若指向同一位置，会浪费搜索容量；全部无人机只追逐高概率线索，又会放弃空白走廊。搜索结果还要经过10像素门限和连续两帧确认，一次短暂看见不能直接形成稳定航迹。",
        "",
        "### 1.2 搜索单元",
        "",
        "算法先把中心线索和来袭走廊统一表示为搜索单元。这样，正确线索、错误线索和无中心线索覆盖的区域可以进入同一套分配计算。设真实目标数为N，正确中心线索数为T，全部中心线索数为S：",
        "",
        "```text",
        "T = 0.8N",
        "S = T / 0.8 = N",
        "错误线索数 = S - T = 0.2N",
        "中心漏掉目标数 = N - T = 0.2N",
        "```",
        "",
        "每条中心线索按位置和速度外推到规划时刻。外推的用途是把旧线索移到目标当前可能出现的位置，关系式为 `p(t)=p0+vΔt`。搜索范围根据位置协方差确定，三个方向的半宽取 `max(30米, 3sqrt(P_ii))`。本试验位置标准差为1米，三倍标准差小于30米，因此使用30米下限。",
        "",
        "中心漏检目标没有对应线索。算法在北向2500至3500米、东向-650至650米、高度-220至-70米的来袭走廊内增加空白单元，数量取 `max(5, ceil(0.4N))`，单元概率为0.32。空白单元只代表需要查看的区域，不代表已经存在目标。",
        "",
    ]
    cue_rows = []
    for run in runs:
        counts = fixture_counts(run.spec.target_count)
        cue_rows.append(
            (
                run.spec.label,
                counts["true_cues"],
                counts["false_cues"],
                counts["missed_targets"],
                counts["gap_cells"],
                run.search["search_cell_count"],
            )
        )
    lines.extend(_table(("场景", "正确线索", "错误线索", "中心漏掉", "空白单元", "总搜索单元"), cue_rows))
    lines.extend(
        [
            "",
            "下图使用20目标场景保存的搜索单元配置绘制。橙色小立方体表示中心线索单元，蓝色半透明体表示空白走廊单元。两类单元分别生成，当前没有执行空间去重，因此20个线索单元均与至少一个空白单元相交。图中只展示在线搜索区域，不显示目标真值。",
            "",
            _figure("01b_search_cells_3d.png", "线索单元与空白走廊单元的三维关系"),
            "",
        ]
    )
    lines.extend(
        [
            "",
            "### 1.3 搜索收益和一一分配",
            "",
            "每轮先建立相机到搜索单元的收益矩阵。若有M台可用相机、K个有效单元，矩阵共有M行、K列。第i行第j列表示第i台相机本轮查看第j个单元的收益。收益需要兼顾目标概率、相机能否看全、转动和到达代价以及是否刚刚看过：",
            "",
            "```text",
            "U = 3p + 4G - 0.8C_slew - 1.0C_arrival - 4C_repeat",
            "G = p × V × Q",
            "```",
            "",
            "式中，p是单元概率；V是相机在700米观察距离上能够覆盖该单元的比例；Q=1/(1+n)，n为既有覆盖次数。C_slew衡量云台和机体需要转动多少，C_arrival衡量到观察位置的距离，C_repeat压低刚刚看过的单元。19度水平视场角在700米处的名义覆盖宽度约234.3米。范围较大的空白单元一次不容易看全，会通过后续复访补齐。",
            "",
            "矩阵右侧再增加M个空闲列，形成M×(K+M)矩阵，空闲收益为-0.05。匈牙利算法一次选出全局组合，使每台相机最多承担一个单元，每个单元在同一轮最多分给一台相机。某台相机若没有收益高于空闲项的单元，就保持空闲。",
            "",
            _figure("01_search_flow.png", "协同搜索计算流程"),
            "",
            "### 1.4 像素门限、连续确认和未发现处理",
            "",
            "相机被放到单元中心前方700米处，并指向单元中心。每个分配单元连续读取3帧，帧间隔0.1秒。1920×1080、水平视场角19度的机载相机像素焦距约5736.7像素。3米目标在700米处的理想成像最长边约24.6像素，超过10像素接口门限；实际判断仍以AirSim检测框为准。",
            "",
            "同一相机、同一单元内，当前检测与上一帧局部航迹先按检测框中心距离计算代价，超过180像素的组合排除，其余组合使用匈牙利算法一一连接。检测框最长边达到10像素记为可识别，同一局部航迹连续2帧满足门限后才生成确认记录。三帧观察提供三次检测机会，但中间漏掉一帧不能把前后检测直接算成连续两帧。",
            "",
            "本轮未发现或未连续确认时，系统只记录该单元已完成一次观察，不生成目标身份。下一轮重复代价会优先让资源转向尚未覆盖的单元；随时间增加，原单元的重复代价逐步下降，仍可再次分配。当前试验没有根据一次未发现动态降低区域概率，也没有实现长时间休眠航迹重接。",
            "",
            "## 二、试验配置",
            "",
            "### 2.1 场景与设备",
            "",
        ]
    )
    lines.extend(
        _table(
            ("项目", "设置"),
            (
                ("仿真模式", "AirSim ComputerVision"),
                ("规模", "20目标/8机、20目标/30机、40目标/50机"),
                ("目标", "无人机静态网格Actor，速度50米/秒，最长尺寸3米"),
                ("场景", "18秒，状态步长0.1秒，ClockSpeed=0.1"),
                ("机载相机", "1920×1080，水平视场角19度，标称观察距离700米"),
                ("中心线索", "固定构造精度80%、召回率80%；位置标准差1米，速度标准差0.2米/秒"),
                ("检测输入", "AirSim simGetDetections元数据，在线入口去除Actor名称"),
                ("识别条件", "检测框最长边不小于10像素，连续2帧确认"),
                ("分配轮数", "3轮，每个分配单元读取3帧，帧间隔0.1秒"),
                ("随机种子", "20260816；每个规模单次运行"),
            ),
        )
    )
    lines.extend(
        [
            "",
            "### 2.2 评价口径",
            "",
            "搜索单元覆盖表示至少执行过一次观察的单元数；达到10像素表示目标至少有一条检测达到接口门限；连续确认表示同一匿名局部航迹连续两帧通过门限；中心漏检补获表示没有正确中心线索的目标最终被空白单元搜索发现。Actor名称只在运行结束后计算这些指标。",
            "",
            "ComputerVision节点按指令改变位姿，不含飞行动力学。AirSim检测元数据不等同于真实可见光或红外探测器。本试验没有注入导航误差、云台误差、通信丢包和真实检测误差。",
            "",
            "## 三、试验过程、结果与分析",
            "",
            "### 3.1 试验过程",
            "",
            "三组试验使用同一计算流程。每轮先筛除过期线索，建立搜索收益矩阵，完成一一分配，再把ComputerVision节点放到对应观察位置。节点连续读取3帧匿名检测，建立短航迹并执行10像素和连续两帧确认。该轮结束后更新覆盖次数和相机姿态，进入下一轮。三轮结束后，离线使用Actor标签统计目标是否被发现。",
            "",
            _figure("02_search_capacity.png", "三组场景的搜索容量与单元覆盖"),
            "",
            "### 3.2 结果",
            "",
        ]
    )
    capacity_rows = []
    result_rows = []
    for run in runs:
        matrix = f"{run.spec.resource_count}×({run.search['search_cell_count']}+{run.spec.resource_count})"
        capacity_rows.append(
            (
                run.spec.label,
                matrix,
                run.search["assignment_capacity"],
                run.search["covered_cell_count"],
                run.search["unassigned_cell_count"],
                f"{float(run.search['planner_compute_mean_ms']):.3f}毫秒",
            )
        )
        result_rows.append(
            (
                run.spec.label,
                f"{run.search['covered_cell_count']}/{run.search['search_cell_count']}",
                f"{run.search['recognized_target_count']}/{run.spec.target_count}",
                f"{run.search['discovered_target_count']}/{run.spec.target_count}",
                f"{run.search['center_missed_recovered_count']}/{run.search['center_missed_target_count']}",
                run.search["online_detection_count"],
            )
        )
    lines.extend(_table(("场景", "分配矩阵", "三轮容量", "唯一覆盖", "未覆盖", "规划平均耗时"), capacity_rows))
    lines.extend(["", _figure("03_search_results.png", "三组场景的目标发现结果"), ""])
    lines.extend(_table(("场景", "单元覆盖", "达到10像素", "连续确认", "中心漏检补获", "匿名检测记录"), result_rows))
    lines.extend(
        [
            "",
            "### 3.3 结果分析",
            "",
            "20目标/8机共有28个搜索单元，三轮最多提供24个分配槽，因此至少有4个单元无法观察。试验实际覆盖24个单元。20个目标都曾达到10像素，但只有19个形成连续确认；中心漏掉的4个目标补获3个。该场景表明，资源容量不足首先造成区域覆盖缺口，随后压缩重访和连续确认机会。",
            "",
            _figure("04_search_coverage_20_8.png", "20目标/8机场景的搜索单元覆盖"),
            "",
            "20目标/30机首轮容量已经超过28个搜索单元。三轮实际执行44次分配，覆盖全部28个单元，其余16次用于复访。全部20个目标连续确认，中心漏掉的4个目标全部补获。规划平均耗时11.739毫秒。继续增加资源的主要作用已经从首次覆盖转向复访。",
            "",
            "40目标/50机共有56个搜索单元，首轮最多覆盖50个，第二轮补齐其余6个。三轮实际执行88次分配，全部40个目标连续确认，中心漏掉的8个目标全部补获。规划矩阵为50×106，平均计算35.753毫秒。该数字只包含确定性分配计算，不包含相机运动、接口等待和通信排队。",
            "",
            _figure("05_search_coverage_40_50.png", "40目标/50机场景的搜索单元覆盖"),
            "",
            "三组结果支持两个判断。搜索单元数量必须与可用相机和滚动轮数共同核算，资源少于单元时无法依靠分配算法消除物理容量缺口。资源达到全覆盖条件后，空白走廊单元能够补获中心漏检目标。当前证据只有单个种子，不能给出稳定成功概率；真实探测器、机动约束和通信时延仍需另行验证。",
            "",
        ]
    )
    return "\n".join(lines)


def build_search_matrix_markdown(summary: Mapping[str, Any]) -> str:
    aggregates = summary["aggregates"]
    rows_by_scenario: dict[str, list[Mapping[str, Any]]] = {}
    for row in aggregates:
        rows_by_scenario.setdefault(str(row["scenario_label"]), []).append(row)
    for rows in rows_by_scenario.values():
        rows.sort(key=lambda item: float(item["position_sigma_m"]))

    def _scenario_result_rows(scenario_label: str) -> list[tuple[str, ...]]:
        return [
            (
                f"{float(row['position_sigma_m']):.0f}米",
                f"{_percent(row['target_discovery_rate_mean'])}/{_percent(row['target_discovery_rate_min'])}",
                f"{_percent(row['continuous_confirmation_rate_mean'])}/{_percent(row['continuous_confirmation_rate_min'])}",
                _percent(row["true_frustum_probability_mass_coverage_rate_mean"]),
                f"{float(row['unexecuted_task_count_mean']):.1f}",
            )
            for row in rows_by_scenario[scenario_label]
        ]

    timing_rows = [
        (
            row["scenario_label"],
            f"{float(row['position_sigma_m']):.0f}米",
            f"{float(row['first_discovery_mean_s']):.2f}秒",
            f"{float(row['planner_compute_p95_ms_mean']):.2f}毫秒",
        )
        for row in aggregates
    ]
    scenario_rank = {"20目标/8机": 0, "20目标/30机": 1, "40目标/50机": 2}
    timing_rows.sort(
        key=lambda item: (scenario_rank[str(item[0])], float(str(item[1]).removesuffix("米")))
    )

    first_discovery_min = min(float(row["first_discovery_mean_s"]) for row in aggregates)
    first_discovery_max = max(float(row["first_discovery_mean_s"]) for row in aggregates)
    planner_p95_min = min(float(row["planner_compute_p95_ms_mean"]) for row in aggregates)
    planner_p95_max = max(float(row["planner_compute_p95_ms_mean"]) for row in aggregates)
    lines = [
        "# 协同搜索试验报告",
        "",
        "本报告说明拦截无人机如何根据中心给出的粗位置，在有限时间内分工搜索并完成连续视觉确认。核心结论有两点。第一，20目标/8机场景只在30米误差档稳定完成全部目标确认；误差扩大到60米和100米后，平均确认率降至97%和91%。第二，资源增加到20目标/30机和40目标/50机后，三档误差、五个固定随机场景均完成全部目标确认。",
        "",
        "本次结果来自既有AirSim目标运动记录上的确定性离线回放。试验矩阵包括3种目标与资源规模、3档粗位置误差和5个固定随机场景，共45组。离线模型计算了平台运动、云台转动、相机视锥和连续两帧确认，没有重新运行AirSim，也没有加入真实检测器波动。报告中的结果用于判断搜索容量和调度逻辑，不能直接作为实装性能。",
        "",
        "## 一、算法原理",
        "",
        "### 1.1 处理流程",
        "",
        "中心线索先外推到当前规划时刻，并按位置误差形成三维预测区域。系统依据相机在预定观察距离上的实际覆盖范围，把预测区域划成若干搜索子单元，再计算每个子单元的目标存在概率。无人机按滚动收益获得观察任务，飞到观察位置后转动云台并取帧。一次看见只形成临时发现，连续两帧满足识别门限后才关闭该线索的搜索任务。",
        "",
        _figure("search100_01_flow.png", "中心粗线索条件下的协同搜索流程"),
        "",
        "搜索过程持续更新。没有发现目标时，只降低相机实际看过区域的剩余概率；发现目标后，释放对应无人机并重新计算其余任务。这样可以把一次性的区域分配改成随观察结果滚动调整的搜索计划。",
        "",
        "### 1.2 粗位置预测区域",
        "",
        "每条线索包含保存时刻的位置、速度和位置误差。系统先按恒速模型把位置外推到规划时刻，再以三倍标准差划定搜索边界。30米误差档形成较小预测区域；60米和100米误差档覆盖范围依次扩大。误差增大后，目标仍可能位于区域内，但需要检查的观察方向和飞行位置明显增加。",
        "",
        "本轮中心线索精度和召回率均设为100%。20个目标对应20条正确线索，40个目标对应40条正确线索，不设置错误线索、重复线索、漏检目标和额外空白走廊。该条件用于单独检查粗位置误差对搜索容量的影响。",
        "",
        "### 1.3 搜索子单元",
        "",
        "相机分辨率为1920×1080，水平视场19度，按画幅比例计算的垂直视场为10.75度。在700米观察距离上，单次视场的水平覆盖约234.28米，垂直覆盖约131.78米。相邻视场保留20%重叠。预测区域沿横向和高度方向按视场足迹分块，深度方向保留完整三倍标准差范围。",
        "",
        "每个子单元的初始概率由目标位置误差分布计算。靠近预测中心的单元概率高，边缘单元概率低。相机没有发现目标时，只扣除真实视锥覆盖到的概率，不把整条线索直接清零；连续确认后才关闭该线索的剩余单元。目标真实编号不参与子单元生成、任务分配和在线关闭判断。",
        "",
        _figure("search100_02_cells_3d.png", "粗位置三倍标准差区域与搜索子单元"),
        "",
        "### 1.4 滚动收益分配",
        "",
        "每次有无人机空闲时，系统建立无人机到候选子单元的收益矩阵。收益使用子单元概率、预计完成时间和飞行距离：",
        "",
        "```text",
        "U = 12p + 1.5/(1+T) - 0.018T - 0.00005D",
        "```",
        "",
        "其中，p为子单元的目标存在概率，T为飞行、转向和观察的总时间，D为无人机到观察点的距离。概率越高、完成越快、距离越近，任务收益越高。匈牙利算法在同一轮内进行一一分配，保证一架无人机只执行一个子单元，一个子单元只分给一架无人机。",
        "",
        "平台飞行和云台转动按可同时进行处理。预计完成时间超过18秒的组合不下发，预算结束仍有效但没有完成观察的子单元记为未执行任务。每次确认目标、完成空视场观察或释放无人机后，收益矩阵重新计算。",
        "",
        "### 1.5 视锥观测与连续确认",
        "",
        "离线观测器在运动后的相机位置和云台角度下建立针孔相机视锥，把保存轨迹中的目标位置投到图像平面。目标位于视锥内且检测框最长边不小于10像素时，生成匿名检测。试验不再加入随机漏检和虚警。同一观察点连续读取3帧，图像平面内使用一一匹配连接短航迹，连续2帧达到门限后形成确认。",
        "",
        "分配、到位和观察分开记录。任务进入收益矩阵或获得分配不等于已经观察；只有平台完成受限运动、相机视锥实际覆盖对应空间并完成取帧，才计入视锥覆盖和发现指标。",
        "",
        "### 1.6 搜索与身份配准边界",
        "",
        "搜索阶段回答的是“预测区域内是否出现了可连续观察的目标”。粗位置误差较大、目标又相互接近时，一条线索的搜索视场可能先看到邻近目标。连续确认可以证明视场内存在稳定目标，不能单独证明该目标就是原线索对应的对象。搜索结果应继续进入中心线索与机载航迹配准，不能在本阶段直接改写目标身份。",
        "",
        "## 二、试验配置",
        "",
        "### 2.1 场景与设备",
        "",
    ]
    lines.extend(
        _table(
            ("项目", "设置"),
            (
                ("规模", "20目标/8机、20目标/30机、40目标/50机"),
                ("目标运动", "保存记录中的3米AirSim移动网格目标，速度约50米/秒；0.8秒后按保存速度外推"),
                ("相机", "1920×1080，水平视场19度，垂直视场10.75度，观察距离700米"),
                ("资源初态", "搜索阶段前出待机线：北向2100米、东向-650至650米、三个高度层"),
                ("运动假设", "平台最大速度97米/秒，云台最大转速200度/秒"),
            ),
        )
    )
    lines.extend(
        [
            "",
            "### 2.2 误差与时间设置",
            "",
        ]
    )
    lines.extend(
        _table(
            ("项目", "设置"),
            (
                ("试验性质", "保存AirSim目标轨迹上的确定性离线搜索调度，不是新AirSim飞行试验"),
                ("中心线索", "精度和召回率均为100%，每个目标对应一条正确粗位置线索"),
                ("位置误差", "北、东、地三轴标准差分别取30米、60米、100米，截断于正负三倍标准差"),
                ("固定随机场景", "20260816至20260820，共5个；只改变粗位置误差采样"),
                ("观察规则", "每点0.3秒，共3帧；检测框最长边不小于10像素；连续2帧确认"),
                ("时间预算", "18秒；预计超出预算的候选不执行"),
                ("检测干扰", "不额外注入随机漏检和虚警"),
                ("试验总数", "3种规模×3档误差×5个固定随机场景，共45组"),
            ),
        )
    )
    lines.extend(
        [
            "",
            "保存的20目标和40目标轨迹均记录到0.8秒，剩余17.2秒按各目标保存速度作恒速外推。该处理保留了AirSim中的初始位置、速度和交叉航向，没有复现新的气动、遮挡和图像检测波动。97米/秒平台速度和200度/秒云台转速均为离线计算假设。",
            "",
            "### 2.3 评价口径",
            "",
        ]
    )
    lines.extend(
        _table(
            ("指标", "计算口径"),
            (
                ("目标发现率", "至少一次进入真实相机视锥，且检测框最长边达到10像素的目标比例"),
                ("连续确认率", "同一匿名短航迹连续两帧达到识别门限的目标比例"),
                ("视锥概率覆盖", "相机实际观察到的子单元概率质量占当前线索总概率质量的比例"),
                ("重复确认", "已确认目标再次满足连续确认条件的观察比例"),
                ("未执行任务", "18秒结束时仍有效、且尚未完成观察的子单元数量"),
                ("首次发现时间", "从搜索开始到目标首次达到10像素门限的平均时间"),
                ("规划95%耗时", "每组滚动分配计算时间的95%分位值"),
            ),
        )
    )
    lines.extend(
        [
            "",
            "发现率和连续确认率同时报告五个固定随机场景的平均值与最差值。视锥概率覆盖只统计相机实际看过的空间。目标一旦连续确认，其余搜索单元即关闭，因此该指标不等同于区域遍历比例，也不要求达到100%。真实身份仅用于离线投影和结束评分，45组在线记录的真实身份泄漏数为0。",
            "",
            "## 三、试验结果",
            "",
            "### 3.1 20目标与8架无人机",
            "",
            "该组用于检查资源紧张时的搜索能力。发现率和连续确认率均按“平均值/最差场景”列示。",
            "",
        ]
    )
    lines.extend(
        _table(
            (
                "位置误差σ",
                "发现率（平均/最差）",
                "连续确认率（平均/最差）",
                "视锥概率覆盖",
                "未执行任务均值",
            ),
            _scenario_result_rows("20目标/8机"),
        )
    )
    lines.extend(
        [
            "",
            "30米误差档的五个场景均完成20个目标连续确认。误差扩大到60米后，平均发现率和连续确认率均为97%，最差场景为90%。100米误差档平均发现率为92%，平均连续确认率为91%，最差场景均为80%；预算结束时平均还有24.6个有效子单元没有执行。资源不足时，误差扩张首先增加待观察单元和飞行时间，随后减少重访与连续确认机会。",
            "",
            "### 3.2 20目标与30架无人机",
            "",
            "该组保持目标数量不变，把搜索资源由8架增加到30架，用于检查并行搜索能否抵消粗位置误差。",
            "",
        ]
    )
    lines.extend(
        _table(
            (
                "位置误差σ",
                "发现率（平均/最差）",
                "连续确认率（平均/最差）",
                "视锥概率覆盖",
                "未执行任务均值",
            ),
            _scenario_result_rows("20目标/30机"),
        )
    )
    lines.extend(
        [
            "",
            "三档误差下，五个固定随机场景均完成全部20个目标发现和连续确认，预算结束时没有剩余有效任务。100米误差档的视锥概率覆盖为61.3%。该数值低于30米档，是因为多机较快发现目标后立即关闭剩余单元，没有继续遍历已经失去搜索必要性的低概率区域。",
            "",
            "### 3.3 40目标与50架无人机",
            "",
            "该组同时增加目标数量和搜索资源，用于检查滚动分配在更大收益矩阵下的结果。",
            "",
        ]
    )
    lines.extend(
        _table(
            (
                "位置误差σ",
                "发现率（平均/最差）",
                "连续确认率（平均/最差）",
                "视锥概率覆盖",
                "未执行任务均值",
            ),
            _scenario_result_rows("40目标/50机"),
        )
    )
    lines.extend(
        [
            "",
            "三档误差下，五个固定随机场景均完成全部40个目标发现和连续确认。100米误差档的视锥概率覆盖为59.6%，预算结束时没有剩余有效任务。结果表明，在当前离线运动假设下，50架无人机的并行搜索容量能够覆盖40个目标的粗位置误差。该结果没有验证机间避碰、通信排队和真实检测波动。",
            "",
            _figure("search100_03_results.png", "三种规模和误差下的目标发现与连续确认"),
            "",
            "### 3.4 重复观察与身份边界",
            "",
            "三种规模、三档误差下的重复确认比例为71.1%至93.2%。目标较密集时，一个19度视场可能同时包含多个目标；多架无人机观察相邻子单元时，也可能再次看到已经确认的目标。重复观察提供了复核机会，同时占用搜索容量。后续可以对刚完成确认的区域设置短时抑制，但仍需保留不同方向的必要复核。",
            "",
            "100米误差下，线索任务被邻近目标触发关闭的平均数量分别为：20目标/8机8.2条、20目标/30机3.4条、40目标/50机6.6条。这些记录仍可计入“发现目标”，不能计入“原线索身份已经确认”。搜索结果必须交给后续末端配准流程建立线索与机载航迹关系。",
            "",
            _figure("search100_04_coverage_budget.png", "真实视锥覆盖与18秒预算内剩余任务"),
            "",
            "### 3.5 首次发现与计算时间",
            "",
        ]
    )
    lines.extend(
        _table(
            ("场景", "位置误差σ", "首次发现均值", "规划95%耗时均值"),
            timing_rows,
        )
    )
    lines.extend(
        [
            "",
            f"九种组合的首次发现平均时间为{first_discovery_min:.2f}至{first_discovery_max:.2f}秒。20目标/8机的60米档比100米档稍慢，原因是固定随机误差方向、无人机初始横向位置和高概率单元顺序共同变化，不能据此判断误差增大有利于搜索。",
            "",
            f"滚动分配95%耗时均值为{planner_p95_min:.2f}至{planner_p95_max:.2f}毫秒。该时间来自当前工作站的Python离线实现，只包含收益矩阵和一一分配计算，不包含相机接口、通信等待和飞行控制执行。",
            "",
            _figure("search100_05_timing.png", "首次发现时间与滚动分配计算时间"),
            "",
            "### 3.6 结论",
            "",
            "第一，在中心线索全部正确、目标尺寸3米、没有额外漏检和虚警的条件下，粗位置预测、搜索子单元、滚动收益分配和连续确认可以形成完整离线流程。30米误差下，8架无人机完成20个目标搜索；误差扩大后，8机资源出现漏搜。",
            "",
            "第二，搜索容量与预测区域大小需要共同设计。20目标/30机和40目标/50机在本轮45组回放中完成全部目标确认，说明增加并行观察资源能够补偿位置误差带来的搜索单元扩张。该结果只适用于当前18秒预算、速度上限、视场和观察距离。",
            "",
            "第三，连续看到目标不等于完成身份绑定。粗位置误差增大后，邻近目标可能提前关闭线索任务。搜索流程应输出匿名机载航迹和观察证据，由末端配准继续判断其与中心线索的对应关系。",
            "",
            "本轮证据只支持离线调度和几何可见性判断。目标轨迹在0.8秒后采用恒速外推，平台和云台使用上限模型，没有加入目标加速度、航迹冲突、导航误差、云台稳定时间、真实图像检测波动和通信时延。上述条件明确后，仍需重新开展AirSim闭环试验或实物数据回放。",
            "",
            "45组机器可读证据已随试验材料封存，包括逐组配置、指标、匿名在线记录、独立真值、输入哈希、汇总表和复现命令。现有封存材料未记录原始运行提交号、依赖版本和运行环境版本，后续正式复验应补齐这些信息。",
            "",
        ]
    )
    return "\n".join(lines)


def build_terminal_markdown_legacy(
    runs: Sequence[RunEvidence], benchmark: BenchmarkEvidence
) -> str:
    center_geometry = [
        benchmark.result(run.spec.scenario_id, "center_handover", "geometry")
        for run in runs
    ]
    center_gnn = [
        benchmark.result(run.spec.scenario_id, "center_handover", "gnn") for run in runs
    ]
    sparse_geometry = [
        benchmark.result(run.spec.scenario_id, "crossview", "geometry", "sector_fov")
        for run in runs
    ]
    sparse_gnn = [
        benchmark.result(run.spec.scenario_id, "crossview", "gnn", "sector_fov")
        for run in runs
    ]
    full_geometry = [
        benchmark.result(run.spec.scenario_id, "crossview", "geometry", "full")
        for run in runs
    ]
    full_gnn = [
        benchmark.result(run.spec.scenario_id, "crossview", "gnn", "full")
        for run in runs
    ]

    lines = [
        "# 末端目标配准试验报告",
        "",
        "本报告说明两类关系如何建立：中心线索与拦截无人机局部航迹的交接，以及多架拦截无人机局部航迹之间的跨视角关联。两类计算都保留未匹配状态，并通过一一匹配和多帧确认限制错误绑定。结果来自三组AirSim匿名观测和保存观测上的图神经网络离线复算。",
        "",
        "## 一、问题、难点与方法",
        "",
        "### 1.1 当前问题与难点",
        "",
        "中心线索给出北东地坐标中的位置、速度和协方差，机载相机给出图像中的匿名检测框，两者坐标不同、时间不同、编号也不同。若直接按最近像点绑定，旧线索、目标交叉和相机姿态变化都会引起错配。中心本身还有20%的错误线索和20%的漏检目标，因此算法必须允许中心线索不匹配，也必须允许机载新发现目标保持未注册。",
        "",
        "多架拦截无人机看到同一目标时，各机只掌握自己的局部编号。目标在不同视角中的像素位置和检测框大小差异较大；相机数增加后，全部相机两两比较会产生大量没有共同视场的候选。机间关联需要先恢复共同几何关系，再解决一条航迹被多个候选同时占用以及错误关系在相机网络中扩散的问题。",
        "",
        _figure("06_terminal_flow.png", "中心交接与机间关联的统一计算流程"),
        "",
        "### 1.2 中心线索状态外推",
        "",
        "第一步把中心线索推到机载图像的测量时刻。这样比较的是同一时刻的预测位置和实际检测，而不是拿旧坐标直接对当前图像。状态记为位置和速度 `x=[p,v]`，图像时刻与线索测量时刻相差Δt：",
        "",
        "```text",
        "x(t) = F x0",
        "F = [[I, Δt·I], [0, I]]",
        "P(t) = F P0 F^T + Q",
        "```",
        "",
        "P表示位置和速度的不确定范围，Q表示外推期间可能发生的机动。本试验加速度标准差为0.5米/秒²，Q的位置块、交叉块和速度块分别按 `qΔt⁴/4`、`qΔt³/2` 和 `qΔt²` 增长，其中q=0.5²。线索越旧，预测范围越大，后续像面门限会自动放宽，但错误候选也会增多。",
        "",
        "### 1.3 坐标转换与像面预测",
        "",
        "外推后的目标位置先减去相机位置，再经过机体、云台和相机安装旋转，得到相机坐标 `(x_c,y_c,z_c)`。AirSim相机x轴朝前、y轴朝图像右侧、z轴朝下。预测点落入图像的位置为：",
        "",
        "```text",
        "u = c_x + f_x · y_c / x_c",
        "v = c_y + f_y · z_c / x_c",
        "```",
        "",
        "式中f是像素焦距，c是图像中心。若目标位于相机后方或预测点在图像外，候选直接排除。线索位置协方差通过投影雅可比矩阵J转换到图像，再与投影误差和检测中心误差相加，得到预测椭圆S。实际检测中心z与预测中心z_hat的偏差按预测椭圆归一化：",
        "",
        "```text",
        "S = J P_pos J^T + R_projection + R_local",
        "d² = (z - z_hat)^T S^-1 (z - z_hat)",
        "```",
        "",
        "d²不只看相差多少像素，还看这条线索本来有多不确定。候选需同时满足检测框不小于10像素、线索已经到达且未过期、预测点在图像内、d²不大于9.2103，以及有历史速度时像面速度差不大于80像素/秒。",
        "",
        _figure("07_handover_geometry.png", "中心线索投影到机载图像并形成预测椭圆"),
        "",
        "### 1.4 中心交接代价与确认",
        "",
        "通过门控的候选进入代价矩阵。若有S条中心线索、L条机载局部航迹，先建立S×L个真实候选，再为每条中心线索增加一个专用未匹配列，矩阵为S×(L+S)。几何代价同时考虑位置和像面运动：",
        "",
        "```text",
        "C_geo = d² + (运动残差 / 80)²",
        "```",
        "",
        "已经确认的中心线索若切换到其他局部航迹，代价增加4.0；未匹配项代价为12.0。匈牙利算法一次求解整个矩阵，使一条中心线索最多占用一条局部航迹，一条局部航迹也不会被多条中心线索重复使用。关系需要在最近3帧中至少2帧被选中，才转为正式交接。未达到条件的中心线索保持未匹配，机载航迹保持未注册。",
        "",
        "图神经网络对照只处理已经通过硬门控的候选，不扩大候选范围。网络输出同一目标概率P_gnn后，将代价修正为 `C_final=C_geo-2log(P_gnn)`，再使用相同的匈牙利算法和多帧确认。网络不能绕过图像范围、时间有效性和马氏距离门限。",
        "",
        "### 1.5 机间时间对齐与双视线交会",
        "",
        "各机先把匿名检测框串成局部航迹。机间关联以局部航迹为单位，不比较不同相机的局部编号。检测框中心 `(u,v)` 先反投影成相机坐标单位视线，再根据相机姿态转到北东地坐标：",
        "",
        "```text",
        "d_c = normalize([1, (u-c_x)/f_x, (v-c_y)/f_y])",
        "d_n = normalize(R_n_c d_c)",
        "```",
        "",
        "两台相机的观测时间允许相差0.16秒。算法对两条局部航迹插值或选择最近观测，形成多组时间对齐样本。对每组样本，分别从相机位置沿两条单位视线延伸，求两条空间直线的最近点，最近点中点作为交会位置，最近点距离作为视线分离误差。至少3组有效交会样本才能进入后续运动拟合。",
        "",
        _figure("10_crossview_rays.png", "两台机载相机通过双视线交会核对同一目标"),
        "",
        "### 1.6 机间几何代价、图网络和目标簇",
        "",
        "候选首先经过硬门控：航迹更新时间差不大于0.65秒、视线夹角不小于0.35度、视线分离不大于2米、重投影误差不大于8像素、运动拟合误差不大于5米、运动转角不大于55度、检测框尺度对数差不大于0.28。通过后，将各项误差除以门限并封顶为3，再计算几何代价：",
        "",
        "```text",
        "C_geo = 0.24C_sep + 0.20C_reproj + 0.10C_time",
        "      + 0.18C_motion + 0.12C_turn + 0.08C_scale + 0.08C_conf",
        "```",
        "",
        "几何代价越小，两条局部航迹越可能属于同一目标。图神经网络对照在同一硬门控白名单内输出同目标概率，再按 `C_final=0.55C_geo+0.45(1-P_gnn)` 修正代价。每个相机对分别建立航迹代价矩阵，未匹配代价为1.05，匈牙利算法完成一一匹配；最近3帧至少2次选中同一关系后确认。",
        "",
        "确认关系最终合并为跨相机目标簇。一个目标簇不能包含同一相机的两条航迹；两个成熟目标簇至少需要两个不同相机对共同支持才能合并；只有2帧的短航迹需要成熟簇内至少两台相机支持。该约束用于阻止一条错误关系把多个真实目标串成一个簇。",
        "",
        "相机数量较多时，不再比较所有相机对。同一搜索责任区的相机对保留；相邻责任区只有在共同帧内视场重叠时保留，并增加5度视场余量；其余相机对排除。保留相机作为节点、可能共同观测的相机对作为边，形成稀疏相机图。这个图只由责任区、相机参数和观测姿态生成，不读取真实目标编号。",
        "",
        _figure("11_crossview_funnel.png", "相机对筛选与跨视角候选压缩"),
        "",
        "## 二、试验配置",
        "",
        "### 2.1 场景与输入",
        "",
    ]
    lines.extend(
        _table(
            ("项目", "设置"),
            (
                ("仿真模式", "AirSim ComputerVision"),
                ("规模", "20目标/8机、20目标/30机、40目标/50机"),
                ("中心相机", "2台，1280×1024，水平视场角3.67度"),
                ("机载相机", "1920×1080，水平视场角19度，相机前移0.5米"),
                ("目标", "无人机静态网格Actor，速度50米/秒，最长尺寸3米"),
                ("中心线索", "精度80%、召回率80%，位置标准差1米，速度标准差0.2米/秒"),
                ("识别接口", "AirSim simGetDetections；检测框最长边不小于10像素"),
                ("在线身份", "只使用匿名检测和局部航迹；不读取Actor名称和真实目标编号"),
                ("图网络", "独立合成数据训练，seed 20260816留出；只做保存观测离线复算"),
                ("随机种子", "20260816；每个规模单次采集"),
            ),
        )
    )
    lines.extend(
        [
            "",
            "### 2.2 评价口径与边界",
            "",
            "中心交接精度按正确绑定数除以全部绑定数计算，召回率按正确绑定数除以正确中心线索数计算。机间关系精度按正确跨相机关系数除以全部输出关系数计算，关系召回率按正确关系数除以应建立关系数计算。身份混合表示同一目标簇内出现多个离线真实目标。上述真值只在运行结束后评分。",
            "",
            "中心交接和跨视角几何基线读取AirSim匿名观测。图神经网络使用同一批保存观测离线复算，没有重新运行Blocks。复算时间包含关联、审计文件和绘图，不能当作机载实时延迟。ComputerVision节点不含飞行动力学，本试验没有验证导航误差、云台姿态误差、通信丢包、真实检测器和物理拦截。",
            "",
            "## 三、试验过程、结果与分析",
            "",
            "### 3.1 中心交接过程与结果",
            "",
            "每组中心交接读取5帧观测。每帧先把全部有效中心线索外推到图像时刻，按相机位姿投影到各机图像，再对10像素、时间、图像范围、马氏距离和像面运动逐项门控。通过门控的候选组成代价矩阵，完成一一匹配并累计最近3帧确认次数。图网络对照复用相同白名单、匹配和确认逻辑。",
            "",
            _figure("09_projection_ellipse_matching.png", "中心预测椭圆与机载局部航迹匹配示例"),
            "",
        ]
    )
    center_rows = []
    for index, run in enumerate(runs):
        for method, result in (("几何", center_geometry[index]), ("图神经网络", center_gnn[index])):
            metrics = result["metrics"]
            center_rows.append(
                (
                    run.spec.label,
                    method,
                    metrics["true_binding_count"],
                    metrics["false_binding_count"],
                    _ratio(metrics["binding_precision"]),
                    _ratio(metrics["binding_recall"]),
                    f"{float(result['timing']['median_wall_duration_s']):.3f}秒",
                )
            )
    lines.extend(_table(("场景", "方法", "正确绑定", "错误绑定", "精度", "召回率", "中位复算时间"), center_rows))
    lines.extend(
        [
            "",
            _figure("08_handover_results.png", "三组中心交接结果"),
            "",
            "20目标/8机中，几何和图网络都正确绑定16条有效中心线索，没有错误绑定。20目标/30机中，两种方法均正确绑定14条，另有2条正确线索没有完成绑定，召回率为0.8750。资源数量增加没有自动提高交接结果，因为三组专项在reset后独立采样，局部航迹数量和连续性并不完全相同。",
            "",
            "40目标/50机中，几何方法正确绑定31条，同时误接1条错误线索，精度和召回率均为0.9688。图网络保留31条正确绑定并拒绝该错误关系，精度提高到1.0000，召回率保持0.9688。该差异只出现在单个留出回放中，支持保留学习对照，不能据此替换几何门控和一一匹配。",
            "",
            "### 3.2 机间关联过程与结果",
            "",
            "跨视角复算先按责任区和视场形成相机图，再对每条保留边上的局部航迹执行时间对齐、双视线交会、运动拟合和几何门控。相机对内完成匈牙利匹配和多帧确认后，再按相机唯一性和多边支持规则合并目标簇。全相机策略作为规模压力对照，责任区/视场稀疏策略作为当前默认路径。",
            "",
            _figure("13_local_pixel_tracks.png", "20目标/8机场景中的多相机局部像面航迹"),
            "",
        ]
    )
    cross_quality_rows = []
    cross_scale_rows = []
    for index, run in enumerate(runs):
        groups = (
            ("全相机", "几何", full_geometry[index]),
            ("全相机", "图神经网络", full_gnn[index]),
            ("责任区/视场稀疏", "几何", sparse_geometry[index]),
            ("责任区/视场稀疏", "图神经网络", sparse_gnn[index]),
        )
        for graph_label, method, result in groups:
            metrics = result["metrics"]
            audit = result["candidate_audit"]
            cross_quality_rows.append(
                (
                    run.spec.label,
                    graph_label,
                    method,
                    metrics["true_positive_relations"],
                    metrics["false_positive_relations"],
                    _ratio(metrics["association_precision"]),
                    _ratio(metrics["association_recall"]),
                    metrics["id_switch_count"],
                )
            )
            cross_scale_rows.append(
                (
                    run.spec.label,
                    graph_label,
                    method,
                    audit["camera_pair_retained_count"],
                    metrics["candidate_edge_count"],
                    f"{float(result['timing']['median_wall_duration_s']):.2f}秒",
                )
            )
    lines.extend(
        _table(
            ("场景", "相机图", "方法", "正确", "错误", "精度", "召回率", "身份混合"),
            cross_quality_rows,
        )
    )
    lines.extend(["", "候选规模和复算时间单独列示，避免将质量指标与计算量混在一张宽表中。", ""])
    lines.extend(
        _table(
            ("场景", "相机图", "方法", "保留相机对", "候选边", "复算时间"),
            cross_scale_rows,
        )
    )
    lines.extend(
        [
            "",
            _figure("14_crossview_relation_graph.png", "20目标/8机场景的跨相机关联关系"),
            "",
            "20目标/8机中，四种组合都得到30条正确关系、0条错误关系和2条漏配，精度1.0000、召回率0.9375。稀疏相机图把相机对从28组降到16组，候选边从5778条降到3296条，质量不变，复算时间从全相机几何的12.43秒降到8.87秒。",
            "",
            "20目标/30机中，全相机候选过密，几何方法精度只有0.6488。责任区和视场筛选后，几何精度提高到0.7402。稀疏图网络进一步把错误关系从198条降到142条，精度达到0.8008、召回率达到0.9078，身份混合从4个降到2个。该规模下，先缩小相机比较范围，再由学习模型处理剩余歧义，产生了可测增益。",
            "",
            "40目标/50机中，全相机几何需要处理1,104,646条候选边，输出2537条错误关系并形成18个身份混合。稀疏策略把相机对从1225组降到403组，候选边降到375,236条。稀疏几何得到4031条正确关系、16条错误关系，精度0.9960、召回率0.9305，身份混合为0。稀疏图网络结果相同，复算时间由770.99秒增加到812.96秒，因此该规模没有继续使用图网络的质量收益。",
            "",
            _figure("12_crossview_results.png", "全相机、稀疏相机图与图网络对照"),
            "",
            "三组结果表明，中心交接和机间关联都需要保留几何白名单、未匹配状态、一一匹配和多帧确认。大规模机间关联的主要改进来自责任区和视场形成的稀疏相机图。图神经网络适合处理硬门控后仍有歧义的候选，在20目标/30机场景产生增益，在40目标/50机稀疏几何已经接近满精度时没有继续改善。当前默认路径仍为稀疏相机图、几何门控和匈牙利匹配。",
            "",
            "以上数字来自seed 20260816的单次AirSim观测和对应离线复算，不具有多seed统计意义。真实相机标定漂移、时间同步偏差、导航误差和真实漏检虚警会直接影响投影、视线交会和单机局部航迹，仍需在后续试验中单独注入并标定。",
            "",
        ]
    )
    return "\n".join(lines)


def _build_terminal_markdown_previous(
    runs: Sequence[RunEvidence],
    benchmark: BenchmarkEvidence,
    selection: Mapping[str, Any],
) -> str:
    center_geometry = {
        run.spec.scenario_id: benchmark.result(
            run.spec.scenario_id, "center_handover", "geometry"
        )
        for run in runs
    }
    geometry = {
        item["scenario_id"]: item for item in selection["geometry_scenario_metrics"]
    }
    selected_gnn = {
        item["scenario_id"]: item
        for item in selection["selected_cold_scenario_metrics"]
    }
    labels = {run.spec.scenario_id: run.spec.label for run in runs}
    parameters = selection["selected_parameters"]

    lines = [
        "# 末端目标配准试验报告",
        "",
        "本报告说明中心航迹如何与拦截无人机的机载航迹建立交接关系，以及多架拦截无人机如何判断各自拍摄到的目标是否相同。在线计算只使用时间戳、相机位姿、检测框和匿名局部航迹。真实目标编号在关联结束后用于离线评分，不进入候选生成、图神经网络或最终身份。",
        "",
        "## 一、问题与方法",
        "",
        "### 1.1 任务难点",
        "",
        "中心航迹位于北东地坐标系，机载检测位于图像坐标系。无人机在运动，云台也在转动，同一目标在不同图像中的位置和运动方向均会变化。若姿态时刻、安装偏移或旋转方向处理错误，中心预测点会整体偏离检测框；多架无人机之间还可能把相邻目标的局部航迹错误合并。",
        "",
        "末端视场按责任区和实际视场保持稀疏。算法只比较可能存在共同视场的相机对，并允许航迹保持未匹配。没有足够几何证据时不强行建立身份关系。",
        "",
        _figure("06_terminal_flow.png", "中心交接与机间配准流程"),
        "",
        "### 1.2 状态外推与拍摄时刻",
        "",
        "中心位置、速度和协方差先外推到图像的测量时刻。状态采用恒速模型 `x(t)=Fx0`，协方差按 `P(t)=FP0F^T+Q` 增长。Q表示外推期间的机动不确定度。这样比较的是同一拍摄时刻的中心预测和机载检测。",
        "",
        "机体位置、机体姿态和云台姿态均按图像的 `measurement_timestamp` 插值。插值需要拍摄时刻前后的姿态样本，任一侧缺失或时间间隔超过门限时停止建立关系。`arrival_timestamp`只用于判断消息是否过期，不参与位姿计算。",
        "",
        "现有三组AirSim回放已经把拍摄时刻的相机光心和最终相机姿态写入每条观测，因此按“合成相机位姿、安装偏移为零”读取。该兼容方式验证了原有回放链路，没有验证非零机体安装偏移。",
        "",
        "### 1.3 坐标旋转与安装偏移",
        "",
        "旋转矩阵方向固定如下：`R_B^N`把北东地坐标转到机体坐标，`R_G^B`把机体坐标转到云台坐标，`R_C^G`把云台坐标转到相机坐标。目标点从北东地坐标转入相机坐标的完整关系为：",
        "",
        "```text",
        "p_C = R_C^G R_G^B R_B^N (p_N - o_C^N)",
        "```",
        "",
        "相机光心不是机体参考点。设机体到云台转轴的偏移为 `r_G^B`，云台转轴到光心的偏移为 `r_C^G`，兼容固定机体偏移为 `r_fix^B`，则视线起点为：",
        "",
        "```text",
        "o_C^N = p_B^N + R_N^B (r_fix^B + r_G^B + R_B^G r_C^G)",
        "```",
        "",
        "相机采用前、右、下坐标。像点 `(u,v)` 的相机系单位视线为 `d_C=normalize([1,(u-cx)/fx,(v-cy)/fy])`，转回北东地坐标后得到 `d_N=(R_C^G R_G^B R_B^N)^T d_C`。正投影和反投影使用同一旋转链和同一光心。",
        "",
        _figure("07_terminal_pose_chain.png", "相机旋转链与安装偏移"),
        "",
        "### 1.4 误差传播",
        "",
        "像面预测范围同时考虑中心航迹位置误差、无人机导航位置误差、机体姿态误差、云台角误差和检测框中心误差。将这些误差组成联合状态 `δx=[δp_t,δp_b,δθ_b,δθ_g,δz]`，利用投影函数的雅可比矩阵传播：",
        "",
        "```text",
        "S_image = J_image Σ_x J_image^T + R_projection",
        "d² = (z - z_hat)^T S_image^-1 (z - z_hat)",
        "```",
        "",
        "两台相机交会定位时，先分别得到光心和单位视线的协方差，再传播到两条视线最近点的中点：`P_X=J_X diag(P_rayA,P_rayB) J_X^T`。本轮新增了完整数值雅可比和单元测试。三组旧回放没有保存导航、机体和云台误差序列，因此结果表仍按原合成位姿评分，不能作为非零姿态误差验证。",
        "",
        "### 1.5 中心航迹交接",
        "",
        "外推后的中心位置按完整相机位姿投到图像，形成预测像点和不确定椭圆。检测框最长边不小于10像素，线索处于有效期内，预测点位于图像内，归一化像面残差和像面运动残差均通过门限后，候选进入匈牙利一一匹配。每条中心航迹和每条机载航迹最多形成一个关系，未匹配项始终保留。最近3帧中至少2帧得到同一结果后才正式交接。",
        "",
        _figure("09_projection_ellipse_matching.png", "中心预测椭圆与机载航迹匹配"),
        "",
        "### 1.6 拦截无人机之间的配准",
        "",
        "各机先形成匿名局部航迹。两条航迹按测量时刻对齐后，将检测中心反投影为北东地单位视线，计算多时刻双视线交会、重投影误差和运动一致性。硬门控检查时间差、交会角、视线分离、重投影、运动拟合和目标尺度。该门控在本轮参数搜索中没有修改。",
        "",
        "通过硬门控的候选使用几何代价，或由图神经网络给出同目标概率并修正代价。随后仍执行相机对内匈牙利一一匹配、最近3帧至少2帧确认和相机唯一性约束。图网络不能恢复被硬门控拒绝的关系，也不能读取真实编号。",
        "",
        _figure("10_crossview_rays.png", "双视线交会与多时刻运动核对"),
        "",
        _figure("11_crossview_funnel.png", "责任区和视场形成的稀疏候选"),
        "",
        "## 二、试验配置",
        "",
        "### 2.1 场景",
        "",
    ]
    lines.extend(
        _table(
            ("项目", "设置"),
            (
                ("仿真模式", "AirSim ComputerVision保存回放"),
                ("规模", "20目标/8机、20目标/30机、40目标/50机"),
                ("机载相机", "1920×1080，水平视场角19度"),
                ("目标", "3米无人机网格Actor，速度50米/秒"),
                ("识别门限", "检测框最长边不小于10像素"),
                ("相机图", "只使用责任区/视场稀疏策略"),
                ("观测种子", "20260816；每个规模一次保存观测"),
                ("在线身份", "匿名局部编号；真实编号只在离线评分阶段读取"),
            ),
        )
    )
    lines.extend(
        [
            "",
            "### 2.2 图网络参数诊断",
            "",
            "参数搜索严格限定为图网络概率阈值、几何与图网络融合权重、未匹配代价。硬几何门控、网络权重、一一匹配和多帧确认保持不变。使用图形处理器对三组保存回放进行离线网格搜索，候选组合共36组。",
            "",
        ]
    )
    lines.extend(
        _table(
            ("参数", "搜索范围", "选定值"),
            (
                ("图网络概率阈值", "0、0.05、0.15、0.30", _ratio(parameters["gnn_probability_threshold"], 2)),
                ("图网络融合权重", "0.25、0.45、0.65", _ratio(parameters["gnn_probability_weight"], 2)),
                ("未匹配代价", "0.85、1.05、1.25", _ratio(parameters["unmatched_cost"], 2)),
            ),
        )
    )
    lines.extend(
        [
            "",
            "排序先减少涉及身份混合的目标数和错误关系；关系精度达到0.80后，再比较每目标等权纯度与完整度、正确独立成簇比例、未完成目标数和耗时。参数直接在同一批报告回放上离线择优，因此属于诊断结果，不是独立留出验证。",
            "",
            "### 2.3 五项评价",
            "",
            "评价分母只包含至少被两台相机看到、具备配准机会的真实目标。航迹关系精度表示输出关系中正确关系的比例。每目标等权纯度表示一个目标的最佳目标簇中有多少成员确属该目标；每目标等权完整度表示该目标应合并的局部航迹有多少进入最佳目标簇。每个目标只计一次，避免航迹多的大型纯净簇抬高总结果。",
            "",
            "正确形成独立纯净目标簇要求该目标的全部可评分局部航迹进入同一簇，且没有混入其他目标。身份混合目标数统计进入混合簇的真实目标数量。未完成配准目标数统计具备双视角机会、但没有形成至少一条正确跨视角关系的目标。",
            "",
            _figure("15_terminal_target_metric.png", "目标等权评价口径"),
            "",
            "## 三、试验结果",
            "",
            "### 3.1 中心航迹交接",
            "",
            "中心交接沿用三组AirSim匿名观测的几何结果。新增安装偏移、拍摄时刻插值和联合误差传播已通过单元测试，尚未用非零导航和云台误差重新采集AirSim数据。",
            "",
        ]
    )
    center_rows = []
    for run in runs:
        result = center_geometry[run.spec.scenario_id]
        metrics = result["metrics"]
        center_rows.append(
            (
                run.spec.label,
                metrics["true_binding_count"],
                metrics["false_binding_count"],
                _ratio(metrics["binding_precision"]),
                _ratio(metrics["binding_recall"]),
                f"{float(result['timing']['median_wall_duration_s']):.2f}秒",
            )
        )
    lines.extend(_table(("场景", "正确绑定", "错误绑定", "精度", "召回率", "原复算时间"), center_rows))
    lines.extend(
        [
            "",
            _figure("08_handover_results.png", "三组中心交接结果"),
            "",
            "20目标/8机完成16条正确交接；20目标/30机完成14条，另有2条正确线索没有完成；40目标/50机完成31条正确交接，同时出现1条错误绑定。该结果说明投影和一一匹配链路能够运行，但单次回放不足以说明导航和云台误差条件下的稳定性。",
            "",
            "### 3.2 机间配准",
            "",
            "下表只列责任区/视场稀疏几何方法和同批回放择优图网络。关系精度与四项目标级指标均来自运行结束后的离线真实编号评分。",
            "",
        ]
    )
    quality_rows = []
    scale_rows = []
    for scenario_id in ("n20_m8", "n20_m30", "n40_m50"):
        for method, record in (("稀疏几何", geometry[scenario_id]), ("择优图网络", selected_gnn[scenario_id])):
            quality_rows.append(
                (
                    labels[scenario_id],
                    method,
                    record["opportunity_target_count"],
                    _ratio(record["association_precision"]),
                    _ratio(record["target_equal_mean_purity"]),
                    _ratio(record["target_equal_mean_completeness"]),
                    _ratio(record["independently_correct_target_rate"]),
                    record["mixed_identity_target_count"],
                    record["unregistered_opportunity_target_count"],
                )
            )
            scale_rows.append(
                (
                    labels[scenario_id],
                    method,
                    record["retained_camera_pair_count"],
                    record["candidate_edge_count"],
                    f"{float(record['elapsed_s']):.2f}秒",
                )
            )
    lines.extend(
        _table(
            ("场景", "方法", "机会目标", "关系精度", "等权纯度", "等权完整度", "独立纯净簇", "混合目标", "未完成目标"),
            quality_rows,
        )
    )
    lines.extend(["", "耗时均为无缓存关联计算，不含Word生成和图片绘制。", ""])
    lines.extend(_table(("场景", "方法", "保留相机对", "候选边", "无缓存耗时"), scale_rows))
    lines.extend(
        [
            "",
            _figure("13_local_pixel_tracks.png", "20目标/30机场景的匿名机载局部航迹"),
            "",
            _figure("14_crossview_relation_graph.png", "20目标/30机场景的跨相机关联关系"),
            "",
            _figure("12_terminal_metric_comparison.png", "稀疏几何与择优图网络结果对比"),
            "",
            "20目标/8机中，稀疏几何关系精度为1.0000，等权完整度为0.9667，没有身份混合或未完成目标。择优图网络保持关系精度1.0000，但等权完整度降至0.2500，15个具备机会的目标没有完成配准。图网络概率在该回放上没有完成标定，0.05阈值仍删掉了大量正确关系。",
            "",
            "20目标/30机中，稀疏几何关系精度为0.7402，涉及7个混合目标。择优图网络把关系精度提高到0.9736，混合目标降为0，等权纯度达到1.0000、完整度为0.9587。该规模存在较多歧义候选，图网络排序产生了明确收益。",
            "",
            "40目标/50机中，稀疏几何关系精度为0.9960，等权完整度为0.9710，没有混合或未完成目标。择优图网络关系精度为0.9971，错误关系减少，但等权完整度降至0.5666。几何基线已经较稳定，概率阈值带来的关系损失大于精度增益。",
            "",
            "### 3.3 阶段判断",
            "",
            "完整坐标链、安装偏移、测量时刻插值、像面联合协方差和双视线交会协方差已经形成可测试实现。旧AirSim观测仅验证合成相机位姿兼容路径。非零安装偏移、导航误差、机体姿态误差和云台角误差仍需重新注入后验证。",
            "",
            "五项指标已经区分关系级正确性和每目标等权的成簇质量。图网络在20目标/30机场景改善明显，在另外两个场景造成较大完整度损失。当前证据不支持用同一组择优参数替换稀疏几何默认路径。图网络可保留为歧义候选诊断手段，下一步需要独立训练、验证和留出回放完成概率校准。",
            "",
            "本轮三个场景均为seed 20260816的单次保存回放，不具备多seed统计意义。真实检测器漏检和虚警、时间同步漂移、导航误差、云台稳定误差及通信延迟尚未进入本轮结果。",
            "",
            "机器可读证据位于 `research_modules/independent_experiments/center_terminal_cv_campaign/outputs/terminal_gnn_diagnostic_selection_20260819_v2/`，包括三份输入清单、SHA256、36组候选表、冻结参数、选择理由、无缓存结果和复现命令。",
            "",
        ]
    )
    return "\n".join(lines)


def build_terminal_markdown(
    runs: Sequence[RunEvidence],
    benchmark: BenchmarkEvidence,
    selection: Mapping[str, Any],
) -> str:
    center_geometry = {
        run.spec.scenario_id: benchmark.result(
            run.spec.scenario_id, "center_handover", "geometry"
        )
        for run in runs
    }
    center_gnn = {
        run.spec.scenario_id: benchmark.result(
            run.spec.scenario_id, "center_handover", "gnn"
        )
        for run in runs
    }
    crossview_geometry = {
        item["scenario_id"]: item for item in selection["geometry_scenario_metrics"]
    }
    crossview_gnn = {
        item["scenario_id"]: item
        for item in selection["selected_cold_scenario_metrics"]
    }
    labels = {run.spec.scenario_id: run.spec.label for run in runs}
    parameters = selection["selected_parameters"]

    lines = [
        "# 末端目标配准试验报告",
        "",
        "本报告研究两类末端关系。第一类是把中心给出的目标航迹与拦截无人机看到的局部航迹对应起来，完成目标交接；第二类是多架拦截无人机同时看到相邻目标时，判断各机航迹是否属于同一目标。在线计算使用目标状态、时间戳、相机位姿、检测框和匿名局部航迹。真实目标编号只在试验结束后用于评分。",
        "",
        "## 一、任务与总体流程",
        "",
        "### 1.1 任务边界",
        "",
        "中心航迹和机载图像不在同一坐标系。中心给出北东地坐标系下的位置、速度和协方差，机载相机给出图像中的检测框和局部航迹。无人机飞行、机体转动和云台转动会同时改变目标在图像中的位置。中心交接必须先把两类数据换算到同一拍摄时刻和同一相机视角。",
        "",
        "机间配准不使用中心目标编号作为答案。每架无人机先独立形成局部航迹，再根据两机的拍摄时刻、位置、姿态和图像观测判断是否为同一目标。视场区没有重合、几何证据不足或候选冲突时，航迹保持未配准状态，不强行建立关系。",
        "",
        "### 1.2 总体流程",
        "",
        "中心交接和机间配准共用三项原则：按图像拍摄时刻取位姿；先用物理和几何条件排除不可能关系；最后进行一一匹配和多帧确认。两条链路分别计算，中心交接成功不代表机间配准自动成功。",
        "",
        _figure("06_terminal_flow.png", "中心交接与机间配准总体流程"),
        "",
        "## 二、中心航迹与无人机配准",
        "",
        "### 2.1 状态外推与时刻对齐",
        "",
        "中心航迹先外推到图像的测量时刻。恒速模型写为 `x(t)=Fx0`，协方差按 `P(t)=FP0F^T+Q` 增长，Q表示外推期间可能发生机动带来的不确定度。机体位置、机体姿态和云台姿态也按图像的测量时间插值。消息到达时间只判断数据是否过期，不用于计算相机朝向。",
        "",
        "插值必须取得拍摄时刻前后的位姿样本。缺少一侧样本或样本间隔超过门限时，当前图像不建立中心交接关系。这样可以避免用消息到达时刻的姿态替代拍摄时刻姿态，造成预测像点整体偏移。",
        "",
        "### 2.2 坐标转换与安装偏移",
        "",
        "旋转顺序固定为北东地坐标到机体坐标、机体坐标到云台坐标、云台坐标到相机坐标。目标点转入相机坐标的关系为：",
        "",
        "```text",
        "p_C = R_C^G R_G^B R_B^N (p_N - o_C^N)",
        "```",
        "",
        "相机光心通常不在无人机机体参考点上。光心位置需要加入机体到云台转轴、云台转轴到相机光心两段安装偏移：",
        "",
        "```text",
        "o_C^N = p_B^N + R_N^B (r_fix^B + r_G^B + R_B^G r_C^G)",
        "```",
        "",
        "像点 `(u,v)` 按针孔相机模型反投影为相机坐标系单位视线，再用上述旋转链转回北东地坐标。正投影和反投影必须使用同一光心、同一旋转方向和同一拍摄时刻位姿。",
        "",
        _figure("07_terminal_pose_chain.png", "相机坐标旋转与安装偏移"),
        "",
        "### 2.3 预测像点与几何匹配",
        "",
        "中心航迹投到机载图像后，结果不是一个绝对准确的像素点。中心目标位置、无人机导航位置、机体姿态、云台角和检测框中心的误差会共同改变预测位置。系统将这些误差传播到图像平面，在预测点周围形成一个不确定范围：",
        "",
        "```text",
        "S_image = J_image Σ_x J_image^T + R_projection",
        "d² = (z - z_hat)^T S_image^-1 (z - z_hat)",
        "```",
        "",
        "其中 `z_hat` 是中心航迹的预测像点，z是机载局部航迹的观测像点。d²同时考虑预测偏差和误差范围，比直接比较像素距离更适合处理粗位置线索。检测框最长边不足10像素、中心线索尚未到达或已经过期、预测点落在图像之外、d²大于9.2103的组合不再继续比较。有连续观测时，还要求两条航迹的像面速度差不超过80像素/秒。",
        "",
        "几何方法把归一化像面距离和运动差形成基础代价。距离越小、运动越接近，候选代价越低。全部候选统一进入带未匹配选项的一一分配，同一条中心航迹和同一条机载航迹都只能使用一次。最近3帧中至少2帧得到相同关系后，系统才确认交接。",
        "",
        "### 2.4 图网络辅助匹配",
        "",
        "目标密集时，一个中心预测范围内可能同时出现多条机载航迹。几何方法能够排除明显不合理的组合，但剩余候选的代价可能很接近。图网络用于处理这部分候选，不扩大前面的预测范围，也不放回已经被几何条件排除的关系。",
        "",
        "候选关系组成一个两侧航迹图。一侧是中心航迹，保存目标存在概率、位置不确定度和有效期；另一侧是机载局部航迹，保存航迹质量、目标像素尺寸和像面位置。通过前述检查的组合形成连线，连线上记录像面距离、运动差和预测时间差。图网络同时比较一条连线及其周边竞争关系，输出两条航迹属于同一目标的概率p。",
        "",
        "图网络不直接发布交接关系，只按 `C=C_base-2ln(p)` 修正基础代价。概率高的关系保留较低代价，概率低的关系受到更大惩罚。修正后的代价仍由同一套匈牙利算法进行一一分配，并执行3帧中2帧确认。该路线已经用于保存AirSim观测的离线回放；当前在线默认仍采用几何方法。",
        "",
        _figure("07b_center_handover_principle.png", "中心航迹与机载航迹交接原理"),
        "",
        "## 三、拦截无人机之间的配准",
        "",
        "### 3.1 视场区与局部航迹",
        "",
        "机间配准从各架无人机独立形成的局部航迹开始，不使用中心目标编号作为答案。无人机位置、机体姿态、云台朝向、相机视场角和目标可能距离共同确定相机当前能够观察的空间范围，报告中称为视场区。两台相机只有在同一时间段内可能看到同一片空间，才进入后续比较。",
        "",
        "保留下来的相机对再比较各自的匿名局部航迹。系统按照图像拍摄时刻对齐观测，并把检测框中心转换为空间视线。一对局部航迹此时只是候选，还不能直接认定为同一目标。系统继续检查多时刻视线能否交会、交会点能否解释两幅图像，以及交会点的运动是否连续。",
        "",
        _figure("10_crossview_rays.png", "双视线交会与多时刻运动核对原理"),
        "",
        "### 3.2 六类硬门控",
        "",
        "六类门控依次回答六个问题：两条航迹是否处于同一时间段，双视线是否具备稳定交会条件，视线是否在空间中靠近，交会结果能否重新解释两幅图像，多个交会点是否形成连续运动，两侧目标尺度是否相符。全部通过只表示这组关系具备继续比较的条件，并不表示已经完成配准。",
        "",
        "#### 时间差",
        "",
        "同一目标必须在相近时刻被两台相机看到。两条航迹先在共同时间轴上对齐，有前后观测时采用线性插值；不能插值时，最近观测与对齐时刻的差值不得超过0.16秒。两条航迹最后一次观测的时差不得超过0.65秒，并且至少取得3个有效对齐样本。这样可以排除在不同时段经过相近方向的目标。",
        "",
        "#### 交会角",
        "",
        "对每个对齐时刻计算两条视线的夹角，再取多时刻中位数。当前门限为0.35度。夹角过小时，两条视线近乎平行，图像中很小的偏差会引起很大的距离误差。此时可以保留各自的局部航迹，但不建立机间关系。",
        "",
        "#### 视线分离",
        "",
        "受测量误差影响，两条空间视线通常不会严格相交。系统在两条视线上分别找到距离最近的点，并计算两点间距 `δ=||(o_A+λ_A d_A)-(o_B+λ_B d_B)||`。多时刻距离中位数不超过2米时，才认为两条视线可能指向同一目标。这里的2米是视线分离距离，不是两架无人机之间的距离。",
        "",
        "#### 重投影",
        "",
        "两条视线最近点的中点作为临时三维位置，再分别投回两台相机。若这个位置确实对应同一目标，投影点应回到原来的检测框附近。每个时刻取两侧误差中较大的一个，多时刻中位数不得超过8像素。",
        "",
        "#### 运动拟合",
        "",
        "多个时刻的临时三维位置应当组成一段连续航迹。系统按 `X(t)=X0+v(t-t0)` 进行短时恒速拟合，拟合均方根残差不得超过5米，相邻运动段相对总体方向的最大转角不得超过55度。位置散乱或运动方向反复跳变的组合被排除。",
        "",
        "#### 目标尺度",
        "",
        "检测框最长边首先应达到10像素，保证观测具备基本辨认条件。系统再根据交会距离z、相机焦距f和检测框最长边 `l_px` 估计目标尺度 `s=l_px z/f`。两侧尺度估计之比不大于约1.32时通过检查。这里使用检测框最长边，不使用波动更大的检测框面积。",
        "",
        _figure("10b_crossview_hard_gates.png", "机间配准六类硬门控及当前阈值"),
        "",
        "### 3.3 候选评分与一一分配",
        "",
        "通过六类门控后，一条局部航迹仍可能对应多条候选。几何方法把各项残差换算到可比较的尺度，再形成综合代价。视线分离和重投影合计占0.44，时间和运动连续性合计占0.40，目标尺度和相机可信度各占0.08。代价越小，两条局部航迹越可能属于同一目标。",
        "",
        "图网络与几何方法使用同一批候选。两侧局部航迹构成节点，通过门控的组合形成连线。网络同时查看一条连线和与它竞争的其他连线，输出同目标概率p。当前诊断采用 `C_final=0.75C_geo+0.25(1-p)`，即几何代价占主要部分，图网络负责修正候选顺序；概率低于0.05的关系不进入分配。",
        "",
        "几何方法和图网络最终都把候选代价交给匈牙利算法。算法从整个候选矩阵中统一选择一一关系，避免同一条航迹同时分给多个目标，并允许证据不足的航迹保持未匹配。最近3帧中至少2帧选中同一关系后才正式确认。",
        "",
        "确认关系随后合并为跨相机目标簇。同一目标簇不能包含同一相机的两条不同航迹；两个已经形成的较大目标簇需要多个相机对共同支持才能继续合并，避免一条偶然关系造成身份混合。",
        "",
        _figure("11b_crossview_assignment_principle.png", "视场区内候选评分与一一匹配流程"),
        "",
        "## 四、试验配置与评价方法",
        "",
        "### 4.1 试验配置",
        "",
    ]
    lines.extend(
        _table(
            ("项目", "设置"),
            (
                ("仿真模式", "AirSim计算机视觉模式保存回放"),
                ("场景规模", "20目标/8机、20目标/30机、40目标/50机"),
                ("目标运动", "3米无人机网格Actor，速度50米/秒"),
                ("机载相机", "1920×1080，水平视场角19度"),
                ("识别条件", "检测框最长边不少于10像素"),
                ("中心线索", "构造精度80%、召回率80%的粗航迹"),
                ("相机关系", "默认只比较视场区可能重合的相机对"),
                ("试验时间", "18秒，AirSim ClockSpeed为0.1"),
                ("试验种子", "20260816；每个规模一组保存观测"),
                ("在线身份", "匿名局部编号；真实编号只用于离线评分"),
            ),
        )
    )
    lines.extend(
        [
            "",
            "三组回放已经保存图像拍摄时刻的相机光心和最终相机姿态，因此本报告结果按合成相机位姿读取。新增加的机体安装偏移、导航误差、机体姿态误差和云台角误差传播已经形成计算与单元测试，但尚未用带非零误差的新AirSim观测重新验证。",
            "",
            "### 4.2 图网络诊断参数",
            "",
            "机间图网络只调整概率门限、几何与图网络融合权重以及未匹配代价。六类硬门控、网络权重文件、匈牙利匹配和多帧确认保持不变。三组保存回放共搜索36组参数，选定值如下。参数直接在本报告回放上选择，结果用于诊断，不能视为独立留出验证。",
            "",
        ]
    )
    lines.extend(
        _table(
            ("参数", "搜索范围", "本报告取值"),
            (
                ("同目标概率门限", "0、0.05、0.15、0.30", _ratio(parameters["gnn_probability_threshold"], 2)),
                ("图网络融合权重", "0.25、0.45、0.65", _ratio(parameters["gnn_probability_weight"], 2)),
                ("未匹配代价", "0.85、1.05、1.25", _ratio(parameters["unmatched_cost"], 2)),
            ),
        )
    )
    lines.extend(
        [
            "",
            "### 4.3 评价方法",
            "",
            "中心交接统计正确绑定、错误绑定、绑定精度和绑定覆盖度。机间配准的评价分母只包含至少被两台相机看到、具备配准机会的真实目标。关系精度表示输出关系中正确关系的比例，关系覆盖度表示应建立的真实关系中已经建立的比例。",
            "",
            "目标等权纯度表示一个目标的最佳目标簇中有多少成员确属该目标；目标等权完整度表示该目标应合并的局部航迹有多少进入最佳目标簇。独立正确成簇比例要求目标的全部可评分局部航迹进入同一簇且没有混入其他目标。身份混合目标数统计进入混合簇的目标，未完成目标数统计有双视角机会但没有形成正确跨视角关系的目标。",
            "",
            "## 五、试验结果",
            "",
            "### 5.1 中心航迹与无人机交接",
            "",
            "中心交接分别采用几何方法和图神经网络方法对同一批AirSim匿名观测复算。图网络使用与试验种子隔离的合成数据训练，试验回放不进入训练。",
            "",
        ]
    )
    center_rows = []
    center_totals = {
        "几何方法": {"true": 0, "false": 0, "correct_source": 0},
        "图神经网络": {"true": 0, "false": 0, "correct_source": 0},
    }
    for run in runs:
        for method, result in (
            ("几何方法", center_geometry[run.spec.scenario_id]),
            ("图神经网络", center_gnn[run.spec.scenario_id]),
        ):
            metrics = result["metrics"]
            center_totals[method]["true"] += int(metrics["true_binding_count"])
            center_totals[method]["false"] += int(metrics["false_binding_count"])
            center_totals[method]["correct_source"] += int(metrics["correct_source_count"])
            center_rows.append(
                (
                    run.spec.label,
                    method,
                    metrics["true_binding_count"],
                    metrics["false_binding_count"],
                    _ratio(metrics["binding_precision"]),
                    _ratio(metrics["binding_recall"]),
                    f"{float(result['timing']['median_wall_duration_s']):.3f}秒",
                )
            )
    for method in ("几何方法", "图神经网络"):
        totals = center_totals[method]
        output_count = totals["true"] + totals["false"]
        center_rows.append(
            (
                "三组合计",
                method,
                totals["true"],
                totals["false"],
                _ratio(totals["true"] / max(output_count, 1)),
                _ratio(totals["true"] / max(totals["correct_source"], 1)),
                "按场景列示",
            )
        )
    lines.extend(
        _table(
            ("场景", "方法", "正确绑定", "错误绑定", "绑定精度", "绑定覆盖度", "复算耗时中位数"),
            center_rows,
        )
    )
    lines.extend(
        [
            "",
            _figure("08_handover_results.png", "三组中心交接的几何与图网络结果"),
            "",
            _figure("09_projection_ellipse_matching.png", "中心预测范围与机载观测匹配实例"),
            "",
            "20目标/8机和20目标/30机中，两种方法得到相同的正确与错误绑定数量。图网络复算耗时分别增加约0.069秒和0.130秒，没有带来数量上的改善。40目标/50机中，几何方法得到31条正确绑定和1条错误绑定；图网络保留31条正确绑定并去除该错误关系，绑定精度由0.9688提高到1.0000，复算耗时增加约0.043秒。",
            "",
            "三组合计，几何方法形成61条正确绑定和1条错误绑定，绑定精度为0.9839，绑定覆盖度为0.9531；图网络同样形成61条正确绑定，没有错误绑定，绑定精度为1.0000，绑定覆盖度保持0.9531。在正确绑定数量和覆盖度不降低的条件下，图网络减少了错误关系，因此本次已测中心交接场景中，图网络总体效果优于几何方法。",
            "",
            "该结论来自种子20260816的保存观测离线回放。图网络已经实际用于中心交接对照，但单个种子的证据还不足以改变在线默认路线。后续需要在导航、姿态、云台、时间同步和检测误差条件下开展多种子复核。",
            "",
            "### 5.2 拦截无人机之间的配准",
            "",
            "下表比较视场区几何方法和同批回放上的图网络诊断结果。所有方法使用相同六类硬门控和相机对范围。",
            "",
        ]
    )
    quality_rows = []
    scale_rows = []
    for scenario_id in ("n20_m8", "n20_m30", "n40_m50"):
        for method, record in (
            ("视场区几何", crossview_geometry[scenario_id]),
            ("视场区图网络", crossview_gnn[scenario_id]),
        ):
            quality_rows.append(
                (
                    labels[scenario_id],
                    method,
                    record["opportunity_target_count"],
                    _ratio(record["association_precision"]),
                    _ratio(record["association_recall"]),
                    _ratio(record["target_equal_mean_purity"]),
                    _ratio(record["target_equal_mean_completeness"]),
                    _ratio(record["independently_correct_target_rate"]),
                    record["mixed_identity_target_count"],
                    record["unregistered_opportunity_target_count"],
                )
            )
            scale_rows.append(
                (
                    labels[scenario_id],
                    method,
                    record["retained_camera_pair_count"],
                    record["candidate_edge_count"],
                    f"{float(record['elapsed_s']):.2f}秒",
                )
            )
    lines.extend(
        _table(
            (
                "场景",
                "方法",
                "机会目标",
                "关系精度",
                "关系覆盖度",
                "目标等权纯度",
                "目标等权完整度",
                "独立正确成簇比例",
                "身份混合目标",
                "未完成目标",
            ),
            quality_rows,
        )
    )
    lines.extend(["", "耗时为无缓存关联计算，不含Word生成和图片绘制。", ""])
    lines.extend(
        _table(
            ("场景", "方法", "视场区相机对", "候选关系", "无缓存耗时"),
            scale_rows,
        )
    )
    lines.extend(
        [
            "",
            _figure("13_local_pixel_tracks.png", "20目标/30机场景的匿名机载局部航迹"),
            "",
            _figure("14_crossview_relation_graph.png", "20目标/30机场景的跨相机关联结果"),
            "",
            _figure("12_terminal_metric_comparison.png", "视场区几何与图网络结果对比"),
            "",
            "20目标/8机中，视场区几何方法的关系精度为1.0000，目标等权完整度为0.9667，没有身份混合或未完成目标。图网络保持关系精度1.0000，但关系覆盖度降至0.1562，15个具备机会的目标没有完成配准。该组参数对低歧义场景过于保守。",
            "",
            "20目标/30机中，几何方法的关系精度为0.7402，7个目标发生身份混合。图网络把关系精度提高到0.9736，身份混合降为0，目标等权完整度保持在0.9587。该场景中，同一视场区内存在较多相邻候选，图网络对候选竞争关系的排序产生了明显作用。",
            "",
            "40目标/50机中，几何方法的关系精度为0.9960，目标等权完整度为0.9710，没有身份混合或未完成目标。图网络关系精度为0.9971，但关系覆盖度降至0.4003，目标等权完整度降至0.5666。几何方法已经能稳定区分大部分候选，图网络概率门限删除了过多正确关系。",
            "",
            "## 六、结论与限制",
            "",
            "中心交接已经实际运行几何方法和图神经网络两条计算路线。两条路线共用时刻对齐、完整相机位姿、误差传播、匈牙利一一匹配和多帧确认。三组回放中，图网络在保持61条正确绑定和0.9531覆盖度的同时，将错误绑定由1条降为0。本次已测中心交接场景中，图网络总体效果优于几何方法；当前在线默认仍采用几何方法，待多种误差和多种子复核后再决定是否切换。",
            "",
            "机间配准已经把时间差、交会角、视线分离、重投影、运动拟合和目标尺度落实为六类硬门控，并在门控后比较几何评分和图网络评分。图网络在20目标/30机场景明显降低身份混合，但同一组参数在另外两个场景损失了较多正确关系。当前不宜用统一图网络参数替换视场区几何方法。",
            "",
            "本报告三组结果均来自种子20260816的一次AirSim保存回放。真实检测器的漏检和虚警、时间同步漂移、非零安装偏移、导航误差、机体姿态误差、云台稳定误差和通信延迟尚未进入本轮结果。下一步应先按误差来源分别注入，再完成多种子标定，并使用独立留出回放确定图网络概率门限。",
            "",
        ]
    )
    return "\n".join(lines)


def _set_font(run: Any, chinese: str, western: str, size: float, *, bold: bool | None = None) -> None:
    run.font.name = western
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), chinese)


def _configure_document(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(1.9)
    section.left_margin = Cm(2.349)
    section.right_margin = Cm(2.349)

    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "宋体")
    for style_name, size in (("Heading 1", 16.5), ("Heading 2", 14.0), ("Heading 3", 12.5)):
        style = document.styles[style_name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = None
        style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "黑体")
    document.styles["Heading 1"].paragraph_format.space_after = Pt(8)


def _add_cover(document: Document, title: str, subtitle: str) -> None:
    for _ in range(5):
        document.add_paragraph()
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(paragraph.add_run(title), "黑体", "Times New Roman", 26, bold=True)
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(paragraph.add_run(subtitle), "黑体", "Times New Roman", 15, bold=True)
    for _ in range(7):
        document.add_paragraph()
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(paragraph.add_run("MSM 项目组"), "宋体", "Times New Roman", 12)
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(paragraph.add_run("2026 年 8 月"), "宋体", "Times New Roman", 11)
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(paragraph.add_run("科研仿真与技术论证材料"), "宋体", "Times New Roman", 9.5)
    document.add_page_break()


def _plain_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return text.replace("\\|", "|")


def _parse_table_row(line: str) -> list[str]:
    return [_plain_markdown(cell.strip()) for cell in line.strip().strip("|").split("|")]


def _shade_cell(cell: Any, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), fill)


def _repeat_table_header(row: Any) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _add_table(document: Document, rows: Sequence[Sequence[str]]) -> None:
    if not rows:
        return
    column_count = len(rows[0])
    table = document.add_table(rows=len(rows), cols=column_count)
    table.style = "Table Grid"
    table.autofit = True
    font_size = 7.5 if column_count >= 10 else (8.5 if column_count >= 7 else 9.5)
    for row_index, values in enumerate(rows):
        for column_index, value in enumerate(values):
            cell = table.cell(row_index, column_index)
            cell.text = value
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                for run in paragraph.runs:
                    _set_font(run, "宋体", "Times New Roman", font_size, bold=row_index == 0)
            if row_index == 0:
                _shade_cell(cell, "D9E2F3")
    _repeat_table_header(table.rows[0])
    document.add_paragraph()


def _add_picture(document: Document, image_path: Path, caption: str, figure_number: int) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(5)
    paragraph.add_run().add_picture(str(image_path), width=Cm(16.0))
    caption_paragraph = document.add_paragraph()
    caption_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption_paragraph.paragraph_format.space_after = Pt(5)
    _set_font(
        caption_paragraph.add_run(f"图 {figure_number}  {caption}"),
        "宋体",
        "Times New Roman",
        9.5,
    )


def build_docx(markdown_path: Path, docx_path: Path, *, title: str, subtitle: str) -> Path:
    document = Document()
    _configure_document(document)
    _add_cover(document, title, subtitle)
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    index = 0
    figure_number = 0
    first_h1_skipped = False
    first_section = True
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("# ") and not first_h1_skipped:
            first_h1_skipped = True
            index += 1
            continue
        if line.startswith("## "):
            paragraph = document.add_paragraph(
                _plain_markdown(line[3:]), style="Heading 1"
            )
            if not first_section:
                paragraph.paragraph_format.page_break_before = True
            first_section = False
            index += 1
            continue
        if line.startswith("### "):
            document.add_paragraph(_plain_markdown(line[4:]), style="Heading 2")
            index += 1
            continue
        if line.startswith("#### "):
            document.add_paragraph(_plain_markdown(line[5:]), style="Heading 3")
            index += 1
            continue
        image_match = re.fullmatch(r"!\[(.*?)\]\((.*?)\)", line)
        if image_match:
            figure_number += 1
            image_path = (markdown_path.parent / image_match.group(2)).resolve()
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            _add_picture(document, image_path, image_match.group(1), figure_number)
            index += 1
            continue
        if line.startswith("```"):
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(3)
            paragraph.paragraph_format.space_after = Pt(5)
            _shade_cell_like_paragraph(paragraph, "F2F2F2")
            _set_font(paragraph.add_run("\n".join(code_lines)), "宋体", "Courier New", 10)
            continue
        if line.startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            parsed = [_parse_table_row(value) for value in table_lines]
            if len(parsed) >= 2 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in parsed[1]):
                parsed.pop(1)
            _add_table(document, parsed)
            continue
        if re.match(r"^\d+\.\s+", line):
            text = re.sub(r"^\d+\.\s+", "", line)
            paragraph = document.add_paragraph(style="List Number")
            _set_font(paragraph.add_run(_plain_markdown(text)), "宋体", "Times New Roman", 12)
            index += 1
            continue
        if line.startswith("- "):
            paragraph = document.add_paragraph(style="List Bullet")
            _set_font(paragraph.add_run(_plain_markdown(line[2:])), "宋体", "Times New Roman", 12)
            index += 1
            continue
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(4)
        _set_font(paragraph.add_run(_plain_markdown(line)), "宋体", "Times New Roman", 12)
        index += 1
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(docx_path)
    return docx_path


def _shade_cell_like_paragraph(paragraph: Any, fill: str) -> None:
    paragraph_properties = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    paragraph_properties.append(shading)


def generate() -> tuple[Path, ...]:
    runs, benchmark = _load_evidence()
    search_summary = _load_search_matrix()
    terminal_selection = _load_terminal_selection()
    search_assets = build_search_assets()
    terminal_assets = build_terminal_assets(terminal_selection)
    SEARCH_MD.write_text(build_search_matrix_markdown(search_summary), encoding="utf-8")
    TERMINAL_MD.write_text(
        build_terminal_markdown(runs, benchmark, terminal_selection),
        encoding="utf-8",
    )
    build_docx(
        SEARCH_MD,
        SEARCH_DOCX,
        title="协同搜索试验报告",
        subtitle="算法原理、试验配置与结果分析",
    )
    build_docx(
        TERMINAL_MD,
        TERMINAL_DOCX,
        title="末端目标配准试验报告",
        subtitle="中心交接、机间关联与试验结果",
    )
    return (
        SEARCH_MD,
        SEARCH_DOCX,
        TERMINAL_MD,
        TERMINAL_DOCX,
        *search_assets,
        *terminal_assets,
    )


def generate_search() -> tuple[Path, ...]:
    search_summary = _load_search_matrix()
    assets = build_search_assets()
    SEARCH_MD.write_text(build_search_matrix_markdown(search_summary), encoding="utf-8")
    build_docx(
        SEARCH_MD,
        SEARCH_DOCX,
        title="协同搜索试验报告",
        subtitle="中心粗位置条件下的离线调度与视锥验证",
    )
    return (SEARCH_MD, SEARCH_DOCX, *assets)


def generate_terminal() -> tuple[Path, ...]:
    runs, benchmark = _load_evidence()
    terminal_selection = _load_terminal_selection()
    assets = build_terminal_assets(terminal_selection)
    TERMINAL_MD.write_text(
        build_terminal_markdown(runs, benchmark, terminal_selection),
        encoding="utf-8",
    )
    build_docx(
        TERMINAL_MD,
        TERMINAL_DOCX,
        title="末端目标配准试验报告",
        subtitle="坐标时间链、中心交接与机间配准",
    )
    return (TERMINAL_MD, TERMINAL_DOCX, *assets)


def main() -> int:
    if "--search-only" in sys.argv[1:]:
        paths = generate_search()
    elif "--terminal-only" in sys.argv[1:]:
        paths = generate_terminal()
    else:
        paths = generate()
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
