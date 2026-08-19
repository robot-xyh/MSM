#!/usr/bin/env python3
"""Build Word-ready Chinese diagrams for direct center-to-interceptor search."""

from __future__ import annotations

from pathlib import Path
import warnings

warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = (
    ROOT
    / "deliverables"
    / "leadership_report"
    / "assets"
    / "scheme_template_material"
)

BLUE = "#2E6F9E"
ORANGE = "#C76E2E"
GREEN = "#2F8B5B"
RED = "#B4473A"
DARK = "#202A33"
GRAY = "#687581"
LIGHT = "#F4F6F7"


def configure() -> None:
    plt.rcParams.update(
        {
            "font.sans-serif": [
                "Noto Sans CJK SC",
                "Noto Sans CJK JP",
                "Source Han Sans SC",
                "Droid Sans Fallback",
                "SimHei",
                "DejaVu Sans",
            ],
            "axes.unicode_minus": False,
            "font.size": 12,
        }
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def box(axis, x, y, width, height, text, *, edge=GRAY, face=LIGHT, size=11) -> None:
    axis.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.025,rounding_size=0.08",
            linewidth=1.7,
            edgecolor=edge,
            facecolor=face,
        )
    )
    axis.text(
        x + width / 2,
        y + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=size,
        color=DARK,
    )


def arrow(axis, start, end, *, color=GRAY, dashed=False, width=1.8) -> None:
    axis.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "lw": width,
            "linestyle": "--" if dashed else "-",
            "mutation_scale": 14,
        },
    )


def drone(axis, x, y, label, color) -> None:
    axis.add_patch(Circle((x, y), 0.14, facecolor=color, edgecolor="white", lw=1.4))
    for dx, dy in ((-0.28, -0.20), (-0.28, 0.20), (0.28, -0.20), (0.28, 0.20)):
        axis.plot([x, x + dx * 0.72], [y, y + dy * 0.72], color=color, lw=2.0)
        axis.add_patch(Circle((x + dx, y + dy), 0.09, facecolor="white", edgecolor=color, lw=1.6))
    axis.text(x, y - 0.48, label, ha="center", va="top", fontsize=10.5, color=color, weight="bold")


def save(figure, filename: str) -> None:
    figure.savefig(OUTPUT_DIR / filename, dpi=220, facecolor="white", bbox_inches="tight")
    plt.close(figure)


def draw_search_architecture() -> None:
    figure, axis = plt.subplots(figsize=(15.5, 8.8))
    axis.set_xlim(0, 16)
    axis.set_ylim(0, 9)
    axis.axis("off")
    axis.text(8, 8.55, "中心粗线索下的拦截无人机协同搜索", ha="center", fontsize=22, weight="bold")
    axis.text(
        8,
        8.13,
        "中心给出概率区域和有效期，各机按自身位置、视场和任务状态分担搜索",
        ha="center",
        fontsize=12,
        color=GRAY,
    )

    box(
        axis,
        5.25,
        6.65,
        5.5,
        0.95,
        "中心双光电与火指控\n目标数量区间、粗概率区域、信息时刻、任务版本",
        edge=BLUE,
        face="#E9F2F8",
        size=11.5,
    )

    axis.add_patch(
        Ellipse(
            (8, 4.65),
            8.8,
            2.55,
            angle=-4,
            facecolor="#EDF2F4",
            edgecolor=GRAY,
            lw=1.8,
            linestyle="--",
        )
    )
    axis.text(8, 5.73, "随时间扩张的目标概率区域", ha="center", fontsize=12, color=DARK, weight="bold")
    cells = (
        (4.55, 4.25, "主搜A", BLUE),
        (6.05, 4.62, "边界B", GREEN),
        (7.55, 4.18, "高概率C", RED),
        (9.05, 4.62, "复核D", ORANGE),
        (10.55, 4.20, "补扫E", GREEN),
    )
    for x, y, label, color in cells:
        box(axis, x, y, 1.15, 0.68, label, edge=color, face="white", size=10.5)

    arrow(axis, (8, 6.65), (8, 5.88), color=BLUE)
    drones = (
        (2.2, 2.45, "无人机1\n主搜索", BLUE, (4.65, 4.22)),
        (5.9, 1.95, "无人机2\n边界补扫", GREEN, (6.55, 4.53)),
        (10.1, 1.95, "无人机3\n候选复核", ORANGE, (9.62, 4.53)),
        (13.8, 2.45, "无人机4\n机动后备", RED, (10.95, 4.15)),
    )
    for x, y, label, color, target in drones:
        drone(axis, x, y, label, color)
        arrow(axis, (x, y + 0.35), target, color=color, dashed=True, width=1.6)

    for start, end in (((2.55, 2.38), (5.48, 2.02)), ((6.3, 1.95), (9.7, 1.95)), ((10.48, 2.02), (13.45, 2.38))):
        axis.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=GRAY,
            lw=1.2,
            linestyle=":",
        )
    box(
        axis,
        2.1,
        0.02,
        11.8,
        0.68,
        "机间互通搜索单元、未发现质量、候选短航迹、云台状态和任务有效期。\n发现目标的无人机转入连续跟踪，未搜索单元立即交给其他无人机。",
        edge=GRAY,
        face=LIGHT,
        size=10.5,
    )
    save(figure, "08_center_interceptor_search_architecture.png")


def draw_search_allocation() -> None:
    figure, axis = plt.subplots(figsize=(15.5, 8.8))
    axis.set_xlim(0, 16)
    axis.set_ylim(0, 9)
    axis.axis("off")
    axis.text(8, 8.55, "拦截无人机搜索单元分配", ha="center", fontsize=22, weight="bold")
    axis.text(
        8,
        8.12,
        "可见光先进行较远距离广域搜索，红外在进入有效距离后承担复核和连续跟踪",
        ha="center",
        fontsize=12,
        color=GRAY,
    )

    axis.add_patch(
        Ellipse(
            (8, 5.15),
            11.6,
            3.8,
            angle=-3,
            facecolor="#F2F5F6",
            edgecolor=GRAY,
            lw=2.0,
            linestyle="--",
        )
    )
    axis.text(8, 6.72, "中心粗线索形成的三维概率区域在当前高度层的投影", ha="center", fontsize=11.5, weight="bold")

    cell_data = (
        (3.25, 4.65, "A\n高概率", RED, "无人机1"),
        (5.05, 5.20, "B\n前沿", BLUE, "无人机2"),
        (6.85, 4.52, "C\n主方向", BLUE, "无人机2"),
        (8.65, 5.10, "D\n候选复核", ORANGE, "无人机3"),
        (10.45, 4.45, "E\n边界", GREEN, "无人机4"),
        (12.25, 5.05, "F\n低概率重访", GRAY, "后续周期"),
    )
    for x, y, label, color, owner in cell_data:
        axis.add_patch(Rectangle((x, y), 1.35, 1.02, facecolor="white", edgecolor=color, lw=1.8))
        axis.text(x + 0.675, y + 0.61, label, ha="center", va="center", fontsize=10.5, color=DARK)
        axis.text(x + 0.675, y + 0.16, owner, ha="center", va="center", fontsize=8.8, color=color)

    drone_positions = (
        (3.2, 2.05, "无人机1", RED, (3.9, 4.62)),
        (6.3, 1.55, "无人机2", BLUE, (6.2, 4.48)),
        (9.7, 1.55, "无人机3", ORANGE, (9.3, 5.05)),
        (12.8, 2.05, "无人机4", GREEN, (11.15, 4.42)),
    )
    for x, y, label, color, target in drone_positions:
        drone(axis, x, y, label, color)
        arrow(axis, (x, y + 0.35), target, color=color, width=1.7)

    box(
        axis,
        1.9,
        0.17,
        12.2,
        0.68,
        "分配收益 = 目标概率 × 预计探测率 × 紧迫度 - 转向时间 - 飞行机动 - 重复覆盖 - 通信风险 - 已锁定任务占用",
        edge=GRAY,
        face=LIGHT,
        size=10.7,
    )
    save(figure, "09_interceptor_search_cell_allocation.png")


def draw_direct_registration() -> None:
    figure, axis = plt.subplots(figsize=(15.5, 8.8))
    axis.set_xlim(0, 16)
    axis.set_ylim(0, 9)
    axis.axis("off")
    axis.text(8, 8.55, "双光电源航迹与机载局部航迹直接配准", ha="center", fontsize=22, weight="bold")
    axis.text(
        8,
        8.12,
        "源航迹直接投影到各拦截机图像，各机本地编号不同，确认后仍沿用同一源编号",
        ha="center",
        fontsize=12,
        color=GRAY,
    )

    box(axis, 0.55, 6.35, 2.55, 0.9, "中心双光电源航迹\n位置、速度、协方差、时刻", edge=BLUE, face="#E9F2F8")
    source_nodes = ((1.25, 4.95, "G1", BLUE), (2.38, 3.95, "G2", ORANGE))
    for x, y, label, color in source_nodes:
        axis.add_patch(Circle((x, y), 0.27, facecolor=color, edgecolor="white", lw=1.3))
        axis.text(x, y, label, color="white", ha="center", va="center", fontsize=10.5, weight="bold")
    arrow(axis, (1.45, 6.35), (1.3, 5.28), color=BLUE)
    arrow(axis, (2.25, 6.35), (2.35, 4.28), color=ORANGE)

    box(axis, 4.05, 6.35, 4.65, 0.9, "拦截机A图像\n预测椭圆内形成局部航迹A1、A2", edge=GREEN, face="#EAF5EF")
    box(axis, 10.15, 6.35, 4.65, 0.9, "拦截机B图像\n预测椭圆内形成局部航迹B1、B2", edge=RED, face="#F8ECEA")

    local_nodes = (
        (5.15, 4.95, "A1", BLUE),
        (7.25, 3.95, "A2", ORANGE),
        (11.25, 3.95, "B1", ORANGE),
        (13.35, 4.95, "B2", BLUE),
    )
    for x, y, label, color in local_nodes:
        axis.add_patch(Circle((x, y), 0.29, facecolor="white", edgecolor=color, lw=2.0))
        axis.text(x, y, label, color=color, ha="center", va="center", fontsize=10.5, weight="bold")

    selected = (
        ((1.52, 4.95), (4.84, 4.95), BLUE),
        ((2.65, 3.95), (6.94, 3.95), ORANGE),
        ((2.60, 4.05), (10.94, 3.95), ORANGE),
        ((1.50, 5.02), (13.04, 4.95), BLUE),
    )
    for start, end, color in selected:
        arrow(axis, start, end, color=color, width=2.2)

    axis.text(6.2, 5.35, "G1→A1", ha="center", fontsize=10.5, color=BLUE, weight="bold")
    axis.text(6.2, 3.52, "G2→A2", ha="center", fontsize=10.5, color=ORANGE, weight="bold")
    axis.text(11.1, 3.50, "G2→B1", ha="center", fontsize=10.5, color=ORANGE, weight="bold")
    axis.text(12.0, 5.35, "G1→B2", ha="center", fontsize=10.5, color=BLUE, weight="bold")

    box(
        axis,
        3.8,
        1.75,
        8.4,
        0.95,
        "时间与几何门控 → 运动连续性 → 一一分配 → 多帧确认\n结果：G1绑定A1、B2；G2绑定A2、B1",
        edge=GRAY,
        face=LIGHT,
        size=11,
    )
    box(
        axis,
        2.0,
        0.35,
        12.0,
        0.68,
        "本机编号只在本机使用。目标交叉时保留多种排列，证据不足时继续跟踪，不在单帧内强制交换身份。",
        edge=GRAY,
        face="white",
        size=10.8,
    )
    save(figure, "12_center_interceptor_direct_registration.png")


def main() -> None:
    configure()
    draw_search_architecture()
    draw_search_allocation()
    draw_direct_registration()


if __name__ == "__main__":
    main()
