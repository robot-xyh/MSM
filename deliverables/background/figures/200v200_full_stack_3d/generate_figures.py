#!/usr/bin/env python3
"""Generate reproducible figures for the 200v200 3D full-stack proposal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager, patches
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
CYAN = "#3F7F8C"
INK = "#263238"
MUTED = "#66727A"
GRID = "#D7DEE3"
PALE_BLUE = "#EAF2F8"
PALE_GREEN = "#EAF5F0"
PALE_AMBER = "#FBF2E4"
PALE_RED = "#FBECEC"
PALE_PURPLE = "#F1ECF5"
PALE_GRAY = "#F4F6F7"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, default=DEFAULT_EPISODE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def configure_matplotlib() -> None:
    from research_modules.scalable_3d_simulation.animation import ensure_mplot3d

    ensure_mplot3d(matplotlib)
    font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if font_path.is_file():
        font_manager.fontManager.addfont(str(font_path))
        family = font_manager.FontProperties(fname=font_path).get_name()
    else:
        family = "DejaVu Sans"
    plt.rcParams.update(
        {
            "font.family": family,
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
    figure.savefig(path, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def read_last_jsonl_record(path: Path) -> dict:
    last_record: dict | None = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last_record = json.loads(line)
    if last_record is None:
        raise ValueError(f"no JSONL records found in {path}")
    return last_record


def nearest_time_index(timestamps: np.ndarray, timestamp: float) -> int:
    return int(np.argmin(np.abs(timestamps - float(timestamp))))


def track_positions(tracks: list[dict]) -> np.ndarray:
    return np.asarray([track["state_ned"][:3] for track in tracks], dtype=float)


def style_3d_axis(axis: plt.Axes, title: str) -> None:
    axis.set_xlabel("北向 / 米")
    axis.set_ylabel("东向 / 米")
    axis.set_zlabel("高度 / 米")
    axis.set_title(title, fontsize=15, fontweight="bold")
    axis.view_init(elev=24, azim=-56)


def add_box(
    axis: plt.Axes,
    xy: tuple[float, float],
    width: float,
    height: float,
    text: str,
    facecolor: str = "white",
    edgecolor: str = BLUE,
    fontsize: float = 10.5,
    linewidth: float = 1.4,
    fontweight: str = "normal",
) -> None:
    box = patches.FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.010,rounding_size=0.010",
        linewidth=linewidth,
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
        fontweight=fontweight,
    )


def add_arrow(
    axis: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str = MUTED,
    linestyle: str = "-",
    width: float = 1.5,
    connectionstyle: str = "arc3",
) -> None:
    axis.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "linewidth": width,
            "linestyle": linestyle,
            "connectionstyle": connectionstyle,
            "shrinkA": 4,
            "shrinkB": 4,
        },
    )


def draw_full_stack_architecture(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(18, 10))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title(
        "200对200三维全流程算法与数据闭环",
        fontsize=22,
        pad=18,
        fontweight="bold",
    )

    stages = (
        ("三维场景与传感器", "200目标\n200拦截资源\n8侦察节点\n雷达/声学/光电", PALE_GRAY, INK),
        ("D1 融合", "双时间戳\nNED六维状态\n扩展卡尔曼滤波\n协方差与质量", PALE_BLUE, BLUE),
        ("D2 关联", "稀疏候选\n马氏距离门\n全局最近邻\n稳定航迹编号", PALE_GREEN, GREEN),
        ("D4 区域层", "区域压力/需求\n规则或强化学习\n配额与跨区转移\n控制权状态", PALE_AMBER, AMBER),
        ("D3 分配", "规则代价\n可选有界残差\n需求槽匈牙利\n版本化计划", PALE_PURPLE, PURPLE),
        ("D5 视觉", "几何投影\n规则或图网络\n跨视角注册\n主动视觉", PALE_BLUE, CYAN),
        ("D7 导引", "位置比例导引\n视觉比例导引\n合同与机动门\n三维命令", PALE_RED, RED),
        ("D6 评估", "真值离线隔离\n身份/分配/降级\n控制/物理结果\n置信区间", PALE_GREEN, GREEN),
    )
    x_values = np.linspace(0.018, 0.866, len(stages))
    width = 0.112
    y_value = 0.62
    height = 0.22
    for index, (title, content, face, edge) in enumerate(stages):
        add_box(
            axis,
            (float(x_values[index]), y_value),
            width,
            height,
            f"{title}\n\n{content}",
            face,
            edge,
            fontsize=9.6,
            fontweight="normal",
        )
        if index < len(stages) - 1:
            add_arrow(
                axis,
                (float(x_values[index]) + width, y_value + height / 2),
                (float(x_values[index + 1]), y_value + height / 2),
                edge,
            )

    add_box(
        axis,
        (0.09, 0.34),
        0.35,
        0.15,
        "确定性在线主线\n规则区域调度 + 规则代价 + 匈牙利/需求槽\n"
        "几何视觉配准 + 确定性主动视觉 + PN/PNG",
        "white",
        BLUE,
        fontsize=11,
        fontweight="bold",
    )
    add_box(
        axis,
        (0.56, 0.34),
        0.35,
        0.15,
        "学习增强层（当前默认关闭）\nD4区域图策略 + D3代价残差\n"
        "D5跨视角图网络 + 主动视觉策略",
        "white",
        PURPLE,
        fontsize=11,
        fontweight="bold",
    )
    add_arrow(axis, (0.265, 0.49), (0.50, 0.62), BLUE, connectionstyle="arc3,rad=-0.15")
    add_arrow(
        axis,
        (0.735, 0.49),
        (0.62, 0.62),
        PURPLE,
        linestyle="--",
        connectionstyle="arc3,rad=0.15",
    )

    safety = patches.FancyBboxPatch(
        (0.04, 0.11),
        0.92,
        0.12,
        boxstyle="round,pad=0.012,rounding_size=0.012",
        linewidth=1.7,
        edgecolor=RED,
        facecolor=PALE_RED,
    )
    axis.add_patch(safety)
    axis.text(
        0.50,
        0.17,
        "确定性安全外壳：双时间戳、协方差、NED坐标、候选硬门、资源守恒、"
        "计划版本、所有者、代次、租约、联盟确认、友方冲突和在线真值隔离。"
        "学习模型只给建议或有界修正。",
        ha="center",
        va="center",
        fontsize=11.2,
        fontweight="bold",
        color="#8E3030",
        wrap=True,
    )
    axis.text(
        0.5,
        0.045,
        "闭环反馈：D5关联质量回写D3/D4，D6结果回灌参数标定和学习模型离线训练；"
        "任务发布与飞行控制不由学习模型直接决定。",
        ha="center",
        va="center",
        fontsize=10.5,
        color=MUTED,
    )
    save_figure(figure, output / "01_full_stack_architecture.png")


def draw_layered_3d_scene(
    output: Path,
    timestamps: np.ndarray,
    intruders: np.ndarray,
    interceptors: np.ndarray,
    recon: np.ndarray,
) -> None:
    figure = plt.figure(figsize=(17, 8.5))
    grid = figure.add_gridspec(1, 2, width_ratios=[1.25, 0.75], wspace=0.08)
    axis = figure.add_subplot(grid[0, 0], projection="3d")
    info = figure.add_subplot(grid[0, 1])
    info.axis("off")

    target_indices = np.linspace(0, intruders.shape[1] - 1, 40, dtype=int)
    resource_indices = np.linspace(0, interceptors.shape[1] - 1, 40, dtype=int)
    for index in target_indices:
        values = intruders[:, index, :3]
        axis.plot(
            values[:, 0],
            values[:, 1],
            -values[:, 2],
            color=RED,
            alpha=0.34,
            linewidth=0.8,
        )
    for index in resource_indices:
        values = interceptors[:, index, :3]
        axis.plot(
            values[:, 0],
            values[:, 1],
            -values[:, 2],
            color=BLUE,
            alpha=0.34,
            linewidth=0.8,
        )

    axis.scatter(
        intruders[-1, :, 0],
        intruders[-1, :, 1],
        -intruders[-1, :, 2],
        s=9,
        color=RED,
        alpha=0.75,
        label="来袭目标",
    )
    axis.scatter(
        interceptors[-1, :, 0],
        interceptors[-1, :, 1],
        -interceptors[-1, :, 2],
        s=9,
        color=BLUE,
        alpha=0.72,
        label="拦截资源",
    )
    axis.scatter(
        recon[-1, :, 0],
        recon[-1, :, 1],
        -recon[-1, :, 2],
        s=95,
        marker="*",
        color=AMBER,
        edgecolor="white",
        linewidth=0.8,
        label="高空侦察节点",
    )

    theta = np.linspace(0.0, 2.0 * np.pi, 220)
    for altitude, alpha in ((0.0, 0.9), (700.0, 0.3)):
        axis.plot(
            1000.0 * np.cos(theta),
            1000.0 * np.sin(theta),
            np.full_like(theta, altitude),
            color=GREEN,
            linestyle="--",
            linewidth=1.2,
            alpha=alpha,
        )
    for region in range(8):
        angle = region * 2.0 * np.pi / 8.0
        axis.plot(
            [0.0, 6000.0 * np.cos(angle)],
            [0.0, 6000.0 * np.sin(angle)],
            [0.0, 0.0],
            color=GRID,
            linewidth=0.8,
        )

    axis.set_xlabel("北向 / 米")
    axis.set_ylabel("东向 / 米")
    axis.set_zlabel("高度 / 米")
    axis.set_title("实际离线回合三维几何", fontsize=16, fontweight="bold")
    axis.view_init(elev=24, azim=-56)
    axis.legend(loc="upper left", fontsize=9)

    add_box(
        info,
        (0.08, 0.75),
        0.84,
        0.16,
        "外层态势\n雷达覆盖全域，声学提供弱方位提示\n"
        "D1/D2形成统一全局航迹",
        PALE_BLUE,
        BLUE,
        fontsize=11,
    )
    add_box(
        info,
        (0.08, 0.51),
        0.84,
        0.16,
        "区域协调\n八个固定区域承载需求预测和资源配额\n"
        "高空侦察节点提供局部二级协调与视觉线索",
        PALE_AMBER,
        AMBER,
        fontsize=11,
    )
    add_box(
        info,
        (0.08, 0.27),
        0.84,
        0.16,
        "末端闭环\nD3将资源分配到具体航迹\n"
        "D5完成视觉配准，D7完成三维位置导引",
        PALE_GREEN,
        GREEN,
        fontsize=11,
    )
    add_box(
        info,
        (0.08, 0.06),
        0.84,
        0.12,
        f"证据属性：seed 1000，{timestamps[-1]:.0f}秒\n"
        "位置和轨迹为实际仿真数据；区域职责说明为方案示意",
        PALE_RED,
        RED,
        fontsize=10.5,
    )
    figure.suptitle(
        "200对200三维质点场景与分层任务空间",
        fontsize=21,
        fontweight="bold",
        y=0.99,
    )
    save_figure(figure, output / "02_layered_3d_scene.png")


def draw_contract_chain(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(18, 9))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title("统一输入输出和信息管理边界", fontsize=21, pad=18, fontweight="bold")

    contracts = (
        (
            "传感器观测",
            "量测值、协方差\n量测时间、到达时间\n传感器/坐标/来源记录",
            PALE_BLUE,
            BLUE,
        ),
        (
            "全局航迹",
            "北—东—地六维状态、6×6协方差\n状态有效时刻、质量等级\n观测来源与状态摘要",
            PALE_GREEN,
            GREEN,
        ),
        (
            "关联航迹",
            "稳定全局航迹编号\n关联风险、连续性\n身份切换次数",
            PALE_AMBER,
            AMBER,
        ),
        (
            "区域建议",
            "区域配额、转移建议\n协调权限、二级准备情况\n更新轮次、有效期、可信度",
            PALE_PURPLE,
            PURPLE,
        ),
        (
            "分配计划",
            "资源-全局航迹绑定\n主用/备用、执行批次、协同成员\n计划标识/版本/有效期",
            PALE_BLUE,
            BLUE,
        ),
        (
            "终端关联",
            "局部视觉轨迹\n候选全局航迹编号\n锁定/待确认/暂停/重新搜索",
            PALE_GREEN,
            GREEN,
        ),
        (
            "导引命令",
            "中段/末段模式\n三维速度或加速度建议\n任务要求、限制条件和拒绝原因",
            PALE_RED,
            RED,
        ),
        (
            "评估记录",
            "指标可用性、统计范围、数据来源\n检测/身份/分配/降级\n控制/物理/时延",
            PALE_GRAY,
            INK,
        ),
    )
    positions = [
        (0.035, 0.62),
        (0.275, 0.62),
        (0.515, 0.62),
        (0.755, 0.62),
        (0.755, 0.30),
        (0.515, 0.30),
        (0.275, 0.30),
        (0.035, 0.30),
    ]
    width = 0.19
    height = 0.18
    for index, ((title, content, face, edge), position) in enumerate(
        zip(contracts, positions)
    ):
        add_box(
            axis,
            position,
            width,
            height,
            f"{title}\n\n{content}",
            face,
            edge,
            fontsize=10.3,
        )
        if index < len(contracts) - 1:
            start = (
                position[0] + (width if index < 3 else 0.0),
                position[1] + height / 2,
            )
            next_position = positions[index + 1]
            if index == 3:
                start = (position[0] + width / 2, position[1])
                end = (next_position[0] + width / 2, next_position[1] + height)
            elif index >= 4:
                start = (position[0], position[1] + height / 2)
                end = (next_position[0] + width, next_position[1] + height / 2)
            else:
                end = (next_position[0], next_position[1] + height / 2)
            add_arrow(axis, start, end, edge)

    axis.text(
        0.50,
        0.89,
        "在线决策数据",
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        color=BLUE,
    )
    axis.text(
        0.50,
        0.16,
        "离线评分与回灌",
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        color=GREEN,
    )
    axis.text(
        0.50,
        0.06,
        "全局航迹编号由中心统一维护；D5、D7和学习模型不得创建、改写或本地换绑。"
        "过期计划、回退版本、已失效授权和在线真实信息输入均拒绝执行。",
        ha="center",
        va="center",
        fontsize=10.8,
        color="#8E3030",
        fontweight="bold",
    )
    save_figure(figure, output / "03_contract_chain.png")


def draw_d1_fusion(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(17, 9))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title("D1 异步多传感器融合", fontsize=21, pad=18, fontweight="bold")

    sensors = (
        ("雷达", "距离/方位/俯仰\n可选径向速度\n距离相关噪声", RED),
        ("声学", "粗方位与类别提示\n不能单独测距\n不能独立建三维航迹", AMBER),
        ("光电", "检测框中心\n像素协方差\n相机内外参", BLUE),
        ("激光雷达", "合成三维位置\n可选研究输入\n非当前AirSim主线", GREEN),
    )
    y_values = (0.72, 0.53, 0.34, 0.15)
    for (title, content, color), y_value in zip(sensors, y_values):
        add_box(
            axis,
            (0.03, y_value),
            0.20,
            0.13,
            f"{title}\n{content}",
            "white",
            color,
            fontsize=9.8,
        )
        add_arrow(axis, (0.23, y_value + 0.065), (0.30, 0.50), color)

    add_box(
        axis,
        (0.30, 0.38),
        0.20,
        0.24,
        "事件时间组织\n\n量测时间排序\n到达时间审计\n来源去重\n固定滞后乱序回放",
        PALE_BLUE,
        BLUE,
        fontsize=11,
    )
    add_arrow(axis, (0.50, 0.50), (0.56, 0.50), BLUE)
    add_box(
        axis,
        (0.56, 0.38),
        0.20,
        0.24,
        "扩展卡尔曼滤波\n\n常速度预测\n非线性量测更新\nJoseph协方差更新\n创新一致性门",
        PALE_GREEN,
        GREEN,
        fontsize=11,
    )
    add_arrow(axis, (0.76, 0.50), (0.82, 0.50), GREEN)
    add_box(
        axis,
        (0.82, 0.35),
        0.15,
        0.30,
        "GlobalTrack\n\nNED六维状态\n6×6协方差\n质量等级\n健康与时延摘要",
        PALE_AMBER,
        AMBER,
        fontsize=10.7,
    )

    ellipse_axis = figure.add_axes([0.37, 0.09, 0.39, 0.22])
    ellipse_axis.set_aspect("equal")
    ellipse_axis.set_xlim(-18, 18)
    ellipse_axis.set_ylim(-11, 11)
    ellipse_axis.grid(alpha=0.25)
    ellipse_axis.set_xlabel("东向位置误差 / 米")
    ellipse_axis.set_ylabel("北向位置误差 / 米")
    ellipse_axis.set_title("协方差随多源观测收缩的机制示意", fontsize=11)
    for width, height, color, label in (
        (30, 17, RED, "预测"),
        (20, 12, AMBER, "雷达更新"),
        (12, 7, BLUE, "雷达+光电"),
    ):
        ellipse_axis.add_patch(
            patches.Ellipse(
                (0, 0),
                width,
                height,
                angle=18,
                fill=False,
                linewidth=2.0,
                edgecolor=color,
                label=label,
            )
        )
    ellipse_axis.legend(loc="upper right", fontsize=8)
    axis.text(
        0.40,
        0.04,
        "输入：异步观测、双时间戳、协方差、坐标与来源谱系",
        ha="center",
        fontsize=10.5,
        color=MUTED,
    )
    axis.text(
        0.79,
        0.04,
        "输出：可供D2消费的带不确定度全局航迹候选",
        ha="center",
        fontsize=10.5,
        color=MUTED,
    )
    save_figure(figure, output / "04_d1_sensor_fusion.png")


def draw_d2_association(output: Path) -> None:
    figure = plt.figure(figsize=(17, 8.7))
    grid = figure.add_gridspec(1, 3, width_ratios=[1.1, 0.9, 0.9], wspace=0.25)
    trajectories = figure.add_subplot(grid[0, 0])
    matrix_axis = figure.add_subplot(grid[0, 1])
    state_axis = figure.add_subplot(grid[0, 2])
    state_axis.axis("off")

    time = np.linspace(0.0, 1.0, 18)
    paths = (
        (np.linspace(-9, 9, 18), -4.2 + 8.4 * time, BLUE, "航迹 G-101"),
        (np.linspace(-9, 9, 18), 4.2 - 8.4 * time, RED, "航迹 G-102"),
        (np.linspace(-9, 9, 18), 1.1 * np.sin(2.0 * np.pi * time), GREEN, "航迹 G-103"),
    )
    rng = np.random.default_rng(20260729)
    for x_values, y_values, color, label in paths:
        trajectories.plot(x_values, y_values, color=color, linewidth=2.0, label=label)
        trajectories.scatter(
            x_values + rng.normal(0.0, 0.23, len(time)),
            y_values + rng.normal(0.0, 0.23, len(time)),
            s=16,
            color=color,
            alpha=0.45,
        )
        trajectories.annotate(
            "",
            xy=(x_values[-1], y_values[-1]),
            xytext=(x_values[-3], y_values[-3]),
            arrowprops={"arrowstyle": "-|>", "color": color, "linewidth": 1.7},
        )
    trajectories.axvspan(-1.8, 1.8, color=PALE_AMBER, alpha=0.85, label="密集交叉区")
    trajectories.set_title("运动与量测候选", fontsize=14, fontweight="bold")
    trajectories.set_xlabel("北向相对位置")
    trajectories.set_ylabel("东向相对位置")
    trajectories.grid(alpha=0.25)
    trajectories.legend(loc="upper left", fontsize=8)

    cost = np.array(
        [
            [0.8, 6.1, 7.0, 10.0],
            [5.8, 1.1, 3.6, 10.0],
            [6.4, 3.1, 1.3, 10.0],
        ]
    )
    image = matrix_axis.imshow(cost, cmap="YlGnBu_r", vmin=0.0, vmax=10.0)
    matrix_axis.set_xticks(range(4), ["量测1", "量测2", "量测3", "未分配"])
    matrix_axis.set_yticks(range(3), ["G-101", "G-102", "G-103"])
    matrix_axis.set_title("门控后的关联代价", fontsize=14, fontweight="bold")
    for row in range(cost.shape[0]):
        for column in range(cost.shape[1]):
            matrix_axis.text(
                column,
                row,
                f"{cost[row, column]:.1f}",
                ha="center",
                va="center",
                color="white" if cost[row, column] < 3.0 else INK,
                fontsize=10,
            )
    for row, column in ((0, 0), (1, 1), (2, 2)):
        matrix_axis.add_patch(
            patches.Rectangle(
                (column - 0.48, row - 0.48),
                0.96,
                0.96,
                fill=False,
                edgecolor=RED,
                linewidth=2.4,
            )
        )
    figure.colorbar(image, ax=matrix_axis, fraction=0.046, pad=0.04, label="代价")

    states = (
        ("候选生成", "空间索引与时间窗\n六维状态预测", PALE_BLUE, BLUE),
        ("精确门控", "创新与协方差\n马氏距离/NIS", PALE_GREEN, GREEN),
        ("全局求解", "运动+类别+时间代价\n稀疏匈牙利", PALE_AMBER, AMBER),
        ("生命周期", "tentative → confirmed\nlost → dropped", PALE_PURPLE, PURPLE),
        ("风险输出", "歧义、连续性\nid_switch_count", PALE_RED, RED),
    )
    y_values = np.linspace(0.79, 0.11, len(states))
    for index, ((title, content, face, edge), y_value) in enumerate(
        zip(states, y_values)
    ):
        add_box(
            state_axis,
            (0.12, float(y_value)),
            0.76,
            0.115,
            f"{title}  {content}",
            face,
            edge,
            fontsize=10.2,
        )
        if index < len(states) - 1:
            add_arrow(
                state_axis,
                (0.50, float(y_value)),
                (0.50, float(y_values[index + 1]) + 0.115),
                edge,
            )
    figure.suptitle("D2 多目标关联与身份连续性", fontsize=21, fontweight="bold")
    figure.text(
        0.5,
        0.02,
        "输入：D1航迹/观测、六维协方差、时间和既有活动航迹；"
        "输出：稳定全局航迹编号、关联日志、风险摘要和显式身份切换计数。图为算法机制示意。",
        ha="center",
        fontsize=10.5,
        color=MUTED,
    )
    save_figure(figure, output / "05_d2_data_association.png")


def draw_d3_assignment(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(18, 9.5))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title("D3 需求槽分配与有界代价修正", fontsize=21, pad=18, fontweight="bold")

    targets = (
        ("普通目标 T001", "需求1", 1, BLUE),
        ("高威胁目标 T002", "2主用+1备用", 3, RED),
        ("协同目标 T003", "2主用", 2, AMBER),
    )
    y_values = (0.72, 0.52, 0.32)
    slot_x = 0.31
    for (title, demand, count, color), y_value in zip(targets, y_values):
        add_box(
            axis,
            (0.03, y_value),
            0.18,
            0.12,
            f"{title}\n{demand}",
            "white",
            color,
            fontsize=10.5,
        )
        add_arrow(axis, (0.21, y_value + 0.06), (0.27, y_value + 0.06), color)
        for index in range(count):
            role = "主用" if not (title.endswith("T002") and index == 2) else "备用"
            add_box(
                axis,
                (slot_x + 0.055 * index, y_value + 0.015),
                0.046,
                0.09,
                f"{role}\n槽{index + 1}",
                PALE_GRAY,
                color,
                fontsize=8.2,
            )

    add_box(
        axis,
        (0.49, 0.58),
        0.20,
        0.22,
        "规则代价 C_rule\n\n接近时间与窗口\n协方差与威胁度\n资源能力与能源\n视场、冲突和换绑",
        PALE_BLUE,
        BLUE,
        fontsize=10.6,
    )
    add_box(
        axis,
        (0.49, 0.30),
        0.20,
        0.18,
        "可选强化学习残差\n\n每条候选边12维观察\n动作 a_ij ∈ [-2,2]\n"
        "ΔC = 0.25 tanh(a_ij)",
        PALE_PURPLE,
        PURPLE,
        fontsize=10.3,
    )
    add_arrow(axis, (0.43, 0.56), (0.49, 0.69), BLUE)
    add_arrow(axis, (0.59, 0.48), (0.59, 0.58), PURPLE, linestyle="--")
    add_box(
        axis,
        (0.74, 0.47),
        0.22,
        0.30,
        "确定性求解与发布\n\n候选硬门与稀疏化\n匈牙利/需求槽求解\n不完整联盟全有或全无\n"
        "20%迟滞、2秒驻留\n计划版本和执行签名",
        PALE_GREEN,
        GREEN,
        fontsize=10.7,
    )
    add_arrow(axis, (0.69, 0.69), (0.74, 0.62), GREEN)
    add_arrow(axis, (0.69, 0.39), (0.74, 0.53), PURPLE, linestyle="--")

    add_box(
        axis,
        (0.20, 0.09),
        0.27,
        0.12,
        "输入\nD2航迹与风险、资源状态、D4区域约束、D5反馈、前序计划",
        "white",
        BLUE,
        fontsize=10.2,
    )
    add_box(
        axis,
        (0.56, 0.09),
        0.27,
        0.12,
        "输出\n版本化AssignmentPlan、联盟角色/波次、D7绑定和D6计划记录",
        "white",
        GREEN,
        fontsize=10.2,
    )
    add_arrow(axis, (0.47, 0.15), (0.56, 0.15), MUTED)
    axis.text(
        0.5,
        0.025,
        "学习残差不能恢复被硬门删除的边，也不能绕过需求槽、资源唯一性、联盟完整性和版本检查。"
        "当前正式20个保留种子中代价矩阵20/20改变，最终绑定0/20改变。",
        ha="center",
        fontsize=10.4,
        color=MUTED,
    )
    save_figure(figure, output / "06_d3_assignment_and_residual.png")


def draw_d4_degradation(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(18, 9.5))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title("D4 主动与被动降级状态机", fontsize=21, pad=18, fontweight="bold")

    add_box(
        axis,
        (0.36, 0.73),
        0.28,
        0.15,
        "中心协调正常\nD3中心计划为当前版本\n中心心跳、时期和摘要可信",
        PALE_GREEN,
        GREEN,
        fontsize=11,
        fontweight="bold",
    )
    add_box(
        axis,
        (0.04, 0.48),
        0.25,
        0.15,
        "主动风险仲裁\nD1不确定度、D2歧义\nD3计划时效、D5末端不一致",
        PALE_AMBER,
        AMBER,
        fontsize=10.6,
    )
    add_box(
        axis,
        (0.375, 0.48),
        0.25,
        0.15,
        "请求中心重规划\n风险可由新计划修复\nD3发布严格更新版本",
        PALE_BLUE,
        BLUE,
        fontsize=10.6,
    )
    add_box(
        axis,
        (0.71, 0.48),
        0.25,
        0.15,
        "被动失效判定\n心跳硬超时、摘要冲突\n网络分区或法定多数",
        PALE_RED,
        RED,
        fontsize=10.6,
    )
    add_arrow(axis, (0.42, 0.73), (0.23, 0.63), AMBER)
    add_arrow(axis, (0.50, 0.73), (0.50, 0.63), BLUE)
    add_arrow(axis, (0.58, 0.73), (0.79, 0.63), RED)

    add_box(
        axis,
        (0.17, 0.22),
        0.29,
        0.15,
        "机动高空侦察二级节点\n持续就绪、覆盖、跨视角注册\nowner/version/epoch/lease全部通过",
        PALE_PURPLE,
        PURPLE,
        fontsize=10.7,
        fontweight="bold",
    )
    add_box(
        axis,
        (0.54, 0.22),
        0.29,
        0.15,
        "完全分布式保底\n本地CBBA/拍卖候选\n成员ACK、代次和租约原子提交",
        PALE_AMBER,
        AMBER,
        fontsize=10.7,
        fontweight="bold",
    )
    add_arrow(axis, (0.17, 0.48), (0.30, 0.37), PURPLE)
    add_arrow(axis, (0.50, 0.48), (0.37, 0.37), PURPLE)
    add_arrow(axis, (0.83, 0.48), (0.42, 0.37), PURPLE)
    add_arrow(axis, (0.46, 0.295), (0.54, 0.295), AMBER)
    axis.text(
        0.50,
        0.405,
        "二级节点持续就绪",
        ha="center",
        fontsize=9.5,
        color=PURPLE,
    )
    axis.text(
        0.50,
        0.265,
        "二级失效或不可用",
        ha="center",
        fontsize=9.5,
        color=AMBER,
    )

    add_box(
        axis,
        (0.08, 0.055),
        0.84,
        0.10,
        "执行边界：D4只输出仲裁、权威层和联盟提交状态。main/D3发布新版本计划；"
        "D5复核视觉身份；D7逐帧检查合同。证据、租约或成员确认不完整时保持或闭锁。",
        PALE_RED,
        RED,
        fontsize=10.7,
        fontweight="bold",
    )
    save_figure(figure, output / "07_d4_degradation_state_machine.png")


def draw_d5_geometry(output: Path) -> None:
    figure = plt.figure(figsize=(17, 9))
    grid = figure.add_gridspec(1, 2, width_ratios=[1.0, 1.1], wspace=0.15)
    world = figure.add_subplot(grid[0, 0], projection="3d")
    image_axis = figure.add_subplot(grid[0, 1])

    world_points = np.array(
        [
            [42.0, -8.0, 8.0],
            [48.0, 0.0, 10.0],
            [53.0, 9.0, 7.0],
            [58.0, 17.0, 12.0],
        ]
    )
    cameras = np.array([[0.0, -15.0, 5.0], [4.0, 18.0, 9.0], [10.0, 0.0, 45.0]])
    camera_colors = (BLUE, GREEN, AMBER)
    for camera_index, (camera, color) in enumerate(zip(cameras, camera_colors), start=1):
        world.scatter(*camera, s=85, marker="^", color=color, label=f"相机{camera_index}")
        for point in world_points:
            world.plot(
                [camera[0], point[0]],
                [camera[1], point[1]],
                [camera[2], point[2]],
                color=color,
                alpha=0.24,
                linewidth=0.9,
            )
    world.scatter(
        world_points[:, 0],
        world_points[:, 1],
        world_points[:, 2],
        s=75,
        color=RED,
        marker="x",
        linewidth=2.2,
        label="中心航迹预测",
    )
    world.set_xlabel("北向")
    world.set_ylabel("东向")
    world.set_zlabel("高度")
    world.set_title("世界系射线与多视角", fontsize=14, fontweight="bold")
    world.view_init(elev=24, azim=-62)
    world.legend(loc="upper left", fontsize=8)

    image_axis.set_xlim(0, 1920)
    image_axis.set_ylim(1080, 0)
    image_axis.set_aspect("equal")
    image_axis.set_title("图像平面投影与候选门控", fontsize=14, fontweight="bold")
    image_axis.set_xlabel("像素 u")
    image_axis.set_ylabel("像素 v")
    image_axis.grid(alpha=0.18)
    projected = np.array([[520, 530], [860, 470], [1190, 560], [1510, 430]])
    local = projected + np.array([[18, -12], [-22, 16], [34, 8], [-15, -20]])
    for index, (prediction, detection) in enumerate(zip(projected, local), start=1):
        image_axis.add_patch(
            patches.Ellipse(
                prediction,
                width=170,
                height=105,
                angle=(-10 + index * 7),
                facecolor=PALE_BLUE,
                edgecolor=BLUE,
                alpha=0.7,
                linewidth=1.5,
            )
        )
        image_axis.scatter(*prediction, color=BLUE, s=34, marker="+")
        image_axis.add_patch(
            patches.Rectangle(
                (detection[0] - 48, detection[1] - 32),
                96,
                64,
                fill=False,
                edgecolor=RED,
                linewidth=1.8,
            )
        )
        image_axis.plot(
            [prediction[0], detection[0]],
            [prediction[1], detection[1]],
            color=GREEN,
            linewidth=1.4,
        )
        image_axis.text(
            detection[0] + 55,
            detection[1],
            f"L-{index:02d} → G-{100 + index}",
            va="center",
            fontsize=9.5,
            color=INK,
        )

    figure.suptitle("D5 中心航迹到多相机视觉配准", fontsize=21, fontweight="bold")
    figure.text(
        0.5,
        0.035,
        "输入：D1/D2全局航迹、协方差、相机内外参、双时间戳和匿名局部轨迹；"
        "处理：预测、针孔投影、协方差雅可比传播、几何门、匈牙利和稳定窗口；"
        "输出：locked/ambiguous/hold/reacquire。图为机制示意。",
        ha="center",
        fontsize=10.2,
        color=MUTED,
    )
    save_figure(figure, output / "08_d5_geometry_registration.png")


def draw_d7_guidance(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(18, 9))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title("D7 雷达中段与视觉末段导引交接", fontsize=21, pad=18, fontweight="bold")

    states = (
        ("雷达中段", "D1/D2目标状态\n三维位置-速度PN\n必要时纯追踪重捕", PALE_BLUE, BLUE),
        ("交接候选", "进入尝试距离\n当前计划和D4许可\nD5同一航迹候选", PALE_AMBER, AMBER),
        ("视觉质量门", "检测框面积/边缘\nLOS质量与延迟\n稳定帧和机动裕度", PALE_PURPLE, PURPLE),
        ("视觉末段", "bbox转LOS\nVM或TTC视觉PNG\n图像KF短时外推", PALE_GREEN, GREEN),
        ("物理判定", "三维最近距离\n5米内记为拦截\n与控制许可分开统计", PALE_RED, RED),
    )
    x_values = np.linspace(0.025, 0.805, len(states))
    width = 0.17
    y_value = 0.55
    height = 0.22
    for index, ((title, content, face, edge), x_value) in enumerate(
        zip(states, x_values)
    ):
        add_box(
            axis,
            (float(x_value), y_value),
            width,
            height,
            f"{title}\n\n{content}",
            face,
            edge,
            fontsize=10.3,
        )
        if index < len(states) - 1:
            add_arrow(
                axis,
                (float(x_value) + width, y_value + height / 2),
                (float(x_values[index + 1]), y_value + height / 2),
                edge,
            )

    add_box(
        axis,
        (0.11, 0.25),
        0.34,
        0.16,
        "合同前置条件\nD3当前binding + D4当前权威/联盟\n"
        "D5同一global_track_id锁定 + 友方/重复锁定安全门",
        "white",
        RED,
        fontsize=10.7,
        fontweight="bold",
    )
    add_box(
        axis,
        (0.55, 0.25),
        0.34,
        0.16,
        "控制状态\n每个资源-目标对独立保存LOS、bbox、KF和迟滞\n"
        "身份、owner、角色或版本变化立即重置",
        "white",
        BLUE,
        fontsize=10.7,
        fontweight="bold",
    )
    add_arrow(axis, (0.28, 0.41), (0.50, 0.55), RED)
    add_arrow(axis, (0.72, 0.41), (0.66, 0.55), BLUE)
    axis.text(
        0.5,
        0.10,
        "当前可扩展三维环境使用三维位置-速度PN基线；AirSim默认路径为位置PN + png_vm，"
        "png_ttc为已验证候选。学习模型不进入D7控制律。",
        ha="center",
        fontsize=10.5,
        color=MUTED,
    )
    axis.text(
        0.5,
        0.045,
        "多个资源指向同一目标时仍是多个独立控制器。当前未实现共同到达、联盟级避碰或协同导引。",
        ha="center",
        fontsize=10.5,
        color="#8E3030",
        fontweight="bold",
    )
    save_figure(figure, output / "09_d7_guidance_handover.png")


def draw_d6_evaluation(
    output: Path,
    stage_timings: dict[str, dict[str, float]],
) -> None:
    figure = plt.figure(figsize=(18, 9))
    grid = figure.add_gridspec(1, 2, width_ratios=[1.05, 0.95], wspace=0.18)
    flow = figure.add_subplot(grid[0, 0])
    timing = figure.add_subplot(grid[0, 1])
    flow.set_xlim(0, 1)
    flow.set_ylim(0, 1)
    flow.axis("off")

    sources = (
        ("D1/D2", "观测、融合、身份\nNIS/NEES/RMSE/IDSW", BLUE),
        ("D3/D4", "分配、联盟、降级\n版本、ACK、租约", AMBER),
        ("D5/D7", "视觉、合同、控制\n模式切换、最近距离", PURPLE),
        ("main", "场景、seed、配置\n运行时、通信和真值旁路", GREEN),
    )
    y_values = (0.76, 0.57, 0.38, 0.19)
    for (title, content, color), y_value in zip(sources, y_values):
        add_box(
            flow,
            (0.02, y_value),
            0.30,
            0.13,
            f"{title}\n{content}",
            "white",
            color,
            fontsize=9.8,
        )
        add_arrow(flow, (0.32, y_value + 0.065), (0.40, 0.50), color)
    add_box(
        flow,
        (0.40, 0.34),
        0.25,
        0.32,
        "D6统一评估\n\n来源与schema审计\n在线真值隔离\navailability三态\n"
        "逐seed统计\nBootstrap置信区间",
        PALE_GREEN,
        GREEN,
        fontsize=10.8,
        fontweight="bold",
    )
    add_arrow(flow, (0.65, 0.50), (0.72, 0.50), GREEN)
    add_box(
        flow,
        (0.72, 0.32),
        0.25,
        0.36,
        "标准输出\n\n逐seed CSV\n聚合JSON\n中文Markdown\n"
        "曲线与失败原因\n模型准入/拒绝结论",
        PALE_BLUE,
        BLUE,
        fontsize=10.7,
    )
    flow.set_title("证据汇总流程", fontsize=15, fontweight="bold")

    selected = [
        ("D1融合", "d1_fusion"),
        ("D2关联", "d2_association"),
        ("D3分配", "d3_assignment"),
        ("D4区域", "d4_region_resource_advisor"),
        ("D5视觉", "d5_terminal_association"),
        ("主动视觉", "d5_active_vision"),
        ("D7导引", "d7_guidance"),
    ]
    values = [
        float(stage_timings.get(key, {}).get("mean_wall_time_ms", 0.0))
        for _, key in selected
    ]
    labels = [label for label, _ in selected]
    colors = [BLUE, GREEN, PURPLE, AMBER, CYAN, "#6E8B74", RED]
    bars = timing.barh(labels[::-1], values[::-1], color=colors[::-1], alpha=0.88)
    timing.set_xlabel("单次调用平均墙钟时间 / 毫秒")
    timing.set_title("seed 1000实际阶段耗时", fontsize=15, fontweight="bold")
    timing.grid(axis="x", alpha=0.25)
    for bar, value in zip(bars, values[::-1]):
        timing.text(
            value + max(values) * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1f}",
            va="center",
            fontsize=9.5,
        )
    timing.set_xlim(0.0, max(values) * 1.20 if max(values) > 0 else 1.0)

    figure.suptitle("D6 指标、证据和运行时评估", fontsize=21, fontweight="bold")
    figure.text(
        0.5,
        0.025,
        "右图来自200对200、seed 1000、10秒确定性回合。阶段调用频率不同，"
        "单次平均耗时不能直接相加为控制周期；该回合实时因子为0.1247。",
        ha="center",
        fontsize=10.3,
        color=MUTED,
    )
    save_figure(figure, output / "10_d6_evaluation_and_timing.png")


def draw_episode_state_machine(output: Path) -> None:
    figure, axis = plt.subplots(figsize=(18, 10))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.set_title("三维仿真 Episode 状态机与运行节拍", fontsize=21, pad=18, fontweight="bold")

    add_box(
        axis,
        (0.04, 0.77),
        0.18,
        0.12,
        "初始化\n读取场景/seed\n创建200+200+8状态",
        PALE_GRAY,
        INK,
        fontsize=10.5,
    )
    add_box(
        axis,
        (0.29, 0.77),
        0.18,
        0.12,
        "世界推进\n质点运动与通信\nphysics_dt=0.05秒",
        PALE_BLUE,
        BLUE,
        fontsize=10.5,
    )
    add_box(
        axis,
        (0.54, 0.77),
        0.18,
        0.12,
        "传感器事件\n雷达0.2秒\n视觉0.1秒/声学0.5秒",
        PALE_GREEN,
        GREEN,
        fontsize=10.5,
    )
    add_box(
        axis,
        (0.79, 0.77),
        0.17,
        0.12,
        "在线总线\n延迟、抖动、丢包\n按到达时刻释放",
        PALE_AMBER,
        AMBER,
        fontsize=10.5,
    )
    add_arrow(axis, (0.22, 0.83), (0.29, 0.83), BLUE)
    add_arrow(axis, (0.47, 0.83), (0.54, 0.83), GREEN)
    add_arrow(axis, (0.72, 0.83), (0.79, 0.83), AMBER)

    modules = (
        ("D1扫描融合", "事件触发", BLUE),
        ("D2关联", "0.2秒", GREEN),
        ("D4区域", "5秒", AMBER),
        ("D3分配", "1秒", PURPLE),
        ("D5视觉/主动视觉", "观测触发", CYAN),
        ("D7导引", "可用状态触发", RED),
    )
    x_values = np.linspace(0.035, 0.835, len(modules))
    for index, ((title, cadence, color), x_value) in enumerate(zip(modules, x_values)):
        add_box(
            axis,
            (float(x_value), 0.50),
            0.13,
            0.13,
            f"{title}\n{cadence}",
            "white",
            color,
            fontsize=9.8,
        )
        if index < len(modules) - 1:
            add_arrow(
                axis,
                (float(x_value) + 0.13, 0.565),
                (float(x_values[index + 1]), 0.565),
                color,
            )
    add_arrow(axis, (0.875, 0.77), (0.10, 0.63), AMBER, connectionstyle="arc3,rad=0.14")

    add_box(
        axis,
        (0.08, 0.23),
        0.24,
        0.13,
        "运行确认与执行\n分配ACK、相机命令ACK\n三维导航命令回写",
        PALE_BLUE,
        BLUE,
        fontsize=10.3,
    )
    add_box(
        axis,
        (0.38, 0.23),
        0.24,
        0.13,
        "终止判定\n到达仿真时长\n数值异常或资源保护线",
        PALE_RED,
        RED,
        fontsize=10.3,
    )
    add_box(
        axis,
        (0.68, 0.23),
        0.24,
        0.13,
        "离线D6\n真值映射、5米接近\n指标、图表与报告",
        PALE_GREEN,
        GREEN,
        fontsize=10.3,
    )
    add_arrow(axis, (0.90, 0.50), (0.20, 0.36), BLUE, connectionstyle="arc3,rad=-0.12")
    add_arrow(axis, (0.32, 0.295), (0.38, 0.295), RED)
    add_arrow(axis, (0.62, 0.295), (0.68, 0.295), GREEN)
    add_arrow(axis, (0.50, 0.23), (0.50, 0.13), RED)
    add_arrow(
        axis,
        (0.50, 0.13),
        (0.38, 0.77),
        MUTED,
        linestyle="--",
        connectionstyle="arc3,rad=-0.30",
    )
    axis.text(
        0.50,
        0.08,
        "多seed批量：重建全部模块状态和随机流，禁止跨episode复用计划、滤波状态或身份缓存",
        ha="center",
        fontsize=10.5,
        color=MUTED,
    )
    save_figure(figure, output / "11_episode_state_machine.png")


def draw_d1_3d_experiment(
    output: Path,
    episode: Path,
    timestamps: np.ndarray,
    intruders: np.ndarray,
    episode_record: dict,
) -> dict:
    record = read_last_jsonl_record(
        episode / "offline_identity" / "online_d1_records.jsonl"
    )
    tracks = list(record["payload"]["tracks"])
    estimates = track_positions(tracks)
    snapshot_timestamp = float(tracks[0]["timestamp"])
    truth_index = nearest_time_index(timestamps, snapshot_timestamp)
    truth_positions = np.asarray(intruders[truth_index, :, :3], dtype=float)

    pair_cost = np.linalg.norm(
        estimates[:, np.newaxis, :] - truth_positions[np.newaxis, :, :],
        axis=2,
    )
    estimate_indices, truth_indices = linear_sum_assignment(pair_cost)
    pair_errors = pair_cost[estimate_indices, truth_indices]
    covariance_sigma = np.asarray(
        [
            np.sqrt(np.trace(np.asarray(track["covariance"], dtype=float)[:3, :3]))
            for track in tracks
        ],
        dtype=float,
    )

    figure = plt.figure(figsize=(18, 9.5))
    grid = figure.add_gridspec(
        2,
        2,
        width_ratios=[1.42, 0.58],
        height_ratios=[0.56, 0.44],
        hspace=0.28,
        wspace=0.18,
    )
    scene = figure.add_subplot(grid[:, 0], projection="3d")
    histogram = figure.add_subplot(grid[0, 1])
    evidence = figure.add_subplot(grid[1, 1])
    evidence.axis("off")

    scene.scatter(
        truth_positions[:, 0],
        truth_positions[:, 1],
        -truth_positions[:, 2],
        s=24,
        marker="x",
        color=RED,
        linewidth=1.1,
        alpha=0.88,
        label="离线真值位置",
    )
    scene.scatter(
        estimates[:, 0],
        estimates[:, 1],
        -estimates[:, 2],
        s=15,
        color=BLUE,
        alpha=0.76,
        label="D1在线融合航迹",
    )
    ordered = np.argsort(pair_errors)
    sample_positions = np.linspace(
        0, len(ordered) - 1, min(32, len(ordered)), dtype=int
    )
    for pair_index in ordered[sample_positions]:
        estimate = estimates[estimate_indices[pair_index]]
        truth = truth_positions[truth_indices[pair_index]]
        scene.plot(
            [estimate[0], truth[0]],
            [estimate[1], truth[1]],
            [-estimate[2], -truth[2]],
            color=MUTED,
            linewidth=0.75,
            alpha=0.56,
        )
    style_3d_axis(scene, f"末帧三维融合快照  t={snapshot_timestamp:.3f}秒")
    scene.legend(loc="upper left", fontsize=9)

    histogram.hist(
        pair_errors,
        bins=18,
        color=BLUE,
        alpha=0.82,
        edgecolor="white",
    )
    histogram.axvline(
        float(np.median(pair_errors)),
        color=GREEN,
        linewidth=1.7,
        label=f"中位数 {np.median(pair_errors):.2f}米",
    )
    histogram.axvline(
        float(np.percentile(pair_errors, 95)),
        color=RED,
        linewidth=1.7,
        linestyle="--",
        label=f"95分位 {np.percentile(pair_errors, 95):.2f}米",
    )
    histogram.set_xlabel("单帧最小几何配对距离 / 米")
    histogram.set_ylabel("配对数量")
    histogram.set_title("离线几何诊断", fontsize=14, fontweight="bold")
    histogram.grid(axis="y", alpha=0.22)
    histogram.legend(fontsize=9)

    consistency = episode_record["d1_consistency"]["metrics"]
    mean_nis = float(consistency["mean_nis"]["value"])
    normalized_nis = float(consistency["mean_normalized_nis"]["value"])
    gate_coverage = float(consistency["nis_gate_coverage"]["value"])
    evidence.text(
        0.02,
        0.95,
        "实测证据",
        fontsize=14,
        fontweight="bold",
        va="top",
    )
    evidence.text(
        0.02,
        0.82,
        "\n".join(
            [
                f"真实目标：{truth_positions.shape[0]}",
                f"D1航迹：{estimates.shape[0]}（额外候选1条）",
                f"创新样本：{consistency['mean_nis']['sample_count']}",
                f"平均归一化创新平方：{normalized_nis:.4f}",
                f"创新门覆盖率：{gate_coverage:.2%}",
                f"位置协方差综合标准差中位数：{np.median(covariance_sigma):.2f}米",
                f"单帧几何配对均方根：{np.sqrt(np.mean(pair_errors**2)):.2f}米",
            ]
        ),
        fontsize=10.7,
        va="top",
        linespacing=1.55,
    )
    evidence.text(
        0.02,
        0.08,
        "单帧配对只用于空间覆盖诊断。D1与真值的完整身份谱系尚未闭合，"
        "正式位置均方根误差和归一化估计误差平方仍标记为不可用。",
        fontsize=9.7,
        color="#8E3030",
        va="bottom",
        wrap=True,
    )

    figure.suptitle(
        "D1 异步多传感器融合三维实验结果",
        fontsize=21,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.018,
        "来源：200对200、seed 1000、10秒确定性回合。真值仅在回合结束后用于离线绘图和评分。",
        ha="center",
        fontsize=10.2,
        color=MUTED,
    )
    save_figure(figure, output / "12_d1_3d_fusion_experiment.png")

    return {
        "snapshot_timestamp": snapshot_timestamp,
        "truth_count": int(truth_positions.shape[0]),
        "online_track_count": int(estimates.shape[0]),
        "geometric_pair_count": int(pair_errors.size),
        "geometric_pair_distance_median_m": float(np.median(pair_errors)),
        "geometric_pair_distance_p95_m": float(np.percentile(pair_errors, 95)),
        "geometric_pair_distance_rms_m": float(np.sqrt(np.mean(pair_errors**2))),
        "geometric_pair_distance_max_m": float(np.max(pair_errors)),
        "position_covariance_sigma_median_m": float(np.median(covariance_sigma)),
        "position_covariance_sigma_p95_m": float(
            np.percentile(covariance_sigma, 95)
        ),
        "mean_nis": mean_nis,
        "mean_normalized_nis": normalized_nis,
        "nis_gate_coverage": gate_coverage,
        "formal_position_rmse_available": False,
        "formal_position_rmse_unavailable_reason": "d2_lineage_mapping_missing",
    }


def draw_d2_3d_experiment(
    output: Path,
    episode: Path,
    timestamps: np.ndarray,
    intruders: np.ndarray,
) -> dict:
    record = read_last_jsonl_record(
        episode / "offline_identity" / "online_d2_records.jsonl"
    )
    tracks = list(record["payload"]["tracks"])
    tracks_by_id = {track["global_track_id"]: track for track in tracks}
    evaluation = json.loads(
        (episode / "offline_identity" / "identity_evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    final_frame = evaluation["frames"][-1]
    snapshot_timestamp = float(final_frame["frame_timestamp"])
    truth_index = nearest_time_index(timestamps, snapshot_timestamp)
    truth_positions = np.asarray(intruders[truth_index, :, :3], dtype=float)
    truth_ids = [f"TGT-{index:04d}" for index in range(1, 201)]
    truth_by_id = {
        target_id: truth_positions[index]
        for index, target_id in enumerate(truth_ids)
    }
    track_values = track_positions(tracks)

    figure = plt.figure(figsize=(18, 9.5))
    grid = figure.add_gridspec(
        2,
        2,
        width_ratios=[1.42, 0.58],
        height_ratios=[0.58, 0.42],
        hspace=0.30,
        wspace=0.18,
    )
    scene = figure.add_subplot(grid[:, 0], projection="3d")
    timeline = figure.add_subplot(grid[0, 1])
    evidence = figure.add_subplot(grid[1, 1])
    evidence.axis("off")

    scene.scatter(
        truth_positions[:, 0],
        truth_positions[:, 1],
        -truth_positions[:, 2],
        s=23,
        marker="x",
        color=RED,
        linewidth=1.0,
        alpha=0.82,
        label="离线真值位置",
    )
    scene.scatter(
        track_values[:, 0],
        track_values[:, 1],
        -track_values[:, 2],
        s=15,
        color=GREEN,
        alpha=0.74,
        label="D2在线关联航迹",
    )

    available_mappings = [
        mapping
        for mapping in final_frame["mappings"]
        if mapping["status"] == "available"
        and mapping.get("truth_target_id") in truth_by_id
        and mapping["global_track_id"] in tracks_by_id
    ]
    sample_positions = np.linspace(
        0,
        len(available_mappings) - 1,
        min(32, len(available_mappings)),
        dtype=int,
    )
    for mapping_index in sample_positions:
        mapping = available_mappings[int(mapping_index)]
        estimate = np.asarray(
            tracks_by_id[mapping["global_track_id"]]["state_ned"][:3],
            dtype=float,
        )
        truth = truth_by_id[mapping["truth_target_id"]]
        scene.plot(
            [estimate[0], truth[0]],
            [estimate[1], truth[1]],
            [-estimate[2], -truth[2]],
            color=MUTED,
            linewidth=0.75,
            alpha=0.52,
        )

    ambiguous_mappings = [
        mapping
        for mapping in final_frame["mappings"]
        if mapping["status"] == "ambiguous"
        and mapping["global_track_id"] in tracks_by_id
    ]
    for mapping in ambiguous_mappings:
        estimate = np.asarray(
            tracks_by_id[mapping["global_track_id"]]["state_ned"][:3],
            dtype=float,
        )
        scene.scatter(
            [estimate[0]],
            [estimate[1]],
            [-estimate[2]],
            s=90,
            marker="D",
            color=AMBER,
            edgecolor="white",
            linewidth=0.8,
            label="末帧歧义航迹",
        )
        for target_id in mapping.get("candidate_truth_target_ids", []):
            if target_id not in truth_by_id:
                continue
            truth = truth_by_id[target_id]
            scene.plot(
                [estimate[0], truth[0]],
                [estimate[1], truth[1]],
                [-estimate[2], -truth[2]],
                color=AMBER,
                linewidth=1.6,
                linestyle="--",
                alpha=0.9,
            )
    style_3d_axis(scene, f"末帧三维关联快照  t={snapshot_timestamp:.3f}秒")
    handles, labels = scene.get_legend_handles_labels()
    unique_legend = dict(zip(labels, handles))
    scene.legend(
        unique_legend.values(),
        unique_legend.keys(),
        loc="upper left",
        fontsize=9,
    )

    frame_times = np.asarray(
        [frame["frame_timestamp"] for frame in evaluation["frames"]],
        dtype=float,
    )
    available_counts = np.asarray(
        [frame["available_mapping_count"] for frame in evaluation["frames"]],
        dtype=float,
    )
    ambiguous_counts = np.asarray(
        [frame["ambiguous_mapping_count"] for frame in evaluation["frames"]],
        dtype=float,
    )
    unavailable_counts = np.asarray(
        [frame["unavailable_mapping_count"] for frame in evaluation["frames"]],
        dtype=float,
    )
    timeline.plot(
        frame_times,
        available_counts,
        color=GREEN,
        linewidth=1.8,
        label="可用映射",
    )
    timeline.plot(
        frame_times,
        unavailable_counts,
        color=MUTED,
        linewidth=1.4,
        label="不可用映射",
    )
    timeline.bar(
        frame_times,
        ambiguous_counts,
        width=0.10,
        color=AMBER,
        alpha=0.82,
        label="歧义映射",
    )
    timeline.set_xlabel("仿真时间 / 秒")
    timeline.set_ylabel("映射数量")
    timeline.set_title("48个关联帧的证据状态", fontsize=14, fontweight="bold")
    timeline.grid(alpha=0.22)
    timeline.legend(fontsize=9, ncol=3, loc="lower right")

    partial = evaluation["partial_identity_diagnostics"]
    state_counts: dict[str, int] = {}
    for track in tracks:
        state = str(track["track_state"])
        state_counts[state] = state_counts.get(state, 0) + 1
    evidence.text(
        0.02,
        0.95,
        "实测证据",
        fontsize=14,
        fontweight="bold",
        va="top",
    )
    evidence.text(
        0.02,
        0.82,
        "\n".join(
            [
                f"末态航迹：{len(tracks)}，真实目标：200",
                f"生命周期：确认{state_counts.get('confirmed', 0)}，"
                f"可执行{state_counts.get('engageable', 0)}，"
                f"暂定{state_counts.get('tentative', 0)}",
                f"末帧映射：可用{final_frame['available_mapping_count']}，"
                f"歧义{final_frame['ambiguous_mapping_count']}，"
                f"不可用{final_frame['unavailable_mapping_count']}",
                f"可评分映射覆盖率：{partial['evaluable_mapping_coverage']:.2%}",
                f"完整帧覆盖率：{partial['evaluable_frame_coverage']:.2%}",
                f"相邻转换覆盖率：{partial['evaluable_transition_coverage']:.2%}",
                f"保守身份切换下界：{partial['id_switch_lower_bound']}",
            ]
        ),
        fontsize=10.6,
        va="top",
        linespacing=1.52,
    )
    evidence.text(
        0.02,
        0.07,
        "存在同一全局航迹对应多个真实目标的离线证据。严格身份切换、连续性和重复航迹指标"
        "继续标记为不可用；48次只是不完整证据下的保守下界。",
        fontsize=9.7,
        color="#8E3030",
        va="bottom",
        wrap=True,
    )

    figure.suptitle(
        "D2 多目标轨迹关联三维实验结果",
        fontsize=21,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.018,
        "来源：200对200、seed 1000、48个D2发布帧。真实身份只在离线评估器中联接。",
        ha="center",
        fontsize=10.2,
        color=MUTED,
    )
    save_figure(figure, output / "13_d2_3d_association_experiment.png")

    return {
        "snapshot_timestamp": snapshot_timestamp,
        "truth_count": 200,
        "online_track_count": len(tracks),
        "lifecycle_state_counts": state_counts,
        "final_available_mapping_count": int(
            final_frame["available_mapping_count"]
        ),
        "final_ambiguous_mapping_count": int(
            final_frame["ambiguous_mapping_count"]
        ),
        "final_unavailable_mapping_count": int(
            final_frame["unavailable_mapping_count"]
        ),
        "evaluable_mapping_coverage": float(
            partial["evaluable_mapping_coverage"]
        ),
        "evaluable_frame_coverage": float(partial["evaluable_frame_coverage"]),
        "evaluable_transition_coverage": float(
            partial["evaluable_transition_coverage"]
        ),
        "id_switch_lower_bound": int(partial["id_switch_lower_bound"]),
        "strict_id_switch_count_available": False,
        "strict_metric_unavailable_reason": "multiple_truth_targets_for_global_track",
    }


def draw_d3_3d_experiment(
    output: Path,
    episode: Path,
    timestamps: np.ndarray,
    interceptors: np.ndarray,
    summary: dict,
) -> dict:
    with (episode / "active_vision_r0_windows.json").open(
        encoding="utf-8"
    ) as handle:
        active_vision = json.load(handle)

    candidate_records: list[tuple[int, str, str, float]] = []
    for record in active_vision["records"]:
        effective_action = record.get("effective_action") or {}
        issued_payload = record.get("issued_command_payload") or {}
        plan_version = effective_action.get(
            "plan_version", issued_payload.get("plan_version")
        )
        resource_id = record.get("resource_id")
        target_id = record.get("target_global_track_id")
        camera_state = (
            (record.get("camera_feedback") or {}).get("camera_state") or {}
        )
        state_timestamp = camera_state.get("state_timestamp")
        if (
            isinstance(plan_version, int)
            and isinstance(resource_id, str)
            and resource_id.startswith("INT-")
            and isinstance(target_id, str)
            and state_timestamp is not None
        ):
            candidate_records.append(
                (
                    plan_version,
                    resource_id,
                    target_id,
                    float(state_timestamp),
                )
            )
    if not candidate_records:
        raise ValueError("no D3 plan bindings found in active vision evidence")

    plan_version = max(record[0] for record in candidate_records)
    plan_records = [
        record for record in candidate_records if record[0] == plan_version
    ]
    binding_by_resource: dict[str, str] = {}
    for _, resource_id, target_id, _ in plan_records:
        previous_target = binding_by_resource.setdefault(resource_id, target_id)
        if previous_target != target_id:
            raise ValueError(
                f"resource {resource_id} changed target within plan {plan_version}"
            )
    plan_timestamp = min(record[3] for record in plan_records)

    closest_d2_record: dict | None = None
    closest_delta = float("inf")
    d2_path = episode / "offline_identity" / "online_d2_records.jsonl"
    with d2_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            frame_timestamp = float(record["payload"]["timestamp"])
            delta = abs(frame_timestamp - plan_timestamp)
            if delta < closest_delta:
                closest_delta = delta
                closest_d2_record = record
    if closest_d2_record is None:
        raise ValueError(f"no D2 records found in {d2_path}")

    d2_timestamp = float(closest_d2_record["payload"]["timestamp"])
    target_positions = {
        track["global_track_id"]: np.asarray(track["state_ned"][:3], dtype=float)
        for track in closest_d2_record["payload"]["tracks"]
    }
    resource_time_index = nearest_time_index(timestamps, plan_timestamp)

    assignment_rows: list[tuple[str, str, np.ndarray, np.ndarray, float]] = []
    missing_target_ids: list[str] = []
    for resource_id, target_id in sorted(binding_by_resource.items()):
        if target_id not in target_positions:
            missing_target_ids.append(target_id)
            continue
        resource_index = int(resource_id.split("-")[1]) - 1
        resource_position = np.asarray(
            interceptors[resource_time_index, resource_index, :3],
            dtype=float,
        )
        target_position = target_positions[target_id]
        distance = float(np.linalg.norm(target_position - resource_position))
        assignment_rows.append(
            (
                resource_id,
                target_id,
                resource_position,
                target_position,
                distance,
            )
        )
    distances = np.asarray([row[4] for row in assignment_rows], dtype=float)

    figure = plt.figure(figsize=(18, 9.5))
    grid = figure.add_gridspec(
        2,
        2,
        width_ratios=[1.42, 0.58],
        height_ratios=[0.56, 0.44],
        hspace=0.30,
        wspace=0.18,
    )
    scene = figure.add_subplot(grid[:, 0], projection="3d")
    histogram = figure.add_subplot(grid[0, 1])
    evidence = figure.add_subplot(grid[1, 1])
    evidence.axis("off")

    resource_values = np.asarray([row[2] for row in assignment_rows], dtype=float)
    target_values = np.asarray([row[3] for row in assignment_rows], dtype=float)
    scene.scatter(
        resource_values[:, 0],
        resource_values[:, 1],
        -resource_values[:, 2],
        s=15,
        color=BLUE,
        alpha=0.78,
        label="拦截资源",
    )
    scene.scatter(
        target_values[:, 0],
        target_values[:, 1],
        -target_values[:, 2],
        s=21,
        marker="x",
        color=RED,
        linewidth=1.0,
        alpha=0.85,
        label="被分配D2航迹",
    )
    region_colors = [BLUE, CYAN, GREEN, "#6E8B74", AMBER, RED, PURPLE, MUTED]
    distance_order = np.argsort(distances)
    emphasized = set(
        distance_order[
            np.linspace(
                0,
                len(distance_order) - 1,
                min(28, len(distance_order)),
                dtype=int,
            )
        ].tolist()
    )
    for index, (_, _, resource, target, _) in enumerate(assignment_rows):
        angle = (np.arctan2(target[1], target[0]) + 2.0 * np.pi) % (
            2.0 * np.pi
        )
        region_index = int(angle / (2.0 * np.pi / 8.0)) % 8
        scene.plot(
            [resource[0], target[0]],
            [resource[1], target[1]],
            [-resource[2], -target[2]],
            color=region_colors[region_index],
            linewidth=1.0 if index in emphasized else 0.45,
            alpha=0.72 if index in emphasized else 0.13,
        )
    style_3d_axis(
        scene,
        f"第{plan_version}版三维分配  t={plan_timestamp:.1f}秒",
    )
    scene.legend(loc="upper left", fontsize=9)

    histogram.hist(
        distances,
        bins=18,
        color=PURPLE,
        alpha=0.82,
        edgecolor="white",
    )
    histogram.axvline(
        float(np.median(distances)),
        color=GREEN,
        linewidth=1.7,
        label=f"中位数 {np.median(distances):.0f}米",
    )
    histogram.axvline(
        float(np.percentile(distances, 95)),
        color=RED,
        linewidth=1.7,
        linestyle="--",
        label=f"95分位 {np.percentile(distances, 95):.0f}米",
    )
    histogram.set_xlabel("资源到分配航迹的初始距离 / 米")
    histogram.set_ylabel("绑定数量")
    histogram.set_title("第8版分配距离", fontsize=14, fontweight="bold")
    histogram.grid(axis="y", alpha=0.22)
    histogram.legend(fontsize=9)

    timing = summary["module_final_diagnostics"]["stage_timings"]["d3_assignment"]
    evidence.text(
        0.02,
        0.95,
        "实测证据",
        fontsize=14,
        fontweight="bold",
        va="top",
    )
    evidence.text(
        0.02,
        0.82,
        "\n".join(
            [
                f"计划版本：{plan_version}",
                f"唯一资源绑定：{len(binding_by_resource)}",
                f"唯一目标航迹：{len(set(binding_by_resource.values()))}",
                f"三维连线可用：{len(assignment_rows)}，缺失目标：{len(missing_target_ids)}",
                f"计划确认：{summary['assignment_plan_ack_count']}次",
                f"绑定确认/控制采用：{summary['assignment_plan_binding_ack_count']}/"
                f"{summary['assignment_plan_control_applied_count']}",
                f"D3单次平均/P95：{timing['mean_wall_time_ms']:.1f}/"
                f"{timing['p95_wall_time_ms']:.1f}毫秒",
            ]
        ),
        fontsize=10.6,
        va="top",
        linespacing=1.55,
    )
    evidence.text(
        0.02,
        0.07,
        "本图证明200条一对一绑定被运行时消费。约3.1千米的中位初始距离和10秒短回合决定了"
        "本次没有五米物理接近；分配完整不等于拦截完成。",
        fontsize=9.7,
        color="#8E3030",
        va="bottom",
        wrap=True,
    )

    figure.suptitle(
        "D3 目标分配三维实验结果",
        fontsize=21,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.018,
        "来源：第8版在线计划、同刻D2航迹和资源状态。连线颜色按目标所在八区域区分。",
        ha="center",
        fontsize=10.2,
        color=MUTED,
    )
    save_figure(figure, output / "14_d3_3d_assignment_experiment.png")

    return {
        "plan_version": plan_version,
        "plan_timestamp": plan_timestamp,
        "d2_snapshot_timestamp": d2_timestamp,
        "unique_resource_binding_count": len(binding_by_resource),
        "unique_target_binding_count": len(set(binding_by_resource.values())),
        "three_dimensional_binding_count": len(assignment_rows),
        "missing_target_count": len(missing_target_ids),
        "duplicate_target_binding_count": (
            len(binding_by_resource) - len(set(binding_by_resource.values()))
        ),
        "assignment_distance_median_m": float(np.median(distances)),
        "assignment_distance_p95_m": float(np.percentile(distances, 95)),
        "assignment_distance_max_m": float(np.max(distances)),
        "assignment_plan_ack_count": int(summary["assignment_plan_ack_count"]),
        "assignment_plan_binding_ack_count": int(
            summary["assignment_plan_binding_ack_count"]
        ),
        "assignment_plan_control_applied_count": int(
            summary["assignment_plan_control_applied_count"]
        ),
        "d3_mean_wall_time_ms": float(timing["mean_wall_time_ms"]),
        "d3_p95_wall_time_ms": float(timing["p95_wall_time_ms"]),
    }


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    episode = args.episode.resolve()
    output.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()

    with np.load(episode / "offline_truth_state.npz") as truth:
        timestamps = np.asarray(truth["timestamps"], dtype=float)
        intruders = np.asarray(truth["intruder_state"], dtype=float)
        interceptors = np.asarray(truth["interceptor_state"], dtype=float)
        recon = np.asarray(truth["recon_state"], dtype=float)
    summary = json.loads((episode / "summary.json").read_text(encoding="utf-8"))
    episode_record = json.loads(
        (episode / "d6_truth_isolated" / "episode_record.json").read_text(
            encoding="utf-8"
        )
    )
    stage_timings = (
        summary.get("module_final_diagnostics", {}).get("stage_timings", {})
        if isinstance(summary, dict)
        else {}
    )

    draw_full_stack_architecture(output)
    draw_layered_3d_scene(output, timestamps, intruders, interceptors, recon)
    draw_contract_chain(output)
    draw_d1_fusion(output)
    draw_d2_association(output)
    draw_d3_assignment(output)
    draw_d4_degradation(output)
    draw_d5_geometry(output)
    draw_d7_guidance(output)
    draw_d6_evaluation(output, stage_timings)
    draw_episode_state_machine(output)
    d1_experiment = draw_d1_3d_experiment(
        output,
        episode,
        timestamps,
        intruders,
        episode_record,
    )
    d2_experiment = draw_d2_3d_experiment(
        output,
        episode,
        timestamps,
        intruders,
    )
    d3_experiment = draw_d3_3d_experiment(
        output,
        episode,
        timestamps,
        interceptors,
        summary,
    )

    experiment_metrics = {
        "schema_version": "msm.200v200.d1_d3_3d_experiment_metrics.v1",
        "source_episode": str(episode.relative_to(ROOT)),
        "source_seed": summary.get("seed"),
        "source_duration_s": summary.get("simulated_duration_s"),
        "truth_use_policy": "offline_evaluation_and_visualization_only",
        "d1_sensor_fusion": d1_experiment,
        "d2_data_association": d2_experiment,
        "d3_assignment": d3_experiment,
    }
    (output / "d1_d3_3d_experiment_metrics.json").write_text(
        json.dumps(experiment_metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "msm.200v200.full_stack_figure_manifest.v2",
        "source_episode": str(episode.relative_to(ROOT)),
        "source_seed": summary.get("seed"),
        "source_duration_s": summary.get("simulated_duration_s"),
        "derived_metrics": "d1_d3_3d_experiment_metrics.json",
        "figures": [
            {
                "file": "01_full_stack_architecture.png",
                "evidence_type": "algorithm_mechanism",
            },
            {
                "file": "02_layered_3d_scene.png",
                "evidence_type": "measured_trajectory_with_scheme_annotations",
            },
            {
                "file": "03_contract_chain.png",
                "evidence_type": "algorithm_mechanism",
            },
            {
                "file": "04_d1_sensor_fusion.png",
                "evidence_type": "algorithm_mechanism",
            },
            {
                "file": "05_d2_data_association.png",
                "evidence_type": "algorithm_mechanism",
            },
            {
                "file": "06_d3_assignment_and_residual.png",
                "evidence_type": "algorithm_mechanism_with_frozen_result_annotation",
            },
            {
                "file": "07_d4_degradation_state_machine.png",
                "evidence_type": "algorithm_mechanism",
            },
            {
                "file": "08_d5_geometry_registration.png",
                "evidence_type": "algorithm_mechanism",
            },
            {
                "file": "09_d7_guidance_handover.png",
                "evidence_type": "algorithm_mechanism",
            },
            {
                "file": "10_d6_evaluation_and_timing.png",
                "evidence_type": "algorithm_mechanism_and_measured_timing",
            },
            {
                "file": "11_episode_state_machine.png",
                "evidence_type": "runtime_mechanism",
            },
            {
                "file": "12_d1_3d_fusion_experiment.png",
                "evidence_type": "measured_online_tracks_with_offline_truth_diagnostic",
            },
            {
                "file": "13_d2_3d_association_experiment.png",
                "evidence_type": "measured_online_tracks_with_offline_identity_evidence",
            },
            {
                "file": "14_d3_3d_assignment_experiment.png",
                "evidence_type": "measured_runtime_assignment_with_3d_geometry",
            },
        ],
    }
    (output / "figure_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
