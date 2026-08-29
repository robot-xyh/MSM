#!/usr/bin/env python3
"""Generate reproducible black-and-white drawings for patent application 1."""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle


OUT_DIR = Path(__file__).resolve().parent
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"
FONT = font_manager.FontProperties(fname=FONT_PATH)
matplotlib.rcParams["svg.hashsalt"] = "msm-patent1-v1"


def setup(width: float = 12.0, height: float = 7.2):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 60)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, label, number=None, *, lw=1.5, dashed=False, fontsize=11):
    rect = Rectangle(
        (x, y),
        w,
        h,
        facecolor="white",
        edgecolor="black",
        linewidth=lw,
        linestyle="--" if dashed else "-",
    )
    ax.add_patch(rect)
    text = f"{number}  {label}" if number is not None else label
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontproperties=FONT,
        fontsize=fontsize,
        linespacing=1.35,
    )
    return rect


def circle(ax, x, y, r, label, number=None, *, fontsize=10, lw=1.4):
    patch = Circle((x, y), r, facecolor="white", edgecolor="black", linewidth=lw)
    ax.add_patch(patch)
    text = f"{number}\n{label}" if number is not None else label
    ax.text(x, y, text, ha="center", va="center", fontproperties=FONT, fontsize=fontsize)
    return patch


def frame(ax, x, y, w, h, label, number, *, fontsize=11, lw=1.6):
    patch = Rectangle((x, y), w, h, facecolor="white", edgecolor="black", linewidth=lw)
    ax.add_patch(patch)
    ax.text(x + 2, y + h - 2, number, ha="left", va="top", fontproperties=FONT, fontsize=9)
    ax.text(x + w / 2, y + h - 3, label, ha="center", va="top", fontproperties=FONT, fontsize=fontsize)
    return patch


def arrow(ax, x1, y1, x2, y2, *, label=None, dashed=False, bend=0.0, lw=1.4):
    patch = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle="-|>",
        mutation_scale=13,
        linewidth=lw,
        linestyle="--" if dashed else "-",
        color="black",
        connectionstyle=f"arc3,rad={bend}",
    )
    ax.add_patch(patch)
    if label:
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2 + (5 * bend if bend else 1.2)
        ax.text(mx, my, label, ha="center", va="bottom", fontproperties=FONT, fontsize=9)
    return patch


def title(ax, text):
    ax.text(50, 57.5, text, ha="center", va="center", fontproperties=FONT, fontsize=14)


def save(fig, stem):
    fig.savefig(
        OUT_DIR / f"{stem}.png",
        dpi=240,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "MSM patent1 build_figures.py"},
    )
    fig.savefig(
        OUT_DIR / f"{stem}.svg",
        bbox_inches="tight",
        facecolor="white",
        metadata={"Date": None},
    )
    plt.close(fig)


def figure_1():
    fig, ax = setup(12, 8)
    title(ax, "集群无人机协同反无人机系统架构")
    box(ax, 3, 49, 94, 7, "集群无人机协同反无人机系统", "100", lw=1.8, fontsize=13)
    boxes = [
        (3, 36, 19, 8, "状态采集模块", "110"),
        (28, 36, 19, 8, "图构建模块", "120"),
        (53, 36, 19, 8, "多智能体决策模块", "130"),
        (78, 36, 19, 8, "安全投影模块", "140"),
        (15, 20, 20, 8, "确定性分配模块", "150"),
        (40, 20, 20, 8, "滚动计划管理模块", "160"),
        (65, 20, 20, 8, "降级接管模块", "170"),
        (40, 6, 20, 8, "计划发布接口", "180"),
    ]
    for item in boxes:
        box(ax, *item)
    arrow(ax, 22, 40, 28, 40)
    arrow(ax, 47, 40, 53, 40)
    arrow(ax, 72, 40, 78, 40)
    arrow(ax, 88, 36, 35, 28, bend=-0.08)
    arrow(ax, 35, 24, 40, 24)
    arrow(ax, 60, 24, 65, 24)
    arrow(ax, 75, 20, 60, 12, bend=-0.05)
    arrow(ax, 50, 20, 50, 14)
    arrow(ax, 15, 20, 10, 36, label="状态反馈", dashed=True, bend=-0.12)
    save(fig, "fig01_system_architecture")


def figure_2():
    fig, ax = setup(12, 7)
    title(ax, "区域状态图与稀疏目标—资源候选图")
    frame(ax, 2, 5, 44, 48, "区域状态图", "210", fontsize=12)
    coords = [(13, 36), (34, 39), (34, 19), (13, 17)]
    labels = [("211", "区域1"), ("212", "区域2"), ("213", "区域3"), ("214", "区域4")]
    for (x, y), (n, lab) in zip(coords, labels):
        circle(ax, x, y, 5.2, lab, n, fontsize=9)
    for edge_index, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)], 1):
        x1, y1 = coords[a]
        x2, y2 = coords[b]
        length = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        radius = 5.2
        ax.plot(
            [x1 + radius * ux, x2 - radius * ux],
            [y1 + radius * uy, y2 - radius * uy],
            color="black",
            linewidth=1.3,
        )
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = [(0, 2), (2, 0), (0, -2), (-2, 0)][edge_index - 1]
        ax.text(mx + dx, my + dy, "215", ha="center", va="center", fontproperties=FONT, fontsize=8)

    frame(ax, 52, 5, 46, 48, "稀疏目标—资源候选图", "220", fontsize=12)
    targets = [(60, 39), (60, 29), (60, 19)]
    resources = [(90, 42), (90, 32), (90, 22), (90, 12)]
    for idx, (x, y) in enumerate(targets, 1):
        circle(ax, x, y, 3.5, f"目标{idx}", "221", fontsize=8)
    for idx, (x, y) in enumerate(resources, 1):
        circle(ax, x, y, 3.5, f"资源{idx}", "222", fontsize=8)
    for ti, ri in [(0, 0), (0, 1), (1, 1), (1, 2), (2, 2), (2, 3)]:
        x1, y1 = targets[ti]
        x2, y2 = resources[ri]
        arrow(ax, x1 + 3.6, y1, x2 - 3.6, y2, label="223", lw=1.0)
    ax.text(75, 7.5, "仅保留通过确定性准入检查的候选边", ha="center", fontproperties=FONT, fontsize=9)
    save(fig, "fig02_region_and_candidate_graphs")


def figure_3():
    fig, ax = setup(12, 7)
    title(ax, "学习修正、幅度约束与确定性安全投影")
    box(ax, 3, 39, 20, 9, "规则代价\nC_rule", "330")
    box(ax, 3, 20, 20, 9, "原始学习修正\ndelta_C", "310")
    box(ax, 29, 20, 21, 9, "有界修正\nalpha*tanh(delta_C)", "320")
    box(ax, 56, 31, 19, 10, "候选最终代价\nC_final", "350")
    box(ax, 80, 25, 17, 22, "确定性安全投影\n资源守恒\n可达与预留\n占用与通信\n空域、版本、有效期", "340", fontsize=9)
    box(ax, 56, 7, 19, 9, "确定性分配求解", "360")
    arrow(ax, 23, 24.5, 29, 24.5)
    arrow(ax, 23, 43.5, 56, 37)
    arrow(ax, 50, 24.5, 56, 35)
    arrow(ax, 75, 36, 80, 36)
    arrow(ax, 88.5, 25, 75, 14, bend=-0.05)
    ax.text(65.5, 25, "C_final = C_rule +\nalpha*tanh(delta_C)", ha="center", va="center", fontproperties=FONT, fontsize=10)
    ax.text(88.5, 20.5, "修正、裁剪或拒绝", ha="center", fontproperties=FONT, fontsize=9)
    save(fig, "fig03_learning_and_safety_projection")


def figure_4():
    fig, ax = setup(12, 7)
    title(ax, "确定性一一分配与多资源任务展开")
    frame(ax, 3, 7, 22, 43, "任务需求项", "410", fontsize=11)
    task_y = [39, 30, 21, 12]
    task_labels = ["目标A-主用", "目标B-主用1", "目标B-主用2", "目标B-备用"]
    for y, label in zip(task_y, task_labels):
        box(ax, 6, y - 3, 16, 5.5, label, None, fontsize=8.5)
    frame(ax, 75, 7, 22, 43, "拦截资源", "420", fontsize=11)
    res_y = [40, 31, 22, 13]
    for idx, y in enumerate(res_y, 1):
        box(ax, 78, y - 3, 16, 5.5, f"无人机{idx}", None, fontsize=9)
    box(ax, 36, 39, 28, 8, "稀疏代价矩阵", "440")
    box(ax, 36, 25, 28, 8, "匈牙利算法或\n最小费用流", "450")
    box(ax, 36, 11, 28, 8, "一一任务关系或\n多资源任务关系", "460")
    arrow(ax, 25, 36, 36, 43)
    arrow(ax, 75, 36, 64, 43)
    arrow(ax, 50, 39, 50, 33)
    arrow(ax, 50, 25, 50, 19)
    arrow(ax, 36, 15, 25, 15, label="未满足项430", dashed=True)
    arrow(ax, 64, 15, 75, 15, label="已分配关系", bend=-0.05)
    save(fig, "fig04_deterministic_assignment")


def figure_5():
    fig, ax = setup(12, 7)
    title(ax, "滚动重规划、版本递增与计划有效期")
    box(ax, 3, 36, 16, 9, "当前计划V_k", "510")
    box(ax, 24, 36, 16, 9, "状态监测", "520")
    box(ax, 45, 36, 18, 9, "触发判定", "530")
    box(ax, 68, 36, 17, 9, "候选计划V_k+1", "540")
    box(ax, 67, 18, 19, 9, "迟滞与最短\n保持时间检查", "550")
    box(ax, 42, 18, 18, 9, "发布新计划", "560")
    box(ax, 17, 18, 18, 9, "版本及有效期\n执行检查", "570")
    arrow(ax, 19, 40.5, 24, 40.5)
    arrow(ax, 40, 40.5, 45, 40.5)
    arrow(ax, 63, 40.5, 68, 40.5)
    arrow(ax, 76.5, 36, 76.5, 27)
    arrow(ax, 67, 22.5, 60, 22.5)
    arrow(ax, 42, 22.5, 35, 22.5)
    arrow(ax, 17, 22.5, 10, 36, label="有效计划继续执行", bend=-0.12)
    arrow(ax, 54, 36, 54, 27, label="硬事件直接重算", dashed=True)
    ax.text(54, 11, "普通变化须满足收益门限；故障、不可达或到期不受迟滞限制", ha="center", fontproperties=FONT, fontsize=9.5)
    save(fig, "fig05_rolling_plan_versions")


def figure_6():
    fig, ax = setup(12, 7.5)
    title(ax, "分级降级接管与受影响任务重算")
    box(ax, 4, 39, 20, 10, "中心节点\n全局计划所有者", "610")
    box(ax, 40, 39, 20, 10, "区域节点\n区域计划所有者", "620")
    box(ax, 76, 39, 20, 10, "临时协调无人机\n临时计划所有者", "640")
    arrow(ax, 24, 44, 40, 44, label="中心失效")
    arrow(ax, 60, 44, 76, 44, label="区域节点失效")
    box(ax, 7, 21, 24, 9, "持续有效的任务关系", "660")
    box(ax, 38, 21, 24, 9, "受影响任务集合", "650")
    box(ax, 69, 21, 24, 9, "确定性局部重算", "670")
    arrow(ax, 50, 39, 50, 30)
    arrow(ax, 88, 39, 81, 30)
    arrow(ax, 62, 25.5, 69, 25.5)
    box(ax, 27, 6, 46, 9, "任期、版本、有效期及唯一发布权校验", "680")
    arrow(ax, 19, 21, 36, 15, label="继承", bend=-0.05)
    arrow(ax, 81, 21, 64, 15, label="发布", bend=0.05)
    ax.text(50, 3, "无法确定唯一发布者或计划冲突时停止发布新的任务关系", ha="center", fontproperties=FONT, fontsize=9.5)
    save(fig, "fig06_degraded_takeover")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    figure_1()
    figure_2()
    figure_3()
    figure_4()
    figure_5()
    figure_6()


if __name__ == "__main__":
    main()
