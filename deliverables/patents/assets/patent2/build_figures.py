#!/usr/bin/env python3
"""Generate reproducible black-and-white drawings for patent draft 2."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, Polygon, Rectangle
import numpy as np


OUTPUT_DIR = Path(__file__).resolve().parent
FONT = "Noto Sans CJK JP"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [FONT, "Droid Sans Fallback", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "svg.fonttype": "none",
        "text.color": "black",
        "axes.edgecolor": "black",
    }
)


def new_figure(width: float = 12.0, height: float = 7.2):
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7.2)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text, number, fontsize=11):
    ax.add_patch(Rectangle((x, y), w, h, facecolor="white", edgecolor="black", linewidth=1.4))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize)
    ax.text(x + 0.12, y + h - 0.12, str(number), ha="left", va="top", fontsize=9)


def arrow(ax, start, end, text=None, fontsize=9, connectionstyle="arc3"):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.2,
            color="black",
            connectionstyle=connectionstyle,
        )
    )
    if text:
        x = (start[0] + end[0]) / 2
        y = (start[1] + end[1]) / 2 + 0.14
        ax.text(x, y, text, ha="center", va="bottom", fontsize=fontsize)


def save(fig, stem):
    fig.tight_layout(pad=0.25)
    fig.savefig(OUTPUT_DIR / f"{stem}.png", dpi=260, bbox_inches="tight", facecolor="white")
    fig.savefig(OUTPUT_DIR / f"{stem}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def figure_1_overall_flow():
    fig, ax = new_figure(12, 8.3)
    ax.set_ylim(0, 8.3)
    labels = [
        ("双站匿名检测及\n测量时刻状态", 101),
        ("像素反投影为\n空间单位视线", 102),
        ("同一扫描检测合并为\n扫描片段", 103),
        ("形成单站角航迹及\n状态协方差", 104),
        ("双站航迹时刻对齐", 105),
        ("归一化共面筛选及\n双向前K候选", 106),
        ("双侧图神经网络\n输出关系概率", 107),
        ("带未匹配项的\n匈牙利一一匹配", 108),
        ("多圈确认及\n短时保持", 109),
        ("双视线交会定位及\n三维运动拟合", 110),
    ]
    positions = []
    for row in range(5):
        y = 6.95 - row * 1.48
        if row % 2 == 0:
            positions.extend([(0.65, y), (6.35, y)])
        else:
            positions.extend([(6.35, y), (0.65, y)])
    for (label, number), (x, y) in zip(labels, positions):
        box(ax, x, y, 5.0, 0.88, label, number, fontsize=10.5)
    for index in range(len(positions) - 1):
        x1, y1 = positions[index]
        x2, y2 = positions[index + 1]
        if abs(y1 - y2) < 0.1:
            if x2 > x1:
                arrow(ax, (x1 + 5.0, y1 + 0.44), (x2, y2 + 0.44))
            else:
                arrow(ax, (x1, y1 + 0.44), (x2 + 5.0, y2 + 0.44))
        else:
            if x1 > 3:
                arrow(ax, (x1 + 2.5, y1), (x2 + 2.5, y2 + 0.88))
            else:
                arrow(ax, (x1 + 2.5, y1), (x2 + 2.5, y2 + 0.88))
    ax.text(6, 8.08, "图1  双光电多目标轨迹配准与交会定位总流程", ha="center", fontsize=13)
    save(fig, "fig1_overall_flow")


def figure_2_pixel_to_ray():
    fig, ax = new_figure()
    ax.text(6, 6.95, "图2  检测框中心像素转换为空间单位视线", ha="center", fontsize=13)
    # Camera and image plane.
    ax.add_patch(Polygon([[1.0, 2.5], [2.1, 3.0], [2.1, 4.2], [1.0, 4.7]], closed=True,
                         fill=False, edgecolor="black", linewidth=1.4))
    ax.text(0.6, 2.15, "相机光心", fontsize=10)
    ax.text(1.1, 2.55, "201", fontsize=9)
    ax.add_patch(Rectangle((3.0, 1.4), 2.4, 4.6, facecolor="white", edgecolor="black", linewidth=1.4))
    ax.text(4.2, 1.05, "理想像平面 202", ha="center", fontsize=10)
    # Detection box and center.
    ax.add_patch(Rectangle((3.55, 3.0), 1.15, 0.85, facecolor="white", edgecolor="black",
                           linewidth=1.3, linestyle="--"))
    ax.plot([4.125], [3.425], marker="o", markersize=5, color="black")
    ax.text(4.25, 3.55, "检测框中心 203", fontsize=9)
    # Rays and target.
    ax.plot([1.55, 4.125, 10.0], [3.6, 3.425, 5.25], color="black", linewidth=1.5)
    ax.add_patch(Circle((10.0, 5.25), 0.16, fill=False, edgecolor="black", linewidth=1.5))
    ax.text(9.45, 5.55, "目标方向 205", fontsize=10)
    arrow(ax, (5.2, 3.75), (8.35, 4.75), "空间单位视线 204")
    # Coordinate frames and rotation chain.
    arrow(ax, (1.55, 3.6), (2.55, 3.6))
    arrow(ax, (1.55, 3.6), (1.55, 4.6))
    ax.text(2.55, 3.35, "x_C", fontsize=9)
    ax.text(1.25, 4.65, "y_C", fontsize=9)
    box(ax, 6.0, 1.0, 4.9, 1.25,
        "内参与畸变校正 K^(-1)\n拍摄时刻旋转 R_NG(t) R_GC", 206, fontsize=10)
    arrow(ax, (5.4, 2.15), (6.0, 1.65))
    ax.text(6, 0.45, "空间射线：L(λ,t)=o(t)+λd(t)，λ>0", ha="center", fontsize=11)
    save(fig, "fig2_pixel_to_ray")


def figure_3_scanlet_track():
    fig, ax = new_figure()
    ax.text(6, 6.95, "图3  同一扫描检测合并及单站角航迹形成", ha="center", fontsize=13)
    ax.arrow(0.8, 1.0, 10.2, 0, head_width=0.11, head_length=0.2, fc="black", ec="black")
    ax.arrow(0.8, 1.0, 0, 5.2, head_width=0.11, head_length=0.2, fc="black", ec="black")
    ax.text(11.1, 0.72, "时间", fontsize=10)
    ax.text(0.28, 6.25, "方位/俯仰", fontsize=10, rotation=90)
    # Three sweeps with clustered detections.
    sweep_centers = [2.4, 5.7, 9.0]
    for idx, center in enumerate(sweep_centers, start=1):
        ax.axvspan(center - 0.75, center + 0.75, ymin=0.12, ymax=0.82,
                   facecolor="white", edgecolor="black", linestyle=":", linewidth=0.9)
        xs = np.array([-0.45, -0.2, 0.05, 0.32]) + center
        ys = 2.0 + 0.35 * idx + np.array([-0.08, 0.03, -0.02, 0.05])
        ax.plot(xs, ys, "x", color="black", markersize=6)
        ax.text(center, 1.35, f"第{idx}圈", ha="center", fontsize=9)
        ax.plot([center], [float(np.mean(ys))], marker="s", markersize=7,
                markerfacecolor="white", markeredgecolor="black")
        ax.text(center + 0.12, float(np.mean(ys)) + 0.18, f"{302 + idx - 1}", fontsize=8)
    ax.text(1.1, 5.85, "同圈相邻匿名检测 301", fontsize=10)
    ax.text(4.25, 5.85, "扫描片段 302-304", fontsize=10)
    # Track and covariance envelopes.
    centers_y = [2.35, 2.70, 3.05]
    ax.plot(sweep_centers, centers_y, color="black", linewidth=1.6)
    for x, y in zip(sweep_centers, centers_y):
        ax.add_patch(Ellipse((x, y), 0.6, 0.45, fill=False, edgecolor="black",
                             linewidth=1.0, linestyle="--"))
    ax.text(6.25, 5.15, "单站角航迹 305", fontsize=10)
    ax.text(6.25, 4.8, "状态：[方位，俯仰，方位角速度，俯仰角速度]", fontsize=9)
    ax.text(6.25, 4.5, "虚线椭圆为协方差 306", fontsize=9)
    # A missed sweep / coast example.
    ax.plot([9.0, 10.6], [3.05, 3.22], color="black", linestyle="--", linewidth=1.2)
    ax.add_patch(Circle((10.6, 3.22), 0.13, fill=False, edgecolor="black"))
    ax.text(9.45, 3.65, "短时漏检预测 307", fontsize=9)
    save(fig, "fig3_scanlet_angular_track")


def figure_4_coplanar_sparse_graph():
    fig, ax = new_figure()
    ax.text(6, 6.95, "图4  协方差归一化共面筛选与稀疏二分图", ha="center", fontsize=13)
    # Left: epipolar geometry.
    ax.add_patch(Circle((0.9, 1.5), 0.16, fill=False, edgecolor="black", linewidth=1.4))
    ax.add_patch(Circle((5.2, 1.5), 0.16, fill=False, edgecolor="black", linewidth=1.4))
    ax.text(0.45, 1.08, "A站 401", fontsize=9)
    ax.text(4.75, 1.08, "B站 402", fontsize=9)
    ax.plot([0.9, 5.2], [1.5, 1.5], color="black", linewidth=1.3)
    ax.text(2.55, 1.15, "基线 403", fontsize=9)
    target = (3.05, 5.25)
    ax.add_patch(Circle(target, 0.15, fill=False, edgecolor="black", linewidth=1.3))
    ax.text(3.2, 5.4, "目标 404", fontsize=9)
    ax.plot([0.9, target[0]], [1.5, target[1]], color="black", linewidth=1.3)
    ax.plot([5.2, target[0]], [1.5, target[1]], color="black", linewidth=1.3)
    ax.text(1.35, 3.55, "d_A 405", fontsize=9)
    ax.text(4.45, 3.55, "d_B 406", fontsize=9)
    # Incorrect candidate ray.
    ax.plot([5.2, 2.0], [1.5, 4.6], color="black", linewidth=1.0, linestyle="--")
    ax.text(3.6, 4.25, "待筛候选 407", fontsize=9)
    ax.text(2.95, 0.42, "r_n=|r_epi|/σ_epi", ha="center", fontsize=10)
    # Divider.
    ax.plot([6.05, 6.05], [0.55, 6.35], color="black", linewidth=1.0)
    # Right: sparse bipartite graph.
    left_nodes = [(7.0, 5.5), (7.0, 4.2), (7.0, 2.9), (7.0, 1.6)]
    right_nodes = [(11.0, 5.5), (11.0, 4.2), (11.0, 2.9), (11.0, 1.6)]
    for idx, (x, y) in enumerate(left_nodes, 1):
        ax.add_patch(Circle((x, y), 0.25, fill=False, edgecolor="black", linewidth=1.3))
        ax.text(x, y, f"A{idx}", ha="center", va="center", fontsize=8)
    for idx, (x, y) in enumerate(right_nodes, 1):
        ax.add_patch(Circle((x, y), 0.25, fill=False, edgecolor="black", linewidth=1.3))
        ax.text(x, y, f"B{idx}", ha="center", va="center", fontsize=8)
    edges = [(0, 0), (0, 1), (1, 1), (1, 2), (2, 1), (2, 2), (3, 2), (3, 3)]
    for i, j in edges:
        ax.plot([left_nodes[i][0] + 0.25, right_nodes[j][0] - 0.25],
                [left_nodes[i][1], right_nodes[j][1]], color="black", linewidth=1.0)
    ax.text(7.0, 6.05, "A站航迹 411", ha="center", fontsize=10)
    ax.text(11.0, 6.05, "B站航迹 412", ha="center", fontsize=10)
    ax.text(9.0, 0.72, "双向前K候选边的并集 413", ha="center", fontsize=10)
    save(fig, "fig4_coplanar_sparse_graph")


def figure_5_gnn_assignment():
    fig, ax = new_figure()
    ax.text(6, 6.95, "图5  图网络候选评分与带未匹配项的一一匹配", ha="center", fontsize=13)
    # Graph scoring block.
    box(ax, 0.45, 4.45, 2.0, 1.25, "A、B两侧\n航迹节点", 501, fontsize=10)
    box(ax, 3.05, 4.45, 2.0, 1.25, "候选边特征\n及邻域竞争", 502, fontsize=10)
    box(ax, 5.65, 4.45, 2.0, 1.25, "双侧消息传递\n与节点更新", 503, fontsize=10)
    box(ax, 8.25, 4.45, 2.0, 1.25, "同目标概率\np_ij", 504, fontsize=10)
    arrow(ax, (2.45, 5.075), (3.05, 5.075))
    arrow(ax, (5.05, 5.075), (5.65, 5.075))
    arrow(ax, (7.65, 5.075), (8.25, 5.075))
    # Matrix.
    ax.text(2.0, 4.02, "增广代价矩阵 505", ha="center", fontsize=10)
    grid_x, grid_y, cell = 0.75, 1.05, 0.55
    values = [
        ["c11", "c12", "u", "∞", "∞"],
        ["∞", "c22", "∞", "u", "∞"],
        ["c31", "∞", "∞", "∞", "u"],
        ["u", "∞", "0", "0", "0"],
        ["∞", "u", "0", "0", "0"],
    ]
    for row in range(5):
        for col in range(5):
            ax.add_patch(Rectangle((grid_x + col * cell, grid_y + (4 - row) * cell),
                                   cell, cell, fill=False, edgecolor="black", linewidth=0.8))
            ax.text(grid_x + (col + 0.5) * cell, grid_y + (4 - row + 0.5) * cell,
                    values[row][col], ha="center", va="center", fontsize=8)
    ax.text(4.25, 2.35, "匈牙利算法\n全局最小代价", ha="center", va="center", fontsize=10)
    arrow(ax, (3.55, 2.35), (3.9, 2.35))
    arrow(ax, (4.6, 2.35), (5.2, 2.35))
    # Matching result.
    left = [(6.0, 3.35), (6.0, 2.35), (6.0, 1.35)]
    right = [(10.1, 3.35), (10.1, 2.35), (10.1, 1.35)]
    for idx, pos in enumerate(left, 1):
        ax.add_patch(Circle(pos, 0.24, fill=False, edgecolor="black", linewidth=1.2))
        ax.text(*pos, f"A{idx}", ha="center", va="center", fontsize=8)
    for idx, pos in enumerate(right, 1):
        ax.add_patch(Circle(pos, 0.24, fill=False, edgecolor="black", linewidth=1.2))
        ax.text(*pos, f"B{idx}", ha="center", va="center", fontsize=8)
    ax.plot([6.24, 9.86], [3.35, 3.35], color="black", linewidth=1.7)
    ax.plot([6.24, 9.86], [2.35, 1.35], color="black", linewidth=1.7)
    ax.plot([5.84, 6.16], [1.19, 1.51], color="black", linewidth=1.2)
    ax.plot([9.94, 10.26], [2.19, 2.51], color="black", linewidth=1.2)
    ax.text(8.05, 3.75, "一一关系 506", ha="center", fontsize=10)
    ax.text(8.05, 0.78, "允许未匹配 507", ha="center", fontsize=10)
    ax.text(6, 0.28, "c_ij=-ln(max(p_ij,ε))；u为未匹配代价", ha="center", fontsize=10)
    save(fig, "fig5_gnn_assignment")


def figure_6_triangulation():
    fig, ax = new_figure()
    ax.text(6, 6.95, "图6  双视线最近点交会定位与多时刻三维拟合", ha="center", fontsize=13)
    origin_a = np.array([1.0, 1.15])
    origin_b = np.array([10.8, 1.15])
    point_a = np.array([5.72, 4.75])
    point_b = np.array([6.08, 4.58])
    midpoint = (point_a + point_b) / 2
    ax.add_patch(Circle(origin_a, 0.16, fill=False, edgecolor="black", linewidth=1.4))
    ax.add_patch(Circle(origin_b, 0.16, fill=False, edgecolor="black", linewidth=1.4))
    ax.text(0.55, 0.68, "A站光心 601", fontsize=9)
    ax.text(10.1, 0.68, "B站光心 602", fontsize=9)
    ax.plot([origin_a[0], 9.0], [origin_a[1], 6.1], color="black", linewidth=1.3)
    ax.plot([origin_b[0], 3.2], [origin_b[1], 6.1], color="black", linewidth=1.3)
    ax.text(2.55, 2.65, "视线L_A 603", fontsize=9, rotation=27)
    ax.text(8.15, 2.65, "视线L_B 604", fontsize=9, rotation=-27)
    ax.plot([point_a[0], point_b[0]], [point_a[1], point_b[1]], color="black",
            linewidth=2.0, linestyle="--")
    ax.plot([point_a[0]], [point_a[1]], marker="o", markerfacecolor="white",
            markeredgecolor="black", markersize=7)
    ax.plot([point_b[0]], [point_b[1]], marker="o", markerfacecolor="white",
            markeredgecolor="black", markersize=7)
    ax.plot([midpoint[0]], [midpoint[1]], marker="s", markerfacecolor="black",
            markeredgecolor="black", markersize=5)
    ax.text(4.45, 5.05, "最近点p_A 605", fontsize=9)
    ax.text(6.25, 4.35, "最近点p_B 606", fontsize=9)
    ax.text(6.05, 5.08, "中点p 607", fontsize=9)
    # Multi-time trajectory samples.
    trajectory = np.array([[5.9, 4.66], [6.55, 4.96], [7.25, 5.23], [8.0, 5.46]])
    ax.plot(trajectory[:, 0], trajectory[:, 1], color="black", linewidth=1.4)
    for idx, (x, y) in enumerate(trajectory):
        ax.add_patch(Ellipse((x, y), 0.45 + idx * 0.05, 0.24 + idx * 0.03,
                             angle=20, fill=False, edgecolor="black", linewidth=0.9,
                             linestyle="--"))
        ax.plot([x], [y], marker="o", markerfacecolor="white", markeredgecolor="black",
                markersize=4)
    arrow(ax, (7.35, 5.26), (8.55, 5.66))
    ax.text(8.55, 5.9, "速度v 608", fontsize=9)
    ax.text(7.0, 4.55, "位置协方差 609", fontsize=9)
    ax.text(6, 0.2, "p=(p_A+p_B)/2；多时刻加权拟合 p(t)=p_0+v(t-t_0)", ha="center", fontsize=10)
    save(fig, "fig6_triangulation")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figure_1_overall_flow()
    figure_2_pixel_to_ray()
    figure_3_scanlet_track()
    figure_4_coplanar_sparse_graph()
    figure_5_gnn_assignment()
    figure_6_triangulation()


if __name__ == "__main__":
    main()
