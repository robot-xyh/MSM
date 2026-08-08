#!/usr/bin/env python3
"""Generate Word-ready figures for cooperative search and visual registration."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle
from PIL import Image, ImageChops, ImageStat


REPORT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPORT_ROOT / "assets"
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc")
BOLD_FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")

FONT = FontProperties(fname=str(FONT_PATH))
BOLD_FONT = FontProperties(fname=str(BOLD_FONT_PATH))

INK = "#18232D"
BLUE = "#24639B"
BLUE_LIGHT = "#EAF3FA"
GREEN = "#2D7654"
GREEN_LIGHT = "#EAF5EF"
ORANGE = "#B36518"
ORANGE_LIGHT = "#FFF2E3"
RED = "#A43B3B"
RED_LIGHT = "#FBECEC"
GRAY = "#5F6872"
GRAY_LIGHT = "#F2F4F6"
WHITE = "#FFFFFF"


def _canvas(title: str, subtitle: str) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(12, 6.75), dpi=160)
    fig.patch.set_facecolor(WHITE)
    ax.set_facecolor(WHITE)
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 67.5)
    ax.axis("off")
    _text(ax, 60, 63.8, title, size=24, bold=True)
    _text(ax, 60, 60.1, subtitle, size=12.5, color=GRAY)
    return fig, ax


def _text(
    ax: plt.Axes,
    x: float,
    y: float,
    value: str,
    *,
    size: float = 12,
    color: str = INK,
    bold: bool = False,
    ha: str = "center",
    va: str = "center",
    zorder: int = 8,
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
        linespacing=1.28,
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
    size: float = 10.5,
    bold: bool = False,
    text_color: str = INK,
    linewidth: float = 1.8,
    linestyle: str = "-",
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.35,rounding_size=0.8",
            facecolor=fill,
            edgecolor=edge,
            linewidth=linewidth,
            linestyle=linestyle,
            zorder=2,
        )
    )
    _text(
        ax,
        x + width / 2,
        y + height / 2,
        value,
        size=size,
        bold=bold,
        color=text_color,
    )


def _arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = GRAY,
    width: float = 1.8,
    connectionstyle: str = "arc3,rad=0",
    linestyle: str = "-",
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            color=color,
            linewidth=width,
            linestyle=linestyle,
            mutation_scale=14,
            shrinkA=2,
            shrinkB=2,
            connectionstyle=connectionstyle,
            zorder=6,
        )
    )


def _camera(ax: plt.Axes, x: float, y: float, color: str, label: str) -> None:
    ax.add_patch(Rectangle((x - 2.2, y - 1.2), 4.4, 2.4, facecolor=color, edgecolor=color, zorder=5))
    ax.add_patch(Circle((x + 2.5, y), 0.8, facecolor=WHITE, edgecolor=color, linewidth=1.8, zorder=6))
    _text(ax, x, y - 3.0, label, size=9.5, color=color, bold=True)


def _drone(ax: plt.Axes, x: float, y: float, color: str, label: str) -> None:
    ax.plot([x - 2.0, x + 2.0], [y - 1.1, y + 1.1], color=color, linewidth=2.0, zorder=5)
    ax.plot([x - 2.0, x + 2.0], [y + 1.1, y - 1.1], color=color, linewidth=2.0, zorder=5)
    for dx, dy in ((-2, -1.1), (-2, 1.1), (2, -1.1), (2, 1.1)):
        ax.add_patch(Circle((x + dx, y + dy), 0.55, facecolor=WHITE, edgecolor=color, linewidth=1.4, zorder=6))
    ax.add_patch(Circle((x, y), 0.85, facecolor=color, edgecolor=WHITE, linewidth=1.0, zorder=6))
    _text(ax, x, y - 3.4, label, size=9.3, color=color, bold=True)


def _target(ax: plt.Axes, x: float, y: float, color: str, label: str, radius: float = 1.0) -> None:
    ax.add_patch(Circle((x, y), radius, facecolor=color, edgecolor=WHITE, linewidth=1.1, zorder=7))
    _text(ax, x, y + 2.4, label, size=9.0, color=color, bold=True)


def _save_and_validate(fig: plt.Figure, filename: str) -> Path:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    path = ASSET_DIR / filename
    fig.savefig(path, dpi=300, facecolor=WHITE, edgecolor=WHITE)
    plt.close(fig)

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        if rgb.width < 2400:
            raise RuntimeError(f"{filename}: width {rgb.width} is below 2400 px")
        if ImageStat.Stat(rgb).stddev == [0.0, 0.0, 0.0]:
            raise RuntimeError(f"{filename}: image is blank")
        bbox = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).getbbox()
        if bbox is None:
            raise RuntimeError(f"{filename}: image has no visible content")
        margin = 18
        if bbox[0] < margin or bbox[1] < margin or bbox[2] > rgb.width - margin or bbox[3] > rgb.height - margin:
            raise RuntimeError(f"{filename}: visible content touches image boundary: {bbox}")
        dpi = image.info.get("dpi", (0, 0))
        if min(dpi) < 295:
            raise RuntimeError(f"{filename}: expected 300 dpi metadata, got {dpi}")
    return path


def build_infrared_recognition_envelope() -> Path:
    fig, ax = _canvas(
        "红外相机的几何识别范围",
        "640×512，水平视场22°，垂直视场18°，目标横向成像按10像素规划",
    )

    panels = (
        (4.0, 55.0, BLUE, BLUE_LIGHT, "Shahed类目标", "特征宽度 2.5米", "理想距离 411.6米", "画面约 160×130米"),
        (65.0, 116.0, ORANGE, ORANGE_LIGHT, "小型穿越机", "特征宽度 0.25米", "理想距离 41.2米", "画面约 16×13米"),
    )
    for left, right, color, fill, name, width_text, range_text, footprint_text in panels:
        ax.add_patch(
            FancyBboxPatch(
                (left, 17.0),
                right - left,
                39.0,
                boxstyle="round,pad=0.4,rounding_size=1.0",
                facecolor=fill,
                edgecolor=color,
                linewidth=2.0,
                zorder=1,
            )
        )
        cx = left + 8.0
        _camera(ax, cx, 35.5, color, "红外相机")
        target_x = right - 8.0
        ax.add_patch(
            Polygon(
                [(cx + 3.2, 35.5), (target_x - 1.5, 46.0), (target_x - 1.5, 25.0)],
                closed=True,
                facecolor=WHITE,
                edgecolor=color,
                linewidth=1.8,
                alpha=0.8,
                zorder=3,
            )
        )
        _target(ax, target_x, 35.5, color, "目标", radius=1.4 if name.startswith("Shahed") else 0.8)
        _text(ax, (left + right) / 2, 52.3, name, size=16, color=color, bold=True)
        _text(ax, (cx + target_x) / 2, 43.7, "水平视场22°", size=9.8, color=color, bold=True)
        _text(ax, (cx + target_x) / 2, 29.2, range_text, size=11.2, color=color, bold=True)
        _box(ax, left + 7.5, 19.0, right - left - 15.0, 7.0, f"{width_text}\n{footprint_text}", fill=WHITE, edge=color, size=9.6, bold=True)

    _box(
        ax,
        8.0,
        5.5,
        104.0,
        7.5,
        "410米和41米是理想几何值。目标姿态、热对比度、大气、运动模糊、光学质量和识别算法都会改变实际有效距离。",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=10.5,
        bold=True,
    )
    return _save_and_validate(fig, "infrared_recognition_envelope.png")


def build_three_level_partition() -> Path:
    fig, ax = _canvas(
        "拦截搜索区域的三级划分",
        "八个战略区负责资源预置，目标簇拦截区和动态搜索单元负责相机覆盖",
    )

    _text(ax, 20, 55.5, "一级  战略防区", size=15, color=BLUE, bold=True)
    x0, y0, w, h = 4.0, 16.0, 32.0, 34.0
    for row in range(2):
        for col in range(4):
            x = x0 + col * w / 4
            y = y0 + row * h / 2
            active = row == 0 and col == 2
            ax.add_patch(
                Rectangle(
                    (x, y),
                    w / 4,
                    h / 2,
                    facecolor=ORANGE_LIGHT if active else BLUE_LIGHT,
                    edgecolor=ORANGE if active else BLUE,
                    linewidth=2.0 if active else 1.2,
                    zorder=2,
                )
            )
            _text(ax, x + w / 8, y + h / 4, f"区域{row * 4 + col + 1}", size=8.8, color=ORANGE if active else BLUE, bold=active)
    _text(ax, 20, 11.8, "确定各方向资源配额、跨区调动和备用量", size=9.5, color=GRAY)

    _arrow(ax, (37.0, 33.0), (46.0, 33.0), color=ORANGE, width=2.4)
    _text(ax, 41.5, 38.0, "航迹进入\n重点区域", size=9.0, color=ORANGE, bold=True)

    _text(ax, 61, 55.5, "二级  目标簇拦截区", size=15, color=GREEN, bold=True)
    ax.add_patch(Ellipse((61, 33), 30, 20, angle=-12, facecolor=GREEN_LIGHT, edgecolor=GREEN, linewidth=2.2, zorder=2))
    ax.add_patch(Ellipse((61, 33), 21, 12, angle=-12, facecolor=WHITE, edgecolor=GREEN, linewidth=1.2, linestyle="--", zorder=3))
    for i, (tx, ty) in enumerate(((54, 35), (59, 29), (64, 37), (69, 31)), start=1):
        _target(ax, tx, ty, GREEN, f"航迹{i}", radius=0.85)
    _arrow(ax, (50, 44), (70, 22), color=GRAY, width=1.2, linestyle="--")
    _text(ax, 61, 19.0, "由预测位置、协方差、延迟和机动范围形成", size=9.5, color=GRAY)

    _arrow(ax, (77.0, 33.0), (85.0, 33.0), color=GREEN, width=2.4)
    _text(ax, 81.0, 38.0, "按有效识别\n覆盖继续细分", size=9.0, color=GREEN, bold=True)

    _text(ax, 102, 55.5, "三级  动态搜索单元", size=15, color=ORANGE, bold=True)
    cell_x, cell_y = 87.0, 19.0
    for row in range(3):
        for col in range(3):
            color = (BLUE, GREEN, ORANGE)[(row + col) % 3]
            ax.add_patch(Rectangle((cell_x + col * 9.5, cell_y + row * 9.5), 9.5, 9.5, facecolor=WHITE, edgecolor=color, linewidth=1.6, zorder=2))
            _text(ax, cell_x + col * 9.5 + 4.75, cell_y + row * 9.5 + 4.75, f"单元{row * 3 + col + 1}", size=7.8, color=color, bold=True)
    _drone(ax, 91, 14, BLUE, "无人机1")
    _drone(ax, 102, 14, GREEN, "无人机2")
    _drone(ax, 113, 14, ORANGE, "无人机3")

    _box(ax, 20.0, 4.0, 80.0, 6.0, "区域数量不是相机覆盖保证。搜索单元随目标簇移动，并按相机有效距离、转动时间和历史覆盖滚动更新。", fill=GRAY_LIGHT, edge=GRAY, size=10.0, bold=True)
    return _save_and_validate(fig, "search_region_three_level_partition.png")


def build_search_cell_allocation() -> Path:
    fig, ax = _canvas(
        "多机动态搜索单元分配",
        "高概率区域优先观察，未发现结果按预计探测概率更新，不直接判定目标不存在",
    )

    ax.add_patch(Ellipse((58, 35), 92, 34, angle=8, facecolor=GRAY_LIGHT, edgecolor=GRAY, linewidth=1.8, linestyle="--", zorder=1))
    _arrow(ax, (15, 24), (104, 47), color=GRAY, width=2.0)
    _text(ax, 105, 50.0, "目标运动方向", size=10.0, color=GRAY, bold=True)

    cells = (
        (20, 28, "A", 0.12, "已搜索", GRAY),
        (34, 32, "B", 0.25, "无人机1", BLUE),
        (48, 36, "C", 0.31, "无人机2", GREEN),
        (62, 39, "D", 0.18, "无人机3", ORANGE),
        (76, 42, "E", 0.09, "待重访", GRAY),
        (90, 45, "F", 0.05, "低优先", GRAY),
    )
    for x, y, label, probability, owner, color in cells:
        ax.add_patch(
            FancyBboxPatch(
                (x - 6, y - 5),
                12,
                10,
                boxstyle="round,pad=0.2,rounding_size=0.7",
                facecolor=WHITE if color != GRAY else GRAY_LIGHT,
                edgecolor=color,
                linewidth=2.0 if color != GRAY else 1.4,
                zorder=3,
            )
        )
        _text(ax, x, y + 1.5, f"单元{label}", size=9.5, color=color, bold=True)
        _text(ax, x, y - 1.3, f"概率 {probability:.2f}", size=8.3, color=INK)
        _text(ax, x, y - 7.1, owner, size=8.8, color=color, bold=True)

    _drone(ax, 34, 53, BLUE, "无人机1")
    _drone(ax, 53, 55, GREEN, "无人机2")
    _drone(ax, 72, 55, ORANGE, "无人机3")
    _arrow(ax, (34, 49.5), (34, 38), color=BLUE)
    _arrow(ax, (53, 51.5), (49, 42), color=GREEN)
    _arrow(ax, (72, 51.5), (63, 45), color=ORANGE)

    _box(ax, 4.0, 7.0, 30.0, 9.0, "优先级\n目标概率 × 预计探测率 × 紧迫度", fill=BLUE_LIGHT, edge=BLUE, size=9.4, bold=True)
    _box(ax, 45.0, 7.0, 30.0, 9.0, "执行代价\n云台转动 + 飞行调整 + 重复覆盖", fill=ORANGE_LIGHT, edge=ORANGE, size=9.4, bold=True)
    _box(ax, 86.0, 7.0, 30.0, 9.0, "滚动更新\n新航迹、未发现、目标机动和任务变化", fill=GREEN_LIGHT, edge=GREEN, size=9.2, bold=True)
    _arrow(ax, (34.2, 11.5), (44.8, 11.5), color=BLUE)
    _arrow(ax, (75.2, 11.5), (85.8, 11.5), color=ORANGE)
    return _save_and_validate(fig, "cooperative_search_cell_allocation.png")


def build_sparse_registration() -> Path:
    fig, ax = _canvas(
        "有限视场下的多机视觉配准",
        "每台相机只看到少量目标；没有共同目标时保留本地轨迹，并安排后续桥接观察",
    )

    cameras = (
        (17, 48, BLUE, "无人机1", ((28, 44, "目标1"), (33, 38, "目标2"))),
        (60, 49, GREEN, "无人机2", ((58, 35, "目标3"),)),
        (102, 48, ORANGE, "无人机3", ((88, 39, "目标4"), (94, 33, "目标5"))),
    )
    for x, y, color, label, targets in cameras:
        _drone(ax, x, y, color, label)
        if x < 40:
            cone = [(x + 2.5, y - 1.0), (38, 47), (38, 30)]
        elif x < 80:
            cone = [(x, y - 2.5), (50, 29), (70, 29)]
        else:
            cone = [(x - 2.5, y - 1.0), (82, 47), (82, 28)]
        ax.add_patch(Polygon(cone, closed=True, facecolor=color, edgecolor=color, linewidth=1.5, alpha=0.10, zorder=1))
        for tx, ty, target_label in targets:
            _target(ax, tx, ty, color, target_label, radius=0.9)

    _box(ax, 5.0, 19.0, 31.0, 8.0, "本机轨迹 A1、A2\n时间、视线、目标框历史", fill=BLUE_LIGHT, edge=BLUE, size=9.5, bold=True)
    _box(ax, 44.5, 19.0, 31.0, 8.0, "本机轨迹 B1\n当前与两侧均无共同目标", fill=GREEN_LIGHT, edge=GREEN, size=9.3, bold=True)
    _box(ax, 84.0, 19.0, 31.0, 8.0, "本机轨迹 C1、C2\n时间、视线、目标框历史", fill=ORANGE_LIGHT, edge=ORANGE, size=9.5, bold=True)

    _box(ax, 10.0, 6.0, 38.0, 8.5, "已有全局航迹投影作为共同参照\n有重叠时再做视线交会和重投影检查", fill=GRAY_LIGHT, edge=GRAY, size=9.3, bold=True)
    _box(ax, 72.0, 6.0, 38.0, 8.5, "没有足够证据时不强行合并\n安排邻机转向或后续交接视角形成桥接", fill=RED_LIGHT, edge=RED, text_color=RED, size=9.3, bold=True)
    _arrow(ax, (36.2, 23), (48, 14.7), color=BLUE, connectionstyle="arc3,rad=0.12")
    _arrow(ax, (60, 18.8), (60, 14.7), color=GREEN)
    _arrow(ax, (83.8, 23), (72, 14.7), color=ORANGE, connectionstyle="arc3,rad=-0.12")
    _arrow(ax, (48.3, 10.2), (71.7, 10.2), color=GRAY, width=1.6, linestyle="--")
    _text(ax, 60, 4.0, "视觉模块不创建、不改写、不换绑全局航迹编号", size=10.5, color=RED, bold=True)
    return _save_and_validate(fig, "visual_registration_overview.png")


def build_closed_loop() -> Path:
    fig, ax = _canvas(
        "搜索、配准与任务分配闭环",
        "搜索任务只决定相机看哪里，最终资源目标关系仍由带版本的任务计划确认",
    )

    boxes = (
        (3, 38, 18, 10, "全局航迹\n位置、速度、双时间戳\n协方差", BLUE_LIGHT, BLUE),
        (27, 38, 18, 10, "目标簇拦截区\n预测范围和任务组", GREEN_LIGHT, GREEN),
        (51, 38, 18, 10, "动态搜索单元\n相机与时间片分工", ORANGE_LIGHT, ORANGE),
        (75, 38, 18, 10, "本机检测跟踪\n匿名局部轨迹", BLUE_LIGHT, BLUE),
        (99, 38, 18, 10, "跨机配准\n锁定或待确认", GREEN_LIGHT, GREEN),
    )
    for x, y, w, h, value, fill, edge in boxes:
        _box(ax, x, y, w, h, value, fill=fill, edge=edge, size=9.1, bold=True)
    for x in (21.2, 45.2, 69.2, 93.2):
        _arrow(ax, (x, 43), (x + 5.6, 43), color=GRAY, width=2.0)

    _box(ax, 20, 18, 31, 10, "任务保持\n视觉证据与原任务一致\n继续当前有效计划", fill=GREEN_LIGHT, edge=GREEN, size=9.4, bold=True)
    _box(ax, 69, 18, 31, 10, "请求重规划\n证据冲突、目标新增或原计划失效\n回流D1/D2后由D3发布新版本", fill=ORANGE_LIGHT, edge=ORANGE, size=9.0, bold=True)
    _arrow(ax, (108, 37.8), (51, 28.2), color=GREEN, connectionstyle="arc3,rad=-0.18")
    _arrow(ax, (108, 37.8), (84.5, 28.2), color=ORANGE, connectionstyle="arc3,rad=0.10")

    _box(ax, 3, 5.5, 114, 7.0, "未发现或配准模糊：更新搜索优先级并继续观察。任何本地相机都不能绕过计划版本直接改派目标。", fill=RED_LIGHT, edge=RED, text_color=RED, size=10.2, bold=True)
    _arrow(ax, (84.5, 17.8), (60, 12.7), color=ORANGE, connectionstyle="arc3,rad=-0.12")
    _arrow(ax, (35.5, 17.8), (60, 12.7), color=GREEN, connectionstyle="arc3,rad=0.12")
    return _save_and_validate(fig, "search_registration_assignment_closed_loop.png")


def main() -> None:
    builders = (
        build_infrared_recognition_envelope,
        build_three_level_partition,
        build_search_cell_allocation,
        build_sparse_registration,
        build_closed_loop,
    )
    for builder in builders:
        path = builder()
        with Image.open(path) as image:
            print(f"{path.name}: {image.width}x{image.height}, dpi={image.info.get('dpi')}")


if __name__ == "__main__":
    main()
