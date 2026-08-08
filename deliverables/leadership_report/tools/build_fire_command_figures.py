"""Generate Word-ready Chinese figures for the fire-command section."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon
from PIL import Image, ImageChops, ImageStat


REPORT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPORT_ROOT / "assets"
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc")
BOLD_FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")

FONT = FontProperties(fname=str(FONT_PATH))
BOLD_FONT = FontProperties(fname=str(BOLD_FONT_PATH))

INK = "#18212B"
BLUE = "#1F5F99"
BLUE_DARK = "#174A78"
BLUE_LIGHT = "#EAF3FB"
GREEN = "#2E7552"
GREEN_LIGHT = "#EAF6EF"
ORANGE = "#B45F12"
ORANGE_LIGHT = "#FFF2E4"
RED = "#A43A3A"
RED_LIGHT = "#FCECEC"
PURPLE = "#6550A5"
PURPLE_LIGHT = "#F0ECFA"
GRAY = "#58636F"
GRAY_MID = "#7A8794"
GRAY_LIGHT = "#F2F4F6"
WHITE = "#FFFFFF"


def _canvas() -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(13.333, 7.5), dpi=150)
    fig.patch.set_facecolor(WHITE)
    ax.set_facecolor(WHITE)
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 67.5)
    ax.axis("off")
    return fig, ax


def _text(
    ax: plt.Axes,
    x: float,
    y: float,
    value: str,
    *,
    size: float = 16,
    color: str = INK,
    bold: bool = False,
    ha: str = "center",
    va: str = "center",
    zorder: int = 7,
) -> None:
    ax.text(
        x,
        y,
        value,
        fontsize=size,
        color=color,
        fontproperties=BOLD_FONT if bold else FONT,
        ha=ha,
        va=va,
        linespacing=1.30,
        zorder=zorder,
    )


def _box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    value: str,
    *,
    fill: str = WHITE,
    edge: str = BLUE,
    text_color: str = INK,
    size: float = 14,
    bold: bool = False,
    linewidth: float = 2.2,
    radius: float = 0.9,
    zorder: int = 3,
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle=f"round,pad=0.32,rounding_size={radius}",
            facecolor=fill,
            edgecolor=edge,
            linewidth=linewidth,
            zorder=zorder,
        )
    )
    _text(
        ax,
        x + width / 2,
        y + height / 2,
        value,
        size=size,
        color=text_color,
        bold=bold,
        zorder=zorder + 2,
    )


def _arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = GRAY,
    width: float = 2.2,
    mutation_scale: float = 17,
    connectionstyle: str = "arc3,rad=0",
    zorder: int = 5,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            color=color,
            linewidth=width,
            mutation_scale=mutation_scale,
            shrinkA=2,
            shrinkB=2,
            connectionstyle=connectionstyle,
            zorder=zorder,
        )
    )


def _band(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    *,
    fill: str,
    edge: str,
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.30,rounding_size=1.2",
            facecolor=fill,
            edgecolor=edge,
            linewidth=2.0,
            zorder=1,
        )
    )
    _text(ax, x + 2.0, y + height - 2.0, title, size=15, color=edge, bold=True, ha="left")


def _drone(ax: plt.Axes, x: float, y: float, *, color: str, scale: float = 1.0) -> None:
    ax.plot([x - 3.0 * scale, x + 3.0 * scale], [y, y], color=color, linewidth=2.4, zorder=6)
    ax.plot([x, x], [y - 1.0 * scale, y + 1.1 * scale], color=color, linewidth=2.1, zorder=6)
    ax.add_patch(Circle((x, y), 0.85 * scale, facecolor=WHITE, edgecolor=color, linewidth=2.0, zorder=7))
    for dx in (-3.1, 3.1):
        ax.add_patch(Circle((x + dx * scale, y), 0.85 * scale, facecolor=WHITE, edgecolor=color, linewidth=1.8, zorder=6))
    ax.add_patch(
        Polygon(
            [
                (x - 0.8 * scale, y - 0.8 * scale),
                (x + 0.8 * scale, y - 0.8 * scale),
                (x, y - 2.0 * scale),
            ],
            closed=True,
            facecolor=color,
            edgecolor=color,
            zorder=6,
        )
    )


def _save_and_validate(fig: plt.Figure, filename: str) -> Path:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    path = ASSET_DIR / filename
    fig.savefig(path, dpi=300, facecolor=WHITE, edgecolor=WHITE)
    plt.close(fig)

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width < 2400:
            raise RuntimeError(f"{filename}: width {width} is below 2400 px")
        if ImageStat.Stat(rgb).stddev == [0.0, 0.0, 0.0]:
            raise RuntimeError(f"{filename}: image is blank")
        difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, WHITE))
        bbox = difference.getbbox()
        if bbox is None:
            raise RuntimeError(f"{filename}: image has no visible content")
        margin = 36
        margins = (bbox[0], bbox[1], width - bbox[2], height - bbox[3])
        if min(margins) < margin:
            raise RuntimeError(f"{filename}: insufficient boundary margin {margins}")
        dpi = image.info.get("dpi", (0, 0))
        if min(dpi) < 295:
            raise RuntimeError(f"{filename}: expected 300 dpi metadata, got {dpi}")
    return path


def build_three_level_structure() -> Path:
    fig, ax = _canvas()
    _text(ax, 60, 64.7, "三级火力指挥控制结构", size=27, bold=True)
    _text(
        ax,
        60,
        61.7,
        "一个有效指挥源，逐级接管；任何层级都受版本、有效期和成员确认约束",
        size=14.5,
        color=GRAY,
    )

    _band(ax, 3, 41.8, 114, 17.0, "一级：中心节点统筹", fill=BLUE_LIGHT, edge=BLUE)
    _box(
        ax,
        8,
        46.0,
        24,
        8.5,
        "区域态势与未来窗口\n需求・威胁・资源・通信\n航迹不确定度",
        fill=WHITE,
        edge=BLUE,
        size=13.2,
    )
    _box(
        ax,
        37,
        45.2,
        27,
        10.0,
        "中心总体技术主线\n强化学习区域调度",
        fill=BLUE_DARK,
        edge=BLUE_DARK,
        text_color=WHITE,
        size=17,
        bold=True,
        linewidth=2.8,
    )
    _box(
        ax,
        69,
        47.0,
        19,
        6.4,
        "确定性安全检查\n与动作修正",
        fill=GREEN_LIGHT,
        edge=GREEN,
        size=14.3,
        bold=True,
    )
    _box(
        ax,
        92,
        47.0,
        20,
        6.4,
        "规则/最小费用流回退",
        fill=ORANGE_LIGHT,
        edge=ORANGE,
        size=11.8,
        bold=True,
    )
    _box(
        ax,
        69,
        42.9,
        43,
        2.8,
        "区域方案通过后：目标级规则代价＋匈牙利匹配",
        fill=WHITE,
        edge=GRAY_MID,
        size=12.4,
        linewidth=1.8,
        radius=0.45,
    )
    _arrow(ax, (32.3, 50.3), (36.7, 50.3), color=BLUE)
    _arrow(ax, (64.3, 50.3), (68.7, 50.3), color=GREEN)
    _arrow(ax, (88.3, 50.3), (91.7, 50.3), color=ORANGE)
    _text(ax, 90.0, 56.1, "异常时", size=10.5, color=ORANGE, bold=True)
    _arrow(ax, (78.5, 46.8), (78.5, 45.9), color=GREEN, width=1.8, mutation_scale=13)
    _arrow(ax, (102.0, 46.8), (102.0, 45.9), color=ORANGE, width=1.8, mutation_scale=13)

    _band(ax, 3, 21.7, 114, 17.4, "二级：机动高空侦察无人机按区域接管", fill=GREEN_LIGHT, edge=GREEN)
    region_x = (8.0, 43.0, 78.0)
    region_names = ("区域甲", "区域乙", "区域丙")
    for x, name in zip(region_x, region_names):
        _box(
            ax,
            x,
            25.0,
            29.0,
            8.0,
            f"{name}\n继承最新有效计划・局部重估\n确定性重分配・发布更高版本",
            fill=WHITE,
            edge=GREEN,
            size=12.4,
            bold=True,
        )
        _drone(ax, x + 14.5, 35.1, color=GREEN, scale=0.75)
        _text(ax, x + 14.5, 22.9, "覆盖与通信持续满足才可接管", size=10.8, color=GREEN)

    _arrow(ax, (60, 41.6), (60, 39.3), color=GREEN, width=2.8)
    _text(ax, 62, 40.4, "中心失去有效控制", size=11.5, color=GREEN, bold=True, ha="left")

    _band(ax, 3, 3.6, 114, 15.4, "三级：完全分布式协商保底", fill=PURPLE_LIGHT, edge=PURPLE)
    peer_x = (14, 31, 48, 72, 89, 106)
    for index, x in enumerate(peer_x, start=1):
        _drone(ax, x, 10.2, color=PURPLE, scale=0.62)
        _text(ax, x, 6.2, f"拦截机{index}", size=10.5, color=PURPLE)
    for first, second in zip(peer_x[:-1], peer_x[1:]):
        ax.plot([first + 2.3, second - 2.3], [10.2, 10.2], color=PURPLE, linewidth=1.7, zorder=4)
    ax.plot([peer_x[0], peer_x[2]], [12.1, 14.7], color=PURPLE, linewidth=1.4, zorder=4)
    ax.plot([peer_x[3], peer_x[5]], [14.7, 12.1], color=PURPLE, linewidth=1.4, zorder=4)
    _box(
        ax,
        36.5,
        12.6,
        47,
        4.2,
        "匿名摘要交换 → 分布式拍卖协商 → 必要成员全部确认",
        fill=WHITE,
        edge=PURPLE,
        size=12.1,
        bold=True,
        radius=0.55,
    )
    _arrow(ax, (60, 21.5), (60, 19.2), color=PURPLE, width=2.8)
    _text(ax, 62, 20.3, "二级节点再次失效", size=11.5, color=PURPLE, bold=True, ha="left")

    _box(
        ax,
        28.0,
        0.7,
        64.0,
        2.3,
        "共同安全语义：唯一发布者・任期号・版本号・有效期",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=10.8,
        bold=True,
        linewidth=1.7,
        radius=0.4,
    )
    return _save_and_validate(fig, "fire_command_three_level_structure.png")


def build_control_flow() -> Path:
    fig, ax = _canvas()
    _text(ax, 60, 64.7, "火力指挥控制连续流程", size=27, bold=True)
    _text(
        ax,
        60,
        61.6,
        "强化学习负责区域决策，确定性机制负责安全收口和具体目标分配",
        size=14.5,
        color=GRAY,
    )

    top_y = 43.0
    _box(
        ax,
        3.5,
        top_y,
        19,
        10.5,
        "态势输入\n区域需求・威胁・资源\n通信・航迹不确定度\n未来窗口",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=12.5,
        bold=True,
    )
    _box(
        ax,
        27.0,
        top_y,
        19,
        10.5,
        "强化学习区域调度\n资源配额・跨区转移\n备用比例・侦察优先级\n重规划时机",
        fill=BLUE_DARK,
        edge=BLUE_DARK,
        text_color=WHITE,
        size=12.5,
        bold=True,
        linewidth=2.8,
    )
    _box(
        ax,
        50.5,
        top_y,
        20,
        10.5,
        "确定性安全检查\n与动作修正\n守恒・备用・执行保护\n通信・机动・权属・有效期",
        fill=GREEN_LIGHT,
        edge=GREEN,
        size=12.1,
        bold=True,
    )
    _box(
        ax,
        75.0,
        top_y,
        19,
        10.5,
        "D3初次分配\n规则代价\n＋有界学习修正\n＋匈牙利匹配",
        fill=BLUE_LIGHT,
        edge=BLUE,
        size=12.7,
        bold=True,
    )
    _box(
        ax,
        98.5,
        top_y,
        18,
        10.5,
        "发布新计划\n发布者・任期号\n版本号・有效期",
        fill=WHITE,
        edge=BLUE,
        size=13.0,
        bold=True,
    )
    _arrow(ax, (22.8, 48.25), (26.7, 48.25), color=BLUE)
    _arrow(ax, (46.3, 48.25), (50.2, 48.25), color=GREEN)
    _arrow(ax, (70.8, 48.25), (74.7, 48.25), color=BLUE)
    _arrow(ax, (94.3, 48.25), (98.2, 48.25), color=BLUE)

    _box(
        ax,
        48.0,
        33.3,
        25.0,
        5.2,
        "异常／超时／硬约束违规\n规则回退／最小费用流回退",
        fill=ORANGE_LIGHT,
        edge=ORANGE,
        size=12.4,
        bold=True,
    )
    _arrow(ax, (60.5, 42.7), (60.5, 38.8), color=ORANGE)
    _arrow(
        ax,
        (73.3, 35.9),
        (84.5, 42.7),
        color=ORANGE,
        connectionstyle="arc3,rad=-0.18",
    )

    _box(
        ax,
        99.8,
        56.0,
        15.4,
        3.6,
        "旧版本拒绝",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=12.7,
        bold=True,
    )
    _arrow(ax, (107.5, 53.7), (107.5, 55.8), color=RED)

    bottom_y = 16.0
    _box(
        ax,
        93.0,
        bottom_y,
        23.5,
        10.0,
        "主动降级仲裁\n综合不确定度、计划年龄\n视觉一致性、通信质量\n和持续时间",
        fill=ORANGE_LIGHT,
        edge=ORANGE,
        size=12.4,
        bold=True,
    )
    _box(
        ax,
        64.0,
        bottom_y,
        23.5,
        10.0,
        "二级节点重分配\n机动高空侦察无人机\n继承有效计划、局部重估\n发布更高版本",
        fill=GREEN_LIGHT,
        edge=GREEN,
        size=12.4,
        bold=True,
    )
    _box(
        ax,
        35.0,
        bottom_y,
        23.5,
        10.0,
        "完全分布式协商\n匿名摘要交换\n分布式拍卖协商\n必要成员全部确认",
        fill=PURPLE_LIGHT,
        edge=PURPLE,
        size=12.4,
        bold=True,
    )
    _box(
        ax,
        6.0,
        15.6,
        23.5,
        10.8,
        "安全执行或保持\n确认完整才执行\n分区或确认不足时\n保持旧安全任务\n或停止新任务",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=11.2,
        bold=True,
    )
    _arrow(ax, (107.5, 42.7), (104.8, 26.3), color=ORANGE, connectionstyle="arc3,rad=-0.07")
    _arrow(ax, (92.7, 21.0), (87.8, 21.0), color=GREEN)
    _text(ax, 90.2, 28.4, "中心失去有效控制", size=10.2, color=GREEN, bold=True)
    _arrow(ax, (63.7, 21.0), (58.8, 21.0), color=PURPLE)
    _text(ax, 61.2, 28.4, "二级再次失效", size=10.2, color=PURPLE, bold=True)
    _arrow(ax, (34.7, 21.0), (29.8, 21.0), color=GRAY)

    _arrow(
        ax,
        (99.5, 26.3),
        (84.5, 42.7),
        color=BLUE,
        connectionstyle="arc3,rad=0.23",
    )
    _text(ax, 86.0, 31.8, "中心可用：请求重规划", size=10.9, color=BLUE, bold=True)
    _arrow(
        ax,
        (17.8, 26.3),
        (12.8, 42.7),
        color=GRAY,
        connectionstyle="arc3,rad=-0.28",
    )
    _text(ax, 5.1, 33.3, "结果与状态反馈", size=10.8, color=GRAY, bold=True, ha="left")

    _box(
        ax,
        10.0,
        3.0,
        100.0,
        6.0,
        "全程安全边界：学习不直接发布具体任务编号；全局航迹编号不得本地改写\n过期计划、多头命令和成员确认不足一律拒绝",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=11.8,
        bold=True,
        radius=0.55,
    )
    return _save_and_validate(fig, "fire_command_control_flow.png")


def build_degraded_algorithm_route() -> Path:
    fig, ax = _canvas()
    _text(ax, 60, 64.7, "降级后的算法路线", size=27, bold=True)
    _text(
        ax,
        60,
        61.6,
        "先确认风险和接管条件，再形成新计划；证据或成员不完整时停止发布新任务",
        size=14.5,
        color=GRAY,
    )

    top_y = 43.5
    stages = (
        (3.0, "风险证据汇集\n航迹・关联・计划\n末端视觉・通信", GRAY_LIGHT, GRAY),
        (26.2, "中心限时修正\n补充观测\n请求重规划", BLUE_LIGHT, BLUE),
        (49.4, "二级接管检查\n覆盖・配准・通信\n权属・剩余能力", GREEN_LIGHT, GREEN),
        (72.6, "区域任务重算\n硬约束＋加权代价\n匈牙利匹配", GREEN_LIGHT, GREEN),
        (95.8, "执行确认\n版本・有效期\n视觉身份・成员状态", WHITE, BLUE),
    )
    for x, label, fill, edge in stages:
        _box(
            ax,
            x,
            top_y,
            20.8,
            10.2,
            label,
            fill=fill,
            edge=edge,
            size=12.5,
            bold=True,
        )
    for x1, x2, color in ((23.8, 25.9, BLUE), (47.0, 49.1, GREEN), (70.2, 72.3, GREEN), (93.4, 95.5, BLUE)):
        _arrow(ax, (x1, 48.6), (x2, 48.6), color=color)

    _box(
        ax,
        28.0,
        55.2,
        17.5,
        4.3,
        "中心修正有效\n继续中心控制",
        fill=BLUE_LIGHT,
        edge=BLUE,
        size=10.8,
        bold=True,
    )
    _arrow(ax, (36.6, 53.9), (36.6, 55.0), color=BLUE, width=1.8, mutation_scale=13)

    _box(
        ax,
        72.6,
        31.0,
        20.8,
        7.6,
        "二级计划质量监测\n覆盖・配准・通信・时效",
        fill=ORANGE_LIGHT,
        edge=ORANGE,
        size=12.8,
        bold=True,
    )
    _arrow(ax, (83.0, 43.2), (83.0, 38.9), color=ORANGE)
    _text(ax, 85.0, 41.0, "持续检查", size=10.2, color=ORANGE, bold=True, ha="left")

    bottom_y = 15.3
    lower = (
        (3.0, "安全执行或保持\n确认完整才执行", GRAY_LIGHT, GRAY),
        (26.2, "分布式成员确认\n同一任务・同一版本\n必要成员全部确认", PURPLE_LIGHT, PURPLE),
        (49.4, "获胜者共识\n报价比较・冲突消解\n多轮一致", PURPLE_LIGHT, PURPLE),
        (72.6, "本地任务报价\n可达性・时间・能力\n通信・视觉风险", PURPLE_LIGHT, PURPLE),
        (95.8, "再次降级判断\n同级移交优先\n无合格节点则分布协商", ORANGE_LIGHT, ORANGE),
    )
    for x, label, fill, edge in lower:
        _box(
            ax,
            x,
            bottom_y,
            20.8,
            9.0,
            label,
            fill=fill,
            edge=edge,
            size=12.0,
            bold=True,
        )
    for x1, x2 in ((95.5, 93.4), (72.3, 70.2), (49.1, 47.0), (25.9, 23.8)):
        _arrow(ax, (x1, 19.8), (x2, 19.8), color=PURPLE if x1 < 95 else ORANGE)
    _arrow(ax, (93.5, 34.8), (106.2, 24.6), color=ORANGE, connectionstyle="arc3,rad=-0.12")

    _box(
        ax,
        20.5,
        3.8,
        79.0,
        5.6,
        "共同安全边界\n全局航迹编号不改写・新任期和新版本才可替代旧计划・超时或证据不足时失败关闭",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=11.5,
        bold=True,
        radius=0.55,
    )
    _arrow(ax, (13.4, 15.0), (13.4, 9.7), color=RED)
    return _save_and_validate(fig, "degraded_algorithm_route.png")


def build_secondary_assignment_principle() -> Path:
    fig, ax = _canvas()
    _text(ax, 60, 64.7, "二级节点重新分配原理", size=27, bold=True)
    _text(
        ax,
        60,
        61.6,
        "继承可执行任务，只重算受影响部分；求解结果通过迟滞、版本和租约检查后发布",
        size=14.5,
        color=GRAY,
    )

    y = 39.5
    boxes = (
        (2.5, 14.5, "冻结中心最后\n有效计划", GRAY_LIGHT, GRAY),
        (20.0, 14.5, "任务拆分\n保留集合\n重算集合", BLUE_LIGHT, BLUE),
        (37.5, 14.5, "硬约束筛选\n可用・可达・时效\n身份・资源占用", RED_LIGHT, RED),
        (55.0, 14.5, "形成代价矩阵\n时间・威胁・误差\n视场・通信・换令", ORANGE_LIGHT, ORANGE),
        (72.5, 14.5, "确定性求解\n一对一：匈牙利\n多机：需求槽", GREEN_LIGHT, GREEN),
        (90.0, 14.5, "计划稳定检查\n收益门限\n最小保持时间", PURPLE_LIGHT, PURPLE),
        (107.5, 10.0, "发布\n新任期\n新版本\n有效期", WHITE, BLUE),
    )
    for x, width, label, fill, edge in boxes:
        _box(
            ax,
            x,
            y,
            width,
            11.5,
            label,
            fill=fill,
            edge=edge,
            size=11.7 if width > 10 else 11.2,
            bold=True,
        )
    arrow_pairs = ((17.2, 19.7), (34.7, 37.2), (52.2, 54.7), (69.7, 72.2), (87.2, 89.7), (104.7, 107.2))
    colors = (BLUE, RED, ORANGE, GREEN, PURPLE, BLUE)
    for (start, end), color in zip(arrow_pairs, colors):
        _arrow(ax, (start, 45.25), (end, 45.25), color=color)

    _band(ax, 3.0, 21.0, 114.0, 12.0, "加权代价的组成", fill=GRAY_LIGHT, edge=GRAY)
    cost_items = (
        (7.0, "预计\n拦截时间", BLUE_LIGHT, BLUE),
        (23.0, "航迹\n不确定度", ORANGE_LIGHT, ORANGE),
        (39.0, "目标威胁\n未分配惩罚", RED_LIGHT, RED),
        (55.0, "资源\n可达性", GREEN_LIGHT, GREEN),
        (71.0, "光电视场\n通信质量", PURPLE_LIGHT, PURPLE),
        (87.0, "任务冲突\n重复占用", RED_LIGHT, RED),
        (103.0, "换令代价\n计划稳定", BLUE_LIGHT, BLUE),
    )
    for x, label, fill, edge in cost_items:
        _box(ax, x, 23.1, 12.0, 6.4, label, fill=fill, edge=edge, size=10.6, bold=True, radius=0.55)
    _arrow(ax, (62.2, 39.2), (62.2, 33.3), color=ORANGE)

    _box(
        ax,
        5.0,
        7.3,
        32.0,
        7.4,
        "保留任务\n身份明确・仍可达・稳定执行\n接管期间不换令",
        fill=GREEN_LIGHT,
        edge=GREEN,
        size=11.8,
        bold=True,
    )
    _box(
        ax,
        44.0,
        7.3,
        32.0,
        7.4,
        "重算任务\n目标丢失・资源失效・计划过期\n末端证据持续冲突",
        fill=ORANGE_LIGHT,
        edge=ORANGE,
        size=11.8,
        bold=True,
    )
    _box(
        ax,
        83.0,
        7.3,
        32.0,
        7.4,
        "拒绝条件\n旧版本・旧任期・租约过期\n友方冲突・来源不明",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=11.8,
        bold=True,
    )
    _arrow(ax, (27.2, 39.2), (21.0, 15.0), color=GREEN, connectionstyle="arc3,rad=0.10")
    _arrow(ax, (27.2, 39.2), (60.0, 15.0), color=ORANGE, connectionstyle="arc3,rad=-0.12")
    return _save_and_validate(fig, "secondary_assignment_principle.png")


def build_distributed_consensus_principle() -> Path:
    fig, ax = _canvas()
    _text(ax, 60, 64.7, "完全分布式协商原理", size=27, bold=True)
    _text(
        ax,
        60,
        61.6,
        "各机只交换任务摘要和报价，通过获胜者共识消除重复分配，多机任务必须全员确认",
        size=14.5,
        color=GRAY,
    )

    _band(ax, 3.0, 37.0, 114.0, 20.5, "获胜者共识循环", fill=PURPLE_LIGHT, edge=PURPLE)
    loop_boxes = (
        (6.0, "本地任务摘要\n位置・误差・时刻\n能力・当前任务"),
        (28.5, "计算本机报价\n威胁收益－时间代价\n－通信与视觉风险"),
        (51.0, "广播获胜者视图\n报价・任期・版本\n信息时刻"),
        (73.5, "比较与冲突消解\n高报价优先\n固定规则解决平局"),
        (96.0, "一致性检查\n获胜关系一致？"),
    )
    for index, (x, label) in enumerate(loop_boxes):
        _box(
            ax,
            x,
            42.0,
            18.0,
            10.5,
            label,
            fill=WHITE if index not in (1, 3) else PURPLE_LIGHT,
            edge=PURPLE,
            size=11.4,
            bold=True,
        )
        if index:
            _arrow(ax, (x - 4.2, 47.25), (x - 0.3, 47.25), color=PURPLE)
    _arrow(
        ax,
        (105.0, 41.7),
        (96.3, 35.5),
        color=PURPLE,
        connectionstyle="arc3,rad=-0.08",
    )
    _box(
        ax,
        73.0,
        32.3,
        23.0,
        3.2,
        "未一致：更新视图，进入下一轮",
        fill=WHITE,
        edge=PURPLE,
        text_color=PURPLE,
        size=9.8,
        bold=True,
        linewidth=1.6,
        radius=0.4,
    )
    _arrow(
        ax,
        (72.7, 33.9),
        (60.0, 38.9),
        color=PURPLE,
        connectionstyle="arc3,rad=-0.08",
    )

    _band(ax, 3.0, 14.0, 114.0, 17.0, "高威胁多机任务的成员确认", fill=GREEN_LIGHT, edge=GREEN)
    state_boxes = (
        (6.0, "提出方案\n目标・成员表\n任期与版本"),
        (29.5, "收集确认\n能力仍满足\n证据仍有效"),
        (53.0, "正式提交\n必要成员全部确认\n租约有效"),
        (76.5, "开始执行\n按当前计划行动\n持续上报状态"),
    )
    for index, (x, label) in enumerate(state_boxes):
        _box(
            ax,
            x,
            18.2,
            19.0,
            8.8,
            label,
            fill=WHITE if index in (0, 3) else GREEN_LIGHT,
            edge=GREEN,
            size=11.3,
            bold=True,
        )
        if index:
            _arrow(ax, (x - 4.2, 22.6), (x - 0.3, 22.6), color=GREEN)
    _box(
        ax,
        100.0,
        18.2,
        14.0,
        8.8,
        "异常出口\n重新组织\n或撤销任务",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=11.4,
        bold=True,
    )
    _arrow(ax, (95.8, 22.6), (99.7, 22.6), color=RED)

    _box(
        ax,
        9.0,
        3.7,
        102.0,
        5.8,
        "失败关闭条件\n协商超时・网络分区・消息过期・旧任期・成员缺席：保留已有安全任务，不发布新的重复任务",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=11.5,
        bold=True,
        radius=0.55,
    )
    _arrow(ax, (107.0, 18.0), (107.0, 9.8), color=RED)
    return _save_and_validate(fig, "distributed_consensus_principle.png")


def main() -> None:
    paths = [
        build_three_level_structure(),
        build_control_flow(),
        build_degraded_algorithm_route(),
        build_secondary_assignment_principle(),
        build_distributed_consensus_principle(),
    ]
    for path in paths:
        with Image.open(path) as image:
            print(f"{path.name}: {image.size[0]}x{image.size[1]} px, dpi={image.info.get('dpi')}")


if __name__ == "__main__":
    main()
