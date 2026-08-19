"""Generate deterministic Chinese diagrams for the GNN algorithm document."""

from __future__ import annotations

from pathlib import Path
import warnings

import matplotlib

matplotlib.use("Agg")
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon
import numpy as np


ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"

BLUE = "#356A8A"
BLUE_FILL = "#E7F0F7"
ORANGE = "#C96D3B"
ORANGE_FILL = "#F8E9DF"
GREEN = "#2E8B57"
GREEN_FILL = "#E5F2EA"
RED = "#A9483D"
RED_FILL = "#F6E5E2"
GRAY = "#7C8A93"
LIGHT_GRAY = "#E5E8EA"
PANEL = "#F5F7F8"
DARK = "#263238"


def configure_font() -> None:
    candidates = (
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Source Han Sans CN",
        "Droid Sans Fallback",
        "WenQuanYi Micro Hei",
        "SimHei",
    )
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def save(fig: plt.Figure, filename: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        FIGURES / filename,
        dpi=200,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def add_box(
    axis: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    *,
    facecolor: str = PANEL,
    edgecolor: str = GRAY,
    fontsize: float = 10.5,
    linewidth: float = 1.5,
) -> None:
    axis.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=linewidth,
        )
    )
    axis.text(
        x + width / 2,
        y + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=DARK,
    )


def add_arrow(
    axis: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = DARK,
    linewidth: float = 1.7,
) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=linewidth,
            color=color,
            shrinkA=3,
            shrinkB=3,
        )
    )


def draw_epipolar_geometry() -> None:
    fig, axis = plt.subplots(figsize=(12.5, 7.2))
    axis.set_xlim(0, 12.5)
    axis.set_ylim(0, 7.2)
    axis.axis("off")
    axis.text(
        6.25,
        6.8,
        "共面性筛选的几何含义",
        ha="center",
        fontsize=18,
        weight="bold",
    )
    axis.text(
        6.25,
        6.4,
        "同一目标的双站视线应落在同一极平面附近",
        ha="center",
        fontsize=11.5,
    )

    plane = Polygon(
        [(1.1, 1.25), (11.4, 1.25), (9.35, 5.35), (3.15, 5.35)],
        closed=True,
        facecolor="#EAF3F7",
        edgecolor=BLUE,
        linewidth=1.5,
        alpha=0.85,
    )
    axis.add_patch(plane)
    axis.text(6.2, 1.55, "A站、B站和真实目标形成的极平面", ha="center", fontsize=11, color=BLUE)

    a = (2.0, 1.75)
    b = (10.5, 1.75)
    target = (6.2, 4.65)
    false_target = (8.7, 5.85)
    for position, label, color in (
        (a, "A站", BLUE),
        (b, "B站", ORANGE),
        (target, "真实目标", GREEN),
        (false_target, "另一目标", RED),
    ):
        axis.add_patch(Circle(position, 0.27, facecolor=color, edgecolor="white", linewidth=1.4, zorder=4))
        axis.text(position[0], position[1] + 0.46, label, ha="center", fontsize=11, weight="bold", color=color)

    axis.plot([a[0], b[0]], [a[1], b[1]], color=GRAY, linestyle="--", linewidth=1.7)
    axis.text(6.25, 1.9, "双站基线", ha="center", fontsize=10.5, color=GRAY)
    axis.plot([a[0], target[0]], [a[1], target[1]], color=BLUE, linewidth=3.0)
    axis.plot([b[0], target[0]], [b[1], target[1]], color=GREEN, linewidth=3.0)
    axis.text(3.65, 3.45, "A站视线", color=BLUE, fontsize=10.5, rotation=34)
    axis.text(8.25, 3.5, "B站正确候选", color=GREEN, fontsize=10.5, rotation=-34)

    axis.plot(
        [b[0], false_target[0]],
        [b[1], false_target[1]],
        color=RED,
        linestyle="--",
        linewidth=2.5,
    )
    axis.plot(
        [false_target[0], false_target[0] - 0.55],
        [false_target[1], 5.2],
        color=RED,
        linestyle=":",
        linewidth=1.5,
    )
    axis.text(9.3, 4.05, "B站错误候选\n偏离极平面", color=RED, fontsize=10.5, ha="center")

    add_box(
        axis,
        0.55,
        0.25,
        3.55,
        0.72,
        "正确候选：共面残差小，进入后续比较",
        facecolor=GREEN_FILL,
        edgecolor=GREEN,
    )
    add_box(
        axis,
        4.45,
        0.25,
        3.55,
        0.72,
        "错误候选：共面残差大，优先排除",
        facecolor=RED_FILL,
        edgecolor=RED,
    )
    add_box(
        axis,
        8.35,
        0.25,
        3.55,
        0.72,
        "接近门限的候选交给图网络继续判断",
        facecolor=BLUE_FILL,
        edgecolor=BLUE,
    )
    axis.text(11.75, 6.05, "空间示意，不按比例", ha="right", fontsize=9.5, color=GRAY)
    save(fig, "06_epipolar_candidate_geometry.png")


def draw_candidate_pruning() -> None:
    fig, axis = plt.subplots(figsize=(13.5, 7.2))
    axis.set_xlim(0, 13.5)
    axis.set_ylim(0, 7.2)
    axis.axis("off")
    axis.text(6.75, 6.8, "从全组合到稀疏候选图", ha="center", fontsize=18, weight="bold")
    axis.text(
        6.75,
        6.4,
        "图网络只处理前级保留下来的候选，不遍历全部组合",
        ha="center",
        fontsize=11.5,
    )

    y_values = np.linspace(1.2, 5.7, 6)
    left_a, left_b = 0.9, 4.2
    right_a, right_b = 9.2, 12.5

    axis.text(2.55, 6.05, "全组合：6×6＝36条关系", ha="center", fontsize=12.5, weight="bold")
    for index, y in enumerate(y_values, start=1):
        for x, color, prefix in ((left_a, BLUE, "A"), (left_b, ORANGE, "B")):
            axis.add_patch(Circle((x, y), 0.22, facecolor=color, edgecolor="white", linewidth=1.0, zorder=4))
            axis.text(x, y, f"{prefix}{index}", ha="center", va="center", color="white", fontsize=8.5, zorder=5)
    for y_a in y_values:
        for y_b in y_values:
            axis.plot([left_a + 0.23, left_b - 0.23], [y_a, y_b], color=LIGHT_GRAY, linewidth=0.65, zorder=1)

    add_box(
        axis,
        5.05,
        2.2,
        3.35,
        2.5,
        "稳定航迹优先\n\n归一化共面残差≤8\n\n双向前K候选取并集",
        facecolor=PANEL,
        edgecolor=GRAY,
        fontsize=11.5,
    )
    add_arrow(axis, (4.35, 3.45), (5.05, 3.45), color=GRAY)
    add_arrow(axis, (8.4, 3.45), (9.05, 3.45), color=GRAY)

    axis.text(10.85, 6.05, "稀疏候选：仅保留可能关系", ha="center", fontsize=12.5, weight="bold")
    for index, y in enumerate(y_values, start=1):
        for x, color, prefix in ((right_a, BLUE, "A"), (right_b, ORANGE, "B")):
            axis.add_patch(Circle((x, y), 0.22, facecolor=color, edgecolor="white", linewidth=1.0, zorder=4))
            axis.text(x, y, f"{prefix}{index}", ha="center", va="center", color="white", fontsize=8.5, zorder=5)
    sparse_edges = (
        (0, 0, GREEN, 3.0),
        (0, 1, GRAY, 1.4),
        (1, 1, GREEN, 3.0),
        (1, 2, GRAY, 1.4),
        (2, 2, GREEN, 3.0),
        (2, 3, GRAY, 1.4),
        (3, 3, GREEN, 3.0),
        (3, 4, GRAY, 1.4),
        (4, 4, GREEN, 3.0),
        (5, 5, GREEN, 3.0),
    )
    for left, right, color, linewidth in sparse_edges:
        axis.plot(
            [right_a + 0.23, right_b - 0.23],
            [y_values[left], y_values[right]],
            color=color,
            linewidth=linewidth,
            zorder=2,
        )

    axis.text(
        6.75,
        0.45,
        "灰线是仍需判断的竞争候选，绿线表示示意中的正确关系；在线计算不知道哪条绿线是真实关系。",
        ha="center",
        fontsize=10.8,
        color=DARK,
    )
    save(fig, "07_candidate_pruning.png")


def draw_feature_groups() -> None:
    fig, axis = plt.subplots(figsize=(14.5, 7.6))
    axis.set_xlim(0, 14.5)
    axis.set_ylim(0, 7.6)
    axis.axis("off")
    axis.text(7.25, 7.18, "图网络输入信息的组成", ha="center", fontsize=18, weight="bold")
    axis.text(
        7.25,
        6.78,
        "节点描述单条航迹是否可靠，候选关系描述两条航迹是否能由同一目标解释",
        ha="center",
        fontsize=11.5,
    )

    axis.text(3.65, 6.25, "单条航迹：15项节点信息", ha="center", fontsize=13, weight="bold", color=BLUE)
    node_groups = (
        ("观测规模与时长\n3项", "观测数、持续时间、扫描圈数", BLUE_FILL, BLUE),
        ("角度范围与运动\n5项", "方位/俯仰范围、合成角速度、两个方向角速度", "#E9EEF8", "#617BA6"),
        ("连续性与检测稳定\n3项", "缺失比例、检测稳定程度、最近三圈命中", GREEN_FILL, GREEN),
        ("不确定度与状态\n4项", "方向和速度不确定度、航迹状态、数据合同", PANEL, GRAY),
    )
    y_positions = (5.0, 3.72, 2.44, 1.16)

    def group_box(
        x: float,
        y: float,
        title: str,
        detail: str,
        face: str,
        edge: str,
    ) -> None:
        width = 6.25
        height = 0.92
        axis.add_patch(
            FancyBboxPatch(
                (x, y),
                width,
                height,
                boxstyle="round,pad=0.02,rounding_size=0.04",
                facecolor=face,
                edgecolor=edge,
                linewidth=1.5,
            )
        )
        axis.plot([x + 1.85, x + 1.85], [y + 0.08, y + height - 0.08], color=edge, linewidth=1.0)
        axis.text(x + 0.93, y + height / 2, title, ha="center", va="center", fontsize=10.0, color=DARK)
        axis.text(x + 4.05, y + height / 2, detail, ha="center", va="center", fontsize=9.5, color=DARK)

    for (title, detail, face, edge), y in zip(node_groups, y_positions):
        group_box(0.52, y, title, detail, face, edge)

    axis.text(10.85, 6.25, "一对航迹：18项候选信息", ha="center", fontsize=13, weight="bold", color=ORANGE)
    edge_groups = (
        ("共面关系\n4项", "残差中位数、高位值、波动、变化率", ORANGE_FILL, ORANGE),
        ("时间证据\n3项", "对齐观测数、时间重叠、最近命中重叠", "#F5EDE4", "#B57A45"),
        ("空间拟合\n5项", "重投影、拟合速度、条件数、交会角、视线残差", GREEN_FILL, GREEN),
        ("运动与不确定度\n6项", "角速度差、归一化残差、合成方向不确定度", PANEL, GRAY),
    )
    for (title, detail, face, edge), y in zip(edge_groups, y_positions):
        group_box(7.73, y, title, detail, face, edge)

    add_box(axis, 5.1, 0.1, 2.15, 0.62, "15项 → 节点编码", facecolor=BLUE_FILL, edgecolor=BLUE, fontsize=10.0)
    add_box(axis, 7.4, 0.1, 2.15, 0.62, "18项 → 候选编码", facecolor=ORANGE_FILL, edgecolor=ORANGE, fontsize=10.0)
    axis.text(
        7.25,
        0.88,
        "所有数值只使用训练数据计算均值和标准差；真实身份不属于任何一项在线输入。",
        ha="center",
        fontsize=10.8,
        color=RED,
    )
    save(fig, "08_feature_groups.png")


def draw_tensor_flow() -> None:
    fig, axis = plt.subplots(figsize=(14.2, 7.5))
    axis.set_xlim(0, 14.2)
    axis.set_ylim(0, 7.5)
    axis.axis("off")
    axis.text(7.1, 7.08, "图神经网络内部张量与计算尺寸", ha="center", fontsize=18, weight="bold")
    axis.text(
        7.1,
        6.68,
        "N_A、N_B为两站航迹数，E为候选关系数；三者均可随场景变化",
        ha="center",
        fontsize=11.5,
    )

    add_box(axis, 0.35, 4.85, 1.65, 0.95, "A站节点\nN_A×15", facecolor=BLUE_FILL, edgecolor=BLUE, fontsize=11)
    add_box(axis, 0.35, 3.3, 1.65, 0.95, "B站节点\nN_B×15", facecolor=ORANGE_FILL, edgecolor=ORANGE, fontsize=11)
    add_box(axis, 0.35, 1.75, 1.65, 0.95, "候选信息\nE×18", facecolor=GREEN_FILL, edgecolor=GREEN, fontsize=11)

    add_box(axis, 2.55, 4.1, 1.9, 1.15, "共享节点编码器\n15 → 64", facecolor=PANEL, edgecolor=GRAY, fontsize=11)
    add_box(axis, 2.55, 1.75, 1.9, 0.95, "候选编码器\n18 → 64", facecolor=PANEL, edgecolor=GRAY, fontsize=11)
    add_arrow(axis, (2.0, 5.32), (2.55, 4.9), color=BLUE)
    add_arrow(axis, (2.0, 3.77), (2.55, 4.43), color=ORANGE)
    add_arrow(axis, (2.0, 2.22), (2.55, 2.22), color=GREEN)

    add_box(
        axis,
        5.05,
        3.1,
        2.2,
        2.25,
        "信息交换第1轮\n\n邻居+候选信息\n平均汇总\n节点更新",
        facecolor=BLUE_FILL,
        edgecolor=BLUE,
        fontsize=11,
    )
    add_box(
        axis,
        7.85,
        3.1,
        2.2,
        2.25,
        "信息交换第2轮\n\n邻居+候选信息\n平均汇总\n节点更新",
        facecolor=BLUE_FILL,
        edgecolor=BLUE,
        fontsize=11,
    )
    add_arrow(axis, (4.45, 4.35), (5.05, 4.35), color=GRAY)
    add_arrow(axis, (4.45, 2.22), (5.5, 3.1), color=GREEN)
    add_arrow(axis, (7.25, 4.22), (7.85, 4.22), color=GRAY)

    add_box(
        axis,
        10.65,
        3.75,
        1.55,
        1.35,
        "端点拼接\nE×256",
        facecolor=GREEN_FILL,
        edgecolor=GREEN,
        fontsize=11,
    )
    add_box(
        axis,
        12.65,
        3.75,
        1.2,
        1.35,
        "分类器\n256→64→1",
        facecolor=GREEN_FILL,
        edgecolor=GREEN,
        fontsize=10.5,
    )
    add_arrow(axis, (10.05, 4.42), (10.65, 4.42), color=GREEN)
    add_arrow(axis, (12.2, 4.42), (12.65, 4.42), color=GREEN)

    add_box(
        axis,
        10.65,
        1.35,
        3.2,
        1.05,
        "Sigmoid后得到E个候选分数\n范围0至1",
        facecolor=ORANGE_FILL,
        edgecolor=ORANGE,
        fontsize=11,
    )
    add_arrow(axis, (13.25, 3.75), (12.25, 2.4), color=ORANGE)
    axis.text(
        7.1,
        0.45,
        "端点拼接包含：A节点64维、B节点64维、两者绝对差64维、候选信息64维。",
        ha="center",
        fontsize=10.8,
        color=DARK,
    )
    save(fig, "09_gnn_tensor_flow.png")


def draw_training_online_isolation() -> None:
    fig, axis = plt.subplots(figsize=(14, 7.6))
    axis.set_xlim(0, 14)
    axis.set_ylim(0, 7.6)
    axis.axis("off")
    axis.text(7, 7.18, "训练数据与在线计算的隔离", ha="center", fontsize=18, weight="bold")
    axis.plot([7, 7], [0.7, 6.65], color=GRAY, linestyle="--", linewidth=2.0)
    axis.text(3.5, 6.68, "离线训练", ha="center", fontsize=14, weight="bold", color=BLUE)
    axis.text(10.5, 6.68, "在线运行", ha="center", fontsize=14, weight="bold", color=GREEN)

    add_box(axis, 0.4, 4.75, 1.7, 1.0, "AirSim航迹\n和干扰数据", facecolor=BLUE_FILL, edgecolor=BLUE)
    add_box(axis, 0.4, 2.7, 1.7, 1.0, "离线真实身份\n只生成标签", facecolor=RED_FILL, edgecolor=RED)
    add_box(axis, 2.55, 4.75, 1.75, 1.0, "15项节点信息\n18项候选信息", facecolor=PANEL, edgecolor=GRAY)
    add_box(axis, 2.55, 2.7, 1.75, 1.0, "正确=1\n错误=0", facecolor=RED_FILL, edgecolor=RED)
    add_box(axis, 4.8, 3.7, 1.55, 1.35, "训练\n验证\n选择参数", facecolor=BLUE_FILL, edgecolor=BLUE, fontsize=11.0)
    add_arrow(axis, (2.1, 5.25), (2.55, 5.25), color=BLUE)
    add_arrow(axis, (2.1, 3.2), (2.55, 3.2), color=RED)
    add_arrow(axis, (4.3, 5.1), (4.8, 4.7), color=BLUE)
    add_arrow(axis, (4.3, 3.2), (4.8, 4.0), color=RED)

    add_box(axis, 5.05, 1.05, 1.95, 1.2, "冻结产物\n权重、标准化\n最低分数", facecolor=ORANGE_FILL, edgecolor=ORANGE, fontsize=10.2)
    add_arrow(axis, (5.65, 3.7), (6.0, 2.25), color=ORANGE)

    add_box(axis, 7.6, 4.75, 1.65, 1.0, "当前和历史航迹\n不含未来观测", facecolor=GREEN_FILL, edgecolor=GREEN, fontsize=10.2)
    add_box(axis, 9.7, 4.75, 1.65, 1.0, "候选图\n不带身份标记", facecolor=GREEN_FILL, edgecolor=GREEN, fontsize=10.2)
    add_box(axis, 11.8, 4.75, 1.65, 1.0, "固定图网络\n只计算分数", facecolor=GREEN_FILL, edgecolor=GREEN, fontsize=10.2)
    add_box(axis, 11.8, 2.8, 1.65, 1.0, "一一选择\n连续确认", facecolor=PANEL, edgecolor=GRAY, fontsize=10.2)
    add_arrow(axis, (9.25, 5.25), (9.7, 5.25), color=GREEN)
    add_arrow(axis, (11.35, 5.25), (11.8, 5.25), color=GREEN)
    add_arrow(axis, (12.62, 4.75), (12.62, 3.8), color=GREEN)
    add_arrow(axis, (7.0, 1.65), (12.0, 4.75), color=ORANGE)

    add_box(
        axis,
        0.85,
        0.75,
        3.95,
        0.78,
        "真实身份的路径到训练标签为止\n在线接口没有身份字段",
        facecolor=RED_FILL,
        edgecolor=RED,
        fontsize=10.2,
    )
    axis.text(
        7,
        0.45,
        "在线只读取冻结产物，不加载训练标签或保留测试答案。",
        ha="center",
        fontsize=10.8,
        color=DARK,
    )
    save(fig, "10_training_online_isolation.png")


def draw_temporal_confirmation() -> None:
    fig, axis = plt.subplots(figsize=(13.5, 6.7))
    axis.set_xlim(0, 13.5)
    axis.set_ylim(0, 6.7)
    axis.axis("off")
    axis.text(6.75, 6.3, "最近三圈至少两次一致的确认过程", ha="center", fontsize=18, weight="bold")
    axis.text(
        6.75,
        5.92,
        "示例关系：A2与B2；绿色表示本圈选中，灰色表示本圈未选中",
        ha="center",
        fontsize=11.5,
    )

    observations = (True, False, True, True, False, False)
    statuses = ("积累", "证据不足", "稳定", "稳定", "稳定", "取消稳定")
    x_values = np.linspace(1.15, 12.35, 6)
    for index, (x, present, status) in enumerate(zip(x_values, observations, statuses), start=1):
        color = GREEN if present else GRAY
        face = GREEN_FILL if present else PANEL
        axis.add_patch(Circle((x, 4.65), 0.34, facecolor=color, edgecolor="white", linewidth=1.2))
        axis.text(x, 4.65, "✓" if present else "×", ha="center", va="center", color="white", fontsize=14, weight="bold")
        axis.text(x, 5.22, f"第{index}圈", ha="center", fontsize=10.5, weight="bold")

        start = max(0, index - 3)
        window = observations[start:index]
        hits = sum(window)
        add_box(
            axis,
            x - 0.72,
            2.5,
            1.44,
            1.25,
            f"最近窗口\n{''.join('✓' if value else '×' for value in window)}\n命中{hits}次",
            facecolor=face,
            edgecolor=color,
            fontsize=9.8,
        )
        axis.text(
            x,
            1.95,
            status,
            ha="center",
            fontsize=10.5,
            color=GREEN if status == "稳定" else RED if status == "取消稳定" else DARK,
            weight="bold" if status in {"稳定", "取消稳定"} else "normal",
        )
    axis.plot([0.75, 12.75], [4.65, 4.65], color=LIGHT_GRAY, linewidth=2.0, zorder=0)
    axis.text(
        6.75,
        0.7,
        "第3圈首次在最近三圈内达到两次一致；第6圈的最近窗口只剩一次一致，因此不再保持稳定关系。",
        ha="center",
        fontsize=10.8,
        color=DARK,
    )
    save(fig, "11_temporal_confirmation.png")


def draw_latency_breakdown() -> None:
    target_counts = np.asarray([20, 40, 60])
    candidate = np.asarray([142.2147, 237.2751, 376.0192])
    end_to_end = np.asarray([154.9476, 248.5309, 394.0999])
    tensor_and_gnn = np.asarray([0.3630 + 1.7597, 0.3943 + 1.7000, 0.4200 + 1.6407])
    hungarian = np.asarray([0.9480, 1.5985, 2.5660])
    confirmation = np.asarray([0.1955, 0.3915, 0.7530])

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.8))
    fig.suptitle("在线计算时间分布", fontsize=18, weight="bold", y=0.98)
    width = 0.35
    x = np.arange(len(target_counts))

    axes[0].bar(x - width / 2, candidate, width, label="候选构建", color=BLUE)
    axes[0].bar(x + width / 2, end_to_end, width, label="端到端", color=ORANGE)
    axes[0].set_xticks(x, [f"{value}目标" for value in target_counts])
    axes[0].set_ylabel("95%分位时间（毫秒）")
    axes[0].set_title("总体时间")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.25)
    for bars in axes[0].containers:
        axes[0].bar_label(bars, fmt="%.1f", padding=3, fontsize=9)

    small_width = 0.24
    axes[1].bar(x - small_width, tensor_and_gnn, small_width, label="张量准备+图网络", color=GREEN)
    axes[1].bar(x, hungarian, small_width, label="匈牙利求解", color=ORANGE)
    axes[1].bar(x + small_width, confirmation, small_width, label="连续确认", color=GRAY)
    axes[1].set_xticks(x, [f"{value}目标" for value in target_counts])
    axes[1].set_ylabel("95%分位时间（毫秒）")
    axes[1].set_title("小耗时环节")
    axes[1].legend(frameon=False, fontsize=9)
    axes[1].grid(axis="y", alpha=0.25)
    for bars in axes[1].containers:
        axes[1].bar_label(bars, fmt="%.2f", padding=3, fontsize=8.5)

    fig.text(
        0.5,
        0.01,
        "候选构建占据主要时间。扩大图网络或替换匈牙利算法不能直接解决当前计算瓶颈。",
        ha="center",
        fontsize=10.8,
        color=DARK,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.94])
    save(fig, "12_latency_breakdown.png")


def main() -> None:
    configure_font()
    draw_epipolar_geometry()
    draw_candidate_pruning()
    draw_feature_groups()
    draw_tensor_flow()
    draw_training_online_isolation()
    draw_temporal_confirmation()
    draw_latency_breakdown()
    for path in sorted(FIGURES.glob("0[6-9]_*.png")) + sorted(FIGURES.glob("1[0-2]_*.png")):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
