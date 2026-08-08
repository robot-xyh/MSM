#!/usr/bin/env python3
"""Generate the terminal cooperative interception decision-flow figure."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "terminal_cooperative_interception_rl_flow.png"
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
WIDTH, HEIGHT = 3200, 1800

COLORS = {
    "background": "#F5F8FA",
    "ink": "#20303D",
    "muted": "#5E7080",
    "blue": "#2D6F9F",
    "blue_light": "#E5F0F7",
    "teal": "#2C827D",
    "teal_light": "#E3F2EF",
    "orange": "#D98232",
    "orange_light": "#FAEDDE",
    "red": "#A94A4A",
    "red_light": "#F8E7E5",
    "white": "#FFFFFF",
    "line": "#B9C8D2",
}


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT.replace("Regular", "Bold") if bold else FONT
    if not Path(path).exists():
        path = FONT
    return ImageFont.truetype(path, size=size, index=0)


def centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    text_font: ImageFont.FreeTypeFont,
    fill: str,
    spacing: int = 12,
) -> None:
    bounds = draw.multiline_textbbox((0, 0), text, font=text_font, spacing=spacing, align="center")
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    x = box[0] + (box[2] - box[0] - text_width) / 2
    y = box[1] + (box[3] - box[1] - text_height) / 2 - bounds[1]
    draw.multiline_text((x, y), text, font=text_font, fill=fill, spacing=spacing, align="center")


def rounded_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    lines: str,
    color: str,
    light: str,
    number: str,
) -> None:
    draw.rounded_rectangle(box, radius=28, fill=COLORS["white"], outline=color, width=5)
    header = (box[0], box[1], box[2], box[1] + 90)
    draw.rounded_rectangle(header, radius=25, fill=light)
    draw.rectangle((box[0], box[1] + 55, box[2], box[1] + 90), fill=light)
    circle = (box[0] + 24, box[1] + 19, box[0] + 76, box[1] + 71)
    draw.ellipse(circle, fill=color)
    centered_text(draw, circle, number, font(30, bold=True), COLORS["white"])
    title_box = (box[0] + 85, box[1] + 10, box[2] - 15, box[1] + 82)
    centered_text(draw, title_box, title, font(37, bold=True), COLORS["ink"])
    body = (box[0] + 22, box[1] + 106, box[2] - 22, box[3] - 18)
    centered_text(draw, body, lines, font(31), COLORS["muted"], spacing=14)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str) -> None:
    draw.line((start, end), fill=color, width=10)
    x, y = end
    draw.polygon([(x, y), (x - 28, y - 18), (x - 28, y + 18)], fill=color)


def build() -> Path:
    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["background"])
    draw = ImageDraw.Draw(image)

    draw.text((160, 80), "末端三机协同拦截强化学习决策流程", font=font(72, bold=True), fill=COLORS["ink"])
    draw.text(
        (164, 175),
        "学习模型选择协同方式，确定性模块负责安全审核与末端执行",
        font=font(37),
        fill=COLORS["muted"],
    )

    boxes = [
        ((130, 330, 670, 790), "信息汇总", "目标航迹与协方差\n三机状态与预计到达时间\n通信、视觉和计划版本", COLORS["blue"], COLORS["blue_light"]),
        ((750, 330, 1290, 790), "可行动作生成", "身份一致性检查\n机动与通信条件筛选\n屏蔽不可执行动作", COLORS["teal"], COLORS["teal_light"]),
        ((1370, 330, 1910, 790), "强化学习决策", "选择协同模式\n分配主攻、备用、包抄\n给出方向与时间参数", COLORS["orange"], COLORS["orange_light"]),
        ((1990, 330, 2530, 790), "确定性安全审核", "转弯可达性与地理边界\n最小机间距离\n计划有效期与成员确认", COLORS["blue"], COLORS["blue_light"]),
        ((2610, 330, 3070, 790), "计划发布", "写入所有者、版本和有效期\n成员确认后执行\n拒绝过期计划", COLORS["teal"], COLORS["teal_light"]),
    ]
    for index, (box, title, lines, color, light) in enumerate(boxes, start=1):
        rounded_box(draw, box, title, lines, color, light, str(index))
    for left, right in zip(boxes, boxes[1:]):
        start_box, end_box = left[0], right[0]
        arrow(draw, (start_box[2] + 10, 560), (end_box[0] - 12, 560), COLORS["line"])

    mode_y = 880
    draw.text((1370, mode_y - 65), "策略候选", font=font(34, bold=True), fill=COLORS["orange"])
    mode_boxes = [
        (1370, mode_y, 1715, mode_y + 155, "同时围捕\n公共到达时刻"),
        (1745, mode_y, 2090, mode_y + 155, "主攻加替补\n失效快速接替"),
        (2120, mode_y, 2465, mode_y + 155, "虚拟终端点\n低通信依赖"),
        (2495, mode_y, 2840, mode_y + 155, "分层接力\n延长接战窗口"),
    ]
    for x1, y1, x2, y2, label in mode_boxes:
        box = (x1, y1, x2, y2)
        draw.rounded_rectangle(box, radius=20, fill=COLORS["orange_light"], outline=COLORS["orange"], width=4)
        centered_text(draw, box, label, font(29, bold=True), COLORS["ink"])

    execute_box = (1930, 1140, 3070, 1485)
    draw.rounded_rectangle(execute_box, radius=28, fill=COLORS["teal_light"], outline=COLORS["teal"], width=5)
    centered_text(
        draw,
        (execute_box[0] + 25, execute_box[1] + 20, execute_box[2] - 25, execute_box[1] + 105),
        "确定性执行与反馈",
        font(42, bold=True),
        COLORS["teal"],
    )
    centered_text(
        draw,
        (execute_box[0] + 30, execute_box[1] + 105, execute_box[2] - 30, execute_box[3] - 20),
        "位置比例导引 → 稳定视觉确认 → 末端视觉导引\n反馈接替状态、剩余窗口、最小距离和任务结果",
        font(34),
        COLORS["ink"],
    )
    draw.line((2840, 790, 2840, 1140), fill=COLORS["teal"], width=10)
    draw.polygon([(2840, 1140), (2822, 1112), (2858, 1112)], fill=COLORS["teal"])

    fallback_box = (130, 1135, 1660, 1490)
    draw.rounded_rectangle(fallback_box, radius=28, fill=COLORS["red_light"], outline=COLORS["red"], width=5)
    draw.text((180, 1180), "规则降级通道", font=font(42, bold=True), fill=COLORS["red"])
    draw.multiline_text(
        (180, 1260),
        "身份不一致：不形成三机协同\n通信不足：虚拟终端点或分层接力\n模型异常、超时或越界：沿用有效计划或规则策略",
        font=font(34),
        fill=COLORS["ink"],
        spacing=18,
    )
    draw.line(
        (2260, 790, 2260, 825, 2105, 825, 2105, 1080, 1660, 1080, 1660, 1135),
        fill=COLORS["red"],
        width=8,
    )
    draw.polygon([(1660, 1135), (1642, 1107), (1678, 1107)], fill=COLORS["red"])

    draw.line((1930, 1320, 1810, 1320, 1810, 1640, 400, 1640, 400, 790), fill=COLORS["blue"], width=9)
    draw.polygon([(400, 790), (382, 820), (418, 820)], fill=COLORS["blue"])
    draw.text((760, 1565), "低频滚动决策：执行结果返回下一周期", font=font(34, bold=True), fill=COLORS["blue"])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, dpi=(300, 300), optimize=True)
    return OUTPUT


if __name__ == "__main__":
    print(build())
