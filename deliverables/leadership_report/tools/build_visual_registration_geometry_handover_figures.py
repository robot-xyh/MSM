#!/usr/bin/env python3
"""Generate Word-ready figures for geometry-led visual registration."""

from __future__ import annotations

import numpy as np
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon, Rectangle

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


def _panel(ax, x: float, y: float, width: float, height: float, title: str, edge: str, fill: str) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.35,rounding_size=0.9",
            facecolor=fill,
            edgecolor=edge,
            linewidth=1.8,
            zorder=1,
        )
    )
    _text(ax, x + width / 2, y + height - 3.2, title, size=14, color=edge, bold=True)


def _project3d(
    point,
    *,
    origin: tuple[float, float] = (60.0, 28.0),
    scale: float = 4.0,
    azimuth: float = 0.0,
    elevation: float = 25.0,
) -> tuple[float, float]:
    """Project a 3-D point to the report canvas using an oblique view."""
    x, y, z = np.asarray(point, dtype=float)
    azimuth_rad = np.deg2rad(azimuth)
    elevation_rad = np.deg2rad(elevation)
    horizontal = np.cos(azimuth_rad) * x - np.sin(azimuth_rad) * y
    depth = np.sin(azimuth_rad) * x + np.cos(azimuth_rad) * y
    vertical = np.cos(elevation_rad) * z - np.sin(elevation_rad) * depth
    return origin[0] + scale * horizontal, origin[1] + scale * vertical


def _line3d(ax, start, end, *, color: str, width: float = 1.8, linestyle: str = "-", **view) -> None:
    p0 = _project3d(start, **view)
    p1 = _project3d(end, **view)
    ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color=color, linewidth=width, linestyle=linestyle, zorder=5)


def _polygon3d(ax, points, *, face: str, edge: str, alpha: float = 0.35, width: float = 1.5, **view) -> None:
    projected = [_project3d(point, **view) for point in points]
    ax.add_patch(
        Polygon(
            projected,
            closed=True,
            facecolor=face,
            edgecolor=edge,
            linewidth=width,
            alpha=alpha,
            zorder=2,
        )
    )


def _point3d(ax, point, label: str, *, color: str, radius: float = 0.9, offset=(0.0, 2.2), **view) -> None:
    x, y = _project3d(point, **view)
    ax.add_patch(Circle((x, y), radius, facecolor=color, edgecolor=WHITE, linewidth=1.0, zorder=8))
    _text(ax, x + offset[0], y + offset[1], label, size=9.2, color=color, bold=True)


def _image_plane(camera, look_at, *, distance: float, width: float, height: float):
    camera = np.asarray(camera, dtype=float)
    look_at = np.asarray(look_at, dtype=float)
    normal = look_at - camera
    normal /= np.linalg.norm(normal)
    reference = np.array([0.0, 0.0, 1.0])
    right = np.cross(reference, normal)
    if np.linalg.norm(right) < 1e-6:
        reference = np.array([0.0, 1.0, 0.0])
        right = np.cross(reference, normal)
    right /= np.linalg.norm(right)
    up = np.cross(normal, right)
    up /= np.linalg.norm(up)
    center = camera + distance * normal
    corners = [
        center - width / 2 * right - height / 2 * up,
        center + width / 2 * right - height / 2 * up,
        center + width / 2 * right + height / 2 * up,
        center - width / 2 * right + height / 2 * up,
    ]
    return center, normal, right, up, corners


def _ray_plane_intersection(ray_origin, ray_point, plane_center, plane_normal):
    ray_origin = np.asarray(ray_origin, dtype=float)
    direction = np.asarray(ray_point, dtype=float) - ray_origin
    denominator = float(np.dot(plane_normal, direction))
    if abs(denominator) < 1e-8:
        raise ValueError("ray is parallel to image plane")
    parameter = float(np.dot(plane_normal, plane_center - ray_origin) / denominator)
    return ray_origin + parameter * direction


def _axes3d(ax, base, *, view) -> None:
    base = np.asarray(base, dtype=float)
    axes = (
        (np.array([2.3, 0.0, 0.0]), "东", BLUE),
        (np.array([0.0, 2.3, 0.0]), "北", GREEN),
        (np.array([0.0, 0.0, 2.3]), "高", ORANGE),
    )
    for vector, label, color in axes:
        end = base + vector
        _line3d(ax, base, end, color=color, width=1.6, **view)
        x, y = _project3d(end, **view)
        _text(ax, x, y + 1.1, label, size=8.5, color=color, bold=True)


def build_overall_architecture_3d():
    fig, ax = _canvas(
        "中心—二级—拦截机两级视觉配准",
        "固定中心先与扇区二级节点建立基准航迹，二级节点再连接拦截无人机的局部短轨迹",
    )

    view = {"origin": (58.0, 18.0), "scale": 3.0, "azimuth": -20.0, "elevation": 25.0}
    center = np.array([-13.0, -1.0, 0.5])
    secondary = np.array([0.0, -3.0, 11.5])
    interceptors = (
        np.array([-8.0, -6.0, 3.0]),
        np.array([0.0, -7.0, 3.2]),
        np.array([8.0, -5.0, 3.0]),
    )
    targets = (
        np.array([-7.0, 5.0, 7.0]),
        np.array([-2.0, 6.0, 7.4]),
        np.array([3.0, 5.5, 7.1]),
        np.array([8.0, 7.0, 7.6]),
        np.array([12.0, 6.0, 7.0]),
    )

    _polygon3d(ax, [center, targets[0], targets[3]], face=BLUE_LIGHT, edge=BLUE, alpha=0.13, width=1.6, **view)
    _polygon3d(ax, [secondary, targets[0], targets[-1]], face=GREEN_LIGHT, edge=GREEN, alpha=0.18, width=1.8, **view)
    _line3d(ax, center, secondary, color=ORANGE, width=2.0, linestyle="--", **view)
    cones = (
        (interceptors[0], targets[0], targets[2], BLUE_LIGHT, BLUE),
        (interceptors[1], targets[1], targets[3], ORANGE_LIGHT, ORANGE),
        (interceptors[2], targets[2], targets[4], GREEN_LIGHT, GREEN),
    )
    for camera, left_target, right_target, fill, edge in cones:
        _polygon3d(ax, [camera, left_target, right_target], face=fill, edge=edge, alpha=0.25, width=1.5, **view)
        _line3d(ax, secondary, camera, color=GRAY, width=1.2, linestyle="--", **view)

    _point3d(ax, center, "固定中心节点", color=BLUE, radius=1.15, offset=(0.0, -2.4), **view)
    _point3d(ax, secondary, "盘旋二级节点", color=GREEN, radius=1.2, offset=(0.0, 2.2), **view)
    interceptor_labels = ("拦截机甲", "拦截机乙", "拦截机丙")
    for camera, label, color in zip(interceptors, interceptor_labels, (BLUE, ORANGE, GREEN)):
        _point3d(ax, camera, label, color=color, radius=0.95, offset=(0.0, -2.2), **view)
    target_offsets = ((-1.5, 1.8), (-0.5, 2.5), (0.0, -2.0), (0.5, 2.0), (2.0, 2.0))
    for index, (target, offset) in enumerate(zip(targets, target_offsets), start=1):
        _point3d(ax, target, f"目标{index}", color=RED, radius=0.82, offset=offset, **view)

    _text(ax, 28, 47.5, "甲机局部视场", size=9.5, color=BLUE, bold=True)
    _text(ax, 61, 43.5, "乙机局部视场", size=9.5, color=ORANGE, bold=True)
    _text(ax, 92, 42.0, "丙机局部视场", size=9.5, color=GREEN, bold=True)
    _text(ax, 59, 49.0, "二级节点滚动区域观察", size=10.0, color=GREEN, bold=True)
    _axes3d(ax, np.array([-15.0, -8.0, 0.0]), view=view)

    _box(
        ax,
        11,
        3.7,
        98,
        5.7,
        "两级关系分别维护协方差、版本和有效期。任一级存在歧义，端到端身份保持未确认。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.1,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_overall_architecture_3d.png")


def build_pose_uncertainty_3d():
    fig, ax = _canvas(
        "位姿误差把极线扩展为概率带",
        "导航位置、机体姿态、云台角度、安装标定和时间误差共同改变相机视线与极平面",
    )

    view = {"origin": (58.0, 21.0), "scale": 4.1, "azimuth": -5.0, "elevation": 25.0}
    camera_nominal = np.array([-7.5, -5.0, 1.0])
    camera_actual = np.array([-6.7, -4.5, 1.35])
    camera_secondary = np.array([7.0, -5.0, 2.0])
    target_actual = np.array([1.3, 2.0, 9.0])
    target_nominal_ray = np.array([0.0, 2.7, 8.3])

    plane_center, plane_normal, _, _, plane_corners = _image_plane(
        camera_secondary,
        target_actual,
        distance=3.1,
        width=5.7,
        height=4.2,
    )

    def epipolar_line(source, ray_target):
        normal = np.cross(camera_secondary - source, ray_target - source)
        normal /= np.linalg.norm(normal)
        direction = np.cross(normal, plane_normal)
        direction /= np.linalg.norm(direction)
        center = _ray_plane_intersection(camera_secondary, ray_target, plane_center, plane_normal)
        return center - 2.5 * direction, center + 2.5 * direction, center

    nominal_start, nominal_end, nominal_center = epipolar_line(camera_nominal, target_nominal_ray)
    actual_start, actual_end, actual_center = epipolar_line(camera_actual, target_actual)

    _polygon3d(
        ax,
        [camera_nominal, camera_secondary, target_nominal_ray],
        face=BLUE_LIGHT,
        edge=BLUE,
        alpha=0.25,
        width=1.6,
        **view,
    )
    _polygon3d(
        ax,
        [camera_actual, camera_secondary, target_actual],
        face=RED_LIGHT,
        edge=RED,
        alpha=0.25,
        width=1.6,
        **view,
    )
    _polygon3d(ax, plane_corners, face=GREEN_LIGHT, edge=GREEN, alpha=0.78, width=2.0, **view)
    _polygon3d(
        ax,
        [nominal_start, nominal_end, actual_end, actual_start],
        face=ORANGE_LIGHT,
        edge=ORANGE,
        alpha=0.7,
        width=1.4,
        **view,
    )
    _line3d(ax, nominal_start, nominal_end, color=BLUE, width=2.3, linestyle="--", **view)
    _line3d(ax, actual_start, actual_end, color=RED, width=2.5, **view)
    _line3d(ax, camera_nominal, camera_actual, color=ORANGE, width=2.0, **view)
    _line3d(ax, camera_actual, target_actual, color=RED, width=1.7, **view)
    _line3d(ax, camera_nominal, target_nominal_ray, color=BLUE, width=1.7, linestyle="--", **view)

    nominal_xy = _project3d(camera_nominal, **view)
    ax.add_patch(Ellipse(nominal_xy, 7.0, 4.0, angle=15, facecolor=ORANGE_LIGHT, edgecolor=ORANGE, linewidth=1.6, alpha=0.7, zorder=4))
    _point3d(ax, camera_nominal, "导航报告位姿", color=BLUE, radius=0.85, offset=(-4.0, -2.4), **view)
    _point3d(ax, camera_actual, "真实相机位姿", color=RED, radius=0.85, offset=(4.0, 2.2), **view)
    _point3d(ax, camera_secondary, "二级节点相机", color=GREEN, radius=1.0, offset=(0.0, -2.4), **view)
    _point3d(ax, target_actual, "实际目标", color=ORANGE, radius=0.9, offset=(0.0, 2.0), **view)
    _point3d(ax, nominal_center, "", color=BLUE, radius=0.5, offset=(0.0, 0.0), **view)
    _point3d(ax, actual_center, "", color=RED, radius=0.5, offset=(0.0, 0.0), **view)

    band_xy = _project3d((nominal_center + actual_center) / 2.0, **view)
    _text(ax, band_xy[0] + 4.5, band_xy[1] + 4.5, "极线概率带", size=10.5, color=ORANGE, bold=True)
    _text(ax, nominal_xy[0] - 1.0, nominal_xy[1] + 5.0, "位置协方差", size=9.5, color=ORANGE, bold=True)
    _axes3d(ax, np.array([-10.0, -7.3, 0.0]), view=view)

    _box(
        ax,
        10,
        3.6,
        100,
        5.8,
        "基础矩阵不再是精确常量。门控区域必须由相机位姿、云台、标定、检测和时间协方差共同传播得到。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.0,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_pose_uncertainty_3d.png")


def build_pixel_ray_depth_ambiguity():
    fig, ax = _canvas(
        "三维场景中的深度歧义",
        "同一个拦截机像素对应一条空间视线，沿线不同深度在二级节点像平面形成不同落点",
    )

    view = {"origin": (59.0, 25.0), "scale": 4.35, "azimuth": -5.0, "elevation": 25.0}
    camera_a = np.array([-8.0, -5.0, 1.0])
    camera_b = np.array([7.0, -5.0, 2.0])
    direction = np.array([6.0, 5.0, 5.0])
    direction /= np.linalg.norm(direction)
    candidates = [camera_a + distance * direction for distance in (6.5, 10.0, 14.0)]

    plane_center, plane_normal, _, _, plane_corners = _image_plane(
        camera_b,
        candidates[1],
        distance=3.2,
        width=5.5,
        height=4.0,
    )
    image_points = [
        _ray_plane_intersection(camera_b, candidate, plane_center, plane_normal)
        for candidate in candidates
    ]

    _polygon3d(ax, [camera_a, camera_b, candidates[-1]], face=BLUE_LIGHT, edge=BLUE, alpha=0.24, **view)
    _polygon3d(ax, plane_corners, face=GREEN_LIGHT, edge=GREEN, alpha=0.75, width=2.0, **view)
    _line3d(ax, camera_a, camera_b, color=GRAY, width=2.0, **view)
    _line3d(ax, camera_a, candidates[-1] + 1.2 * direction, color=BLUE, width=2.4, **view)

    labels = (
        ("近距离候选", (-2.5, 2.0)),
        ("中距离候选", (0.0, 3.0)),
        ("远距离候选", (3.0, 2.0)),
    )
    for candidate, image_point, (label, offset) in zip(candidates, image_points, labels):
        _line3d(ax, camera_b, candidate, color=GREEN, width=1.2, linestyle="--", **view)
        _point3d(ax, candidate, label, color=ORANGE, radius=0.9, offset=offset, **view)
        _point3d(ax, image_point, "", color=RED, radius=0.6, offset=(0.0, 0.0), **view)

    _point3d(ax, camera_a, "拦截机相机", color=BLUE, radius=1.1, offset=(-1.0, -2.5), **view)
    _point3d(ax, camera_b, "二级节点相机", color=GREEN, radius=1.1, offset=(0.0, -2.5), **view)
    plane_label = _project3d(plane_center, **view)
    _text(ax, plane_label[0] + 5.0, plane_label[1] + 5.0, "二级节点像平面", size=10.0, color=GREEN, bold=True)
    _text(ax, 59, 13.5, "浅蓝色三角面表示两相机光心和目标视线所在的极平面", size=9.8, color=BLUE, bold=True)
    _axes3d(ax, np.array([-10.0, -7.0, 0.0]), view=view)

    _box(
        ax,
        12,
        3.7,
        96,
        5.5,
        "三个候选在拦截机图像中是同一个像素；从二级节点观察时，因距离不同而落在三个不同位置。",
        fill=RED_LIGHT,
        edge=RED,
        text_color=RED,
        size=10.2,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_pixel_ray_depth_ambiguity.png")


def build_epipolar_candidate_region():
    fig, ax = _canvas(
        "极线约束与二级节点候选区",
        "相对位姿先给出极线，中心粗距离再把极线缩小为有限搜索区域",
    )

    ax.add_patch(Rectangle((6, 11), 78, 43, facecolor=BLUE_LIGHT, edgecolor=BLUE, linewidth=2.0, zorder=1))
    _text(ax, 45, 51.0, "二级节点图像", size=13.5, color=BLUE, bold=True)
    ax.plot([12, 78], [18, 47], color=GRAY, linewidth=2.0, linestyle="--", zorder=3)
    ax.plot([36, 60], [28.5, 39.0], color=ORANGE, linewidth=6.0, solid_capstyle="round", alpha=0.75, zorder=4)
    ax.add_patch(Ellipse((50, 34.7), 14, 8, angle=24, facecolor=GREEN_LIGHT, edgecolor=GREEN, linewidth=2.2, zorder=5))

    detections = ((27, 28, "检测甲", RED), (49, 34.5, "检测乙", GREEN), (67, 28, "检测丙", RED))
    for x, y, label, color in detections:
        ax.add_patch(Circle((x, y), 1.15, facecolor=color, edgecolor=WHITE, linewidth=1.0, zorder=7))
        _text(ax, x, y + 3.1, label, size=9.0, color=color, bold=True)
    _text(ax, 27, 17.0, "不在极线附近\n直接排除", size=9.5, color=RED, bold=True)
    _text(ax, 50, 24.0, "落入预测区域\n进入后续核对", size=9.5, color=GREEN, bold=True)

    steps = (
        (89, 44.5, "1  相机相对位姿", "生成完整极线", BLUE, BLUE_LIGHT),
        (89, 32.5, "2  中心粗距离", "限制为有限线段", ORANGE, ORANGE_LIGHT),
        (89, 20.5, "3  协方差传播", "形成预测误差椭圆", GREEN, GREEN_LIGHT),
    )
    for x, y, title, body, color, fill in steps:
        _box(ax, x, y, 25, 8.0, f"{title}\n{body}", fill=fill, edge=color, size=9.5, bold=True, text_color=color)

    _box(
        ax,
        13,
        3.5,
        94,
        5.3,
        "极线只形成候选关系。实际检测、视线交会和多帧运动一致性共同决定是否为同一目标。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.0,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_epipolar_candidate_region.png")


def build_epipolar_plane_3d():
    fig, ax = _canvas(
        "极线在三维空间中的形成过程",
        "两个相机光心和拦截机的一条目标视线确定极平面；极平面与二级节点像平面的交线就是极线",
    )

    view = {"origin": (59.0, 20.5), "scale": 4.25, "azimuth": -4.0, "elevation": 25.0}
    camera_a = np.array([-8.0, -5.0, 1.0])
    camera_b = np.array([7.0, -5.0, 1.5])
    target = np.array([1.0, 2.0, 10.0])

    center_a, _, _, _, corners_a = _image_plane(camera_a, target, distance=2.4, width=3.2, height=2.2)
    center_b, normal_b, _, _, corners_b = _image_plane(camera_b, target, distance=3.1, width=5.2, height=3.8)
    plane_normal = np.cross(camera_b - camera_a, target - camera_a)
    plane_normal /= np.linalg.norm(plane_normal)
    epipolar_direction = np.cross(plane_normal, normal_b)
    epipolar_direction /= np.linalg.norm(epipolar_direction)
    line_start = center_b - 2.4 * epipolar_direction
    line_end = center_b + 2.4 * epipolar_direction

    _polygon3d(ax, [camera_a, camera_b, target], face=ORANGE_LIGHT, edge=ORANGE, alpha=0.42, width=2.0, **view)
    _polygon3d(ax, corners_a, face=BLUE_LIGHT, edge=BLUE, alpha=0.82, width=1.8, **view)
    _polygon3d(ax, corners_b, face=GREEN_LIGHT, edge=GREEN, alpha=0.82, width=2.0, **view)
    _line3d(ax, camera_a, camera_b, color=GRAY, width=2.2, **view)
    _line3d(ax, camera_a, target, color=BLUE, width=2.4, **view)
    _line3d(ax, camera_b, target, color=GREEN, width=2.2, linestyle="--", **view)
    _line3d(ax, line_start, line_end, color=RED, width=3.2, **view)

    _point3d(ax, camera_a, "拦截机相机光心", color=BLUE, radius=1.05, offset=(-1.0, -2.5), **view)
    _point3d(ax, camera_b, "二级节点相机光心", color=GREEN, radius=1.05, offset=(1.0, -2.5), **view)
    _point3d(ax, target, "空间目标", color=ORANGE, radius=1.0, offset=(0.0, -2.4), **view)
    _point3d(ax, center_a, "拦截机检测点", color=RED, radius=0.55, offset=(-2.5, 1.8), **view)
    _point3d(ax, center_b, "二级节点候选点", color=RED, radius=0.55, offset=(4.0, 2.0), **view)

    line_label = _project3d(line_end, **view)
    _text(ax, line_label[0] + 3.2, line_label[1] - 2.0, "极线", size=10.5, color=RED, bold=True)
    plane_label = _project3d((camera_a + camera_b + target) / 3.0, **view)
    _text(ax, plane_label[0], plane_label[1] + 7.0, "极平面", size=11.0, color=ORANGE, bold=True)
    _axes3d(ax, np.array([-10.0, -7.2, 0.0]), view=view)

    _box(
        ax,
        13,
        3.6,
        94,
        5.7,
        "二级节点的正确匹配点必须落在红色极线附近。多个检测同时靠近极线时，仍需距离、运动和一对一约束继续筛选。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.0,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_epipolar_plane_3d.png")


def build_dynamic_time_alignment_3d():
    fig, ax = _canvas(
        "异步拍摄下的运动补偿",
        "传统极线约束假设两个相机看到同一时刻的同一空间点；目标运动后必须先统一量测时刻",
    )

    _panel(ax, 3, 12, 54, 43, "直接比较两个拍摄时刻", RED, RED_LIGHT)
    _panel(ax, 63, 12, 54, 43, "预测到共同量测时刻", GREEN, GREEN_LIGHT)

    camera_a = np.array([-6.0, -4.0, 1.0])
    camera_b = np.array([6.0, -4.0, 1.2])
    target_t1 = np.array([-1.2, 2.0, 7.0])
    target_t2 = np.array([3.0, 3.0, 7.8])
    predicted_t2 = np.array([2.7, 2.8, 7.7])

    left_view = {"origin": (29.5, 25.5), "scale": 2.65, "azimuth": -5.0, "elevation": 25.0}
    _line3d(ax, camera_a, camera_b, color=GRAY, width=1.6, **left_view)
    _line3d(ax, camera_a, target_t1, color=BLUE, width=2.0, **left_view)
    _line3d(ax, camera_b, target_t1, color=GREEN, width=1.8, linestyle="--", **left_view)
    _point3d(ax, camera_a, "相机甲  时刻一", color=BLUE, radius=0.8, offset=(0.0, -2.2), **left_view)
    _point3d(ax, camera_b, "相机乙  时刻二", color=GREEN, radius=0.8, offset=(0.0, -2.2), **left_view)
    _point3d(ax, target_t1, "目标位置一", color=ORANGE, radius=0.85, offset=(-1.5, 2.0), **left_view)
    _point3d(ax, target_t2, "实际位置二", color=RED, radius=0.9, offset=(1.5, 2.0), **left_view)
    start = _project3d(target_t1, **left_view)
    end = _project3d(target_t2, **left_view)
    _arrow(ax, start, end, color=RED, width=2.0)
    _text(ax, 30, 17.2, "目标已从位置一运动到位置二\n直接使用静态极线会产生系统偏差", size=9.4, color=RED, bold=True)

    right_view = {"origin": (89.5, 25.5), "scale": 2.65, "azimuth": -5.0, "elevation": 25.0}
    _line3d(ax, camera_a, camera_b, color=GRAY, width=1.6, **right_view)
    _line3d(ax, camera_a, target_t1, color=BLUE, width=1.7, linestyle="--", **right_view)
    _line3d(ax, camera_b, predicted_t2, color=GREEN, width=2.2, **right_view)
    _point3d(ax, camera_a, "相机甲  时刻一", color=BLUE, radius=0.8, offset=(0.0, -2.2), **right_view)
    _point3d(ax, camera_b, "相机乙  时刻二", color=GREEN, radius=0.8, offset=(0.0, -2.2), **right_view)
    _point3d(ax, target_t1, "起始量测", color=ORANGE, radius=0.8, offset=(-1.0, 2.0), **right_view)
    _point3d(ax, predicted_t2, "预测位置二", color=GREEN, radius=0.9, offset=(-1.0, 2.0), **right_view)
    actual_xy = _project3d(target_t2, **right_view)
    ax.add_patch(Ellipse(actual_xy, 5.0, 3.2, angle=15, facecolor=GREEN_LIGHT, edgecolor=GREEN, linewidth=1.8, zorder=4))
    _point3d(ax, target_t2, "实际检测", color=RED, radius=0.75, offset=(2.0, -2.0), **right_view)
    start = _project3d(target_t1, **right_view)
    end = _project3d(predicted_t2, **right_view)
    _arrow(ax, start, end, color=ORANGE, width=2.0)
    _text(ax, 90, 17.2, "先按运动模型预测到时刻二\n再投影并按协方差形成门限", size=9.4, color=GREEN, bold=True)

    _box(
        ax,
        14,
        3.6,
        92,
        5.7,
        "运动补偿使用拍摄时间，不使用消息到达时间。时间差过大或目标机动超出模型时，极线候选降级为搜索提示。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.0,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_dynamic_time_alignment_3d.png")


def build_secondary_overlap_reprojection_3d():
    fig, ax = _canvas(
        "两视角交会与双向重投影",
        "中心—二级和二级—拦截机均用空间视线估计三维候选，再把候选投回两幅图像检查残差",
    )

    view = {"origin": (59.0, 19.5), "scale": 3.7, "azimuth": -12.0, "elevation": 25.0}
    interceptor = np.array([-8.0, -5.0, 1.5])
    secondary = np.array([8.0, -4.0, 5.0])
    target = np.array([1.0, 4.0, 8.5])

    center_i, normal_i, right_i, up_i, corners_i = _image_plane(
        interceptor,
        target,
        distance=3.0,
        width=4.8,
        height=3.5,
    )
    center_s, normal_s, right_s, up_s, corners_s = _image_plane(
        secondary,
        target,
        distance=3.0,
        width=4.8,
        height=3.5,
    )
    _polygon3d(ax, corners_i, face=BLUE_LIGHT, edge=BLUE, alpha=0.55, width=1.8, **view)
    _polygon3d(ax, corners_s, face=GREEN_LIGHT, edge=GREEN, alpha=0.55, width=1.8, **view)

    _line3d(ax, interceptor, target, color=BLUE, width=2.2, **view)
    _line3d(ax, secondary, target, color=GREEN, width=2.2, **view)
    _line3d(ax, interceptor, secondary, color=GRAY, width=1.3, linestyle="--", **view)

    reprojection_i = _ray_plane_intersection(interceptor, target, center_i, normal_i)
    reprojection_s = _ray_plane_intersection(secondary, target, center_s, normal_s)
    detection_i = reprojection_i + 0.16 * right_i - 0.10 * up_i
    detection_s = reprojection_s - 0.14 * right_s + 0.11 * up_s

    for reprojection, detection, plane_color in (
        (reprojection_i, detection_i, BLUE),
        (reprojection_s, detection_s, GREEN),
    ):
        projected = _project3d(reprojection, **view)
        measured = _project3d(detection, **view)
        ax.plot(
            [projected[0], measured[0]],
            [projected[1], measured[1]],
            color=RED,
            linewidth=2.0,
            zorder=9,
        )
        ax.add_patch(Circle(projected, 0.58, facecolor=RED, edgecolor=WHITE, linewidth=1.0, zorder=10))
        ax.add_patch(Circle(measured, 0.82, facecolor=WHITE, edgecolor=plane_color, linewidth=2.0, zorder=9))

    _point3d(ax, interceptor, "拦截机相机", color=BLUE, radius=1.0, offset=(0.0, -2.5), **view)
    _point3d(ax, secondary, "二级节点相机", color=GREEN, radius=1.0, offset=(3.8, -2.8), **view)
    _point3d(ax, target, "三维交会候选", color=ORANGE, radius=1.0, offset=(0.0, 2.4), **view)

    label_i = _project3d(center_i, **view)
    label_s = _project3d(center_s, **view)
    _text(ax, label_i[0] - 2.0, label_i[1] + 5.4, "拦截机像平面", size=9.4, color=BLUE, bold=True)
    _text(ax, label_s[0] + 1.0, label_s[1] + 5.7, "二级节点像平面", size=9.4, color=GREEN, bold=True)
    _text(ax, label_i[0] + 8.0, label_i[1] - 6.0, "检测点与重投影点", size=8.7, color=RED, bold=True)
    _text(ax, label_s[0] - 3.0, label_s[1] - 5.2, "检测点与重投影点", size=8.7, color=RED, bold=True)
    _axes3d(ax, np.array([-11.0, -8.0, 0.0]), view=view)

    _box(
        ax,
        12,
        3.7,
        96,
        5.6,
        "两条视线的最近距离、正深度和双向重投影残差均通过门限时，才保留为同一目标候选；单次交会不直接确认身份。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=9.9,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_secondary_overlap_reprojection_3d.png")


def build_identity_evidence_chain():
    fig, ax = _canvas(
        "同一目标的五级证据链",
        "每一级都缩小候选范围，单帧几何吻合不直接形成确定身份",
    )

    stages = (
        (3, "时间对齐", "使用拍摄时刻\n补偿扫描与通信延迟", BLUE, BLUE_LIGHT),
        (27, "极线门控", "排除不满足\n相机几何的候选", ORANGE, ORANGE_LIGHT),
        (51, "视线交会", "检查空间距离\n正深度和任务空域", GREEN, GREEN_LIGHT),
        (75, "重投影与航迹", "核对两幅图像\n和扇区基准航迹", BLUE, BLUE_LIGHT),
        (99, "整体匹配", "一对一约束\n连续多帧确认", GREEN, GREEN_LIGHT),
    )
    for index, (x, title, body, color, fill) in enumerate(stages):
        _box(ax, x, 37, 18, 14, f"{index + 1}  {title}\n{body}", fill=fill, edge=color, size=9.3, bold=True, text_color=color)
        if index < len(stages) - 1:
            _arrow(ax, (x + 18.5, 44), (stages[index + 1][0] - 0.5, 44), color=GRAY, width=1.8)

    _arrow(ax, (108, 36.0), (108, 28.5), color=GREEN, width=2.0)
    _box(ax, 91, 19, 25, 8.5, "候选唯一且持续稳定\n确认只读身份映射", fill=GREEN_LIGHT, edge=GREEN, text_color=GREEN, size=10.0, bold=True)

    _arrow(ax, (60, 36.0), (60, 28.5), color=ORANGE, width=2.0)
    _box(ax, 47.5, 19, 25, 8.5, "候选接近或几何退化\n保持多个身份假设", fill=ORANGE_LIGHT, edge=ORANGE, text_color=ORANGE, size=10.0, bold=True)

    _arrow(ax, (12, 36.0), (12, 28.5), color=RED, width=2.0)
    _box(ax, 3, 19, 18, 8.5, "时间或数据失效\n排除或重新搜索", fill=RED_LIGHT, edge=RED, text_color=RED, size=9.5, bold=True)

    _box(
        ax,
        20,
        5.0,
        80,
        7.0,
        "证据不足时继续观察。图网络和外观评分不能越过时间、几何和一对一约束。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.5,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_five_stage_evidence_chain.png")


def build_coarse_track_overlap():
    fig, ax = _canvas(
        "三维扇区基准航迹的可分与重叠",
        "中心与二级节点完成第一阶段配准后仍保留协方差；误差体重叠时不能向拦截无人机传递确定身份",
    )

    _panel(ax, 4, 12, 53, 43, "候选可分", GREEN, GREEN_LIGHT)
    left_view = {"origin": (30.0, 20.5), "scale": 2.7, "azimuth": -12.0, "elevation": 25.0}
    left_camera = np.array([-6.0, -5.0, 1.0])
    left_targets = (np.array([-1.5, 2.0, 6.0]), np.array([5.0, 3.0, 6.7]))
    _line3d(ax, left_camera, left_targets[0], color=GREEN, width=2.0, **left_view)
    _point3d(ax, left_camera, "本机相机", color=GREEN, radius=0.8, offset=(0.0, -2.0), **left_view)
    for target, label, color in zip(left_targets, ("航迹甲", "航迹乙"), (BLUE, ORANGE)):
        xy = _project3d(target, **left_view)
        ax.add_patch(Ellipse(xy, 10.0, 6.0, angle=12, facecolor=BLUE_LIGHT if color == BLUE else ORANGE_LIGHT, edgecolor=color, linewidth=2.0, alpha=0.85, zorder=3))
        _point3d(ax, target, label, color=color, radius=0.72, offset=(0.0, 2.6), **left_view)
    _point3d(ax, left_targets[0] + np.array([0.2, -0.1, 0.0]), "局部检测", color=RED, radius=0.5, offset=(0.0, -2.0), **left_view)
    _axes3d(ax, np.array([-8.0, -7.0, 0.0]), view=left_view)
    _text(ax, 30.5, 16.2, "预测误差体相互分离\n局部检测只有一个候选", size=9.5, color=GREEN, bold=True)

    _panel(ax, 63, 12, 53, 43, "候选重叠", RED, RED_LIGHT)
    right_view = {"origin": (89.5, 20.5), "scale": 2.7, "azimuth": -12.0, "elevation": 25.0}
    right_camera = np.array([-6.0, -5.0, 1.0])
    right_targets = (np.array([0.0, 2.0, 6.0]), np.array([2.2, 2.5, 6.2]))
    detection = (right_targets[0] + right_targets[1]) / 2.0
    _line3d(ax, right_camera, detection, color=RED, width=2.0, **right_view)
    _point3d(ax, right_camera, "本机相机", color=RED, radius=0.8, offset=(0.0, -2.0), **right_view)
    for target, label, color, angle in zip(right_targets, ("航迹甲", "航迹乙"), (BLUE, ORANGE), (15, -10)):
        xy = _project3d(target, **right_view)
        ax.add_patch(Ellipse(xy, 17.0, 10.0, angle=angle, facecolor=BLUE_LIGHT if color == BLUE else ORANGE_LIGHT, edgecolor=color, linewidth=2.0, alpha=0.72, zorder=3))
        _point3d(ax, target, label, color=color, radius=0.72, offset=(0.0, 3.2), **right_view)
    _point3d(ax, detection, "局部检测", color=RED, radius=0.55, offset=(0.0, -2.2), **right_view)
    _axes3d(ax, np.array([-8.0, -7.0, 0.0]), view=right_view)
    _text(ax, 89.5, 16.2, "预测误差体相互重叠\n保持待确认并调度复核", size=9.5, color=RED, bold=True)

    _box(
        ax,
        16,
        3.7,
        88,
        5.5,
        "扇区基准航迹误差覆盖目标间距时，只能用于指向云台，不能证明拦截无人机局部检测的身份。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.2,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_coarse_track_overlap.png")


def build_nonoverlap_handoff_3d():
    fig, ax = _canvas(
        "非共同视场的三维轨迹交接",
        "前一相机输出离场状态和空间走廊，后一相机按预测时间与方向形成入场短轨迹",
    )

    view = {"origin": (58.0, 19.5), "scale": 3.4, "azimuth": -18.0, "elevation": 25.0}
    camera_a = np.array([-9.0, -6.0, 2.0])
    camera_b = np.array([9.0, -4.0, 3.0])
    coordinator = np.array([0.0, -2.0, 10.0])
    path = (
        np.array([-5.0, 0.0, 7.0]),
        np.array([-2.0, 1.5, 7.5]),
        np.array([2.0, 3.0, 8.0]),
        np.array([6.0, 4.5, 7.6]),
    )

    _polygon3d(ax, [camera_a, path[0] - np.array([1.0, 0.5, 0.0]), path[1] + np.array([0.5, 0.5, 0.0])], face=BLUE_LIGHT, edge=BLUE, alpha=0.3, width=1.7, **view)
    _polygon3d(ax, [camera_b, path[2] - np.array([0.5, 0.5, 0.0]), path[3] + np.array([1.0, 0.5, 0.0])], face=GREEN_LIGHT, edge=GREEN, alpha=0.3, width=1.7, **view)
    for start, end in zip(path[:-1], path[1:]):
        _line3d(ax, start, end, color=RED, width=2.8, **view)
        _line3d(ax, start + np.array([0.0, -0.7, 0.5]), end + np.array([0.0, -0.7, 0.5]), color=ORANGE, width=1.2, linestyle="--", **view)
        _line3d(ax, start + np.array([0.0, 0.7, -0.5]), end + np.array([0.0, 0.7, -0.5]), color=ORANGE, width=1.2, linestyle="--", **view)

    _line3d(ax, coordinator, path[2], color=ORANGE, width=1.5, linestyle="--", **view)
    _point3d(ax, camera_a, "相机甲", color=BLUE, radius=1.0, offset=(2.6, -2.7), **view)
    _point3d(ax, camera_b, "相机乙", color=GREEN, radius=1.0, offset=(0.0, -2.3), **view)
    _point3d(ax, coordinator, "二级节点或复核机", color=ORANGE, radius=1.0, offset=(0.0, 2.0), **view)
    _point3d(ax, path[1], "离场状态", color=BLUE, radius=0.85, offset=(-1.0, 2.0), **view)
    _point3d(ax, path[2], "入场候选", color=GREEN, radius=0.85, offset=(1.0, 2.0), **view)
    _text(ax, 57, 16.0, "橙色虚线表示随时间扩大的三维预测走廊", size=9.8, color=ORANGE, bold=True)
    _axes3d(ax, np.array([-13.0, -10.0, 0.0]), view=view)

    _box(
        ax,
        12,
        3.7,
        96,
        5.6,
        "预测走廊内只有一个入场短轨迹时才允许交接；多个候选同时进入时保留多假设并请求新的观察。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.0,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_nonoverlap_handoff_3d.png")


def _graph_node(ax, x: float, y: float, label: str, color: str) -> None:
    ax.add_patch(Circle((x, y), 2.0, facecolor=WHITE, edgecolor=color, linewidth=2.0, zorder=6))
    _text(ax, x, y, label, size=8.5, color=color, bold=True)


def build_graph_observability_boundary():
    fig, ax = _canvas(
        "轨迹关系图的可观测边界",
        "图网络可以综合已有候选边，无法跨越没有时间、几何或交接证据的断点",
    )

    panels = (
        (3, "关系连通", GREEN, GREEN_LIGHT),
        (43, "关系断开", RED, RED_LIGHT),
        (83, "主动补充后连通", BLUE, BLUE_LIGHT),
    )
    for x, title, color, fill in panels:
        _panel(ax, x, 13, 34, 41, title, color, fill)

    connected_nodes = ((10, 39, "甲1", BLUE), (20, 44, "乙1", GREEN), (29, 37, "丙1", ORANGE), (18, 27, "甲2", BLUE), (29, 24, "乙2", GREEN))
    connected_edges = ((0, 1), (1, 2), (0, 3), (3, 4), (2, 4))
    for a, b in connected_edges:
        ax.plot([connected_nodes[a][0], connected_nodes[b][0]], [connected_nodes[a][1], connected_nodes[b][1]], color=GRAY, linewidth=1.8, zorder=3)
    for node in connected_nodes:
        _graph_node(ax, *node)
    _text(ax, 20, 17.5, "时间与几何候选形成连通关系\n可以执行整体匹配", size=9.2, color=GREEN, bold=True)

    left_group = ((50, 39, "甲1", BLUE), (58, 31, "乙1", GREEN))
    right_group = ((68, 42, "丙1", ORANGE), (74, 29, "甲2", BLUE))
    ax.plot([50, 58], [39, 31], color=GRAY, linewidth=1.8, zorder=3)
    ax.plot([68, 74], [42, 29], color=GRAY, linewidth=1.8, zorder=3)
    for node in left_group + right_group:
        _graph_node(ax, *node)
    ax.plot([61, 65], [35, 36], color=RED, linewidth=2.0, linestyle="--", zorder=3)
    _text(ax, 63, 38.5, "无边", size=8.5, color=RED, bold=True)
    _text(ax, 60, 17.5, "没有共同观察和交接证据\n不能恢复跨组身份", size=9.2, color=RED, bold=True)

    bridge_nodes = ((90, 39, "甲1", BLUE), (99, 31, "乙1", GREEN), (110, 41, "丙1", ORANGE), (105, 47, "复核", RED))
    bridge_edges = ((0, 1), (1, 2), (0, 3), (3, 2))
    for a, b in bridge_edges:
        ax.plot([bridge_nodes[a][0], bridge_nodes[b][0]], [bridge_nodes[a][1], bridge_nodes[b][1]], color=GRAY, linewidth=1.8, zorder=3)
    for node in bridge_nodes:
        _graph_node(ax, *node)
    _text(ax, 100, 17.5, "二级节点或邻机复核增加新边\n候选关系重新连通", size=9.2, color=BLUE, bold=True)

    _box(
        ax,
        20,
        4.3,
        80,
        5.5,
        "连通只表示具备推断条件。最终身份仍需满足几何、一对一和连续多帧约束。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.0,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_graph_observability_boundary.png")


def build_active_baseline_observation():
    fig, ax = _canvas(
        "三维观察基线与定位误差",
        "候选不唯一时，通过二级节点凝视、邻机转向或平台机动增大两条空间视线的夹角",
    )

    _panel(ax, 4, 12, 52, 43, "观察基线过小", RED, RED_LIGHT)
    left_view = {"origin": (30.0, 20.0), "scale": 2.65, "azimuth": -14.0, "elevation": 25.0}
    left_a = np.array([-6.0, -5.0, 1.0])
    left_b = np.array([-3.0, -4.5, 1.3])
    left_target = np.array([5.0, 5.0, 8.0])
    _line3d(ax, left_a, left_b, color=GRAY, width=1.8, **left_view)
    _line3d(ax, left_a, left_target, color=BLUE, width=2.1, **left_view)
    _line3d(ax, left_b, left_target, color=GREEN, width=2.1, **left_view)
    target_xy = _project3d(left_target, **left_view)
    ax.add_patch(Ellipse(target_xy, 6.0, 16.0, angle=-35, facecolor=ORANGE_LIGHT, edgecolor=ORANGE, linewidth=1.8, alpha=0.85, zorder=3))
    _point3d(ax, left_a, "相机甲", color=BLUE, radius=0.8, offset=(0.0, -2.0), **left_view)
    _point3d(ax, left_b, "相机乙", color=GREEN, radius=0.8, offset=(0.0, 2.0), **left_view)
    _point3d(ax, left_target, "远距离目标", color=ORANGE, radius=0.9, offset=(0.0, 2.2), **left_view)
    _axes3d(ax, np.array([-8.0, -7.0, 0.0]), view=left_view)
    _text(ax, 30, 16.2, "基线小、视线近平行\n距离误差沿视线方向放大", size=9.5, color=RED, bold=True)

    _panel(ax, 64, 12, 52, 43, "主动形成较大基线", GREEN, GREEN_LIGHT)
    right_view = {"origin": (89.5, 20.0), "scale": 2.65, "azimuth": -14.0, "elevation": 25.0}
    right_a = np.array([-7.0, -5.0, 1.0])
    right_b = np.array([6.0, -3.0, 2.0])
    right_target = np.array([1.0, 5.0, 8.0])
    _line3d(ax, right_a, right_b, color=GRAY, width=1.8, **right_view)
    _line3d(ax, right_a, right_target, color=BLUE, width=2.2, **right_view)
    _line3d(ax, right_b, right_target, color=GREEN, width=2.2, **right_view)
    target_xy = _project3d(right_target, **right_view)
    ax.add_patch(Ellipse(target_xy, 4.2, 3.3, angle=5, facecolor=GREEN_LIGHT, edgecolor=GREEN, linewidth=1.8, zorder=3))
    _point3d(ax, right_a, "相机甲", color=BLUE, radius=0.8, offset=(0.0, -2.0), **right_view)
    _point3d(ax, right_b, "邻机复核", color=GREEN, radius=0.8, offset=(0.0, -2.0), **right_view)
    _point3d(ax, right_target, "同一候选目标", color=ORANGE, radius=0.9, offset=(0.0, 2.2), **right_view)
    _axes3d(ax, np.array([-9.0, -7.0, 0.0]), view=right_view)
    _text(ax, 90, 16.2, "基线和观察夹角增大\n空间交会误差收缩", size=9.5, color=GREEN, bold=True)

    _arrow(ax, (55.5, 33), (63.5, 33), color=ORANGE, width=2.2)
    _text(ax, 59.5, 36.5, "调度新视角", size=9.5, color=ORANGE, bold=True)

    _box(
        ax,
        12,
        3.8,
        96,
        5.5,
        "已进入末端稳定跟踪的无人机保持锁定；优先由二级节点、备用机或未承担末端任务的邻机执行复核。",
        fill=GRAY_LIGHT,
        edge=GRAY,
        size=10.0,
        bold=True,
    )
    return _save_and_validate(fig, "visual_registration_active_baseline_observation.png")


def main() -> None:
    builders = (
        build_overall_architecture_3d,
        build_pixel_ray_depth_ambiguity,
        build_epipolar_plane_3d,
        build_pose_uncertainty_3d,
        build_epipolar_candidate_region,
        build_dynamic_time_alignment_3d,
        build_secondary_overlap_reprojection_3d,
        build_identity_evidence_chain,
        build_coarse_track_overlap,
        build_nonoverlap_handoff_3d,
        build_graph_observability_boundary,
        build_active_baseline_observation,
    )
    for builder in builders:
        path = builder()
        print(path)


if __name__ == "__main__":
    main()
