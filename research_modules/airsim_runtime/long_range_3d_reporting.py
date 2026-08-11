"""Three-dimensional reporting for completed D5 long-range AirSim episodes."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class TrajectorySeries:
    """One actor or camera trajectory sampled in the AirSim NED frame."""

    object_id: str
    frame_indices: np.ndarray
    timestamps_s: np.ndarray
    positions_ned_m: np.ndarray


def write_long_range_3d_trajectory_figures(
    episode_dir: Path,
    *,
    scenario_path: Path,
    output_dir: Path,
) -> tuple[dict[str, Path], dict[str, Any]]:
    """Render positions, trajectories, time slices, and association locations."""

    episode_dir = Path(episode_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = load_actor_trajectories(episode_dir / "actor_trajectory_truth.csv")
    interceptor = load_interceptor_trajectory(episode_dir / "scan_gimbal.csv")
    scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    center_position = np.asarray(
        scenario["scenario"]["center_position_ned"], dtype=float
    )
    association_events = load_association_event_positions(
        episode_dir / "associations.csv", targets
    )

    if not targets:
        raise ValueError("actor_trajectory_truth.csv contains no target trajectories")

    paths = {
        "global_trajectory_3d": output_dir / "airsim_3d_global_trajectory.png",
        "target_trajectory_detail_3d": output_dir
        / "airsim_3d_target_trajectory_detail.png",
        "time_slices_3d": output_dir / "airsim_3d_time_slices.png",
        "association_events_3d": output_dir / "airsim_3d_association_events.png",
        "trajectory_summary_json": output_dir / "airsim_3d_trajectory_summary.json",
    }

    _plot_global_trajectory(
        paths["global_trajectory_3d"], targets, interceptor, center_position
    )
    _plot_target_detail(
        paths["target_trajectory_detail_3d"], targets, interceptor
    )
    _plot_time_slices(paths["time_slices_3d"], targets, interceptor)
    _plot_association_events(
        paths["association_events_3d"], targets, interceptor, association_events
    )

    summary = build_trajectory_summary(
        targets=targets,
        interceptor=interceptor,
        center_position_ned_m=center_position,
        association_events=association_events,
        scenario=scenario,
    )
    paths["trajectory_summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return paths, summary


def load_actor_trajectories(path: Path) -> dict[str, TrajectorySeries]:
    """Load offline actor trajectories without exposing them to online matching."""

    grouped: dict[str, list[tuple[int, float, np.ndarray]]] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            object_id = str(row["object_id"])
            grouped.setdefault(object_id, []).append(
                (
                    int(row["frame_index"]),
                    float(row["simulation_timestamp"]),
                    np.asarray(
                        [
                            float(row["px_ned_m"]),
                            float(row["py_ned_m"]),
                            float(row["pz_ned_m"]),
                        ],
                        dtype=float,
                    ),
                )
            )
    return {
        object_id: _series_from_rows(object_id, rows)
        for object_id, rows in sorted(grouped.items(), key=lambda item: _numeric_id(item[0]))
    }


def load_interceptor_trajectory(path: Path) -> TrajectorySeries:
    """Load the ComputerVision interceptor camera trajectory."""

    rows: list[tuple[int, float, np.ndarray]] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                (
                    int(row["frame_index"]),
                    float(row["measurement_timestamp"]),
                    np.asarray(
                        [
                            float(row["interceptor_position_x"]),
                            float(row["interceptor_position_y"]),
                            float(row["interceptor_position_z"]),
                        ],
                        dtype=float,
                    ),
                )
            )
    if not rows:
        raise ValueError("scan_gimbal.csv contains no interceptor trajectory")
    return _series_from_rows("Interceptor_CV", rows)


def load_association_event_positions(
    path: Path,
    targets: Mapping[str, TrajectorySeries],
) -> dict[str, np.ndarray]:
    """Map association events to target truth positions for offline plots only."""

    if not Path(path).exists():
        return {}
    frame_lookup = {
        object_id: {
            int(frame): position
            for frame, position in zip(series.frame_indices, series.positions_ned_m)
        }
        for object_id, series in targets.items()
    }
    seen: set[tuple[str, int, str]] = set()
    grouped: dict[str, list[np.ndarray]] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            camera = str(row["camera_id"]).split(":", 1)[0]
            frame = int(row["frame_index"])
            global_track_id = str(row["global_track_id"])
            key = (camera, frame, global_track_id)
            if key in seen:
                continue
            seen.add(key)
            object_id = _object_id_from_global_track(global_track_id)
            position = frame_lookup.get(object_id, {}).get(frame)
            if position is not None:
                grouped.setdefault(camera, []).append(position)
    return {
        camera: np.asarray(positions, dtype=float)
        for camera, positions in grouped.items()
    }


def build_trajectory_summary(
    *,
    targets: Mapping[str, TrajectorySeries],
    interceptor: TrajectorySeries,
    center_position_ned_m: np.ndarray,
    association_events: Mapping[str, np.ndarray],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    """Build auditable position and path-length statistics for the report."""

    target_series = list(targets.values())
    all_positions = np.vstack([series.positions_ned_m for series in target_series])
    starts = np.vstack([series.positions_ned_m[0] for series in target_series])
    ends = np.vstack([series.positions_ned_m[-1] for series in target_series])
    path_lengths = np.asarray(
        [_path_length(series.positions_ned_m) for series in target_series], dtype=float
    )
    interceptor_path = _path_length(interceptor.positions_ned_m)
    duration_s = max(float(series.timestamps_s[-1]) for series in target_series)

    return {
        "schema_version": "d5-long-range-3d-trajectory-report-v1",
        "evidence_boundary": {
            "airsim_actor_positions": "offline_truth_only",
            "association_event_positions": "offline_reporting_only",
            "online_association_modified": False,
        },
        "target_count": len(target_series),
        "duration_s": duration_s,
        "center_position_ned_m": center_position_ned_m.tolist(),
        "center_altitude_m": float(-center_position_ned_m[2]),
        "target_initial_north_range_m": _range(starts[:, 0]),
        "target_final_north_range_m": _range(ends[:, 0]),
        "target_all_east_range_m": _range(all_positions[:, 1]),
        "target_all_altitude_range_m": _range(-all_positions[:, 2]),
        "target_initial_distance_to_center_range_m": _range(
            np.linalg.norm(starts - center_position_ned_m, axis=1)
        ),
        "target_final_distance_to_center_range_m": _range(
            np.linalg.norm(ends - center_position_ned_m, axis=1)
        ),
        "target_path_length_m": {
            "minimum": float(path_lengths.min()),
            "mean": float(path_lengths.mean()),
            "maximum": float(path_lengths.max()),
        },
        "interceptor_start_ned_m": interceptor.positions_ned_m[0].tolist(),
        "interceptor_end_ned_m": interceptor.positions_ned_m[-1].tolist(),
        "interceptor_path_length_m": interceptor_path,
        "interceptor_displacement_m": float(
            np.linalg.norm(
                interceptor.positions_ned_m[-1] - interceptor.positions_ned_m[0]
            )
        ),
        "minimum_3d_target_separation_m": float(
            scenario.get("minimum_3d_separation_m", math.nan)
        ),
        "association_event_count_by_camera": {
            camera: int(len(positions))
            for camera, positions in sorted(association_events.items())
        },
    }


def _plot_global_trajectory(
    path: Path,
    targets: Mapping[str, TrajectorySeries],
    interceptor: TrajectorySeries,
    center_position: np.ndarray,
) -> None:
    plt = _pyplot()
    from matplotlib.lines import Line2D

    fig = plt.figure(figsize=(15, 9))
    ax = fig.add_subplot(111, projection="3d")
    colors = _target_colors(len(targets), plt)
    for color, series in zip(colors, targets.values()):
        north, east, altitude = _plot_coordinates(series.positions_ned_m)
        ax.plot(north, east, altitude, color=color, linewidth=1.5, alpha=0.8)
        ax.scatter(north[0], east[0], altitude[0], color=color, marker="o", s=25)
        ax.scatter(north[-1], east[-1], altitude[-1], color=color, marker="^", s=30)

    centroid = np.mean(
        np.stack([series.positions_ned_m for series in targets.values()]), axis=0
    )
    cn, ce, ca = _plot_coordinates(centroid)
    ax.plot(cn, ce, ca, color="#4d4d4d", linestyle=":", linewidth=2.0)

    north, east, altitude = _plot_coordinates(interceptor.positions_ned_m)
    ax.plot(north, east, altitude, color="#12355b", linewidth=3.0)
    ax.scatter(north[0], east[0], altitude[0], color="#12355b", marker="s", s=70)
    ax.scatter(north[-1], east[-1], altitude[-1], color="#12355b", marker="D", s=60)
    ax.scatter(
        center_position[0],
        center_position[1],
        -center_position[2],
        color="#c1121f",
        marker="*",
        s=220,
    )

    _format_3d_axis(ax, title="AirSim二十目标全局位置与轨迹", global_view=True)
    ax.legend(
        handles=[
            Line2D([0], [0], color="#6a6a6a", label="目标轨迹"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor="#4c78a8", label="初始位置"),
            Line2D([0], [0], marker="^", color="none", markerfacecolor="#4c78a8", label="结束位置"),
            Line2D([0], [0], color="#12355b", linewidth=3, label="拦截相机轨迹"),
            Line2D([0], [0], marker="*", color="none", markerfacecolor="#c1121f", markersize=14, label="中心相机"),
        ],
        loc="upper left",
        frameon=True,
    )
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_target_detail(
    path: Path,
    targets: Mapping[str, TrajectorySeries],
    interceptor: TrajectorySeries,
) -> None:
    plt = _pyplot()
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111, projection="3d")
    colors = _target_colors(len(targets), plt)
    all_target_positions = np.vstack(
        [series.positions_ned_m for series in targets.values()]
    )
    for color, (object_id, series) in zip(colors, targets.items()):
        north, east, altitude = _plot_coordinates(series.positions_ned_m)
        ax.plot(north, east, altitude, color=color, linewidth=2.0)
        ax.scatter(north[0], east[0], altitude[0], color=color, marker="o", s=32)
        ax.scatter(north[-1], east[-1], altitude[-1], color=color, marker="^", s=38)
        ax.text(
            north[-1], east[-1], altitude[-1] + 1.0, object_id.replace("TGT-", "T"),
            fontsize=7, color=color,
        )
    north, east, altitude = _plot_coordinates(interceptor.positions_ned_m)
    ax.plot(north, east, altitude, color="#12355b", linewidth=3.0, label="拦截相机")
    _set_target_limits(ax, all_target_positions, interceptor.positions_ned_m)
    _format_3d_axis(ax, title="目标群三维轨迹局部放大", global_view=False)
    ax.legend(loc="upper left")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_time_slices(
    path: Path,
    targets: Mapping[str, TrajectorySeries],
    interceptor: TrajectorySeries,
) -> None:
    plt = _pyplot()
    fig = plt.figure(figsize=(18, 13))
    duration = max(series.timestamps_s[-1] for series in targets.values())
    times = np.linspace(0.0, duration, 4)
    colors = _target_colors(len(targets), plt)
    all_target_positions = np.vstack(
        [series.positions_ned_m for series in targets.values()]
    )
    for subplot_index, time_s in enumerate(times, start=1):
        ax = fig.add_subplot(2, 2, subplot_index, projection="3d")
        for color, series in zip(colors, targets.values()):
            index = int(np.abs(series.timestamps_s - time_s).argmin())
            history = series.positions_ned_m[: index + 1]
            north, east, altitude = _plot_coordinates(history)
            ax.plot(north, east, altitude, color=color, linewidth=0.9, alpha=0.55)
            ax.scatter(north[-1], east[-1], altitude[-1], color=color, s=26)
        interceptor_index = int(np.abs(interceptor.timestamps_s - time_s).argmin())
        history = interceptor.positions_ned_m[: interceptor_index + 1]
        north, east, altitude = _plot_coordinates(history)
        ax.plot(north, east, altitude, color="#12355b", linewidth=2.4)
        ax.scatter(north[-1], east[-1], altitude[-1], color="#12355b", marker="D", s=48)
        _set_target_limits(ax, all_target_positions, interceptor.positions_ned_m)
        _format_3d_axis(ax, title=f"仿真时刻 {time_s:.1f} 秒", global_view=False)
        ax.tick_params(labelsize=7)
    fig.suptitle("二十目标三维位置随时间变化", fontsize=18)
    fig.subplots_adjust(wspace=0.04, hspace=0.12, top=0.92)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_association_events(
    path: Path,
    targets: Mapping[str, TrajectorySeries],
    interceptor: TrajectorySeries,
    association_events: Mapping[str, np.ndarray],
) -> None:
    plt = _pyplot()
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111, projection="3d")
    all_target_positions = np.vstack(
        [series.positions_ned_m for series in targets.values()]
    )
    for series in targets.values():
        north, east, altitude = _plot_coordinates(series.positions_ned_m)
        ax.plot(north, east, altitude, color="#8d99ae", linewidth=1.0, alpha=0.45)
    styles = {
        "Center_CV": ("#0077b6", "o", "中心相机关联事件"),
        "Interceptor_CV": ("#d0006f", "^", "拦截相机关联事件"),
    }
    for camera, positions in association_events.items():
        if len(positions) == 0:
            continue
        color, marker, label = styles.get(camera, ("#444444", ".", camera))
        north, east, altitude = _plot_coordinates(positions)
        ax.scatter(
            north, east, altitude, color=color, marker=marker, s=14,
            alpha=0.35, label=f"{label}（{len(positions)}）",
        )
    north, east, altitude = _plot_coordinates(interceptor.positions_ned_m)
    ax.plot(north, east, altitude, color="#12355b", linewidth=2.5, label="拦截相机轨迹")
    _set_target_limits(ax, all_target_positions, interceptor.positions_ned_m)
    _format_3d_axis(
        ax,
        title="配准事件在三维轨迹上的位置（离线回填）",
        global_view=False,
    )
    ax.legend(loc="upper left")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _series_from_rows(
    object_id: str, rows: Sequence[tuple[int, float, np.ndarray]]
) -> TrajectorySeries:
    ordered = sorted(rows, key=lambda row: (row[0], row[1]))
    return TrajectorySeries(
        object_id=object_id,
        frame_indices=np.asarray([row[0] for row in ordered], dtype=int),
        timestamps_s=np.asarray([row[1] for row in ordered], dtype=float),
        positions_ned_m=np.vstack([row[2] for row in ordered]),
    )


def _object_id_from_global_track(global_track_id: str) -> str:
    match = re.search(r"(\d+)$", global_track_id)
    if match is None:
        return global_track_id
    return f"TGT-{int(match.group(1)):03d}"


def _numeric_id(value: str) -> int:
    match = re.search(r"(\d+)$", value)
    return int(match.group(1)) if match else 0


def _path_length(positions: np.ndarray) -> float:
    if len(positions) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum())


def _range(values: np.ndarray) -> dict[str, float]:
    return {"minimum": float(np.min(values)), "maximum": float(np.max(values))}


def _plot_coordinates(positions_ned_m: np.ndarray) -> tuple[np.ndarray, ...]:
    return positions_ned_m[:, 0], positions_ned_m[:, 1], -positions_ned_m[:, 2]


def _target_colors(count: int, plt: Any) -> np.ndarray:
    return plt.get_cmap("turbo")(np.linspace(0.02, 0.98, count))


def _set_target_limits(
    ax: Any, target_positions: np.ndarray, interceptor_positions: np.ndarray
) -> None:
    combined = np.vstack([target_positions, interceptor_positions])
    north_padding = max(50.0, float(np.ptp(combined[:, 0])) * 0.04)
    east_padding = max(20.0, float(np.ptp(combined[:, 1])) * 0.06)
    altitude = -combined[:, 2]
    altitude_padding = max(5.0, float(np.ptp(altitude)) * 0.12)
    ax.set_xlim(combined[:, 0].min() - north_padding, combined[:, 0].max() + north_padding)
    ax.set_ylim(combined[:, 1].min() - east_padding, combined[:, 1].max() + east_padding)
    ax.set_zlim(altitude.min() - altitude_padding, altitude.max() + altitude_padding)


def _format_3d_axis(ax: Any, *, title: str, global_view: bool) -> None:
    ax.set_title(title, pad=18, fontsize=16)
    ax.set_xlabel("北向位置 / 米", labelpad=10)
    ax.set_ylabel("东向位置 / 米", labelpad=10)
    ax.set_zlabel("高度 / 米", labelpad=8)
    ax.view_init(elev=24, azim=-63)
    ax.grid(True, alpha=0.25)
    ax.set_box_aspect((3.2, 1.25, 0.65) if global_view else (2.5, 1.5, 0.8))


def _pyplot() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    # The workstation has system and user Matplotlib packages installed. Keep
    # mplot3d on the same package root as the imported Matplotlib version.
    import mpl_toolkits

    matching_toolkits = str(
        Path(matplotlib.__file__).resolve().parent.parent / "mpl_toolkits"
    )
    if matching_toolkits not in mpl_toolkits.__path__:
        mpl_toolkits.__path__.insert(0, matching_toolkits)
    from mpl_toolkits.mplot3d import Axes3D
    from matplotlib.projections import register_projection

    register_projection(Axes3D)
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    cjk_font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if cjk_font_path.exists():
        font_manager.fontManager.addfont(str(cjk_font_path))
        family = font_manager.FontProperties(fname=str(cjk_font_path)).get_name()
    else:
        family = "DejaVu Sans"
    plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt
