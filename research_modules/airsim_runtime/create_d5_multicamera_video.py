#!/usr/bin/env python3
"""Render the D5 multi-camera AirSim branch as a synchronized process video."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import re
import statistics
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


VIDEO_SIZE = (1920, 1080)
MONTAGE_HEIGHT = 720
BACKGROUND = (14, 21, 29)
PANEL = (21, 31, 42)
GRID = (53, 68, 82)
TEXT = (233, 239, 244)
MUTED = (155, 169, 181)
GREEN = (79, 201, 139)
ORANGE = (245, 166, 35)
BLUE = (71, 155, 255)
TARGET_COLORS = [
    (255, 183, 77),
    (113, 204, 83),
    (54, 188, 235),
    (222, 93, 171),
    (75, 139, 245),
]
SNAPSHOT_PATTERN = re.compile(r"frame_(\d+)_t(\d+(?:\.\d+)?)s")
FRAME_ID_PATTERN = re.compile(r":(\d{4}):")


@dataclass(frozen=True)
class Snapshot:
    timestamp: float
    path: Path


@dataclass(frozen=True)
class FontSet:
    title: ImageFont.FreeTypeFont
    heading: ImageFont.FreeTypeFont
    body: ImageFont.FreeTypeFont
    small: ImageFont.FreeTypeFont
    tiny: ImageFont.FreeTypeFont


def _font_path() -> Path:
    candidates = (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/todesk/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No CJK font found for Chinese video labels")


def _fonts() -> FontSet:
    font_path = str(_font_path())
    return FontSet(
        title=ImageFont.truetype(font_path, 32),
        heading=ImageFont.truetype(font_path, 24),
        body=ImageFont.truetype(font_path, 20),
        small=ImageFont.truetype(font_path, 17),
        tiny=ImageFont.truetype(font_path, 14),
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _frame_index(row: dict[str, str]) -> int:
    match = FRAME_ID_PATTERN.search(row["frame_id"])
    if not match:
        raise ValueError(f"Cannot parse frame index from {row['frame_id']!r}")
    return int(match.group(1))


def _load_snapshots(branch_dir: Path) -> list[Snapshot]:
    snapshots: list[Snapshot] = []
    for path in branch_dir.glob("annotated_snapshots/*/montage_*.png"):
        match = SNAPSHOT_PATTERN.fullmatch(path.parent.name)
        if match:
            snapshots.append(Snapshot(timestamp=float(match.group(2)), path=path))
    snapshots.sort(key=lambda item: item.timestamp)
    if len(snapshots) < 2:
        raise FileNotFoundError(
            f"At least two annotated montage snapshots are required under {branch_dir}"
        )
    return snapshots


def _group_rows(
    candidates: Iterable[dict[str, str]],
) -> dict[int, list[dict[str, str]]]:
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        grouped[_frame_index(row)].append(row)
    return grouped


def _group_detection_counts(
    rows: Iterable[dict[str, str]],
) -> dict[int, dict[str, int]]:
    grouped: dict[int, dict[str, int]] = defaultdict(
        lambda: {"detections": 0, "cameras": 0}
    )
    for row in rows:
        frame_index = int(row["frame_index"])
        grouped[frame_index]["detections"] += int(row["online_detection_count"])
        grouped[frame_index]["cameras"] += 1
    return grouped


def _blend_montage(
    snapshots: list[Snapshot],
    images: list[Image.Image],
    timestamp: float,
) -> tuple[Image.Image, str]:
    times = [snapshot.timestamp for snapshot in snapshots]
    right_index = bisect.bisect_right(times, timestamp)
    if right_index <= 0:
        return images[0].copy(), f"{times[0]:.1f} s"
    if right_index >= len(snapshots):
        return images[-1].copy(), f"{times[-1]:.1f} s"
    left_index = right_index - 1
    left_time = times[left_index]
    right_time = times[right_index]
    alpha = (timestamp - left_time) / max(right_time - left_time, 1e-9)
    blended = Image.blend(images[left_index], images[right_index], alpha)
    label = f"{left_time:.1f}-{right_time:.1f} s 抽帧间淡化"
    return blended, label


def _interpolate_position(
    frames: list[dict[str, Any]],
    timestamps: list[float],
    timestamp: float,
    object_id: str,
) -> tuple[float, float, float]:
    right_index = bisect.bisect_right(timestamps, timestamp)
    left_index = max(0, right_index - 1)
    right_index = min(right_index, len(frames) - 1)
    left_frame = frames[left_index]
    right_frame = frames[right_index]

    def lookup(frame: dict[str, Any]) -> list[float]:
        for target in frame["truth_objects"]:
            if target["object_id"] == object_id:
                return target["position_ned"]
        raise KeyError(object_id)

    left = lookup(left_frame)
    right = lookup(right_frame)
    left_time = float(left_frame["timestamp"])
    right_time = float(right_frame["timestamp"])
    if right_time <= left_time:
        return tuple(float(value) for value in left)  # type: ignore[return-value]
    alpha = (timestamp - left_time) / (right_time - left_time)
    return tuple(
        float(a + alpha * (b - a)) for a, b in zip(left, right)
    )  # type: ignore[return-value]


def _nearest_frame_index(
    frames: list[dict[str, Any]], timestamps: list[float], timestamp: float
) -> int:
    index = bisect.bisect_right(timestamps, timestamp) - 1
    return int(frames[max(0, min(index, len(frames) - 1))]["frame_index"])


def _rounded_panel(
    image: Image.Image,
    box: tuple[int, int, int, int],
    radius: int = 8,
    fill: tuple[int, int, int] = PANEL,
) -> None:
    ImageDraw.Draw(image).rounded_rectangle(box, radius=radius, fill=fill)


def _fit_xy(
    north: float,
    east: float,
    plot_box: tuple[int, int, int, int],
    north_range: tuple[float, float],
    east_range: tuple[float, float],
) -> tuple[int, int]:
    left, top, right, bottom = plot_box
    x = left + (north - north_range[0]) / (
        north_range[1] - north_range[0]
    ) * (right - left)
    y = bottom - (east - east_range[0]) / (
        east_range[1] - east_range[0]
    ) * (bottom - top)
    return round(x), round(y)


def _plot_ranges(
    frames: list[dict[str, Any]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    north_values: list[float] = []
    east_values: list[float] = []
    for frame in frames:
        for target in frame["truth_objects"]:
            north_values.append(float(target["position_ned"][0]))
            east_values.append(float(target["position_ned"][1]))
    for camera in frames[0]["cameras"]:
        north_values.append(float(camera["position_ned"][0]))
        east_values.append(float(camera["position_ned"][1]))

    def padded(values: list[float]) -> tuple[float, float]:
        lower = min(values)
        upper = max(values)
        span = max(upper - lower, 10.0)
        padding = max(2.0, span * 0.1)
        return lower - padding, upper + padding

    return padded(north_values), padded(east_values)


def _nice_ticks(lower: float, upper: float, count: int = 6) -> list[float]:
    span = max(upper - lower, 1e-9)
    rough_step = span / max(count - 1, 1)
    magnitude = 10.0 ** math.floor(math.log10(rough_step))
    normalized = rough_step / magnitude
    if normalized <= 1.0:
        step = magnitude
    elif normalized <= 2.0:
        step = 2.0 * magnitude
    elif normalized <= 5.0:
        step = 5.0 * magnitude
    else:
        step = 10.0 * magnitude
    start = math.ceil(lower / step) * step
    ticks: list[float] = []
    value = start
    while value <= upper + step * 1e-6:
        ticks.append(value)
        value += step
    return ticks


def _tick_label(value: float) -> str:
    return f"{value:.0f}" if abs(value - round(value)) < 1e-6 else f"{value:.1f}"


def _dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    fill: tuple[int, int, int, int],
    width: int = 2,
    dash: int = 7,
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance <= 0:
        return
    count = max(1, math.ceil(distance / dash))
    for index in range(0, count, 2):
        t0 = index / count
        t1 = min(1.0, (index + 1) / count)
        draw.line(
            (
                start[0] + dx * t0,
                start[1] + dy * t0,
                start[0] + dx * t1,
                start[1] + dy * t1,
            ),
            fill=fill,
            width=width,
        )


def _track_id_to_target(global_track_id: str) -> str | None:
    match = re.fullmatch(r"G-(\d+)", global_track_id)
    if not match:
        return None
    target_number = int(match.group(1)) - 100
    if target_number <= 0:
        return None
    return f"TGT-{target_number:03d}"


def _owner_positions(frame: dict[str, Any]) -> dict[str, tuple[float, float, float]]:
    positions: dict[str, tuple[float, float, float]] = {}
    for camera in frame["cameras"]:
        positions[camera["owner_id"]] = tuple(
            float(value) for value in camera["position_ned"]
        )
    return positions


def _draw_header(
    image: Image.Image,
    fonts: FontSet,
    timestamp: float,
    sample_label: str,
) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        (520, 672, 1400, 714), radius=7, fill=(7, 13, 18, 218)
    )
    draw.text(
        (960, 693),
        f"AirSim 六路相机采样画面  |  仿真 {timestamp:05.2f} s  |  {sample_label}",
        font=fonts.small,
        fill=TEXT,
        anchor="mm",
    )
    image.alpha_composite(overlay)


def _draw_trajectory_panel(
    image: Image.Image,
    frames: list[dict[str, Any]],
    timestamps: list[float],
    timestamp: float,
    selected_rows: list[dict[str, str]],
    stable_count: int,
    fonts: FontSet,
) -> None:
    panel_box = (18, 738, 1192, 1062)
    plot_box = (72, 790, 1154, 1020)
    north_range, east_range = _plot_ranges(frames)
    _rounded_panel(image, panel_box)
    draw = ImageDraw.Draw(image)
    draw.text((42, 752), "目标运动与跨视角配准", font=fonts.heading, fill=TEXT)
    draw.text(
        (1165, 756),
        "NED俯视图；轨迹位置为离线真值，仅用于结果展示",
        font=fonts.tiny,
        fill=MUTED,
        anchor="ra",
    )

    for north in _nice_ticks(*north_range):
        x, _ = _fit_xy(north, 0, plot_box, north_range, east_range)
        draw.line((x, plot_box[1], x, plot_box[3]), fill=GRID, width=1)
        draw.text(
            (x, plot_box[3] + 8),
            _tick_label(north),
            font=fonts.tiny,
            fill=MUTED,
            anchor="ma",
        )
    for east in _nice_ticks(*east_range):
        _, y = _fit_xy(0, east, plot_box, north_range, east_range)
        draw.line((plot_box[0], y, plot_box[2], y), fill=GRID, width=1)
        draw.text(
            (plot_box[0] - 9, y),
            _tick_label(east),
            font=fonts.tiny,
            fill=MUTED,
            anchor="rm",
        )
    draw.text(
        ((plot_box[0] + plot_box[2]) // 2, 1044),
        "北向 / m",
        font=fonts.tiny,
        fill=MUTED,
        anchor="ma",
    )
    draw.text(
        (plot_box[0], plot_box[1] - 11),
        "东向 / m",
        font=fonts.tiny,
        fill=MUTED,
        anchor="la",
    )

    target_ids = [
        target["object_id"] for target in frames[0]["truth_objects"]
    ]
    current_positions = {
        target_id: _interpolate_position(
            frames, timestamps, timestamp, target_id
        )
        for target_id in target_ids
    }

    association_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    association_draw = ImageDraw.Draw(association_layer)
    camera_positions = _owner_positions(frames[0])
    unique_associations: set[tuple[str, str]] = set()
    for row in selected_rows:
        owner = row["camera_id"].split(":", 1)[0]
        target_id = _track_id_to_target(row["global_track_id"])
        if (
            target_id not in current_positions
            or owner not in camera_positions
            or (owner, target_id) in unique_associations
        ):
            continue
        unique_associations.add((owner, target_id))
        camera_position = camera_positions[owner]
        target_position = current_positions[target_id]
        start = _fit_xy(
            camera_position[0],
            camera_position[1],
            plot_box,
            north_range,
            east_range,
        )
        end = _fit_xy(
            target_position[0],
            target_position[1],
            plot_box,
            north_range,
            east_range,
        )
        stable = row["stable_cross_view_support"] == "True"
        color = (*GREEN, 82) if stable else (*ORANGE, 118)
        if stable:
            association_draw.line((start, end), fill=color, width=2)
        else:
            _dashed_line(association_draw, start, end, color)
    image.alpha_composite(association_layer)
    draw = ImageDraw.Draw(image)

    for target_index, target_id in enumerate(target_ids):
        color = TARGET_COLORS[target_index % len(TARGET_COLORS)]
        trail: list[tuple[int, int]] = []
        for frame in frames:
            if float(frame["timestamp"]) > timestamp:
                break
            for target in frame["truth_objects"]:
                if target["object_id"] == target_id:
                    north, east, _ = target["position_ned"]
                    trail.append(
                        _fit_xy(
                            north,
                            east,
                            plot_box,
                            north_range,
                            east_range,
                        )
                    )
                    break
        current = current_positions[target_id]
        current_px = _fit_xy(
            current[0], current[1], plot_box, north_range, east_range
        )
        if not trail or trail[-1] != current_px:
            trail.append(current_px)
        if len(trail) >= 2:
            draw.line(trail, fill=color, width=4)
        x, y = current_px
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color, outline=TEXT)
        draw.text(
            (x + 11, y - 2),
            f"G-{101 + target_index}",
            font=fonts.tiny,
            fill=color,
            anchor="lm",
        )

    for owner, (north, east, down) in camera_positions.items():
        x, y = _fit_xy(north, east, plot_box, north_range, east_range)
        if owner == "D5_Recon_1":
            draw.polygon(
                ((x, y - 10), (x + 10, y), (x, y + 10), (x - 10, y)),
                fill=(220, 229, 237),
                outline=BLUE,
            )
            draw.text(
                (x + 13, y + 13),
                "侦察节点 高差50m",
                font=fonts.tiny,
                fill=TEXT,
                anchor="la",
            )
        else:
            draw.rectangle(
                (x - 6, y - 6, x + 6, y + 6), fill=BLUE, outline=TEXT
            )
    state_color = GREEN if stable_count else ORANGE
    draw.text(
        (920, 1044),
        "实线：稳定注册" if stable_count else "虚线：初始候选",
        font=fonts.tiny,
        fill=state_color,
        anchor="ma",
    )


def _draw_metric_panel(
    image: Image.Image,
    timestamp: float,
    frame_index: int,
    final_frame_index: int,
    target_count: int,
    detection_summary: dict[str, int],
    selected_rows: list[dict[str, str]],
    fonts: FontSet,
) -> None:
    panel_box = (1210, 738, 1902, 1062)
    _rounded_panel(image, panel_box)
    draw = ImageDraw.Draw(image)
    selected_count = len(selected_rows)
    stable_rows = [
        row
        for row in selected_rows
        if row["stable_cross_view_support"] == "True"
    ]
    stable_count = len(stable_rows)
    stable_rate = stable_count / selected_count if selected_count else 0.0
    registered_tracks = sorted(
        {row["global_track_id"] for row in stable_rows}
    )
    candidate_tracks = sorted(
        {row["global_track_id"] for row in selected_rows}
    )
    status = "稳定注册" if stable_count else "候选建立"
    status_color = GREEN if stable_count else ORANGE

    draw.text((1238, 752), "配准状态", font=fonts.heading, fill=TEXT)
    draw.rounded_rectangle((1738, 748, 1876, 786), radius=7, fill=status_color)
    draw.text(
        (1807, 767),
        status,
        font=fonts.small,
        fill=(10, 18, 24),
        anchor="mm",
    )
    rows = (
        ("仿真时刻", f"{timestamp:05.2f} s"),
        ("状态帧", f"{frame_index:02d} / {final_frame_index:02d}"),
        ("六路检测框", str(detection_summary.get("detections", 0))),
        ("选中关联", str(selected_count)),
        ("稳定关联", str(stable_count)),
        ("稳定率", f"{stable_rate * 100:5.1f}%"),
    )
    y = 805
    for label, value in rows:
        draw.text((1242, y), label, font=fonts.small, fill=MUTED)
        draw.text(
            (1510, y), value, font=fonts.body, fill=TEXT, anchor="ra"
        )
        y += 34

    draw.line((1540, 804, 1540, 1008), fill=GRID, width=1)
    draw.text((1568, 805), "中心航迹注册", font=fonts.small, fill=MUTED)
    tracks = registered_tracks if registered_tracks else candidate_tracks
    for index in range(target_count):
        track_id = f"G-{101 + index}"
        active = track_id in tracks
        chip_color = TARGET_COLORS[index]
        chip_y = 844 + index * 32
        draw.ellipse(
            (1568, chip_y + 3, 1582, chip_y + 17),
            fill=chip_color if active else GRID,
        )
        draw.text(
            (1592, chip_y),
            f"{track_id}  {'已注册' if stable_count and active else '候选' if active else '未见'}",
            font=fonts.small,
            fill=TEXT if active else MUTED,
        )

    draw.rounded_rectangle((1238, 1017, 1878, 1049), radius=6, fill=(31, 47, 60))
    draw.text(
        (1558, 1033),
        "global_track_id 由中心维护  |  本地改写次数 0",
        font=fonts.small,
        fill=(177, 219, 248),
        anchor="mm",
    )


def _render_frame(
    frames: list[dict[str, Any]],
    timestamps: list[float],
    snapshots: list[Snapshot],
    montage_images: list[Image.Image],
    candidates_by_frame: dict[int, list[dict[str, str]]],
    detection_by_frame: dict[int, dict[str, int]],
    timestamp: float,
    fonts: FontSet,
) -> Image.Image:
    montage, sample_label = _blend_montage(
        snapshots, montage_images, timestamp
    )
    image = Image.new("RGBA", VIDEO_SIZE, (*BACKGROUND, 255))
    image.alpha_composite(montage.convert("RGBA"), (0, 0))
    _draw_header(image, fonts, timestamp, sample_label)
    frame_index = _nearest_frame_index(frames, timestamps, timestamp)
    selected_rows = [
        row
        for row in candidates_by_frame.get(frame_index, [])
        if row["selected"] == "True"
    ]
    stable_count = sum(
        row["stable_cross_view_support"] == "True" for row in selected_rows
    )
    _draw_trajectory_panel(
        image,
        frames,
        timestamps,
        timestamp,
        selected_rows,
        stable_count,
        fonts,
    )
    _draw_metric_panel(
        image,
        timestamp,
        frame_index,
        int(frames[-1]["frame_index"]),
        len(frames[0]["truth_objects"]),
        detection_by_frame.get(frame_index, {}),
        selected_rows,
        fonts,
    )
    return image.convert("RGB")


def _encode_video(
    output_path: Path,
    frame_iter: Iterable[Image.Image],
    fps: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{VIDEO_SIZE[0]}x{VIDEO_SIZE[1]}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame in frame_iter:
            process.stdin.write(frame.tobytes())
    finally:
        process.stdin.close()
    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a synchronized D5 multi-camera AirSim process video."
    )
    parser.add_argument(
        "branch_dir",
        type=Path,
        help="Experiment branch containing logs and annotated_snapshots.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output H.264 MP4 path.",
    )
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument(
        "--poster",
        type=Path,
        help="Optional PNG poster rendered at the temporal midpoint.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    branch_dir = args.branch_dir.resolve()
    frames = _load_jsonl(branch_dir / "blocks_frames.jsonl")
    frames.sort(key=lambda frame: float(frame["timestamp"]))
    timestamps = [float(frame["timestamp"]) for frame in frames]
    candidates_by_frame = _group_rows(
        _load_csv(branch_dir / "d5_multicamera_candidates.csv")
    )
    detection_by_frame = _group_detection_counts(
        _load_csv(branch_dir / "d5_multicamera_frame_metrics.csv")
    )
    snapshots = _load_snapshots(branch_dir)
    montage_images = [
        Image.open(snapshot.path).convert("RGB") for snapshot in snapshots
    ]
    for index, montage in enumerate(montage_images):
        if montage.size != (VIDEO_SIZE[0], MONTAGE_HEIGHT):
            montage_images[index] = montage.resize(
                (VIDEO_SIZE[0], MONTAGE_HEIGHT), Image.Resampling.LANCZOS
            )
    fonts = _fonts()
    duration = timestamps[-1]
    snapshot_interval_s = statistics.median(
        right.timestamp - left.timestamp
        for left, right in zip(snapshots, snapshots[1:])
    )
    frame_count = max(2, round(duration * args.fps))
    video_times = [
        index * duration / (frame_count - 1) for index in range(frame_count)
    ]

    if args.poster:
        poster = _render_frame(
            frames,
            timestamps,
            snapshots,
            montage_images,
            candidates_by_frame,
            detection_by_frame,
            duration / 2.0,
            fonts,
        )
        args.poster.parent.mkdir(parents=True, exist_ok=True)
        poster.save(args.poster)

    _encode_video(
        args.output,
        (
            _render_frame(
                frames,
                timestamps,
                snapshots,
                montage_images,
                candidates_by_frame,
                detection_by_frame,
                timestamp,
                fonts,
            )
            for timestamp in video_times
        ),
        args.fps,
    )
    print(
        json.dumps(
            {
                "branch_dir": str(branch_dir),
                "output": str(args.output.resolve()),
                "duration_s": duration,
                "fps": args.fps,
                "frame_count": frame_count,
                "resolution": list(VIDEO_SIZE),
                "snapshot_count": len(snapshots),
                "snapshot_interval_s": snapshot_interval_s,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
