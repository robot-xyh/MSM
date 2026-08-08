#!/usr/bin/env python3
"""Generate reproducible figures for the 200v200 learning/GNN report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib import font_manager
import numpy as np
from scipy.optimize import linear_sum_assignment


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_EPISODE = (
    ROOT
    / "research_modules/scalable_3d_simulation/outputs"
    / "200v200_learning_gnn_report_seed1000_20260728"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent

BLUE = "#2F6B9A"
RED = "#C94A4A"
GREEN = "#2F7D65"
AMBER = "#D18B2C"
PURPLE = "#76558F"
INK = "#263238"
MUTED = "#66727A"
GRID = "#D7DEE3"
PALE_BLUE = "#EAF2F8"
PALE_GREEN = "#EAF5F0"
PALE_AMBER = "#FBF2E4"
PALE_RED = "#FBECEC"
PALE_PURPLE = "#F1ECF5"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, default=DEFAULT_EPISODE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def configure_matplotlib() -> None:
    font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if font_path.is_file():
        font_manager.fontManager.addfont(str(font_path))
        font_family = font_manager.FontProperties(fname=font_path).get_name()
    else:
        font_family = "DejaVu Sans"
    plt.rcParams.update(
        {
            "font.family": font_family,
            "axes.unicode_minus": False,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": INK,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def save_figure(figure: plt.Figure, path: Path) -> None:
    figure.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def add_box(
    axis: plt.Axes,
    xy: tuple[float, float],
    width: float,
    height: float,
    text: str,
    facecolor: str,
    edgecolor: str,
    fontsize: float = 11,
) -> None:
    box = patches.FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.012",
        linewidth=1.4,
        edgecolor=edgecolor,
        facecolor=facecolor,
    )
    axis.add_patch(box)
    axis.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        linespacing=1.35,
    )


def add_arrow(
    axis: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str = MUTED,
) -> None:
    axis.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "linewidth": 1.5,
            "shrinkA": 4,
            "shrinkB": 4,
        },
    )


def draw_architecture(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(16, 9))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title(
        "强化学习与图神经网络输入输出及确定性闭环",
        fontsize=21,
        pad=18,
        fontweight="bold",
    )

    headers = (
        (0.115, "在线输入"),
        (0.365, "学习增强"),
        (0.625, "确定性求解与安全检查"),
        (0.865, "规范输出"),
    )
    for x_value, label in headers:
        axis.text(
            x_value,
            0.905,
            label,
            ha="center",
            va="center",
            fontsize=13,
            fontweight="bold",
            color=INK,
        )

    rows = [
        (
            0.73,
            "D1/D2航迹、协方差\n资源状态、历史计划",
            "D3有界代价残差\n输出 ΔC 和重规划建议",
            "规则代价 + 线性指派\n迟滞、版本、联盟检查",
            "版本化分配计划",
            BLUE,
            PALE_BLUE,
        ),
        (
            0.55,
            "区域目标流量\n资源、通信、节点健康",
            "D4区域资源策略\n配额、备用和转移建议",
            "资源守恒投影\n最小费用流或规则回退",
            "区域配额与转移计划",
            GREEN,
            PALE_GREEN,
        ),
        (
            0.37,
            "匿名局部轨迹\n标定、双时间戳、几何特征",
            "D5图神经网络\n候选边同目标概率",
            "几何门、同相机互斥\n受约束聚类、中心绑定",
            "跨视角视觉簇",
            PURPLE,
            PALE_PURPLE,
        ),
        (
            0.19,
            "目标投影、不确定度\n可见性、带宽、云台状态",
            "D5主动视觉策略\n观察对象、搜索和视场建议",
            "云台限位、速率、版本门\n确定性姿态执行器",
            "相机观察任务",
            AMBER,
            PALE_AMBER,
        ),
    ]
    x_values = (0.025, 0.275, 0.505, 0.795)
    widths = (0.18, 0.18, 0.24, 0.15)
    height = 0.12
    for y_value, source, learner, solver, result, color, pale in rows:
        add_box(axis, (x_values[0], y_value), widths[0], height, source, "white", color)
        add_box(axis, (x_values[1], y_value), widths[1], height, learner, pale, color)
        add_box(axis, (x_values[2], y_value), widths[2], height, solver, "white", color)
        add_box(axis, (x_values[3], y_value), widths[3], height, result, pale, color)
        add_arrow(axis, (0.205, y_value + 0.06), (0.275, y_value + 0.06), color)
        add_arrow(axis, (0.455, y_value + 0.06), (0.505, y_value + 0.06), color)
        add_arrow(axis, (0.745, y_value + 0.06), (0.795, y_value + 0.06), color)

    safety = patches.FancyBboxPatch(
        (0.025, 0.035),
        0.92,
        0.075,
        boxstyle="round,pad=0.012,rounding_size=0.012",
        linewidth=1.6,
        edgecolor=RED,
        facecolor=PALE_RED,
    )
    axis.add_patch(safety)
    axis.text(
        0.485,
        0.072,
        "统一安全外壳：候选硬门控、资源守恒、计划版本、联盟确认、友方冲突、"
        "模型超时/分布外回退；学习模型不修改全局航迹编号，不直接控制飞行",
        ha="center",
        va="center",
        fontsize=11.5,
        fontweight="bold",
        color="#8E3030",
    )
    axis.text(
        0.975,
        0.135,
        "当前状态：学习模块为开发或影子路径，在线默认仍为确定性规则",
        ha="right",
        va="center",
        fontsize=9.5,
        color=MUTED,
    )
    save_figure(figure, output / "01_learning_gnn_architecture.png")


def draw_deterministic_regional_flow(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(17, 8.5))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title(
        "不使用强化学习的区域调度流程",
        fontsize=21,
        pad=18,
        fontweight="bold",
    )

    steps = (
        (
            "1  在线汇总",
            "D1/D2航迹与协方差\nD5可见率与一致性\n资源、通信、控制权",
            PALE_BLUE,
            BLUE,
        ),
        (
            "2  需求预测",
            "进入区域概率 p(j,r)\n多机需求 k(j)\n配额、保障量、备用量",
            PALE_GREEN,
            GREEN,
        ),
        (
            "3  区域优化",
            "当前压力贪心回退\n或区域最小费用流\n决定区域间转移数量",
            PALE_AMBER,
            AMBER,
        ),
        (
            "4  具体资源",
            "可释放资源候选\n到达、能源、能力代价\n稀疏线性指派",
            PALE_BLUE,
            BLUE,
        ),
        (
            "5  区域内分配",
            "D3目标需求槽\n普通目标与多机任务\n匈牙利确定性求解",
            PALE_PURPLE,
            PURPLE,
        ),
        (
            "6  发布与执行",
            "迟滞与最小驻留\n版本、租约、联盟确认\n运行确认与D6评估",
            PALE_GREEN,
            GREEN,
        ),
    )
    x_values = np.linspace(0.025, 0.835, len(steps))
    width = 0.14
    height = 0.22
    y_value = 0.58
    for index, (label, text_value, pale, color) in enumerate(steps):
        add_box(
            axis,
            (float(x_values[index]), y_value),
            width,
            height,
            f"{label}\n\n{text_value}",
            pale,
            color,
            fontsize=10.5,
        )
        if index < len(steps) - 1:
            add_arrow(
                axis,
                (float(x_values[index]) + width, y_value + height / 2),
                (float(x_values[index + 1]), y_value + height / 2),
                color,
            )

    add_box(
        axis,
        (0.10, 0.30),
        0.34,
        0.16,
        "冷启动\n全部可用资源 × 区域编制槽位\n200架资源可形成200×200线性指派",
        "white",
        BLUE,
        fontsize=11,
    )
    add_box(
        axis,
        (0.56, 0.30),
        0.34,
        0.16,
        "滚动运行\n只优化空闲、任务完成和可释放资源\n区域流决定数量，线性指派选择具体资源",
        "white",
        GREEN,
        fontsize=11,
    )
    add_arrow(axis, (0.41, 0.58), (0.28, 0.46), AMBER)
    add_arrow(axis, (0.41, 0.58), (0.73, 0.46), AMBER)

    safety = patches.FancyBboxPatch(
        (0.05, 0.10),
        0.90,
        0.10,
        boxstyle="round,pad=0.012,rounding_size=0.012",
        linewidth=1.5,
        edgecolor=RED,
        facecolor=PALE_RED,
    )
    axis.add_patch(safety)
    axis.text(
        0.5,
        0.15,
        "硬约束：资源守恒、最低备用、已承诺资源保护、区域邻接、通信与机动可用、"
        "控制权、计划版本、代次、租约和联盟确认。任何一项失败均保持或回退。",
        ha="center",
        va="center",
        fontsize=11,
        color="#8E3030",
        fontweight="bold",
    )
    axis.text(
        0.5,
        0.035,
        "确定性方案不需要训练数据；权重、预测时间窗和迟滞参数仍需通过独立场景校准。",
        ha="center",
        va="center",
        fontsize=10,
        color=MUTED,
    )
    save_figure(figure, output / "08_deterministic_regional_flow.png")


def draw_learning_regional_flow(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(17, 8.8))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title(
        "区域资源学习调度流程",
        fontsize=21,
        pad=18,
        fontweight="bold",
    )

    steps = (
        (
            "1  区域态势汇总",
            "目标压力、可用资源\n侦察覆盖、通信状态\n不读取真实目标身份",
            PALE_BLUE,
            BLUE,
        ),
        (
            "2  学习模型判断",
            "综合本区和邻区状态\n评估后续多个周期\n输出建议及可信度",
            PALE_PURPLE,
            PURPLE,
        ),
        (
            "3  区域调整建议",
            "增加或减少资源\n邻区转移、备用比例\n不指定无人机和目标",
            PALE_AMBER,
            AMBER,
        ),
        (
            "4  建议检查",
            "输入完整、数值正常\n可信度≥0.60\n单次计算≤50毫秒",
            PALE_RED,
            RED,
        ),
        (
            "5  转为可执行方案",
            "邻接、容量、备用\n已分配资源、协调权限\n汇总区域资源名额",
            PALE_GREEN,
            GREEN,
        ),
        (
            "6  规则程序执行",
            "选择具体调动资源\n目标分配模块确定目标\n记录版本和执行结果",
            PALE_BLUE,
            BLUE,
        ),
    )
    x_values = np.linspace(0.025, 0.835, len(steps))
    width = 0.14
    height = 0.22
    y_value = 0.61
    for index, (label, text_value, pale, color) in enumerate(steps):
        add_box(
            axis,
            (float(x_values[index]), y_value),
            width,
            height,
            f"{label}\n\n{text_value}",
            pale,
            color,
            fontsize=10.3,
        )
        if index < len(steps) - 1:
            add_arrow(
                axis,
                (float(x_values[index]) + width, y_value + height / 2),
                (float(x_values[index + 1]), y_value + height / 2),
                color,
            )

    add_box(
        axis,
        (0.08, 0.30),
        0.24,
        0.15,
        "建议未通过\n超时、可信度低、输入异常\n立即采用现有规则方案",
        PALE_RED,
        RED,
        fontsize=10.5,
    )
    add_box(
        axis,
        (0.39, 0.30),
        0.24,
        0.15,
        "执行结果记录\n任务计划、负责节点、更新轮次\n统计8项区域运行代价",
        PALE_BLUE,
        BLUE,
        fontsize=10.5,
    )
    add_box(
        axis,
        (0.70, 0.30),
        0.24,
        0.15,
        "离线训练与复核\n根据历史回合调整模型\n使用独立数据复核",
        PALE_PURPLE,
        PURPLE,
        fontsize=10.5,
    )
    add_arrow(axis, (0.59, 0.61), (0.20, 0.45), RED)
    add_arrow(axis, (0.905, 0.61), (0.51, 0.45), BLUE)
    add_arrow(axis, (0.63, 0.375), (0.70, 0.375), PURPLE)
    axis.annotate(
        "",
        xy=(0.26, 0.61),
        xytext=(0.82, 0.45),
        arrowprops={
            "arrowstyle": "-|>",
            "color": PURPLE,
            "linewidth": 1.4,
            "linestyle": "--",
            "connectionstyle": "arc3,rad=-0.18",
        },
    )

    safety = patches.FancyBboxPatch(
        (0.05, 0.08),
        0.90,
        0.10,
        boxstyle="round,pad=0.012,rounding_size=0.012",
        linewidth=1.5,
        edgecolor=RED,
        facecolor=PALE_RED,
    )
    axis.add_patch(safety)
    axis.text(
        0.5,
        0.13,
        "学习模型只提供区域资源增减建议。具体资源、具体目标、协调权限和飞行控制仍由"
        "规则程序决定；当前学习建议不进入实际控制。",
        ha="center",
        va="center",
        fontsize=11,
        color="#8E3030",
        fontweight="bold",
    )
    axis.text(
        0.5,
        0.025,
        "现有运行记录只证明接口可用，尚未证明学习方法优于规则方法。",
        ha="center",
        va="center",
        fontsize=10,
        color=MUTED,
    )
    save_figure(figure, output / "10_learning_regional_flow.png")


def draw_replay_3d(
    output: Path,
    timestamps: np.ndarray,
    intruders: np.ndarray,
    interceptors: np.ndarray,
    recon: np.ndarray,
    summary: dict[str, object],
) -> None:
    try:
        from research_modules.scalable_3d_simulation.animation import (
            ensure_mplot3d,
        )

        ensure_mplot3d(matplotlib)
    except Exception:
        pass

    figure = plt.figure(figsize=(16, 7.5))
    grid = figure.add_gridspec(1, 2, width_ratios=[1.08, 1.0], wspace=0.12)
    axis_3d = figure.add_subplot(grid[0, 0], projection="3d")
    axis_map = figure.add_subplot(grid[0, 1])

    target_indices = np.linspace(0, intruders.shape[1] - 1, 32, dtype=int)
    resource_indices = np.linspace(0, interceptors.shape[1] - 1, 32, dtype=int)
    for index in target_indices:
        values = intruders[:, index, :3]
        axis_3d.plot(
            values[:, 0],
            values[:, 1],
            -values[:, 2],
            color=RED,
            alpha=0.48,
            linewidth=0.9,
        )
    for index in resource_indices:
        values = interceptors[:, index, :3]
        axis_3d.plot(
            values[:, 0],
            values[:, 1],
            -values[:, 2],
            color=BLUE,
            alpha=0.48,
            linewidth=0.9,
        )
    axis_3d.scatter(
        intruders[-1, :, 0],
        intruders[-1, :, 1],
        -intruders[-1, :, 2],
        s=8,
        color=RED,
        alpha=0.75,
        label="来袭目标（200）",
    )
    axis_3d.scatter(
        interceptors[-1, :, 0],
        interceptors[-1, :, 1],
        -interceptors[-1, :, 2],
        s=8,
        color=BLUE,
        alpha=0.75,
        label="拦截资源（200）",
    )
    axis_3d.scatter(
        recon[-1, :, 0],
        recon[-1, :, 1],
        -recon[-1, :, 2],
        s=70,
        marker="*",
        color=AMBER,
        edgecolor="white",
        linewidth=0.8,
        label="侦察节点（8）",
    )
    circle_angle = np.linspace(0, 2 * np.pi, 240)
    axis_3d.plot(
        1000 * np.cos(circle_angle),
        1000 * np.sin(circle_angle),
        np.zeros_like(circle_angle),
        color=GREEN,
        linewidth=1.4,
        linestyle="--",
        label="保护区边界",
    )
    axis_3d.set_xlabel("北向 / 米")
    axis_3d.set_ylabel("东向 / 米")
    axis_3d.set_zlabel("高度 / 米")
    axis_3d.set_title("三维轨迹重跑结果", fontsize=15, fontweight="bold")
    axis_3d.view_init(elev=24, azim=-58)
    axis_3d.legend(loc="upper left", fontsize=9)

    axis_map.scatter(
        intruders[0, :, 0],
        intruders[0, :, 1],
        s=7,
        color=RED,
        alpha=0.2,
    )
    axis_map.scatter(
        intruders[-1, :, 0],
        intruders[-1, :, 1],
        s=12,
        color=RED,
        alpha=0.8,
        label="目标末态",
    )
    axis_map.scatter(
        interceptors[-1, :, 0],
        interceptors[-1, :, 1],
        s=12,
        color=BLUE,
        alpha=0.75,
        label="资源末态",
    )
    axis_map.scatter(
        recon[-1, :, 0],
        recon[-1, :, 1],
        s=90,
        marker="*",
        color=AMBER,
        edgecolor="white",
        linewidth=0.8,
        label="侦察节点",
    )
    target_delta = intruders[-1, :, :2] - intruders[0, :, :2]
    resource_delta = interceptors[-1, :, :2] - interceptors[0, :, :2]
    axis_map.quiver(
        intruders[0, :, 0],
        intruders[0, :, 1],
        target_delta[:, 0],
        target_delta[:, 1],
        angles="xy",
        scale_units="xy",
        scale=1,
        color=RED,
        alpha=0.28,
        width=0.0018,
    )
    axis_map.quiver(
        interceptors[0, :, 0],
        interceptors[0, :, 1],
        resource_delta[:, 0],
        resource_delta[:, 1],
        angles="xy",
        scale_units="xy",
        scale=1,
        color=BLUE,
        alpha=0.28,
        width=0.0018,
    )
    axis_map.add_patch(
        patches.Circle(
            (0, 0),
            1000,
            fill=False,
            edgecolor=GREEN,
            linestyle="--",
            linewidth=1.4,
        )
    )
    for region in range(8):
        angle = region * 2 * np.pi / 8
        axis_map.plot(
            [0, 6000 * np.cos(angle)],
            [0, 6000 * np.sin(angle)],
            color=GRID,
            linewidth=0.8,
        )
    axis_map.set_aspect("equal")
    axis_map.set_xlim(-6000, 6000)
    axis_map.set_ylim(-6000, 6000)
    axis_map.set_xlabel("北向 / 米")
    axis_map.set_ylabel("东向 / 米")
    axis_map.set_title("俯视运动与八区域边界", fontsize=15, fontweight="bold")
    axis_map.grid(alpha=0.3)
    axis_map.legend(loc="upper right", fontsize=9)

    figure.suptitle(
        "200对200三维质点全栈离线重跑",
        fontsize=20,
        fontweight="bold",
        y=0.995,
    )
    figure.text(
        0.5,
        0.015,
        "实际重跑：seed 1000，10秒，200目标 + 200资源 + 8侦察节点；"
        f"在线观测 {summary.get('online_observation_count')} 条，在线真值使用 "
        f"{summary.get('online_truth_use_count')}，墙钟 "
        f"{float(summary.get('wall_time_s', 0.0)):.2f} 秒。"
        "学习模型未启用，10秒窗口内未形成五米拦截。",
        ha="center",
        va="bottom",
        fontsize=10,
        color=MUTED,
    )
    save_figure(figure, output / "02_replay_3d_200v200.png")


def normalized_view(points: np.ndarray, transform: np.ndarray, offset: np.ndarray) -> np.ndarray:
    values = points @ transform.T + offset
    low = values.min(axis=0)
    span = np.maximum(values.max(axis=0) - low, 1e-6)
    return 0.12 + 0.76 * (values - low) / span


def draw_crossview_matching(
    output: Path,
    intruders: np.ndarray,
) -> None:
    points = intruders[len(intruders) // 2, :, :2]
    angles = np.arctan2(points[:, 1], points[:, 0])
    center_angle = np.pi / 4
    angle_error = np.abs(np.angle(np.exp(1j * (angles - center_angle))))
    selected = np.argsort(angle_error)[:6]
    base = points[selected]
    base = (base - base.mean(axis=0)) / np.maximum(np.ptp(base, axis=0), 1.0)

    views = [
        normalized_view(base, np.array([[1.0, 0.12], [-0.08, 0.92]]), np.array([0.02, 0.01])),
        normalized_view(base, np.array([[0.78, -0.24], [0.16, 0.86]]), np.array([-0.03, 0.02])),
        normalized_view(base, np.array([[0.68, 0.28], [-0.20, 0.74]]), np.array([0.04, -0.03])),
    ]
    visible = [
        np.array([True, True, True, True, False, False]),
        np.array([False, True, True, True, True, True]),
        np.array([True, False, True, False, True, True]),
    ]
    local_orders = [
        ["A-04", "A-01", "A-07", "A-03", "A-09", "A-12"],
        ["B-08", "B-02", "B-06", "B-11", "B-03", "B-09"],
        ["C-05", "C-10", "C-01", "C-07", "C-04", "C-12"],
    ]
    colors = [BLUE, RED, GREEN, AMBER, PURPLE, "#4F8A8B"]

    figure = plt.figure(figsize=(16, 9))
    grid = figure.add_gridspec(2, 3, height_ratios=[1.0, 1.25], hspace=0.28, wspace=0.18)
    image_axes: list[plt.Axes] = []
    for camera in range(3):
        axis = figure.add_subplot(grid[0, camera])
        image_axes.append(axis)
        axis.set_facecolor("#F5F7F8")
        axis.set_xlim(0, 1)
        axis.set_ylim(1, 0)
        axis.set_xticks([])
        axis.set_yticks([])
        axis.set_title(f"相机 {chr(ord('A') + camera)}：匿名局部轨迹", fontweight="bold")
        for target in range(6):
            if not visible[camera][target]:
                continue
            x_value, y_value = views[camera][target]
            width = 0.055 + 0.012 * target
            height = width * 0.65
            axis.add_patch(
                patches.Rectangle(
                    (x_value - width / 2, y_value - height / 2),
                    width,
                    height,
                    fill=False,
                    edgecolor=colors[target],
                    linewidth=2.0,
                )
            )
            axis.text(
                x_value,
                y_value - height / 2 - 0.025,
                local_orders[camera][target],
                ha="center",
                va="bottom",
                fontsize=9,
                color=colors[target],
                fontweight="bold",
            )
        axis.text(
            0.02,
            0.97,
            "局部编号不含全局身份",
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.5,
            color=MUTED,
        )

    graph_axis = figure.add_subplot(grid[1, :])
    graph_axis.set_xlim(0, 1)
    graph_axis.set_ylim(-0.35, 3.15)
    graph_axis.axis("off")
    graph_axis.set_title(
        "稀疏候选图：灰色虚线为几何候选，彩色实线为图网络高概率同目标边",
        fontsize=14,
        fontweight="bold",
        pad=8,
    )

    node_positions: dict[tuple[int, int], tuple[float, float]] = {}
    for camera in range(3):
        y_value = 2.55 - camera
        graph_axis.text(
            0.015,
            y_value,
            f"相机 {chr(ord('A') + camera)}",
            ha="left",
            va="center",
            fontsize=11,
            fontweight="bold",
        )
        for target in range(6):
            if not visible[camera][target]:
                continue
            x_value = 0.15 + 0.12 * target + 0.015 * camera
            node_positions[(camera, target)] = (x_value, y_value)

    false_edges = [
        ((0, 1), (1, 2)),
        ((0, 2), (1, 3)),
        ((1, 3), (2, 4)),
        ((1, 4), (2, 5)),
    ]
    for first, second in false_edges:
        if first in node_positions and second in node_positions:
            x1, y1 = node_positions[first]
            x2, y2 = node_positions[second]
            graph_axis.plot(
                [x1, x2],
                [y1, y2],
                color="#A8B0B5",
                linestyle="--",
                linewidth=1.2,
                zorder=1,
            )

    for target in range(6):
        nodes = [
            node_positions[(camera, target)]
            for camera in range(3)
            if (camera, target) in node_positions
        ]
        for first, second in zip(nodes, nodes[1:]):
            graph_axis.plot(
                [first[0], second[0]],
                [first[1], second[1]],
                color=colors[target],
                linewidth=2.4,
                zorder=2,
            )

    for (camera, target), (x_value, y_value) in node_positions.items():
        graph_axis.scatter(
            [x_value],
            [y_value],
            s=210,
            color="white",
            edgecolor=colors[target],
            linewidth=2.2,
            zorder=3,
        )
        graph_axis.text(
            x_value,
            y_value,
            local_orders[camera][target].split("-")[1],
            ha="center",
            va="center",
            fontsize=8.5,
            color=colors[target],
            fontweight="bold",
            zorder=4,
        )

    for target in range(6):
        graph_axis.text(
            0.87,
            2.75 - 0.45 * target,
            f"视觉簇 V{target + 1}",
            ha="left",
            va="center",
            fontsize=9.5,
            color=colors[target],
            fontweight="bold",
        )
    graph_axis.text(
        0.87,
        -0.12,
        "视觉簇再与中心已有航迹匹配\nD5不创建或改写全局航迹编号",
        ha="left",
        va="bottom",
        fontsize=9.2,
        color=MUTED,
        linespacing=1.4,
    )

    figure.suptitle(
        "D5多相机图神经网络配准机制",
        fontsize=20,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.5,
        0.012,
        "机制示意：目标位置取自本次离线三维重跑，视角变换和遮挡用于绘图；"
        "颜色仅表示离线标签。当前正式G1证据来自合成候选图，不代表真实相机配准效果。",
        ha="center",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    save_figure(figure, output / "03_gnn_crossview_matching.png")


def draw_gnn_algorithm_pipeline(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(17, 9))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title(
        "D5跨视角图神经网络算法流程",
        fontsize=21,
        pad=18,
        fontweight="bold",
    )

    steps = (
        (
            "1  匿名局部轨迹",
            "每台相机独立多目标跟踪\n双时间戳、像素协方差\n框尺度、像面速度、置信度",
            PALE_BLUE,
            BLUE,
        ),
        (
            "2  几何稀疏候选",
            "时间窗、视锥与相机对预算\n极线、射线、重投影门\n中心航迹投影门与节点度上限",
            PALE_GREEN,
            GREEN,
        ),
        (
            "3  图特征编码",
            "10维节点特征\n14维边特征\n固定顺序、尺度归一化",
            PALE_PURPLE,
            PURPLE,
        ),
        (
            "4  两轮消息传递",
            "端点状态 + 边状态生成消息\n双向聚合并按节点度归一\n残差更新与层归一化",
            PALE_PURPLE,
            PURPLE,
        ),
        (
            "5  边概率与校准",
            "对称端点组合输出边logit\n验证集温度和决策阈值\n得到同一目标概率 p(i,j)",
            PALE_AMBER,
            AMBER,
        ),
        (
            "6  确定性身份绑定",
            "同相机互斥的受约束聚类\n簇到中心航迹平均投影代价\n匈牙利绑定与模糊保持",
            PALE_BLUE,
            BLUE,
        ),
    )
    x_values = np.linspace(0.02, 0.835, len(steps))
    width = 0.145
    height = 0.255
    y_value = 0.57
    for index, (label, body, pale, color) in enumerate(steps):
        add_box(
            axis,
            (float(x_values[index]), y_value),
            width,
            height,
            f"{label}\n\n{body}",
            pale,
            color,
            fontsize=10.2,
        )
        if index < len(steps) - 1:
            add_arrow(
                axis,
                (float(x_values[index]) + width, y_value + height / 2),
                (float(x_values[index + 1]), y_value + height / 2),
                color,
            )

    add_box(
        axis,
        (0.04, 0.29),
        0.27,
        0.15,
        "在线输入边界\n节点和边只含匿名观测、相机几何及\n中心投影摘要，不含仿真真实目标编号",
        "white",
        BLUE,
        fontsize=10.5,
    )
    add_box(
        axis,
        (0.365, 0.29),
        0.27,
        0.15,
        "离线训练边界\n真实身份只在图冻结后生成边标签\n按场景和随机种子划分训练/验证/测试",
        "white",
        PURPLE,
        fontsize=10.5,
    )
    add_box(
        axis,
        (0.69, 0.29),
        0.27,
        0.15,
        "输出边界\n模型只改变合法候选边概率\n不能创建、重写或本地换绑全局航迹编号",
        "white",
        RED,
        fontsize=10.5,
    )
    add_arrow(axis, (0.175, 0.44), (0.175, 0.57), BLUE)
    add_arrow(axis, (0.50, 0.44), (0.50, 0.57), PURPLE)
    add_arrow(axis, (0.825, 0.57), (0.825, 0.44), RED)

    safety = patches.FancyBboxPatch(
        (0.04, 0.08),
        0.92,
        0.11,
        boxstyle="round,pad=0.012,rounding_size=0.012",
        linewidth=1.5,
        edgecolor=RED,
        facecolor=PALE_RED,
    )
    axis.add_patch(safety)
    axis.text(
        0.5,
        0.135,
        "失败关闭：候选图召回不足、模型文件校验失败、输入分布外、概率非有限、"
        "推理超时、置信度不足或聚类冲突时，回退到几何规则概率并输出模糊/保持。",
        ha="center",
        va="center",
        fontsize=11,
        color="#8E3030",
        fontweight="bold",
    )
    axis.text(
        0.5,
        0.025,
        "本图为算法结构示意。图神经网络只处理已经通过物理和几何预筛的稀疏候选边。",
        ha="center",
        va="center",
        fontsize=9.5,
        color=MUTED,
    )
    save_figure(figure, output / "12_gnn_algorithm_pipeline.png")


def draw_gnn_message_passing(output: Path) -> None:
    figure, axes = plt.subplots(
        1,
        3,
        figsize=(17, 8.8),
        gridspec_kw={"width_ratios": [1.05, 1.15, 1.05]},
    )
    for axis in axes:
        axis.set_xlim(0, 1)
        axis.set_ylim(0, 1)
        axis.axis("off")

    left, middle, right = axes
    left.set_title("稀疏候选图", fontsize=15, fontweight="bold", pad=10)
    camera_rows = ((0.78, "相机A"), (0.50, "相机B"), (0.22, "相机C"))
    node_positions = {
        "A1": (0.28, 0.78),
        "A2": (0.70, 0.78),
        "B1": (0.20, 0.50),
        "B2": (0.53, 0.50),
        "B3": (0.82, 0.50),
        "C1": (0.30, 0.22),
        "C2": (0.68, 0.22),
    }
    for y_value, label in camera_rows:
        left.text(0.02, y_value, label, ha="left", va="center", fontsize=10, color=MUTED)
        left.plot([0.15, 0.94], [y_value, y_value], color=GRID, linewidth=0.8, zorder=0)
    candidate_edges = (
        ("A1", "B1", GREEN, "-"),
        ("A1", "B2", "#A8B0B5", "--"),
        ("A2", "B2", GREEN, "-"),
        ("A2", "B3", "#A8B0B5", "--"),
        ("B1", "C1", GREEN, "-"),
        ("B2", "C2", GREEN, "-"),
        ("B3", "C2", "#A8B0B5", "--"),
    )
    for source, target, color, style in candidate_edges:
        x1, y1 = node_positions[source]
        x2, y2 = node_positions[target]
        left.plot([x1, x2], [y1, y2], color=color, linestyle=style, linewidth=2.0, zorder=1)
    for label, (x_value, y_value) in node_positions.items():
        left.scatter(
            [x_value],
            [y_value],
            s=430,
            color="white",
            edgecolor=BLUE,
            linewidth=2.0,
            zorder=2,
        )
        left.text(x_value, y_value, label, ha="center", va="center", fontsize=9, fontweight="bold")
    left.text(
        0.50,
        0.06,
        "实线：高概率同目标边\n虚线：几何合法但存在竞争的困难候选",
        ha="center",
        va="center",
        fontsize=9.5,
        color=MUTED,
        linespacing=1.4,
    )

    middle.set_title("消息传递与边分类", fontsize=15, fontweight="bold", pad=10)
    add_box(
        middle,
        (0.08, 0.72),
        0.84,
        0.15,
        "初始编码\nh_i(0) = 节点编码器(x_i)    e_ij = 边编码器(z_ij)",
        PALE_PURPLE,
        PURPLE,
        fontsize=11,
    )
    add_box(
        middle,
        (0.08, 0.47),
        0.84,
        0.19,
        "第 l 轮消息\nm_ij(l) = 消息网络(h_i(l), h_j(l), e_ij)\n"
        "a_i(l) = 平均聚合{m_ij(l)}\n"
        "h_i(l+1) = 层归一化(h_i(l) + 更新网络[h_i(l), a_i(l)])",
        "white",
        PURPLE,
        fontsize=9.7,
    )
    add_box(
        middle,
        (0.08, 0.25),
        0.84,
        0.17,
        "对称边解码\nq_ij = [h_i+h_j, abs(h_i-h_j), h_i*h_j, e_ij]\n"
        "p_ij = sigmoid(边分类器(q_ij) / 温度)",
        PALE_AMBER,
        AMBER,
        fontsize=10.8,
    )
    add_arrow(middle, (0.50, 0.72), (0.50, 0.66), PURPLE)
    add_arrow(middle, (0.50, 0.47), (0.50, 0.42), PURPLE)
    middle.text(
        0.50,
        0.09,
        "端点和、绝对差和乘积使 i→j 与 j→i 的分类保持一致；\n"
        "邻域消息使一条边的判断同时考虑同节点的其他竞争候选。",
        ha="center",
        va="center",
        fontsize=9.5,
        color=MUTED,
        linespacing=1.4,
    )

    right.set_title("聚类与中心绑定", fontsize=15, fontweight="bold", pad=10)
    add_box(
        right,
        (0.08, 0.72),
        0.84,
        0.14,
        "边概率排序与阈值\n只处理模型输出有限、校准有效的候选边",
        PALE_AMBER,
        AMBER,
        fontsize=10.5,
    )
    add_box(
        right,
        (0.08, 0.51),
        0.84,
        0.14,
        "受约束聚类\n合并前检查相机集合不相交\n同一相机最多一个轨迹段进入同一簇",
        PALE_GREEN,
        GREEN,
        fontsize=10.5,
    )
    add_box(
        right,
        (0.08, 0.30),
        0.84,
        0.14,
        "簇到中心航迹代价\n平均投影马氏距离 + 时间新鲜度 + 证据裕量",
        PALE_BLUE,
        BLUE,
        fontsize=10.5,
    )
    add_box(
        right,
        (0.08, 0.09),
        0.84,
        0.14,
        "匈牙利一对一绑定\n唯一且裕量充分→支持已有全局航迹\n否则→模糊/保持/重捕获",
        "white",
        RED,
        fontsize=10.3,
    )
    add_arrow(right, (0.50, 0.72), (0.50, 0.65), AMBER)
    add_arrow(right, (0.50, 0.51), (0.50, 0.44), GREEN)
    add_arrow(right, (0.50, 0.30), (0.50, 0.23), BLUE)

    figure.suptitle(
        "图神经网络消息传递与确定性身份约束",
        fontsize=20,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.5,
        0.012,
        "算法原理示意。离线真实身份只用于生成边标签和评分；在线图、模型输入和绑定输出均不携带真实目标编号。",
        ha="center",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    figure.tight_layout(rect=[0, 0.04, 1, 0.95])
    save_figure(figure, output / "13_gnn_message_passing_and_binding.png")


def choose_cost_residual(
    rule_cost: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    for scale in (1.0, 0.5, 0.25, 0.1):
        working_cost = rule_cost * scale
        row_rule, col_rule = linear_sum_assignment(working_cost)
        selected = dict(zip(row_rule.tolist(), col_rule.tolist()))
        candidates: list[tuple[float, int, int]] = []
        for first in range(working_cost.shape[0]):
            for second in range(first + 1, working_cost.shape[0]):
                first_target = selected[first]
                second_target = selected[second]
                swap_gap = (
                    working_cost[first, second_target]
                    + working_cost[second, first_target]
                    - working_cost[first, first_target]
                    - working_cost[second, second_target]
                )
                candidates.append((float(swap_gap), first, second))
        candidates.sort(key=lambda item: item[0])

        for _, first, second in candidates:
            residual = np.zeros_like(working_cost)
            first_target = selected[first]
            second_target = selected[second]
            residual[first, first_target] = 0.25
            residual[second, second_target] = 0.25
            residual[first, second_target] = -0.25
            residual[second, first_target] = -0.25
            final_cost = working_cost + residual
            _, col_final = linear_sum_assignment(final_cost)
            if not np.array_equal(col_rule, col_final):
                return working_cost, residual, col_rule, col_final
    raise RuntimeError("unable to construct a bounded residual assignment example")


def draw_cost_residual(
    output: Path,
    intruders: np.ndarray,
    interceptors: np.ndarray,
) -> None:
    frame = len(intruders) // 2
    target_indices = np.linspace(0, intruders.shape[1] - 1, 10, dtype=int)
    target_points = intruders[frame, target_indices, :3]
    resource_indices: list[int] = []
    for target in target_points:
        distances = np.linalg.norm(interceptors[frame, :, :3] - target, axis=1)
        for index in np.argsort(distances):
            if int(index) not in resource_indices:
                resource_indices.append(int(index))
                break
    resource_points = interceptors[frame, resource_indices, :3]
    distances = np.linalg.norm(
        resource_points[:, None, :] - target_points[None, :, :],
        axis=2,
    )
    rule_cost = distances / max(float(np.percentile(distances, 75)), 1.0)
    rule_cost += 0.03 * np.abs(
        np.arange(10)[:, None] - np.arange(10)[None, :]
    )
    rule_cost, residual, rule_assignment, final_assignment = choose_cost_residual(
        rule_cost
    )
    final_cost = rule_cost + residual
    changed = int(np.count_nonzero(rule_assignment != final_assignment))

    figure, axes = plt.subplots(1, 3, figsize=(16, 5.8))
    titles = (
        "规则代价 $C_{rule}$",
        "有界修正 $\\Delta C$",
        "最终代价 $C_{final}$ 与重新求解",
    )
    matrices = (rule_cost, residual, final_cost)
    assignments = (rule_assignment, None, final_assignment)
    cmaps = ("YlGnBu", "coolwarm", "YlGnBu")
    limits = (
        (float(rule_cost.min()), float(rule_cost.max())),
        (-0.25, 0.25),
        (float(final_cost.min()), float(final_cost.max())),
    )
    for axis, title, matrix, assignment, cmap, (minimum, maximum) in zip(
        axes,
        titles,
        matrices,
        assignments,
        cmaps,
        limits,
    ):
        image = axis.imshow(matrix, cmap=cmap, vmin=minimum, vmax=maximum, aspect="equal")
        axis.set_title(title, fontsize=13, fontweight="bold")
        axis.set_xlabel("目标候选")
        axis.set_ylabel("拦截资源")
        axis.set_xticks(range(10))
        axis.set_yticks(range(10))
        if assignment is not None:
            for row, column in enumerate(assignment):
                is_changed = (
                    title.startswith("最终")
                    and rule_assignment[row] != final_assignment[row]
                )
                axis.scatter(
                    [column],
                    [row],
                    s=95 if is_changed else 62,
                    facecolors="none",
                    edgecolors=AMBER if is_changed else "white",
                    linewidths=2.3 if is_changed else 1.4,
                )
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)

    figure.suptitle(
        "D3强化学习代价残差与确定性分配",
        fontsize=19,
        fontweight="bold",
        y=1.02,
    )
    figure.text(
        0.5,
        -0.01,
        f"机制示例：单边修正限制在±0.25，最终仍由线性指派求解；"
        f"本示例10条绑定中有{changed}条变化。当前正式D3证据为20/20代价矩阵改变、"
        "0/20最终绑定改变，因此本图不代表已测得任务收益。",
        ha="center",
        va="top",
        fontsize=9.6,
        color=MUTED,
    )
    figure.tight_layout()
    save_figure(figure, output / "04_d3_cost_residual_assignment.png")


def largest_remainder_quota(weights: np.ndarray, total: int) -> np.ndarray:
    raw = weights / np.sum(weights) * total
    quota = np.floor(raw).astype(int)
    remainder = total - int(np.sum(quota))
    if remainder > 0:
        order = np.argsort(-(raw - quota))
        quota[order[:remainder]] += 1
    return quota


def regional_indices(points: np.ndarray) -> np.ndarray:
    angle = (np.arctan2(points[:, 1], points[:, 0]) + 2 * np.pi) % (2 * np.pi)
    return np.floor(angle / (2 * np.pi / 8)).astype(int)


def deterministic_region_transfers(
    current_quota: np.ndarray,
    desired_quota: np.ndarray,
) -> list[tuple[int, int, int]]:
    surplus = {
        index: int(current_quota[index] - desired_quota[index])
        for index in range(8)
        if current_quota[index] > desired_quota[index]
    }
    deficit = {
        index: int(desired_quota[index] - current_quota[index])
        for index in range(8)
        if desired_quota[index] > current_quota[index]
    }
    transfers: list[tuple[int, int, int]] = []
    while surplus and deficit:
        candidates = []
        for source in surplus:
            for target in deficit:
                clockwise = (target - source) % 8
                counterclockwise = (source - target) % 8
                candidates.append(
                    (min(clockwise, counterclockwise), source, target)
                )
        _, source, target = min(candidates)
        count = min(surplus[source], deficit[target])
        transfers.append((source, target, count))
        surplus[source] -= count
        deficit[target] -= count
        if surplus[source] == 0:
            del surplus[source]
        if deficit[target] == 0:
            del deficit[target]
    return transfers


def draw_deterministic_regional_3d(
    output: Path,
    intruders: np.ndarray,
    interceptors: np.ndarray,
    recon: np.ndarray,
) -> None:
    try:
        from research_modules.scalable_3d_simulation.animation import (
            ensure_mplot3d,
        )

        ensure_mplot3d(matplotlib)
    except Exception:
        pass

    frame = len(intruders) // 2
    target = intruders[frame]
    resource = interceptors[frame]
    scout = recon[frame]
    target_region = regional_indices(target)
    resource_region = regional_indices(resource)
    target_count = np.bincount(target_region, minlength=8)
    current_quota = np.bincount(resource_region, minlength=8)
    desired_quota = largest_remainder_quota(target_count.astype(float), len(resource))
    transfers = deterministic_region_transfers(current_quota, desired_quota)

    figure = plt.figure(figsize=(17, 8.5))
    grid = figure.add_gridspec(1, 2, width_ratios=[1.18, 0.82], wspace=0.08)
    axis = figure.add_subplot(grid[0, 0], projection="3d")
    bar_axis = figure.add_subplot(grid[0, 1])

    history_start = max(0, frame - 28)
    for index in np.linspace(0, target.shape[0] - 1, 24, dtype=int):
        values = intruders[history_start : frame + 1, index]
        axis.plot(
            values[:, 0],
            values[:, 1],
            -values[:, 2],
            color=RED,
            alpha=0.28,
            linewidth=0.8,
        )
    for index in np.linspace(0, resource.shape[0] - 1, 24, dtype=int):
        values = interceptors[history_start : frame + 1, index]
        axis.plot(
            values[:, 0],
            values[:, 1],
            -values[:, 2],
            color=BLUE,
            alpha=0.28,
            linewidth=0.8,
        )

    axis.scatter(
        target[:, 0],
        target[:, 1],
        -target[:, 2],
        s=12,
        color=RED,
        alpha=0.72,
        label="来袭目标",
    )
    axis.scatter(
        resource[:, 0],
        resource[:, 1],
        -resource[:, 2],
        s=11,
        marker="s",
        color=BLUE,
        alpha=0.62,
        label="拦截资源",
    )
    axis.scatter(
        scout[:, 0],
        scout[:, 1],
        -scout[:, 2],
        s=90,
        marker="*",
        color=AMBER,
        edgecolor="white",
        linewidth=0.8,
        label="高空侦察节点",
    )

    radius_line = np.linspace(0, 5900, 80)
    for region in range(8):
        angle = region * np.pi / 4
        axis.plot(
            radius_line * np.cos(angle),
            radius_line * np.sin(angle),
            np.zeros_like(radius_line),
            color=GRID,
            linewidth=1.0,
        )
        label_angle = (region + 0.5) * np.pi / 4
        axis.text(
            5700 * np.cos(label_angle),
            5700 * np.sin(label_angle),
            30,
            f"R{region + 1}",
            color=MUTED,
            fontsize=9,
            ha="center",
        )
    circle_angle = np.linspace(0, 2 * np.pi, 240)
    axis.plot(
        1000 * np.cos(circle_angle),
        1000 * np.sin(circle_angle),
        np.zeros_like(circle_angle),
        color=GREEN,
        linewidth=1.5,
        linestyle="--",
        label="保护区",
    )

    anchor_radius = 1700.0
    anchor_height = 350.0
    for source, target_index, count in transfers:
        source_angle = (source + 0.5) * np.pi / 4
        target_angle = (target_index + 0.5) * np.pi / 4
        start = np.array(
            [
                anchor_radius * np.cos(source_angle),
                anchor_radius * np.sin(source_angle),
                anchor_height,
            ]
        )
        end = np.array(
            [
                anchor_radius * np.cos(target_angle),
                anchor_radius * np.sin(target_angle),
                anchor_height,
            ]
        )
        vector = end - start
        axis.quiver(
            start[0],
            start[1],
            start[2],
            vector[0],
            vector[1],
            vector[2],
            color=GREEN,
            linewidth=2.2,
            arrow_length_ratio=0.12,
        )
        midpoint = (start + end) / 2
        axis.text(
            midpoint[0],
            midpoint[1],
            midpoint[2] + 100,
            f"转移{count}架",
            color=GREEN,
            fontsize=9,
            ha="center",
            fontweight="bold",
        )

    velocity_indices = np.linspace(0, target.shape[0] - 1, 18, dtype=int)
    velocity = target[velocity_indices, 3:6] * 55.0
    axis.quiver(
        target[velocity_indices, 0],
        target[velocity_indices, 1],
        -target[velocity_indices, 2],
        velocity[:, 0],
        velocity[:, 1],
        -velocity[:, 2],
        color=RED,
        alpha=0.45,
        linewidth=0.8,
        arrow_length_ratio=0.15,
    )
    axis.set_xlim(-6000, 6000)
    axis.set_ylim(-6000, 6000)
    axis.set_zlim(0, 850)
    axis.set_xlabel("北向 / 米")
    axis.set_ylabel("东向 / 米")
    axis.set_zlabel("高度 / 米")
    axis.set_title("固定八区域三维质点场景", fontsize=15, fontweight="bold")
    axis.view_init(elev=25, azim=-58)
    axis.set_box_aspect((1, 1, 0.42))
    axis.legend(loc="upper left", fontsize=8.5)

    x_values = np.arange(8)
    width = 0.36
    bar_axis.bar(
        x_values - width / 2,
        current_quota,
        width,
        color=BLUE,
        label="当前资源",
    )
    bar_axis.bar(
        x_values + width / 2,
        desired_quota,
        width,
        color=GREEN,
        label="按目标数量计算的配额",
    )
    for index, value in enumerate(desired_quota):
        bar_axis.text(
            index + width / 2,
            value + 0.35,
            str(int(value)),
            ha="center",
            va="bottom",
            fontsize=9,
        )
    bar_axis.set_xticks(x_values, [f"R{index + 1}" for index in x_values])
    bar_axis.set_ylabel("资源数量")
    bar_axis.set_title("确定性区域配额与转移", fontsize=15, fontweight="bold")
    bar_axis.set_ylim(0, max(32, int(desired_quota.max()) + 5))
    bar_axis.grid(axis="y", alpha=0.25)
    bar_axis.legend(loc="upper left", fontsize=9)
    figure.suptitle(
        "确定性区域调度三维场景",
        fontsize=20,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.5,
        0.012,
        "位置来自200对200离线重跑中间帧；八区域边界、按目标数量形成的配额和绿色转移箭头"
        "为确定性机制重算示意，不是该回合实际执行的区域转移。",
        ha="center",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    save_figure(figure, output / "09_deterministic_regional_3d.png")


def draw_learning_regional_3d(
    output: Path,
    intruders: np.ndarray,
    interceptors: np.ndarray,
    recon: np.ndarray,
) -> None:
    try:
        from research_modules.scalable_3d_simulation.animation import (
            ensure_mplot3d,
        )

        ensure_mplot3d(matplotlib)
    except Exception:
        pass

    frame = len(intruders) // 2
    target = intruders[frame]
    resource = interceptors[frame]
    scout = recon[frame]
    target_region = regional_indices(target)
    resource_region = regional_indices(resource)
    target_radius = np.linalg.norm(target[:, :2], axis=1)
    radial_velocity = np.sum(target[:, :2] * target[:, 3:5], axis=1) / np.maximum(
        target_radius,
        1.0,
    )
    closing = np.clip(-radial_velocity / 5.0, 0.0, 1.0)
    closeness = 1.0 - (target_radius - target_radius.min()) / max(
        float(np.ptp(target_radius)),
        1.0,
    )
    target_weight = 1.0 + 0.8 * closing + 0.5 * closeness
    pressure = np.bincount(
        target_region,
        weights=target_weight,
        minlength=8,
    )
    pressure_min = float(pressure.min())
    pressure_span = max(float(np.ptp(pressure)), 1e-6)
    pressure_norm = (pressure - pressure_min) / pressure_span
    current_quota = np.bincount(resource_region, minlength=8)
    illustrative_quota = largest_remainder_quota(pressure, len(resource))

    figure = plt.figure(figsize=(17, 8.5))
    grid = figure.add_gridspec(1, 2, width_ratios=[1.18, 0.82], wspace=0.08)
    axis = figure.add_subplot(grid[0, 0], projection="3d")
    action_axis = figure.add_subplot(grid[0, 1])

    axis.scatter(
        target[:, 0],
        target[:, 1],
        -target[:, 2],
        s=10,
        color=RED,
        alpha=0.28,
        label="来袭目标",
    )
    axis.scatter(
        resource[:, 0],
        resource[:, 1],
        -resource[:, 2],
        s=9,
        marker="s",
        color=BLUE,
        alpha=0.24,
        label="拦截资源",
    )
    axis.scatter(
        scout[:, 0],
        scout[:, 1],
        -scout[:, 2],
        s=85,
        marker="*",
        color=AMBER,
        edgecolor="white",
        linewidth=0.8,
        label="高空侦察节点",
    )

    node_radius = 3500.0
    node_xyz = []
    for region in range(8):
        angle = (region + 0.5) * np.pi / 4
        node_xyz.append(
            (
                node_radius * np.cos(angle),
                node_radius * np.sin(angle),
                650.0 + 1250.0 * pressure_norm[region],
            )
        )
    node_xyz_array = np.asarray(node_xyz)
    for region in range(8):
        next_region = (region + 1) % 8
        axis.plot(
            [node_xyz_array[region, 0], node_xyz_array[next_region, 0]],
            [node_xyz_array[region, 1], node_xyz_array[next_region, 1]],
            [node_xyz_array[region, 2], node_xyz_array[next_region, 2]],
            color=PURPLE,
            alpha=0.45,
            linewidth=1.5,
        )
        axis.plot(
            [node_xyz_array[region, 0], node_xyz_array[region, 0]],
            [node_xyz_array[region, 1], node_xyz_array[region, 1]],
            [0, node_xyz_array[region, 2]],
            color=GRID,
            alpha=0.8,
            linestyle="--",
            linewidth=0.8,
        )
    node_scatter = axis.scatter(
        node_xyz_array[:, 0],
        node_xyz_array[:, 1],
        node_xyz_array[:, 2],
        c=pressure_norm,
        cmap="YlOrRd",
        vmin=0,
        vmax=1,
        s=140 + 190 * pressure_norm,
        edgecolor=INK,
        linewidth=0.7,
        label="区域图节点",
    )
    for region, point in enumerate(node_xyz_array):
        axis.text(
            point[0],
            point[1],
            point[2] + 120,
            f"R{region + 1}",
            ha="center",
            fontsize=9,
            fontweight="bold",
        )

    gradients: list[tuple[float, int, int]] = []
    for region in range(8):
        next_region = (region + 1) % 8
        if pressure[region] <= pressure[next_region]:
            source, target_index = region, next_region
        else:
            source, target_index = next_region, region
        gradients.append(
            (
                abs(float(pressure[target_index] - pressure[source])),
                source,
                target_index,
            )
        )
    for gradient, source, target_index in sorted(gradients, reverse=True)[:3]:
        start = node_xyz_array[source]
        end = node_xyz_array[target_index]
        vector = end - start
        axis.quiver(
            start[0],
            start[1],
            start[2],
            vector[0],
            vector[1],
            vector[2],
            color=GREEN,
            linewidth=2.4,
            arrow_length_ratio=0.12,
        )
        midpoint = (start + end) / 2
        axis.text(
            midpoint[0],
            midpoint[1],
            midpoint[2] + 130,
            f"建议转移强度 {gradient:.1f}",
            ha="center",
            fontsize=8.5,
            color=GREEN,
        )

    circle_angle = np.linspace(0, 2 * np.pi, 240)
    axis.plot(
        1000 * np.cos(circle_angle),
        1000 * np.sin(circle_angle),
        np.zeros_like(circle_angle),
        color=GREEN,
        linewidth=1.4,
        linestyle="--",
    )
    axis.set_xlim(-6000, 6000)
    axis.set_ylim(-6000, 6000)
    axis.set_zlim(0, 2200)
    axis.set_xlabel("北向 / 米")
    axis.set_ylabel("东向 / 米")
    axis.set_zlabel("高度及区域压力示意")
    axis.set_title("区域图观察与邻区动作", fontsize=15, fontweight="bold")
    axis.view_init(elev=25, azim=-58)
    axis.set_box_aspect((1, 1, 0.48))
    axis.legend(loc="upper left", fontsize=8.5)

    x_values = np.arange(8)
    width = 0.36
    action_axis.bar(
        x_values - width / 2,
        current_quota,
        width,
        color=BLUE,
        label="当前资源",
    )
    action_axis.bar(
        x_values + width / 2,
        illustrative_quota,
        width,
        color=AMBER,
        label="策略动作经守恒投影后的配额示意",
    )
    for index, value in enumerate(illustrative_quota):
        action_axis.text(
            index + width / 2,
            value + 0.35,
            str(int(value)),
            ha="center",
            va="bottom",
            fontsize=9,
        )
    action_axis.set_xticks(x_values, [f"R{index + 1}" for index in x_values])
    action_axis.set_ylabel("资源数量")
    action_axis.set_title("图策略动作的工程落点", fontsize=15, fontweight="bold")
    action_axis.set_ylim(0, max(32, int(illustrative_quota.max()) + 5))
    action_axis.grid(axis="y", alpha=0.25)
    action_axis.legend(loc="upper left", fontsize=9)
    figure.suptitle(
        "区域强化学习三维机制示意",
        fontsize=20,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.5,
        0.012,
        "目标、资源和侦察节点位置来自200对200离线重跑中间帧；区域压力、图节点高度、"
        "绿色动作箭头和橙色配额为机制示意，不是当前学习模型实测收益。",
        ha="center",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    save_figure(figure, output / "11_learning_regional_3d.png")


def draw_regional_policy(
    output: Path,
    intruders: np.ndarray,
    interceptors: np.ndarray,
) -> None:
    frame = len(intruders) // 2
    target = intruders[frame, :, :]
    resource = interceptors[frame, :, :]
    target_angle = (np.arctan2(target[:, 1], target[:, 0]) + 2 * np.pi) % (
        2 * np.pi
    )
    resource_angle = (
        np.arctan2(resource[:, 1], resource[:, 0]) + 2 * np.pi
    ) % (2 * np.pi)
    target_region = np.floor(target_angle / (2 * np.pi / 8)).astype(int)
    resource_region = np.floor(resource_angle / (2 * np.pi / 8)).astype(int)

    radius = np.linalg.norm(target[:, :2], axis=1)
    radial_velocity = np.sum(target[:, :2] * target[:, 3:5], axis=1) / np.maximum(
        radius,
        1.0,
    )
    closing = np.clip(-radial_velocity / 5.0, 0.0, 1.0)
    closeness = 1.0 - (radius - radius.min()) / max(float(np.ptp(radius)), 1.0)
    threat = 1.0 + 0.5 * closing + 0.4 * closeness
    cluster_candidates = np.flatnonzero(
        np.isin(target_region, np.array([1, 2]))
    )
    cluster_order = cluster_candidates[
        np.argsort(-(closing[cluster_candidates] + closeness[cluster_candidates]))
    ]
    high_threat = cluster_order[:28]
    threat[high_threat] += 2.2

    demand = np.bincount(target_region, weights=threat, minlength=8)
    projected_quota = largest_remainder_quota(demand, resource.shape[0])
    current_quota = np.bincount(resource_region, minlength=8)

    figure = plt.figure(figsize=(16, 7.2))
    grid = figure.add_gridspec(1, 2, width_ratios=[1.1, 0.9], wspace=0.18)
    map_axis = figure.add_subplot(grid[0, 0])
    bar_axis = figure.add_subplot(grid[0, 1])

    region_colors = plt.get_cmap("tab20")(np.linspace(0, 1, 8))
    for region in range(8):
        wedge = patches.Wedge(
            (0, 0),
            5900,
            region * 45,
            (region + 1) * 45,
            facecolor=region_colors[region],
            alpha=0.06,
            edgecolor=GRID,
            linewidth=0.8,
        )
        map_axis.add_patch(wedge)
        label_angle = (region + 0.5) * np.pi / 4
        map_axis.text(
            5600 * np.cos(label_angle),
            5600 * np.sin(label_angle),
            f"R{region + 1}",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=MUTED,
        )
    map_axis.scatter(
        target[:, 0],
        target[:, 1],
        c=[region_colors[index] for index in target_region],
        s=14,
        alpha=0.7,
        label="普通目标",
    )
    map_axis.scatter(
        target[high_threat, 0],
        target[high_threat, 1],
        s=62,
        facecolors="none",
        edgecolors=RED,
        linewidths=1.6,
        label="高威胁目标（场景注入）",
    )
    map_axis.scatter(
        resource[:, 0],
        resource[:, 1],
        s=12,
        marker="s",
        color=BLUE,
        alpha=0.55,
        label="当前资源",
    )
    map_axis.add_patch(
        patches.Circle(
            (0, 0),
            1000,
            fill=False,
            edgecolor=GREEN,
            linestyle="--",
            linewidth=1.4,
        )
    )
    map_axis.set_xlim(-6000, 6000)
    map_axis.set_ylim(-6000, 6000)
    map_axis.set_aspect("equal")
    map_axis.set_xlabel("北向 / 米")
    map_axis.set_ylabel("东向 / 米")
    map_axis.set_title("八区域目标压力与资源分布", fontsize=15, fontweight="bold")
    map_axis.legend(loc="lower left", fontsize=9)

    x_values = np.arange(8)
    width = 0.36
    bar_axis.bar(
        x_values - width / 2,
        current_quota,
        width,
        color=BLUE,
        label="当前静态资源数",
    )
    bar_axis.bar(
        x_values + width / 2,
        projected_quota,
        width,
        color=AMBER,
        label="学习建议经守恒投影后的配额",
    )
    for index, value in enumerate(projected_quota):
        bar_axis.text(
            index + width / 2,
            value + 0.7,
            str(int(value)),
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK,
        )
    bar_axis.set_xticks(x_values, [f"R{index + 1}" for index in x_values])
    bar_axis.set_ylabel("资源数量")
    bar_axis.set_title("静态均分与威胁加权配额", fontsize=15, fontweight="bold")
    bar_axis.grid(axis="y", alpha=0.25)
    bar_axis.legend(loc="upper left", fontsize=9)

    figure.suptitle(
        "D4区域资源强化学习的期望作用",
        fontsize=20,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.5,
        0.012,
        "机制示意：位置来自本次离线三维重跑，高威胁集中为附加试验条件；"
        "橙色配额是威胁权重经资源守恒投影后的期望输出，不是当前A2模型实测结果。",
        ha="center",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    save_figure(figure, output / "05_regional_resource_policy.png")


def wrap_angle(value: np.ndarray | float) -> np.ndarray | float:
    return np.arctan2(np.sin(value), np.cos(value))


def project_bearings(
    camera: np.ndarray,
    targets: np.ndarray,
    center_yaw: float,
    center_pitch: float,
    horizontal_fov_deg: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    delta = targets[:, :3] - camera[:3]
    horizontal_range = np.linalg.norm(delta[:, :2], axis=1)
    bearing = np.arctan2(delta[:, 1], delta[:, 0])
    altitude_delta = -targets[:, 2] - (-camera[2])
    elevation = np.arctan2(altitude_delta, np.maximum(horizontal_range, 1.0))
    horizontal_fov = np.deg2rad(horizontal_fov_deg)
    vertical_fov = horizontal_fov * 9.0 / 16.0
    u_value = 0.5 + np.asarray(wrap_angle(bearing - center_yaw)) / horizontal_fov
    v_value = 0.5 - (elevation - center_pitch) / vertical_fov
    visible = (
        (u_value >= 0.0)
        & (u_value <= 1.0)
        & (v_value >= 0.0)
        & (v_value <= 1.0)
    )
    return u_value, v_value, visible, np.linalg.norm(delta, axis=1)


def draw_camera_frame(
    axis: plt.Axes,
    u_value: np.ndarray,
    v_value: np.ndarray,
    visible: np.ndarray,
    distance: np.ndarray,
    high_target: int,
    fov_deg: float,
    title: str,
) -> float:
    axis.set_xlim(0, 1)
    axis.set_ylim(1, 0)
    axis.set_facecolor("#F3F5F6")
    axis.set_xticks([])
    axis.set_yticks([])
    axis.set_title(title, fontsize=13, fontweight="bold")
    high_area = 0.0
    for index in np.flatnonzero(visible):
        angular_scale = np.deg2rad(70.0) / np.deg2rad(fov_deg)
        width = np.clip(0.018 * angular_scale * 2800.0 / max(distance[index], 400.0), 0.018, 0.16)
        height = width * 0.65
        color = RED if index == high_target else BLUE
        linewidth = 2.5 if index == high_target else 1.5
        axis.add_patch(
            patches.Rectangle(
                (u_value[index] - width / 2, v_value[index] - height / 2),
                width,
                height,
                fill=False,
                edgecolor=color,
                linewidth=linewidth,
            )
        )
        axis.text(
            u_value[index],
            v_value[index] - height / 2 - 0.02,
            "高威胁" if index == high_target else f"T{index + 1}",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color=color,
            fontweight="bold" if index == high_target else "normal",
        )
        if index == high_target:
            high_area = width * height
    axis.text(
        0.02,
        0.97,
        f"水平视场 {fov_deg:.0f}°",
        transform=axis.transAxes,
        ha="left",
        va="bottom",
        fontsize=9,
        color=MUTED,
    )
    return high_area


def draw_active_vision(
    output: Path,
    intruders: np.ndarray,
    recon: np.ndarray,
) -> None:
    frame = len(intruders) // 2
    camera = recon[frame, 0, :]
    target = intruders[frame, :, :]
    delta = target[:, :2] - camera[:2]
    distances = np.linalg.norm(target[:, :3] - camera[:3], axis=1)
    high_global = int(np.argmin(distances))
    center_bearing = float(np.arctan2(delta[high_global, 1], delta[high_global, 0]))
    all_bearings = np.arctan2(delta[:, 1], delta[:, 0])
    angular_error = np.abs(np.asarray(wrap_angle(all_bearings - center_bearing)))
    selected_global = np.argsort(angular_error)[:14]
    selected_target = target[selected_global]
    high_local = int(np.flatnonzero(selected_global == high_global)[0])

    selected_delta = selected_target[:, :3] - camera[:3]
    horizontal_range = np.linalg.norm(selected_delta[:, :2], axis=1)
    selected_elevation = np.arctan2(
        -selected_target[:, 2] - (-camera[2]),
        np.maximum(horizontal_range, 1.0),
    )
    wide_center_pitch = float(np.median(selected_elevation))
    active_pitch = float(selected_elevation[high_local])

    wide = project_bearings(camera, selected_target, center_bearing, wide_center_pitch, 70.0)
    zoom = project_bearings(camera, selected_target, center_bearing, active_pitch, 18.0)

    figure = plt.figure(figsize=(16, 6.6))
    grid = figure.add_gridspec(1, 3, width_ratios=[1.05, 1.0, 1.0], wspace=0.16)
    map_axis = figure.add_subplot(grid[0, 0])
    wide_axis = figure.add_subplot(grid[0, 1])
    zoom_axis = figure.add_subplot(grid[0, 2])

    map_axis.scatter(
        selected_target[:, 0],
        selected_target[:, 1],
        s=28,
        color=BLUE,
        alpha=0.8,
        label="候选目标",
    )
    map_axis.scatter(
        [selected_target[high_local, 0]],
        [selected_target[high_local, 1]],
        s=90,
        facecolors="none",
        edgecolors=RED,
        linewidths=2,
        label="分配的高威胁目标",
    )
    map_axis.scatter(
        [camera[0]],
        [camera[1]],
        s=120,
        marker="*",
        color=AMBER,
        edgecolor="white",
        linewidth=0.8,
        label="侦察相机",
    )
    plot_radius = max(float(np.max(np.linalg.norm(selected_target[:, :2] - camera[:2], axis=1))), 1000.0)
    for fov, color, alpha, label in (
        (70.0, BLUE, 0.10, "广角搜索"),
        (18.0, RED, 0.16, "主动指向/变焦"),
    ):
        map_axis.add_patch(
            patches.Wedge(
                (camera[0], camera[1]),
                plot_radius * 1.08,
                np.rad2deg(center_bearing) - fov / 2,
                np.rad2deg(center_bearing) + fov / 2,
                facecolor=color,
                edgecolor=color,
                alpha=alpha,
                linewidth=1.3,
                label=label,
            )
        )
    map_axis.set_aspect("equal")
    margin = 300
    x_values = np.concatenate(([camera[0]], selected_target[:, 0]))
    y_values = np.concatenate(([camera[1]], selected_target[:, 1]))
    map_axis.set_xlim(x_values.min() - margin, x_values.max() + margin)
    map_axis.set_ylim(y_values.min() - margin, y_values.max() + margin)
    map_axis.set_xlabel("北向 / 米")
    map_axis.set_ylabel("东向 / 米")
    map_axis.set_title("融合航迹提示与云台指向", fontsize=13, fontweight="bold")
    map_axis.legend(loc="best", fontsize=8.5)

    wide_area = draw_camera_frame(
        wide_axis,
        wide[0],
        wide[1],
        wide[2],
        wide[3],
        high_local,
        70.0,
        "规则广角搜索",
    )
    zoom_area = draw_camera_frame(
        zoom_axis,
        zoom[0],
        zoom[1],
        zoom[2],
        zoom[3],
        high_local,
        18.0,
        "主动指向与变焦确认",
    )
    ratio = zoom_area / wide_area if wide_area > 0 else float("nan")
    zoom_axis.text(
        0.5,
        0.94,
        f"高威胁目标示意框面积约为广角的 {ratio:.1f} 倍",
        transform=zoom_axis.transAxes,
        ha="center",
        va="top",
        fontsize=9,
        color=RED,
        fontweight="bold",
    )

    figure.suptitle(
        "主动观察示意",
        fontsize=20,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.5,
        0.012,
        "图中位置来自离线三维回合，目标框按距离和视场模拟，不代表真实检测效果。"
        "学习模型只提出观察对象、搜索方向和视场建议，最终目标核对仍由末端视觉配准模块按相机几何和运动关系完成。",
        ha="center",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    save_figure(figure, output / "06_active_vision_reconnaissance.png")


def draw_evidence_boundary(output: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(15, 8))
    cards = [
        (
            axes[0, 0],
            "D3 有界代价残差",
            BLUE,
            [
                ("代价矩阵改变", "20/20"),
                ("最终绑定改变", "0/20"),
                ("硬约束违规", "0"),
            ],
            "结论：软件链路有效，任务收益未形成",
        ),
        (
            axes[0, 1],
            "D4 区域资源策略",
            GREEN,
            [
                ("八区域原始执行", "1/3"),
                ("候选权限执行", "0"),
                ("动作不一致且过门", "51/315"),
            ],
            "结论：就绪度分布和置信度仍需校准",
        ),
        (
            axes[1, 0],
            "D5 跨视角图网络",
            PURPLE,
            [
                ("合成保留集 F1", "1.000"),
                ("错误合并率", "0"),
                ("CPU 推理 P95", "0.913 ms"),
            ],
            "结论：合成证据通过，真实相机泛化待验证",
        ),
        (
            axes[1, 1],
            "D5 主动视觉",
            AMBER,
            [
                ("总体动作准确率", "0.956"),
                ("观察目标召回率", "0"),
                ("侦察相机准确率", "0.622"),
            ],
            "结论：类别失衡，运行收益证据不足",
        ),
    ]
    for axis, title, color, metrics, conclusion in cards:
        axis.set_xlim(0, 1)
        axis.set_ylim(0, 1)
        axis.axis("off")
        card = patches.FancyBboxPatch(
            (0.02, 0.05),
            0.96,
            0.9,
            boxstyle="round,pad=0.018,rounding_size=0.018",
            edgecolor=color,
            facecolor="white",
            linewidth=1.8,
        )
        axis.add_patch(card)
        axis.text(
            0.06,
            0.84,
            title,
            ha="left",
            va="center",
            fontsize=15,
            fontweight="bold",
            color=color,
        )
        for row, (label, value) in enumerate(metrics):
            y_value = 0.65 - 0.16 * row
            axis.text(0.08, y_value, label, ha="left", va="center", fontsize=11)
            axis.text(
                0.9,
                y_value,
                value,
                ha="right",
                va="center",
                fontsize=15,
                fontweight="bold",
                color=INK,
            )
            if row < len(metrics) - 1:
                axis.plot([0.08, 0.92], [y_value - 0.08, y_value - 0.08], color=GRID)
        axis.text(
            0.08,
            0.12,
            conclusion,
            ha="left",
            va="center",
            fontsize=10,
            color=MUTED,
        )
        axis.text(
            0.92,
            0.12,
            "在线权限：关闭",
            ha="right",
            va="center",
            fontsize=10,
            color=RED,
            fontweight="bold",
        )
    figure.suptitle(
        "当前学习模块证据边界",
        fontsize=20,
        fontweight="bold",
        y=0.99,
    )
    figure.text(
        0.5,
        0.012,
        "数据来自截至2026年7月28日的冻结离线证据；合成指标、接口可用和推理时延"
        "均不等同于真实任务收益或在线准入。",
        ha="center",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    figure.tight_layout(rect=[0, 0.04, 1, 0.96])
    save_figure(figure, output / "07_current_evidence_boundary.png")


def write_manifest(
    output: Path,
    episode: Path,
    summary: dict[str, object],
) -> None:
    payload = {
        "schema_version": "msm-200v200-learning-gnn-report-figures-v2",
        "generated_date": "2026-07-29",
        "source_episode": str(episode.relative_to(ROOT)),
        "source_episode_id": summary.get("episode_id"),
        "source_summary": {
            "target_count": summary.get("target_count"),
            "resource_count": summary.get("resource_count"),
            "recon_count": summary.get("recon_count"),
            "simulated_duration_s": summary.get("simulated_duration_s"),
            "seed": summary.get("seed"),
            "finite_state": summary.get("finite_state"),
            "online_truth_use_count": summary.get("online_truth_use_count"),
            "online_observation_count": summary.get("online_observation_count"),
            "wall_time_s": summary.get("wall_time_s"),
            "real_time_factor": summary.get("real_time_factor"),
            "intercepted_target_count": summary.get("intercepted_target_count"),
        },
        "figures": [
            {
                "path": "01_learning_gnn_architecture.png",
                "evidence_type": "architecture_schematic",
            },
            {
                "path": "02_replay_3d_200v200.png",
                "evidence_type": "actual_offline_rerun",
            },
            {
                "path": "03_gnn_crossview_matching.png",
                "evidence_type": "mechanism_schematic_from_offline_positions",
            },
            {
                "path": "04_d3_cost_residual_assignment.png",
                "evidence_type": "mechanism_schematic",
            },
            {
                "path": "05_regional_resource_policy.png",
                "evidence_type": "expected_effect_schematic_from_offline_positions",
            },
            {
                "path": "06_active_vision_reconnaissance.png",
                "evidence_type": "expected_effect_schematic_from_offline_positions",
            },
            {
                "path": "07_current_evidence_boundary.png",
                "evidence_type": "frozen_evidence_summary",
            },
            {
                "path": "08_deterministic_regional_flow.png",
                "evidence_type": "deterministic_architecture_schematic",
            },
            {
                "path": "09_deterministic_regional_3d.png",
                "evidence_type": (
                    "deterministic_mechanism_schematic_from_offline_positions"
                ),
            },
            {
                "path": "10_learning_regional_flow.png",
                "evidence_type": "learning_architecture_schematic",
            },
            {
                "path": "11_learning_regional_3d.png",
                "evidence_type": (
                    "learning_expected_effect_schematic_from_offline_positions"
                ),
            },
            {
                "path": "12_gnn_algorithm_pipeline.png",
                "evidence_type": "gnn_algorithm_pipeline_schematic",
            },
            {
                "path": "13_gnn_message_passing_and_binding.png",
                "evidence_type": "gnn_message_passing_and_binding_schematic",
            },
        ],
        "boundary": (
            "Only figure 02 is a direct rerun visualization. Figures 03-06 and "
            "08-13 are architecture, mechanism, or expected-effect schematics. "
            "Figures 09 and 11 reuse offline positions but their regional "
            "overlays do not establish executed scheduling or learning benefit."
        ),
    }
    (output / "figure_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    args.output.mkdir(parents=True, exist_ok=True)
    truth_path = args.episode / "offline_truth_state.npz"
    summary_path = args.episode / "summary.json"
    if not truth_path.is_file() or not summary_path.is_file():
        raise FileNotFoundError("episode must contain offline_truth_state.npz and summary.json")

    truth = np.load(truth_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    timestamps = truth["timestamps"]
    intruders = truth["intruder_state"]
    interceptors = truth["interceptor_state"]
    recon = truth["recon_state"]

    draw_architecture(args.output)
    draw_replay_3d(
        args.output,
        timestamps,
        intruders,
        interceptors,
        recon,
        summary,
    )
    draw_crossview_matching(args.output, intruders)
    draw_cost_residual(args.output, intruders, interceptors)
    draw_deterministic_regional_flow(args.output)
    draw_deterministic_regional_3d(
        args.output,
        intruders,
        interceptors,
        recon,
    )
    draw_regional_policy(args.output, intruders, interceptors)
    draw_learning_regional_flow(args.output)
    draw_learning_regional_3d(
        args.output,
        intruders,
        interceptors,
        recon,
    )
    draw_active_vision(args.output, intruders, recon)
    draw_evidence_boundary(args.output)
    draw_gnn_algorithm_pipeline(args.output)
    draw_gnn_message_passing(args.output)
    write_manifest(args.output, args.episode, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
