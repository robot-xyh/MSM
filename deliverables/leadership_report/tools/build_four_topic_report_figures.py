#!/usr/bin/env python3
"""Generate Word-ready figures for the airborne-secondary-node reports."""

from __future__ import annotations

import math

from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon, Rectangle, Wedge

from build_search_visual_assignment_figures import (
    BLUE,
    BLUE_LIGHT,
    GRAY,
    GRAY_LIGHT,
    GREEN,
    GREEN_LIGHT,
    INK,
    ORANGE,
    ORANGE_LIGHT,
    RED,
    RED_LIGHT,
    WHITE,
    _arrow,
    _box,
    _camera,
    _canvas,
    _drone,
    _save_and_validate,
    _target,
    _text,
)


COLORS = (BLUE, GREEN, ORANGE, RED)
FILLS = (BLUE_LIGHT, GREEN_LIGHT, ORANGE_LIGHT, RED_LIGHT)


def _horizontal_flow(
    filename: str,
    title: str,
    subtitle: str,
    steps: list[tuple[str, str]],
    footer: str,
) -> None:
    fig, ax = _canvas(title, subtitle)
    count = len(steps)
    box_width = min(20.0, (108.0 - (count - 1) * 4.0) / count)
    gap = (108.0 - count * box_width) / max(1, count - 1)
    x = 6.0
    for index, (heading, detail) in enumerate(steps):
        color = COLORS[index % len(COLORS)]
        fill = FILLS[index % len(FILLS)]
        _box(ax, x, 29.0, box_width, 18.0, f"{heading}\n{detail}", fill=fill, edge=color, size=9.6, bold=True)
        if index < count - 1:
            _arrow(ax, (x + box_width + 0.4, 38.0), (x + box_width + gap - 0.4, 38.0), color=color, width=2.0)
        x += box_width + gap
    _box(ax, 12.0, 8.0, 96.0, 8.0, footer, fill=GRAY_LIGHT, edge=GRAY, size=9.8, bold=True)
    _save_and_validate(fig, filename)


def _secondary_node(ax, x: float, y: float, color: str, label: str) -> None:
    ax.add_patch(Ellipse((x, y + 0.5), 14, 6.5, facecolor="none", edgecolor=color, linewidth=1.4, linestyle="--", zorder=2))
    _arrow(ax, (x - 5.5, y + 2.4), (x + 5.5, y + 2.4), color=color, width=1.2, connectionstyle="arc3,rad=-0.35")
    _drone(ax, x, y + 1.0, color, "")
    _camera(ax, x, y - 3.2, color, "")
    _text(ax, x, y - 7.2, f"{label}\n光电云台", size=8.2, color=color, bold=True)


def build_eight_region_airborne_secondary_architecture() -> None:
    fig, ax = _canvas("八区域空中二级节点体系", "中心负责跨区调度，盘旋二级节点负责区内搜索、配准、通信和本地分配")
    _box(ax, 43, 51, 34, 7, "中心节点\n粗区域、资源配额、跨区冲突", fill=GRAY_LIGHT, edge=INK, size=10.5, bold=True)
    x0, y0, w, h = 5.0, 14.0, 110.0, 32.0
    for row in range(2):
        for col in range(4):
            index = row * 4 + col + 1
            x = x0 + col * w / 4
            y = y0 + (1 - row) * h / 2
            color = COLORS[col]
            ax.add_patch(Rectangle((x, y), w / 4, h / 2, facecolor=FILLS[col], edgecolor=color, linewidth=1.4))
            _secondary_node(ax, x + w / 8, y + h / 4 + 1.5, color, f"区域{index}节点")
            _arrow(ax, (60, 51), (x + w / 8, y + h / 2), color=GRAY, width=0.9, linestyle="--")
    for col in range(3):
        x_left = x0 + (col + 0.5) * w / 4
        x_right = x0 + (col + 1.5) * w / 4
        _arrow(ax, (x_left + 6, 22), (x_right - 6, 22), color=RED, width=1.1)
        _arrow(ax, (x_left + 6, 38), (x_right - 6, 38), color=RED, width=1.1)
    _box(ax, 12, 5, 96, 6, "相邻二级节点直接交换边界目标和资源摘要；中心不代替区内目标配准与分配。", fill=RED_LIGHT, edge=RED, text_color=RED, size=9.8, bold=True)
    _save_and_validate(fig, "eight_region_airborne_secondary_architecture.png")


def build_secondary_eo_payload_parameters() -> None:
    fig, ax = _canvas("区域二级节点光电载荷", "周扫红外负责快速告警，凝视红外和可见光负责持续复核")
    columns = (
        (4, 34, BLUE, BLUE_LIGHT, "周扫红外", "1280×1024  中波制冷InSb\n300毫米  15微米\n单像元视场 0.05毫弧度\n视场 2.93°×3.67°\n扫描角速度 200°/秒", "10千米：512×640米\n15千米：约768×960米"),
        (43, 34, GREEN, GREEN_LIGHT, "凝视红外", "640×512  中波InSb\n600毫米  15微米\n单像元视场 0.025毫弧度\n视场 0.917°×0.733°\n跟踪角速度不低于60°/秒", "10千米：160×128米\n15千米：约240×192米"),
        (82, 34, ORANGE, ORANGE_LIGHT, "凝视可见光", "2600×2160  CMOS\n600毫米  2.5微米\n单像元视场 0.00417毫弧度\n视场 0.621°×0.516°\n跟踪角速度不低于60°/秒", "10千米：108×90米\n15千米：约163×135米"),
    )
    for x, width, color, fill, title, specs, footprint in columns:
        ax.add_patch(FancyBboxPatch((x, 17), width, 38, boxstyle="round,pad=0.3,rounding_size=0.8", facecolor=fill, edgecolor=color, linewidth=1.8))
        _text(ax, x + width / 2, 51, title, size=14, color=color, bold=True)
        _text(ax, x + width / 2, 36.5, specs, size=9.3, color=INK)
        _box(ax, x + 3, 20, width - 6, 8, footprint, fill=WHITE, edge=color, size=9.1, bold=True)
    _box(ax, 12, 6, 96, 7, "吊舱融合输出频率为100赫兹；该数值用于状态更新和时间同步，不代表三个探测器各自的原始帧率。", fill=GRAY_LIGHT, edge=GRAY, size=9.7, bold=True)
    _save_and_validate(fig, "secondary_eo_payload_parameters.png")


def build_region_four_level_structure() -> None:
    _horizontal_flow(
        "region_four_level_structure.png",
        "区域重划的四个尺度",
        "固定战略区与动态光电搜索区分开管理",
        [("战略区域", "八区固定\n跨区资源配额"), ("光电监视区", "二级节点盘旋\n周扫与凝视覆盖"), ("无人机责任区", "盲区补扫\n目标附近复核"), ("云台观察单元", "世界坐标边界\n方位俯仰时间片")],
        "二级节点扩大了区域感知范围，但窄视场和平台运动决定区内责任区仍需滚动调整。",
    )


def build_secondary_weighted_region_partition() -> None:
    fig, ax = _canvas("二级节点主持的区内责任区划分", "远距周扫由二级节点承担，拦截无人机补充盲区、边界和重点目标周边")
    ax.add_patch(Ellipse((60, 34), 108, 38, angle=4, facecolor=GRAY_LIGHT, edgecolor=GRAY, linewidth=1.8, linestyle="--"))
    areas = (
        ([(9, 24), (40, 21), (44, 48), (14, 49)], BLUE_LIGHT, BLUE, "盲区补扫\n遮挡和低空"),
        ([(40, 21), (78, 22), (75, 49), (44, 48)], GREEN_LIGHT, GREEN, "二级节点主扫\n高概率通道"),
        ([(78, 22), (112, 27), (108, 47), (75, 49)], ORANGE_LIGHT, ORANGE, "边界复核\n跨区交接"),
    )
    for points, fill, edge, label in areas:
        ax.add_patch(Polygon(points, closed=True, facecolor=fill, edgecolor=edge, linewidth=2.0))
        _text(ax, sum(x for x, _ in points) / 4, sum(y for _, y in points) / 4, label, size=10.5, color=edge, bold=True)
    _secondary_node(ax, 60, 53, GREEN, "盘旋二级节点")
    _drone(ax, 24, 54, BLUE, "补扫机1")
    _drone(ax, 96, 54, ORANGE, "边界机2")
    _box(ax, 10, 6, 100, 7, "边界由目标概率、预计像素、重访时间、遮挡、无人机到达能力和通信质量共同决定。", fill=RED_LIGHT, edge=RED, size=9.8, bold=True)
    _save_and_validate(fig, "secondary_weighted_region_partition.png")


def build_moving_node_world_angle_mapping() -> None:
    fig, ax = _canvas("盘旋节点的世界区域与云台角度转换", "搜索边界固定在世界坐标，云台方位和俯仰随平台位置姿态实时变化")
    _secondary_node(ax, 22, 43, BLUE, "时刻一")
    _secondary_node(ax, 48, 50, GREEN, "时刻二")
    ax.add_patch(Rectangle((75, 22), 34, 24, facecolor=ORANGE_LIGHT, edgecolor=ORANGE, linewidth=2.0))
    _text(ax, 92, 42, "世界坐标搜索单元", size=12.5, color=ORANGE, bold=True)
    for row in range(2):
        for col in range(3):
            ax.add_patch(Rectangle((78 + col * 9, 25 + row * 8), 9, 8, facecolor=WHITE, edgecolor=ORANGE, linewidth=1.0))
    _arrow(ax, (27, 42), (78, 38), color=BLUE, width=2.0)
    _arrow(ax, (53, 49), (78, 34), color=GREEN, width=2.0)
    _box(ax, 7, 13, 30, 8, "拍摄时刻平台状态\n位置、速度、姿态", fill=BLUE_LIGHT, edge=BLUE, size=9.7, bold=True)
    _box(ax, 45, 13, 30, 8, "拍摄时刻云台状态\n方位、俯仰、稳定质量", fill=GREEN_LIGHT, edge=GREEN, size=9.7, bold=True)
    _box(ax, 83, 13, 30, 8, "输出角度任务\n方位、俯仰、停留时间", fill=ORANGE_LIGHT, edge=ORANGE, size=9.7, bold=True)
    _arrow(ax, (37.5, 17), (44.5, 17), color=GRAY, width=1.5)
    _arrow(ax, (75.5, 17), (82.5, 17), color=GRAY, width=1.5)
    _save_and_validate(fig, "moving_node_world_angle_mapping.png")


def build_adjacent_secondary_boundary_handoff() -> None:
    fig, ax = _canvas("相邻二级节点的边界目标交接", "共同观察先完成轨迹映射，再转移区域责任和拦截资源")
    ax.add_patch(Rectangle((5, 18), 52, 34, facecolor=BLUE_LIGHT, edgecolor=BLUE, linewidth=2.0))
    ax.add_patch(Rectangle((63, 18), 52, 34, facecolor=GREEN_LIGHT, edgecolor=GREEN, linewidth=2.0))
    ax.add_patch(Rectangle((52, 18), 16, 34, facecolor=ORANGE_LIGHT, edgecolor=ORANGE, linewidth=1.5, alpha=0.8))
    _text(ax, 26, 49, "区域A", size=14, color=BLUE, bold=True)
    _text(ax, 94, 49, "区域B", size=14, color=GREEN, bold=True)
    _text(ax, 60, 21, "交接带", size=10, color=ORANGE, bold=True)
    _secondary_node(ax, 24, 39, BLUE, "二级节点A")
    _secondary_node(ax, 96, 39, GREEN, "二级节点B")
    _target(ax, 59, 35, RED, "边界目标", radius=1.4)
    _arrow(ax, (29, 37), (56, 35), color=BLUE, width=2.0)
    _arrow(ax, (91, 37), (62, 35), color=GREEN, width=2.0)
    _box(ax, 16, 7, 88, 8, "共同观察 → 区域临时编号映射 → 唯一负责节点确认 → 任务计划升版 → 交接完成", fill=GRAY_LIGHT, edge=GRAY, size=9.8, bold=True)
    _save_and_validate(fig, "adjacent_secondary_boundary_handoff.png")


def build_secondary_region_repartition_flow() -> None:
    _horizontal_flow(
        "secondary_region_repartition_flow.png",
        "二级节点主持的滚动重划",
        "平台盘旋、目标移动和搜索证据共同驱动局部边界更新",
        [("检查变化", "盘旋位置\n目标跨区\n负担失衡"), ("保护任务", "稳定凝视\n安全拦截\n边界交接"), ("重算边界", "主扫区域\n补扫区域\n高度层"), ("发布新计划", "区域任期\n严格升版\n短有效期"), ("继承证据", "已扫单元\n未发现质量\n区域目标表")],
        "普通变化满足收益门限和最小保持时间；节点故障、计划到期和任务不可达直接进入安全重划。",
    )


def build_secondary_region_repartition_example() -> None:
    fig, ax = _canvas("二级节点区内重划算例", "周扫发现来袭通道后，把无人机从平均布置调整到盲区、边界和目标前沿")
    ax.add_patch(Ellipse((60, 34), 108, 36, angle=5, facecolor=GRAY_LIGHT, edgecolor=GRAY, linewidth=1.7, linestyle="--"))
    _secondary_node(ax, 60, 53, GREEN, "区域二级节点")
    zones = ((12, 22, 29, 25, BLUE, BLUE_LIGHT, "低空盲区"), (41, 22, 39, 28, GREEN, GREEN_LIGHT, "主要来袭通道"), (80, 25, 29, 22, ORANGE, ORANGE_LIGHT, "边界交接区"))
    for x, y, w, h, color, fill, label in zones:
        ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=color, linewidth=2.0))
        _text(ax, x + w / 2, y + h / 2, label, size=10.5, color=color, bold=True)
    _drone(ax, 25, 16, BLUE, "补扫机")
    _drone(ax, 60, 16, GREEN, "复核机")
    _drone(ax, 95, 16, ORANGE, "边界机")
    for x, y in ((52, 38), (62, 35), (71, 41)):
        _target(ax, x, y, RED, "候选", radius=0.8)
    _box(ax, 16, 5, 88, 7, "二级节点继续周扫；无人机只进入需要补视角、补像素或跨区确认的局部区域。", fill=RED_LIGHT, edge=RED, size=9.8, bold=True)
    _save_and_validate(fig, "secondary_region_repartition_example.png")


def build_secondary_interceptor_search_architecture() -> None:
    fig, ax = _canvas("二级节点与拦截无人机协同搜索", "区域节点负责主搜索和通信汇聚，无人机负责盲区补扫、近距复核与连续跟踪")
    _secondary_node(ax, 60, 51, GREEN, "盘旋二级节点")
    _target(ax, 60, 37, RED, "区域候选", radius=1.4)
    _drone(ax, 18, 23, BLUE, "补扫机1")
    _drone(ax, 46, 18, GREEN, "复核机2")
    _drone(ax, 76, 18, ORANGE, "跟踪机3")
    _drone(ax, 104, 23, RED, "边界机4")
    _arrow(ax, (58, 46), (60, 39), color=GREEN, width=2.2)
    for x, y, color in ((18, 23, BLUE), (46, 18, GREEN), (76, 18, ORANGE), (104, 23, RED)):
        _arrow(ax, (57, 48), (x, y + 4), color=color, width=1.2, linestyle="--")
    _box(ax, 8, 7, 104, 7, "常态交换搜索单元、方位线索、轨迹摘要和任务版本；关键图像或短视频按需传输。", fill=GRAY_LIGHT, edge=GRAY, size=9.8, bold=True)
    _save_and_validate(fig, "secondary_interceptor_search_architecture.png")


def build_secondary_gimbal_scan_modes() -> None:
    fig, ax = _canvas("云台三种搜索工作状态", "2秒快速周扫用于告警，标准搜索积累连续证据，凝视通道完成复核")
    modes = (
        (5, BLUE, BLUE_LIGHT, "快速告警周扫", "约2秒一圈\n200°/秒\n单次穿越约14.7毫秒", "输出候选方位\n不直接形成身份"),
        (43, GREEN, GREEN_LIGHT, "标准区域搜索", "建议4至6秒一圈\n降低扫描速度\n多圈积累与优先重访", "形成连续周扫轨迹\n周期待设备实测"),
        (81, ORANGE, ORANGE_LIGHT, "凝视确认", "快速转向候选\n凝视红外持续跟踪\n可见光条件允许时识别", "确认后返回周扫\n重点目标可持续保持"),
    )
    for x, color, fill, title, detail, output in modes:
        ax.add_patch(FancyBboxPatch((x, 17), 34, 38, boxstyle="round,pad=0.35,rounding_size=1", facecolor=fill, edgecolor=color, linewidth=2.0))
        _text(ax, x + 17, 50, title, size=14, color=color, bold=True)
        if title.startswith("快速"):
            ax.add_patch(Wedge((x + 17, 34), 10, 0, 330, width=2.2, facecolor=color, edgecolor=color, alpha=0.6))
        elif title.startswith("标准"):
            for radius in (4, 7, 10):
                ax.add_patch(Circle((x + 17, 34), radius, facecolor="none", edgecolor=color, linewidth=1.2, linestyle="--"))
        else:
            _camera(ax, x + 10, 34, color, "凝视通道")
            _target(ax, x + 25, 34, RED, "目标", radius=1.1)
            _arrow(ax, (x + 13, 34), (x + 23, 34), color=color, width=2.0)
        _text(ax, x + 17, 23, detail, size=9.2, color=INK)
        _box(ax, x + 4, 7, 26, 7, output, fill=WHITE, edge=color, size=8.8, bold=True)
    _save_and_validate(fig, "secondary_gimbal_scan_modes.png")


def build_secondary_search_priority_cycle() -> None:
    _horizontal_flow(
        "secondary_search_priority_cycle.png",
        "基础周扫与重点重访循环",
        "云台调度在区域覆盖和目标连续性之间滚动切换",
        [("基础周扫", "方位扇区\n高度层\n未覆盖单元"), ("线索入队", "威胁\n信息年龄\n角度误差"), ("快速转向", "平台姿态补偿\n云台稳定检查"), ("凝视复核", "红外连续性\n可见光辅助"), ("恢复周扫", "更新概率\n安排重访\n保留轨迹")],
        "高威胁、长时间未观察、预计像素充足且转向代价较低的任务优先；低质量未发现不清空概率。",
    )


def build_secondary_search_cell_allocation() -> None:
    fig, ax = _canvas("二级节点主持的搜索单元分配", "二级节点保留主周扫，无人机只承担不能由当前周扫可靠完成的局部单元")
    ax.add_patch(Ellipse((60, 35), 104, 35, angle=6, facecolor=GRAY_LIGHT, edgecolor=GRAY, linewidth=1.7, linestyle="--"))
    cells = ((18, 30, BLUE, "盲区A\n补扫机1"), (36, 34, GREEN, "主扫B\n二级节点"), (54, 38, GREEN, "主扫C\n二级节点"), (72, 40, ORANGE, "复核D\n无人机2"), (90, 43, RED, "边界E\n邻区协同"))
    for x, y, color, label in cells:
        _box(ax, x - 7, y - 5, 14, 10, label, fill=WHITE, edge=color, size=8.8, bold=True)
    _secondary_node(ax, 58, 54, GREEN, "区域二级节点")
    _drone(ax, 18, 17, BLUE, "无人机1")
    _drone(ax, 73, 17, ORANGE, "无人机2")
    _drone(ax, 104, 20, RED, "邻区节点")
    _arrow(ax, (18, 21), (18, 25), color=BLUE, width=1.7)
    _arrow(ax, (73, 21), (72, 35), color=ORANGE, width=1.7)
    _arrow(ax, (102, 24), (94, 39), color=RED, width=1.7)
    _box(ax, 12, 6, 96, 7, "分配收益 = 目标概率 × 预计探测质量 × 紧迫度 − 转向代价 − 平台机动 − 重复覆盖 − 通信风险", fill=GRAY_LIGHT, edge=GRAY, size=9.4, bold=True)
    _save_and_validate(fig, "secondary_search_cell_allocation.png")


def build_secondary_interceptor_cue_handoff() -> None:
    fig, ax = _canvas("二级节点向拦截无人机交接搜索线索", "线索包含观察时刻、空间视线和误差窗口，不只发送一个方位角")
    _secondary_node(ax, 22, 43, GREEN, "二级节点")
    _box(ax, 41, 38, 35, 16, "区域搜索线索\n传感器通道与拍摄时刻\n平台和云台姿态\n视线、误差范围、质量\n建议观察窗口与有效期", fill=GREEN_LIGHT, edge=GREEN, size=9.2, bold=True)
    _drone(ax, 99, 43, BLUE, "拦截无人机")
    _arrow(ax, (29, 43), (40, 46), color=GREEN, width=2.0)
    _arrow(ax, (76.5, 46), (94, 43), color=BLUE, width=2.0)
    _target(ax, 99, 27, RED, "局部候选", radius=1.3)
    _arrow(ax, (99, 39), (99, 30), color=BLUE, width=2.0)
    _box(ax, 13, 8, 94, 9, "无人机回传：本机轨迹、检测框历史、像面速度、拍摄时刻和观察质量。\n二级节点继续周扫，不因单个候选长期放弃剩余区域。", fill=GRAY_LIGHT, edge=GRAY, size=9.4, bold=True)
    _save_and_validate(fig, "secondary_interceptor_cue_handoff.png")


def build_search_probability_update() -> None:
    fig, ax = _canvas("未发现结果的概率更新", "只有成像、稳定、遮挡和观察次数满足要求，未发现才明显降低目标概率")
    scenarios = ((7, BLUE, BLUE_LIGHT, "观察前", 0.60, "初始区域概率"), (43, GREEN, GREEN_LIGHT, "高质量未发现", 0.18, "像素足、稳定、多圈观察"), (79, ORANGE, ORANGE_LIGHT, "快速扫过未发现", 0.50, "仅一次短时穿越"))
    for x, color, fill, title, value, note in scenarios:
        ax.add_patch(FancyBboxPatch((x, 17), 30, 36, boxstyle="round,pad=0.3,rounding_size=0.8", facecolor=fill, edgecolor=color, linewidth=1.9))
        _text(ax, x + 15, 49, title, size=13, color=color, bold=True)
        ax.add_patch(Rectangle((x + 9, 24), 12, 18, facecolor=WHITE, edgecolor=color, linewidth=1.4))
        ax.add_patch(Rectangle((x + 9, 24), 12, 18 * value, facecolor=color, edgecolor=color, alpha=0.75))
        _text(ax, x + 15, 35, f"{value:.2f}", size=16, color=INK, bold=True)
        _text(ax, x + 15, 20, note, size=8.9, color=color, bold=True)
    _arrow(ax, (37.5, 35), (42.5, 35), color=GREEN, width=2.2)
    _arrow(ax, (73.5, 35), (78.5, 35), color=ORANGE, width=2.2)
    _box(ax, 15, 6, 90, 7, "2秒快速周扫适合发现候选，不适合作为排除目标的唯一依据。", fill=RED_LIGHT, edge=RED, text_color=RED, size=10, bold=True)
    _save_and_validate(fig, "search_probability_update.png")


def build_secondary_search_failover() -> None:
    _horizontal_flow(
        "secondary_search_failover.png",
        "二级节点失效后的搜索接替",
        "先保留有效观察任务，再把未覆盖区域交给无人机临时协调或分布式认领",
        [("二级协调", "周扫计划\n线索队列\n区域目标表"), ("节点失效", "心跳超时\n光电不可用\n通信中断"), ("保持任务", "连续本机轨迹\n已确认凝视\n安全拦截"), ("临时协调", "连接稳定无人机\n继承搜索证据"), ("分布认领", "未覆盖单元\n报价和版本\n冲突消解")],
        "无法形成唯一协调者、消息过期或网络分区时，不发布新的跨分区搜索任务。",
    )


def build_secondary_anchor_registration_overview() -> None:
    fig, ax = _canvas("移动二级节点作为区域配准基准", "二级节点连接多架无人机的局部目标子集，形成共同时间与几何参照")
    _secondary_node(ax, 60, 53, GREEN, "区域二级节点")
    targets = {1: (34, 38), 2: (47, 33), 3: (60, 39), 4: (73, 33), 5: (86, 38)}
    for tid, (x, y) in targets.items():
        _target(ax, x, y, RED, f"目标{tid}", radius=0.9)
        _arrow(ax, (60, 48), (x, y + 2), color=GREEN, width=0.9, linestyle="--")
    cameras = ((18, 18, BLUE, "无人机1：1、2、3、4", (1, 2, 3, 4)), (60, 17, GREEN, "无人机2：2、3、4、5", (2, 3, 4, 5)), (102, 18, ORANGE, "无人机3：1、2、4、5", (1, 2, 4, 5)))
    for x, y, color, label, visible in cameras:
        _drone(ax, x, y, color, label)
        for tid in visible:
            tx, ty = targets[tid]
            ax.plot([x, tx], [y + 2, ty - 1], color=color, linewidth=0.7, alpha=0.28)
    _box(ax, 14, 5, 92, 6, "二级节点提供区域轨迹和视线基准；各无人机仍保留本机轨迹编号，不按画面顺序直接合并。", fill=GRAY_LIGHT, edge=GRAY, size=9.6, bold=True)
    _save_and_validate(fig, "secondary_anchor_registration_overview.png")


def build_moving_platform_geometry_compensation() -> None:
    _horizontal_flow(
        "moving_platform_geometry_compensation.png",
        "盘旋平台观测的拍摄时刻补偿",
        "配准使用拍摄时刻的平台和云台状态，不能用消息到达时的最新姿态代替",
        [("视觉量测", "检测框\n传感器通道\n量测时刻"), ("平台状态", "拍摄时刻位置\n速度和机体姿态"), ("云台状态", "方位俯仰\n稳定质量\n标定版本"), ("空间视线", "内参去畸变\n外参变换\n误差传播"), ("统一时刻", "运动预测\n视线交会\n重投影检查")],
        "每条消息同时保存量测时间和到达时间；导航、姿态、云台、标定和距离误差共同进入配准门限。",
    )


def build_visual_registration_evidence_chain_secondary() -> None:
    _horizontal_flow(
        "visual_registration_evidence_chain_secondary.png",
        "区域目标配准的证据顺序",
        "周扫线索、凝视确认和机载复核分层进入身份判断",
        [("时间与来源", "量测/到达时刻\n节点和通道"), ("移动几何", "平台/云台姿态\n空间视线"), ("运动连续性", "方向和速度\n目标框历史"), ("多视角复核", "二级节点\n拦截无人机\n相邻节点"), ("外观辅助", "凝视可见光\n红外特征\n类别提示")],
        "时间、几何、同相机冲突或信息过期直接拒绝；低像素外观和学习评分不能绕过硬条件。",
    )


def build_secondary_overlap_reprojection() -> None:
    fig, ax = _canvas("二级节点与无人机的共同视场复核", "两条拍摄时刻视线估计空间位置，再投回两幅图像检查一致性")
    _secondary_node(ax, 22, 21, GREEN, "二级节点")
    _drone(ax, 98, 20, BLUE, "拦截无人机")
    _target(ax, 60, 43, RED, "空间候选", radius=1.5)
    ax.plot([25, 60], [23, 43], color=GREEN, linewidth=2.3)
    ax.plot([95, 60], [22, 43], color=BLUE, linewidth=2.3)
    ax.add_patch(Ellipse((60, 43), 12, 7, facecolor=RED_LIGHT, edgecolor=RED, linewidth=1.5, linestyle="--"))
    _box(ax, 8, 48, 31, 8, "二级节点轨迹\n周扫或凝视视线 + 误差", fill=GREEN_LIGHT, edge=GREEN, size=9.4, bold=True)
    _box(ax, 81, 48, 31, 8, "无人机本机轨迹\n检测框历史 + 相机姿态", fill=BLUE_LIGHT, edge=BLUE, size=9.4, bold=True)
    _box(ax, 36, 7, 48, 8, "估计位置重新投影到两幅图像\n连续多帧检查重投影误差", fill=ORANGE_LIGHT, edge=ORANGE, size=9.8, bold=True)
    _arrow(ax, (60, 39), (60, 15.5), color=ORANGE, width=2.0)
    _save_and_validate(fig, "secondary_overlap_reprojection.png")


def build_secondary_nonoverlap_bridge() -> None:
    fig, ax = _canvas("非共同视场的二级节点桥接", "无人机视场不重叠时，区域节点用连续周扫轨迹连接离开与进入事件")
    _drone(ax, 16, 22, BLUE, "无人机A")
    _drone(ax, 104, 22, ORANGE, "无人机B")
    _secondary_node(ax, 60, 51, GREEN, "二级节点")
    _target(ax, 28, 39, RED, "离开A", radius=1.1)
    _target(ax, 92, 39, RED, "进入B", radius=1.1)
    _arrow(ax, (31, 39), (89, 39), color=GRAY, width=2.0, linestyle="--")
    _text(ax, 60, 43, "运动可达范围 + 交接时间窗", size=10.5, color=GRAY, bold=True)
    _arrow(ax, (58, 47), (30, 40), color=GREEN, width=1.7)
    _arrow(ax, (62, 47), (90, 40), color=GREEN, width=1.7)
    _box(ax, 18, 7, 84, 8, "二级节点轨迹连续时形成A-节点-B桥接；周扫短时丢失或候选不唯一时保持待复核。", fill=RED_LIGHT, edge=RED, size=9.7, bold=True)
    _save_and_validate(fig, "secondary_nonoverlap_bridge.png")


def build_visual_registration_small_target_matching() -> None:
    fig, ax = _canvas("少量目标的一对一匹配", "硬门限先删除不可能关系，再在剩余候选中求取总代价较小的组合")
    left_y = (46, 35, 24)
    right_y = (48, 36, 22)
    for i, y in enumerate(left_y, 1):
        _box(ax, 8, y - 3, 22, 6, f"二级节点轨迹 S{i}", fill=GREEN_LIGHT, edge=GREEN, size=9.1, bold=True)
    for i, y in enumerate(right_y, 1):
        _box(ax, 90, y - 3, 22, 6, f"无人机轨迹 U{i}", fill=BLUE_LIGHT, edge=BLUE, size=9.1, bold=True)
    edges = ((0, 0, 0.18, True), (0, 1, 0.80, False), (1, 0, 0.65, False), (1, 1, 0.22, True), (1, 2, 0.71, False), (2, 1, 0.76, False), (2, 2, 0.15, True))
    for li, ri, cost, selected in edges:
        color = ORANGE if selected else GRAY
        ax.plot([30, 90], [left_y[li], right_y[ri]], color=color, linewidth=3.0 if selected else 1.0, alpha=0.9 if selected else 0.45)
        _text(ax, 60, (left_y[li] + right_y[ri]) / 2, f"{cost:.2f}", size=8.0, color=color, bold=selected)
    _box(ax, 35, 7, 50, 7, "选中关系：S1-U1、S2-U2、S3-U3\n每条本机轨迹最多支持一个区域目标", fill=ORANGE_LIGHT, edge=ORANGE, size=9.5, bold=True)
    _save_and_validate(fig, "visual_registration_small_target_matching.png")


def build_visual_registration_dense_track_graph() -> None:
    fig, ax = _canvas("密集目标的稀疏轨迹图", "节点包括二级节点和无人机短轨迹，连接表示可能属于同一目标")
    columns = ((18, GREEN, GREEN_LIGHT, "二级节点"), (52, BLUE, BLUE_LIGHT, "无人机A"), (86, ORANGE, ORANGE_LIGHT, "无人机B"), (112, RED, RED_LIGHT, "邻区节点"))
    positions: dict[tuple[int, int], tuple[float, float]] = {}
    for ci, (x, color, fill, label) in enumerate(columns):
        _text(ax, x, 53, label, size=11.5, color=color, bold=True)
        for ti, y in enumerate((43, 33, 23)):
            positions[(ci, ti)] = (x, y)
            ax.add_patch(Circle((x, y), 2.7, facecolor=fill, edgecolor=color, linewidth=1.7, zorder=5))
            _text(ax, x, y, f"{ci + 1}-{ti + 1}", size=7.8, color=color, bold=True)
    selected = (((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (3, 0)), ((0, 1), (1, 1)), ((1, 1), (2, 2)), ((0, 2), (2, 1)))
    candidates = (((0, 0), (1, 1)), ((1, 0), (2, 1)), ((1, 2), (3, 2)), ((0, 2), (2, 2)))
    for a, b in candidates:
        ax.plot([positions[a][0], positions[b][0]], [positions[a][1], positions[b][1]], color=GRAY, linewidth=1.0, linestyle="--", alpha=0.55)
    for a, b in selected:
        ax.plot([positions[a][0], positions[b][0]], [positions[a][1], positions[b][1]], color=RED, linewidth=2.4, alpha=0.9)
    _box(ax, 12, 7, 96, 8, "时间和几何先删边 → 图模型辅助连接评分 → 一对一和跨视角闭环检查 → 连续多帧确认", fill=GRAY_LIGHT, edge=GRAY, size=9.6, bold=True)
    _save_and_validate(fig, "visual_registration_dense_track_graph.png")


def build_regional_target_boundary_lifecycle() -> None:
    _horizontal_flow(
        "regional_target_boundary_lifecycle.png",
        "区域临时目标编号与跨区映射",
        "编号来自多帧多视角证据，跨区时先建立映射再转移责任",
        [("区域候选", "周扫线索\n无人机本机轨迹"), ("区内确认", "凝视复核\n区域临时编号"), ("进入交接带", "邻区共同观察\n映射候选"), ("责任移交", "唯一负责节点\n计划升版"), ("失效或继承", "短时丢失预测\n节点故障继承")],
        "相同编号字符、位置接近或目标数量先验都不能替代支持轨迹、任期、版本和有效期检查。",
    )


def build_secondary_local_assignment_architecture() -> None:
    fig, ax = _canvas("区域二级节点常态本地分配", "中心配置区域资源，二级节点依据区域目标表发布短时区内任务")
    _box(ax, 8, 45, 25, 9, "中心节点\n区域配额与跨区调动", fill=GRAY_LIGHT, edge=INK, size=10, bold=True)
    _secondary_node(ax, 60, 47, GREEN, "区域二级节点")
    _box(ax, 87, 45, 25, 9, "相邻二级节点\n边界映射与资源支援", fill=ORANGE_LIGHT, edge=ORANGE, size=9.8, bold=True)
    _arrow(ax, (33.5, 49), (51, 49), color=GRAY, width=2.0)
    _arrow(ax, (69, 49), (86.5, 49), color=ORANGE, width=2.0)
    tasks = ((9, BLUE, BLUE_LIGHT, "搜索任务"), (31, GREEN, GREEN_LIGHT, "凝视确认"), (53, ORANGE, ORANGE_LIGHT, "跟踪保持"), (75, RED, RED_LIGHT, "拦截任务"), (97, GRAY, GRAY_LIGHT, "备用任务"))
    for x, color, fill, label in tasks:
        _box(ax, x, 23, 15, 8, label, fill=fill, edge=color, size=9.0, bold=True)
        _arrow(ax, (60, 42), (x + 7.5, 31.5), color=color, width=1.2)
    _box(ax, 12, 7, 96, 8, "二级节点计划包含发布者、区域、任期、版本、有效期和执行回执；中心不直接替代区内目标关系。", fill=GRAY_LIGHT, edge=GRAY, size=9.7, bold=True)
    _save_and_validate(fig, "secondary_local_assignment_architecture.png")


def build_secondary_task_maturity_gate() -> None:
    fig, ax = _canvas("光电证据决定可发布的任务类型", "低成熟度线索先安排搜索和确认，稳定区域目标才进入拦截分配")
    stages = ((5, BLUE, BLUE_LIGHT, "快速周扫线索", "候选方位\n短时证据", "只能搜索"), (34, GREEN, GREEN_LIGHT, "连续周扫轨迹", "多圈积累\n运动趋势", "搜索或凝视"), (63, ORANGE, ORANGE_LIGHT, "凝视确认", "连续红外\n可见光辅助", "跟踪或复核"), (92, RED, RED_LIGHT, "区域目标确认", "多帧多视角\n版本和有效期", "允许进入分配"))
    for x, color, fill, title, evidence, action in stages:
        _box(ax, x, 30, 23, 18, f"{title}\n{evidence}", fill=fill, edge=color, size=9.5, bold=True)
        _box(ax, x + 2, 17, 19, 7, action, fill=WHITE, edge=color, size=9.2, bold=True)
    for x in (28.5, 57.5, 86.5):
        _arrow(ax, (x, 39), (x + 5, 39), color=GRAY, width=2.0)
    _box(ax, 13, 6, 94, 7, "周扫短时线索、高威胁或距离较近都不能绕过身份、时效、可达、视觉和安全门限。", fill=RED_LIGHT, edge=RED, text_color=RED, size=9.6, bold=True)
    _save_and_validate(fig, "secondary_task_maturity_gate.png")


def build_local_assignment_cost_components_secondary() -> None:
    fig, ax = _canvas("二级节点本地分配的综合代价", "距离最近不一定最适合，目标证据和区域通信条件共同影响任务")
    _box(ax, 44, 28, 32, 12, "无人机 i → 区域目标 j\n综合代价 Cij", fill=GRAY_LIGHT, edge=INK, size=12.5, bold=True)
    components = ((8, 47, "到达时间\n航向和允许空域", BLUE, BLUE_LIGHT), (44, 49, "机动能力\n速度和转弯余量", GREEN, GREEN_LIGHT), (80, 47, "目标证据\n身份质量和时效", ORANGE, ORANGE_LIGHT), (8, 11, "视觉连续性\n保持或重新获得", GREEN, GREEN_LIGHT), (44, 8, "通信风险\n二级链路和边界", BLUE, BLUE_LIGHT), (80, 11, "换令与威胁\n稳定性和优先级", RED, RED_LIGHT))
    for x, y, label, color, fill in components:
        _box(ax, x, y, 32, 9, label, fill=fill, edge=color, size=9.3, bold=True)
        _arrow(ax, (x + 16, y if y > 40 else y + 9), (60, 40 if y > 40 else 28), color=color, width=1.4)
    _save_and_validate(fig, "local_assignment_cost_components_secondary.png")


def build_local_assignment_hungarian() -> None:
    fig, ax = _canvas("匈牙利算法形成区内一对一任务", "在全部可行组合上选择总代价较小且资源不重复的关系")
    matrix = ((2.1, 5.6, 7.2, 6.8), (4.9, 1.8, 4.2, 5.5), (6.0, 3.7, 2.0, 4.1), (5.8, 4.9, 3.8, 1.7))
    left, bottom, cell = 36, 17, 10
    _text(ax, 19, 48, "拦截无人机", size=12, color=BLUE, bold=True)
    _text(ax, 74, 55, "区域临时目标", size=13, color=GREEN, bold=True)
    for col in range(4):
        _text(ax, left + col * cell + cell / 2, 49.5, f"目标{col + 1}", size=9.3, color=GREEN, bold=True)
    for row in range(4):
        _text(ax, 29, bottom + (3 - row) * cell + cell / 2, f"无人机{row + 1}", size=9.1, color=BLUE, bold=True)
        for col in range(4):
            selected = row == col
            x = left + col * cell
            y = bottom + (3 - row) * cell
            ax.add_patch(Rectangle((x, y), cell, cell, facecolor=ORANGE_LIGHT if selected else WHITE, edgecolor=ORANGE if selected else GRAY, linewidth=2.4 if selected else 1.0))
            _text(ax, x + cell / 2, y + cell / 2, f"{matrix[row][col]:.1f}", size=10.3, color=ORANGE if selected else INK, bold=selected)
    _box(ax, 82, 23, 29, 18, "选中组合\n机1-目标1\n机2-目标2\n机3-目标3\n机4-目标4", fill=ORANGE_LIGHT, edge=ORANGE, size=9.3, bold=True)
    _box(ax, 24, 6, 72, 7, "目标多于资源时保留未分配项；资源多于目标时保留搜索和备用力量。", fill=GRAY_LIGHT, edge=GRAY, size=9.8, bold=True)
    _save_and_validate(fig, "local_assignment_hungarian.png")


def build_local_assignment_multi_resource_slots() -> None:
    fig, ax = _canvas("高威胁目标的多资源任务槽", "目标需求展开为主用和备用槽位，每架无人机仍只承担一个主要任务")
    _target(ax, 60, 48, RED, "高威胁区域目标", radius=2.0)
    slots = ((22, 30, BLUE, BLUE_LIGHT, "主用槽1"), (48, 24, GREEN, GREEN_LIGHT, "主用槽2"), (75, 24, ORANGE, ORANGE_LIGHT, "备用槽"), (101, 30, GRAY, GRAY_LIGHT, "持续观察"))
    for x, y, color, fill, label in slots:
        _box(ax, x - 10, y - 4, 20, 8, label, fill=fill, edge=color, size=9.8, bold=True)
        _arrow(ax, (x, y + 4), (58, 45), color=color, width=1.6)
    for x, color, label in ((20, BLUE, "无人机1"), (45, GREEN, "无人机2"), (75, ORANGE, "无人机3"), (101, GRAY, "无人机4")):
        _drone(ax, x, 13, color, label)
    _box(ax, 13, 4, 94, 6, "本阶段不把同时到达设为硬条件；任务明确主用、备用、观察方向和启动条件。", fill=RED_LIGHT, edge=RED, text_color=RED, size=9.7, bold=True)
    _save_and_validate(fig, "local_assignment_multi_resource_slots.png")


def build_secondary_cross_region_support() -> None:
    fig, ax = _canvas("相邻区域的目标责任和资源支援", "边界目标先确定唯一负责节点，再申请邻区无人机支援")
    _box(ax, 6, 38, 34, 15, "区域A二级节点\n区域目标 A-17\n资源不足", fill=BLUE_LIGHT, edge=BLUE, size=10, bold=True)
    _box(ax, 80, 38, 34, 15, "区域B二级节点\n完成 A-17 映射\n可提供一架无人机", fill=GREEN_LIGHT, edge=GREEN, size=10, bold=True)
    _target(ax, 60, 32, RED, "边界目标", radius=1.5)
    _arrow(ax, (40.5, 45), (79.5, 45), color=ORANGE, width=2.2)
    _text(ax, 60, 49, "目标映射 + 支援请求", size=10, color=ORANGE, bold=True)
    _arrow(ax, (80, 41), (63, 34), color=GREEN, width=2.0)
    _drone(ax, 91, 21, GREEN, "邻区支援机")
    _arrow(ax, (88, 24), (63, 31), color=GREEN, width=1.8)
    _box(ax, 10, 7, 100, 8, "唯一负责节点发布计划；支援节点确认目标映射、计划版本和有效期，不生成第二份独立拦截任务。", fill=GRAY_LIGHT, edge=GRAY, size=9.7, bold=True)
    _save_and_validate(fig, "secondary_cross_region_support.png")


def build_local_assignment_hysteresis() -> None:
    fig, ax = _canvas("二级节点计划的滚动更新和迟滞", "普通变化控制换令，硬事件直接进入安全重算")
    _box(ax, 5, 34, 24, 12, "区域状态变化", fill=BLUE_LIGHT, edge=BLUE, size=11.5, bold=True)
    _arrow(ax, (29.5, 40), (41, 47), color=GREEN, width=2.0)
    _arrow(ax, (29.5, 40), (41, 28), color=RED, width=2.0)
    _box(ax, 41, 42, 32, 12, "普通变化\n短时转向、轻微代价变化\n单次链路延迟", fill=GREEN_LIGHT, edge=GREEN, size=9.3, bold=True)
    _box(ax, 41, 18, 32, 12, "硬事件\n任务不可达、节点或资源故障\n计划到期、身份冲突", fill=RED_LIGHT, edge=RED, size=9.3, bold=True)
    _arrow(ax, (73.5, 48), (84, 48), color=GREEN, width=2.0)
    _arrow(ax, (73.5, 24), (84, 24), color=RED, width=2.0)
    _box(ax, 84, 42, 31, 12, "收益门限 + 保持时间\n改善不足则保持原任务", fill=GREEN_LIGHT, edge=GREEN, size=9.3, bold=True)
    _box(ax, 84, 18, 31, 12, "立即安全重算\n只处理受影响目标与资源", fill=RED_LIGHT, edge=RED, size=9.3, bold=True)
    _box(ax, 38, 5, 45, 8, "二级节点发布严格升版的短时计划", fill=ORANGE_LIGHT, edge=ORANGE, size=9.8, bold=True)
    _save_and_validate(fig, "local_assignment_hysteresis.png")


def build_secondary_assignment_failover() -> None:
    _horizontal_flow(
        "secondary_assignment_failover.png",
        "二级节点失效后的本地分配接替",
        "已有安全任务继续执行，未完成任务由临时协调或分布式报价形成新关系",
        [("二级计划", "区域目标表\n任期版本\n执行回执"), ("节点失效", "心跳超时\n光电或通信故障"), ("保留任务", "身份明确\n仍可到达\n计划未到期"), ("临时协调", "继承目标映射\n只重算受影响任务"), ("分布报价", "可达和视觉\n冲突消解\n新任期")],
        "协商超时、网络分区、目标版本冲突或必要成员未确认时，停止发布新的拦截任务。",
    )


def build_region_repartition_difficulty() -> None:
    fig, ax = _canvas("区域重划的主要难点", "粗提示、窄视场、移动平台和滚动边界同时作用")
    panels = (
        (4, BLUE, BLUE_LIGHT, "粗提示大于单帧视场", "中心给出大范围和数量区间", "高概率通道可能只占局部"),
        (43, GREEN, GREEN_LIGHT, "平台运动改变观察几何", "盘旋位置与姿态持续变化", "世界单元必须实时换算云台角"),
        (82, ORANGE, ORANGE_LIGHT, "边界更新容易产生抖动", "目标跨区、任务占用、节点故障", "既要及时调整又要保护稳定任务"),
    )
    for x, color, fill, title, line1, line2 in panels:
        ax.add_patch(FancyBboxPatch((x, 15), 34, 40, boxstyle="round,pad=0.35,rounding_size=1", facecolor=fill, edgecolor=color, linewidth=2.0))
        _text(ax, x + 17, 51, title, size=12.3, color=color, bold=True)
        if x == 4:
            ax.add_patch(Ellipse((x + 17, 36), 25, 16, facecolor=WHITE, edgecolor=color, linewidth=1.7, linestyle="--"))
            ax.add_patch(Rectangle((x + 13, 32), 8, 7, facecolor=ORANGE_LIGHT, edgecolor=ORANGE, linewidth=1.6))
            _text(ax, x + 17, 35.5, "单帧", size=8.7, color=ORANGE, bold=True)
        elif x == 43:
            _secondary_node(ax, x + 11, 38, color, "时刻一")
            _secondary_node(ax, x + 24, 42, ORANGE, "时刻二")
            _arrow(ax, (x + 14, 35), (x + 28, 30), color=color, width=1.4)
            _arrow(ax, (x + 27, 39), (x + 28, 30), color=ORANGE, width=1.4)
        else:
            ax.add_patch(Rectangle((x + 5, 28), 12, 15, facecolor=WHITE, edgecolor=color, linewidth=1.5))
            ax.add_patch(Rectangle((x + 17, 28), 12, 15, facecolor=WHITE, edgecolor=RED, linewidth=1.5))
            _target(ax, x + 17, 36, RED, "边界目标", radius=1.0)
            _arrow(ax, (x + 13, 25), (x + 22, 25), color=RED, width=1.6)
            _arrow(ax, (x + 22, 21), (x + 13, 21), color=RED, width=1.6)
        _text(ax, x + 17, 22.5, f"{line1}\n{line2}", size=8.8, color=INK)
    _box(ax, 13, 5, 94, 7, "一次性平均分区不能同时保证有效覆盖、重访时效、负担均衡和边界唯一责任。", fill=RED_LIGHT, edge=RED, size=9.8, bold=True)
    _save_and_validate(fig, "region_repartition_difficulty.png")


def build_region_rl_state_action_reward() -> None:
    fig, ax = _canvas("区域重划强化学习的状态、动作和回报", "学习模型判断搜索重点和重划时机，不直接控制飞行或云台电机")
    _box(ax, 4, 18, 31, 37, "状态\n\n三维目标概率与信息年龄\n预计像素和遮挡\n平台、云台和任务负担\n通信关系与当前边界\n最近若干周期变化", fill=BLUE_LIGHT, edge=BLUE, size=9.5, bold=True)
    _box(ax, 44, 29, 32, 20, "图结构与时间窗口\n\n提取相邻单元关系\n判断负担和概率变化\n估计长期搜索价值", fill=GREEN_LIGHT, edge=GREEN, size=10.2, bold=True)
    _box(ax, 85, 18, 31, 37, "有限动作\n\n单元优先级修正\n观察者责任权重\n重点重访比例\n凝视任务保护\n提前重划建议", fill=ORANGE_LIGHT, edge=ORANGE, size=9.5, bold=True)
    _arrow(ax, (35.5, 38), (43.5, 38), color=BLUE, width=2.2)
    _arrow(ax, (76.5, 38), (84.5, 38), color=ORANGE, width=2.2)
    _box(ax, 36, 8, 48, 10, "回报：信息增益 + 有效发现 + 负担均衡 − 重访延迟 − 重复覆盖 − 换令代价", fill=RED_LIGHT, edge=RED, size=9.4, bold=True)
    _arrow(ax, (99, 18), (80, 13), color=RED, width=1.4, connectionstyle="arc3,rad=0.2")
    _arrow(ax, (40, 13), (20, 18), color=RED, width=1.4, connectionstyle="arc3,rad=0.2")
    _save_and_validate(fig, "region_rl_state_action_reward.png")


def build_region_rl_safe_closed_loop() -> None:
    _horizontal_flow(
        "region_rl_safe_closed_loop.png",
        "学习策略与确定性分区闭环",
        "强化学习给出搜索重点，安全检查和确定性算法形成具体任务",
        [
            ("形成区域状态", "概率网格\n平台云台\n通信与计划"),
            ("学习策略", "优先级修正\n责任权重\n重划建议"),
            ("安全投影", "边界唯一\n任务保护\n能力和版本"),
            ("确定性分区", "具体搜索单元\n方位俯仰\n短有效期"),
            ("观察反馈", "发现与未发现\n质量和回执\n更新概率"),
        ],
        "模型异常、输入越界、推理超时或动作无法修正时，完整回退到传统概率搜索与能力加权分区。",
    )


def build_search_limited_fov_difficulty() -> None:
    fig, ax = _canvas("有限视场协同搜索的主要难点", "看见一个方向会暂时放弃其他方向，多平台还要避免重复和空档")
    panels = (
        (4, BLUE, BLUE_LIGHT, "窄视场与目标运动", "一次只覆盖小范围\n目标可能跨高度层和方向"),
        (43, GREEN, GREEN_LIGHT, "多云台任务竞争", "周扫、凝视、跟踪同时争用\n全部追随同一线索会重复"),
        (82, ORANGE, ORANGE_LIGHT, "未发现证据不等价", "像素、稳定、遮挡和曝光不同\n低质量未发现不能清空概率"),
    )
    for x, color, fill, title, detail in panels:
        ax.add_patch(FancyBboxPatch((x, 15), 34, 40, boxstyle="round,pad=0.35,rounding_size=1", facecolor=fill, edgecolor=color, linewidth=2.0))
        _text(ax, x + 17, 51, title, size=12.5, color=color, bold=True)
        if x == 4:
            _camera(ax, x + 8, 35, color, "云台")
            ax.add_patch(Polygon([(x + 11, 35), (x + 29, 43), (x + 29, 27)], closed=True, facecolor=WHITE, edgecolor=color, linewidth=1.5))
            for tx, ty in ((x + 24, 38), (x + 29, 32), (x + 18, 24)):
                _target(ax, tx, ty, RED, "", radius=0.8)
        elif x == 43:
            _target(ax, x + 17, 34, RED, "同一候选", radius=1.2)
            for cx, cy in ((x + 7, 44), (x + 27, 44), (x + 17, 25)):
                _camera(ax, cx, cy, color, "")
                _arrow(ax, (cx, cy - 1.5), (x + 17, 34), color=color, width=1.2)
        else:
            for index, (value, label) in enumerate(((0.18, "高质量"), (0.50, "快速扫过"))):
                bx = x + 5 + index * 14
                ax.add_patch(Rectangle((bx, 27), 9, 17, facecolor=WHITE, edgecolor=color, linewidth=1.3))
                ax.add_patch(Rectangle((bx, 27), 9, 17 * value, facecolor=color, edgecolor=color, alpha=0.7))
                _text(ax, bx + 4.5, 35, f"{value:.2f}", size=10, bold=True)
                _text(ax, bx + 4.5, 24, label, size=8.3, color=color, bold=True)
        _text(ax, x + 17, 19.5, detail, size=8.8, color=INK)
    _box(ax, 14, 5, 92, 7, "协同搜索必须同时管理概率、有效观察质量、云台占用、重访时限和多机重复覆盖。", fill=RED_LIGHT, edge=RED, size=9.8, bold=True)
    _save_and_validate(fig, "search_limited_fov_difficulty.png")


def build_search_rl_state_action_reward() -> None:
    fig, ax = _canvas("主动搜索强化学习的状态、动作和回报", "上层策略选择看哪里、看多久，下层控制器执行合法云台和飞行任务")
    _box(ax, 4, 18, 31, 37, "状态\n\n目标概率与数量区间\n单元信息年龄和预计像素\n二级节点与无人机状态\n云台占用和通信关系\n最近观察结果", fill=BLUE_LIGHT, edge=BLUE, size=9.4, bold=True)
    _box(ax, 44, 29, 32, 20, "主动搜索策略\n\n概率网格编码\n多平台关系编码\n多周期观察价值", fill=GREEN_LIGHT, edge=GREEN, size=10.4, bold=True)
    _box(ax, 85, 18, 31, 37, "有限动作\n\n空间单元和俯仰层\n周扫、凝视或可见光\n停留时间等级\n重点重访比例\n无人机补扫请求", fill=ORANGE_LIGHT, edge=ORANGE, size=9.4, bold=True)
    _arrow(ax, (35.5, 38), (43.5, 38), color=BLUE, width=2.2)
    _arrow(ax, (76.5, 38), (84.5, 38), color=ORANGE, width=2.2)
    _box(ax, 34, 8, 52, 10, "回报：信息增益 + 首次发现 + 有效覆盖 − 重访延迟 − 转向能耗 − 重复观察", fill=RED_LIGHT, edge=RED, size=9.4, bold=True)
    _save_and_validate(fig, "search_rl_state_action_reward.png")


def build_search_rl_training_inference() -> None:
    fig, ax = _canvas("主动搜索训练与在线执行闭环", "离线学习长期观察价值，在线输出有限任务并接受确定性检查")
    _text(ax, 7, 49, "离线训练", size=13, color=BLUE, bold=True, ha="left")
    offline = ((8, "随机化场景\n目标、遮挡、通信", BLUE, BLUE_LIGHT), (34, "规则示范\n优先队列与概率搜索", GREEN, GREEN_LIGHT), (60, "近端策略优化\n多回合训练", ORANGE, ORANGE_LIGHT), (86, "独立验证\n未见场景与安全门", RED, RED_LIGHT))
    for index, (x, label, color, fill) in enumerate(offline):
        _box(ax, x, 39, 22, 10, label, fill=fill, edge=color, size=9.2, bold=True)
        if index < len(offline) - 1:
            _arrow(ax, (x + 22.5, 44), (offline[index + 1][0] - 0.5, 44), color=color, width=1.8)
    _text(ax, 7, 29, "在线执行", size=13, color=GREEN, bold=True, ha="left")
    online = ((8, "更新概率与平台状态", BLUE, BLUE_LIGHT), (34, "策略生成候选任务", GREEN, GREEN_LIGHT), (60, "安全和能力检查", ORANGE, ORANGE_LIGHT), (86, "确定性控制与反馈", RED, RED_LIGHT))
    for index, (x, label, color, fill) in enumerate(online):
        _box(ax, x, 18, 22, 10, label, fill=fill, edge=color, size=9.2, bold=True)
        if index < len(online) - 1:
            _arrow(ax, (x + 22.5, 23), (online[index + 1][0] - 0.5, 23), color=color, width=1.8)
    _arrow(ax, (97, 18), (19, 18), color=GRAY, width=1.3, connectionstyle="arc3,rad=-0.16", linestyle="--")
    _box(ax, 24, 5, 72, 7, "模型异常或动作被拒绝时，使用完整传统搜索方案，不保留来源不明的旧动作。", fill=GRAY_LIGHT, edge=GRAY, size=9.6, bold=True)
    _save_and_validate(fig, "search_rl_training_inference.png")


def build_visual_registration_multisubset_difficulty() -> None:
    fig, ax = _canvas("不同相机目标子集与配准难点", "本机轨迹编号只在本相机有效，重叠子集需要通过时间、几何和运动建立对应")
    cameras = ((15, 46, BLUE, "无人机甲\n看到 1、2、3、4", (1, 2, 3, 4)), (15, 32, GREEN, "无人机乙\n看到 2、3、4、5", (2, 3, 4, 5)), (15, 18, ORANGE, "无人机丙\n看到 1、2、4、5", (1, 2, 4, 5)))
    target_x = {1: 62, 2: 74, 3: 86, 4: 98, 5: 110}
    target_y = {1: 48, 2: 42, 3: 35, 4: 28, 5: 21}
    for x, y, color, label, visible in cameras:
        _box(ax, x - 10, y - 5, 24, 10, label, fill=WHITE, edge=color, size=8.9, bold=True)
        for target_id in visible:
            ax.plot([x + 14, target_x[target_id] - 1.5], [y, target_y[target_id]], color=color, linewidth=1.0, alpha=0.28, zorder=2)
    for target_id in range(1, 6):
        _target(ax, target_x[target_id], target_y[target_id], RED, f"目标{target_id}", radius=1.2)
    _box(ax, 42, 7, 72, 8, "交叉、遮挡、非共同视场和时间偏差会改变候选；相同本机编号或画面顺序不能作为身份。", fill=RED_LIGHT, edge=RED, size=9.5, bold=True)
    _save_and_validate(fig, "visual_registration_multisubset_difficulty.png")


def build_visual_registration_gnn_message_passing() -> None:
    fig, ax = _canvas("轨迹图神经网络的节点、边和消息传递", "硬门控建立稀疏候选图，图网络综合多相机关系输出同一目标评分")
    _box(ax, 4, 19, 25, 35, "节点特征\n\n相机和时间\n检测框历史\n像面速度与尺度\n几何协方差\n通道与观察质量\n可选外观特征", fill=BLUE_LIGHT, edge=BLUE, size=9.2, bold=True)
    node_positions = ((47, 46, BLUE, "甲-1"), (58, 46, BLUE, "甲-2"), (43, 33, GREEN, "乙-1"), (60, 31, GREEN, "乙-2"), (49, 20, ORANGE, "丙-1"), (65, 19, ORANGE, "丙-2"))
    for x, y, color, label in node_positions:
        ax.add_patch(Circle((x, y), 3.1, facecolor=WHITE, edgecolor=color, linewidth=1.8, zorder=5))
        _text(ax, x, y, label, size=8.1, color=color, bold=True)
    candidate_edges = ((0, 2, RED), (0, 4, GRAY), (1, 3, RED), (1, 5, RED), (2, 4, RED), (3, 5, GRAY))
    for a, b, color in candidate_edges:
        x1, y1 = node_positions[a][:2]
        x2, y2 = node_positions[b][:2]
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=2.0 if color == RED else 1.2, linestyle="-" if color == RED else "--", alpha=0.8, zorder=3)
    _text(ax, 54, 55, "稀疏候选图", size=12, color=GREEN, bold=True)
    _box(ax, 78, 19, 38, 35, "边特征与评分\n\n时间差和视场关系\n视线距离与重投影\n马氏距离和运动方向\n尺度趋势与外观相似\n邻接消息聚合\n输出同一目标概率", fill=ORANGE_LIGHT, edge=ORANGE, size=9.2, bold=True)
    _arrow(ax, (29.5, 36.5), (38.5, 36.5), color=BLUE, width=2.0)
    _arrow(ax, (69, 36.5), (77.5, 36.5), color=ORANGE, width=2.0)
    _box(ax, 31, 7, 58, 7, "图网络只辅助评分；同相机互斥、一对一关系和多帧确认仍由确定性规则执行。", fill=RED_LIGHT, edge=RED, size=9.4, bold=True)
    _save_and_validate(fig, "visual_registration_gnn_message_passing.png")


def build_visual_registration_ai_safe_pipeline() -> None:
    _horizontal_flow(
        "visual_registration_ai_safe_pipeline.png",
        "深度学习评分与确定性确认流程",
        "学习模型处理复杂候选关系，几何和身份约束形成最终区域目标",
        [
            ("本机短轨迹", "检测框历史\n拍摄时间\n本机编号"),
            ("硬门控", "时间可达\n视场关系\n几何协方差"),
            ("图网络评分", "运动与尺度\n重投影\n可选外观"),
            ("全局匹配", "一对一\n同相机互斥\n跨视角闭环"),
            ("多帧确认", "候选差距\n支持来源\n区域临时编号"),
        ],
        "真实目标编号只用于离线评价；低像素外观、模型高分和数量先验都不能绕过几何与版本检查。",
    )


def build_local_assignment_difficulty() -> None:
    fig, ax = _canvas("本地目标分配的主要难点", "非等量任务、多资源需求、长期资源价值和节点失效需要统一处理")
    panels = (
        (4, BLUE, BLUE_LIGHT, "目标与资源不等量", "目标多时保留未分配原因\n资源多时保留搜索和备用"),
        (43, GREEN, GREEN_LIGHT, "高威胁需要多资源", "两架主用、一架备用\n成员角色和启动条件必须完整"),
        (82, ORANGE, ORANGE_LIGHT, "状态变化与节点失效", "换令过快造成抖动\n通信分区可能产生重复计划"),
    )
    for x, color, fill, title, detail in panels:
        ax.add_patch(FancyBboxPatch((x, 15), 34, 40, boxstyle="round,pad=0.35,rounding_size=1", facecolor=fill, edgecolor=color, linewidth=2.0))
        _text(ax, x + 17, 51, title, size=12.3, color=color, bold=True)
        if x == 4:
            for dx in (8, 17, 26):
                _drone(ax, x + dx, 40, color, "")
            for index, tx in enumerate((x + 7, x + 14, x + 21, x + 28)):
                _target(ax, tx, 29, RED, f"{index + 1}", radius=0.8)
        elif x == 43:
            _target(ax, x + 17, 42, RED, "高威胁", radius=1.4)
            for dx, c in ((8, BLUE), (17, GREEN), (26, ORANGE)):
                _drone(ax, x + dx, 27, c, "")
                _arrow(ax, (x + dx, 30), (x + 17, 39), color=c, width=1.2)
        else:
            _box(ax, x + 4, 35, 12, 9, "二级计划", fill=WHITE, edge=color, size=8.5, bold=True)
            _box(ax, x + 19, 35, 12, 9, "接替计划", fill=WHITE, edge=RED, size=8.5, bold=True)
            _arrow(ax, (x + 16.5, 39.5), (x + 18.5, 39.5), color=RED, width=1.7)
            _box(ax, x + 8, 24, 18, 7, "任期、版本、回执", fill=GRAY_LIGHT, edge=GRAY, size=8.2, bold=True)
        _text(ax, x + 17, 19.5, detail, size=8.8, color=INK)
    _box(ax, 13, 5, 94, 7, "分配必须同时满足身份成熟度、资源约束、任务窗口、计划稳定和唯一发布责任。", fill=RED_LIGHT, edge=RED, size=9.8, bold=True)
    _save_and_validate(fig, "local_assignment_difficulty.png")


def build_local_assignment_rl_state_action_reward() -> None:
    fig, ax = _canvas("学习增强分配的状态、动作和回报", "学习模型修正规则代价和重规划时机，不直接发布最终配对")
    _box(ax, 4, 18, 31, 37, "状态\n\n目标威胁、证据和窗口\n资源机动、相机和余量\n候选边规则代价\n通信关系和当前任务\n最近计划变化", fill=BLUE_LIGHT, edge=BLUE, size=9.3, bold=True)
    _box(ax, 44, 29, 32, 20, "目标—资源图策略\n\n综合邻接和历史变化\n判断长期资源价值\n限制学习修正幅度", fill=GREEN_LIGHT, edge=GREEN, size=10.1, bold=True)
    _box(ax, 85, 18, 31, 37, "有限动作\n\n候选边代价修正\n未分配惩罚修正\n备用启用建议\n提前重规划建议\n保持当前计划", fill=ORANGE_LIGHT, edge=ORANGE, size=9.3, bold=True)
    _arrow(ax, (35.5, 38), (43.5, 38), color=BLUE, width=2.2)
    _arrow(ax, (76.5, 38), (84.5, 38), color=ORANGE, width=2.2)
    _box(ax, 32, 8, 56, 10, "回报：任务满足 + 高威胁优先 + 有效窗口 − 未分配 − 能耗 − 换令 − 通信负担", fill=RED_LIGHT, edge=RED, size=9.2, bold=True)
    _save_and_validate(fig, "local_assignment_rl_state_action_reward.png")


def build_local_assignment_cost_correction_flow() -> None:
    _horizontal_flow(
        "local_assignment_cost_correction_flow.png",
        "规则代价、学习修正与确定性求解流程",
        "强化学习调整有限评分，硬条件和求解器保持最终任务可解释",
        [
            ("硬条件筛选", "身份成熟\n可达机动\n视觉通信"),
            ("规则代价", "到达、证据\n能源、威胁\n换令风险"),
            ("学习修正", "有界代价差\n备用建议\n重规划建议"),
            ("确定性求解", "匈牙利或流\n一对一与多槽\n资源不重复"),
            ("计划与回执", "任期版本\n有效期\n执行反馈"),
        ],
        "不可行边不会被学习模型恢复；模型异常时使用完整规则代价，不沿用来源不明的旧修正。",
    )


def build_all() -> None:
    builders = (
        build_eight_region_airborne_secondary_architecture,
        build_secondary_eo_payload_parameters,
        build_region_repartition_difficulty,
        build_region_four_level_structure,
        build_region_rl_state_action_reward,
        build_secondary_weighted_region_partition,
        build_region_rl_safe_closed_loop,
        build_moving_node_world_angle_mapping,
        build_adjacent_secondary_boundary_handoff,
        build_secondary_region_repartition_flow,
        build_secondary_region_repartition_example,
        build_secondary_interceptor_search_architecture,
        build_secondary_gimbal_scan_modes,
        build_search_limited_fov_difficulty,
        build_search_rl_state_action_reward,
        build_secondary_search_priority_cycle,
        build_secondary_search_cell_allocation,
        build_search_rl_training_inference,
        build_secondary_interceptor_cue_handoff,
        build_search_probability_update,
        build_secondary_search_failover,
        build_secondary_anchor_registration_overview,
        build_visual_registration_multisubset_difficulty,
        build_moving_platform_geometry_compensation,
        build_visual_registration_evidence_chain_secondary,
        build_visual_registration_gnn_message_passing,
        build_secondary_overlap_reprojection,
        build_secondary_nonoverlap_bridge,
        build_visual_registration_small_target_matching,
        build_visual_registration_dense_track_graph,
        build_visual_registration_ai_safe_pipeline,
        build_regional_target_boundary_lifecycle,
        build_secondary_local_assignment_architecture,
        build_local_assignment_difficulty,
        build_secondary_task_maturity_gate,
        build_local_assignment_rl_state_action_reward,
        build_local_assignment_cost_components_secondary,
        build_local_assignment_cost_correction_flow,
        build_local_assignment_hungarian,
        build_local_assignment_multi_resource_slots,
        build_secondary_cross_region_support,
        build_local_assignment_hysteresis,
        build_secondary_assignment_failover,
    )
    for builder in builders:
        builder()
        print(builder.__name__)


if __name__ == "__main__":
    build_all()
