"""Generate trajectory and registration figures from an anonymous test snapshot."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import warnings

import matplotlib

matplotlib.use("Agg")
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Unable to import Axes3D.*")
    import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import LineCollection
import numpy as np


ROOT = Path(__file__).resolve().parent
CASE_ROOT = ROOT / "outputs" / "scale_funnel_v3" / "targets_040"
SNAPSHOT = (
    CASE_ROOT
    / "dataset"
    / "snapshots"
    / "test"
    / "20284201"
    / "medium"
    / "revolution_06.json"
)
PUBLICATION = (
    CASE_ROOT
    / "results"
    / "publications"
    / "20284201"
    / "medium"
    / "revolution_06_gnn.json"
)
FIGURES = ROOT / "figures"

COLORS = (
    "#356A8A",
    "#C96D3B",
    "#2E8B57",
    "#8A5A9B",
    "#B58A24",
    "#2A8C9D",
    "#A9483D",
    "#657A35",
    "#6B7280",
    "#8C6A43",
)


@dataclass(frozen=True)
class JointFit:
    reference_time: float
    position_at_reference: np.ndarray
    velocity: np.ndarray
    rms_angular_residual_mrad: float
    design_condition_number: float


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


def _normalized(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError("zero-length direction")
    return vector / norm


def direction_to_angles_deg(direction: np.ndarray) -> tuple[float, float]:
    direction = _normalized(np.asarray(direction, dtype=float))
    azimuth = np.degrees(np.arctan2(direction[1], direction[0]))
    elevation = np.degrees(
        np.arctan2(-direction[2], np.hypot(direction[0], direction[1]))
    )
    return float(azimuth), float(elevation)


def fit_joint_constant_velocity(
    track_a: dict[str, object],
    track_b: dict[str, object],
    camera_positions: dict[str, np.ndarray],
) -> JointFit:
    observations: list[tuple[float, np.ndarray, np.ndarray]] = []
    for camera_id, track in (("Optical_A", track_a), ("Optical_B", track_b)):
        camera_position = np.asarray(camera_positions[camera_id], dtype=float)
        for sample in track["samples"]:
            observations.append(
                (
                    float(sample["timestamp"]),
                    camera_position,
                    _normalized(np.asarray(sample["direction_ned"], dtype=float)),
                )
            )
    if len(observations) < 4:
        raise ValueError("joint fitting requires at least four sight-line samples")

    reference_time = float(np.mean([item[0] for item in observations]))
    design_rows: list[np.ndarray] = []
    right_rows: list[np.ndarray] = []
    for timestamp, camera_position, direction in observations:
        projection = np.eye(3) - np.outer(direction, direction)
        design_rows.append(
            np.hstack(
                [projection, (timestamp - reference_time) * projection]
            )
        )
        right_rows.append(projection @ camera_position)
    design = np.vstack(design_rows)
    right = np.hstack(right_rows)
    solution, *_ = np.linalg.lstsq(design, right, rcond=None)
    position = solution[:3]
    velocity = solution[3:]

    residuals: list[float] = []
    for timestamp, camera_position, direction in observations:
        fitted_position = position + velocity * (timestamp - reference_time)
        predicted = _normalized(fitted_position - camera_position)
        angle = np.arccos(np.clip(float(predicted @ direction), -1.0, 1.0))
        residuals.append(float(angle * 1000.0))
    return JointFit(
        reference_time=reference_time,
        position_at_reference=position,
        velocity=velocity,
        rms_angular_residual_mrad=float(np.sqrt(np.mean(np.square(residuals)))),
        design_condition_number=float(np.linalg.cond(design)),
    )


def _track_index(snapshot: dict[str, object]) -> dict[str, dict[str, dict[str, object]]]:
    return {
        camera_id: {track["track_id"]: track for track in tracks}
        for camera_id, tracks in snapshot["tracks"].items()
    }


def _evaluate_matches(
    snapshot: dict[str, object], publication: dict[str, object]
) -> list[dict[str, object]]:
    tracks = _track_index(snapshot)
    camera_positions = {
        key: np.asarray(value, dtype=float)
        for key, value in snapshot["camera_positions_ned"].items()
    }
    evaluated: list[dict[str, object]] = []
    for match in publication["matches"]:
        track_a = tracks["Optical_A"].get(match["track_a_id"])
        track_b = tracks["Optical_B"].get(match["track_b_id"])
        if track_a is None or track_b is None:
            continue
        fit = fit_joint_constant_velocity(track_a, track_b, camera_positions)
        evaluated.append(
            {
                "match": match,
                "track_a": track_a,
                "track_b": track_b,
                "fit": fit,
            }
        )
    return sorted(
        evaluated,
        key=lambda row: (
            row["fit"].rms_angular_residual_mrad,
            -min(len(row["track_a"]["samples"]), len(row["track_b"]["samples"])),
        ),
    )


def _track_series(track: dict[str, object]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    timestamps: list[float] = []
    azimuths: list[float] = []
    elevations: list[float] = []
    for sample in track["samples"]:
        timestamps.append(float(sample["timestamp"]))
        state = sample.get("state_vector")
        if state is not None:
            azimuths.append(float(state[0]))
            elevations.append(float(state[1]))
        else:
            azimuth, elevation = direction_to_angles_deg(sample["direction_ned"])
            azimuths.append(azimuth)
            elevations.append(elevation)
    return np.asarray(timestamps), np.asarray(azimuths), np.asarray(elevations)


def draw_local_trajectories(selected: list[dict[str, object]]) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8.6))
    fig.subplots_adjust(
        left=0.07,
        right=0.98,
        top=0.89,
        bottom=0.14,
        hspace=0.36,
        wspace=0.18,
    )
    panels = (
        (axes[0, 0], "track_a", 1, "A站方位轨迹", "方位角（度）"),
        (axes[0, 1], "track_b", 1, "B站方位轨迹", "方位角（度）"),
        (axes[1, 0], "track_a", 2, "A站俯仰轨迹", "俯仰角（度）"),
        (axes[1, 1], "track_b", 2, "B站俯仰轨迹", "俯仰角（度）"),
    )
    for axis, track_key, value_index, title, ylabel in panels:
        for pair_index, row in enumerate(selected):
            timestamps, azimuths, elevations = _track_series(row[track_key])
            values = azimuths if value_index == 1 else elevations
            axis.plot(
                timestamps,
                values,
                marker="o",
                markersize=4.5,
                linewidth=1.8,
                color=COLORS[pair_index],
                label=f"关系{pair_index + 1}",
            )
        axis.set_title(title, fontsize=13, weight="bold")
        axis.set_xlabel("测量时刻（秒）")
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.22)
    axes[0, 0].legend(ncol=2, frameon=False, fontsize=9)
    fig.suptitle("两站匿名局部轨迹历史", fontsize=17, weight="bold")
    fig.text(
        0.5,
        0.025,
        "同一颜色表示算法最终给出的双站对应关系；颜色仅用于解释算法输出，不代表在线使用真实身份。",
        ha="center",
        fontsize=9.5,
        color="#555555",
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    output = FIGURES / "15_local_track_histories.png"
    fig.savefig(output, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output


def _predicted_angles(
    fit: JointFit,
    camera_position: np.ndarray,
    timestamps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    azimuths: list[float] = []
    elevations: list[float] = []
    for timestamp in timestamps:
        position = fit.position_at_reference + fit.velocity * (
            float(timestamp) - fit.reference_time
        )
        azimuth, elevation = direction_to_angles_deg(position - camera_position)
        azimuths.append(azimuth)
        elevations.append(elevation)
    return np.asarray(azimuths), np.asarray(elevations)


def draw_joint_fit(
    row: dict[str, object], camera_positions: dict[str, np.ndarray]
) -> Path:
    track_a = row["track_a"]
    track_b = row["track_b"]
    fit: JointFit = row["fit"]
    score = float(row["match"]["score"])
    times_a, az_a, _ = _track_series(track_a)
    times_b, az_b, _ = _track_series(track_b)
    pred_az_a, _ = _predicted_angles(fit, camera_positions["Optical_A"], times_a)
    pred_az_b, _ = _predicted_angles(fit, camera_positions["Optical_B"], times_b)

    residual_time: list[float] = []
    residual_value: list[float] = []
    residual_camera: list[str] = []
    for camera_id, track in (("Optical_A", track_a), ("Optical_B", track_b)):
        camera_position = camera_positions[camera_id]
        for sample in track["samples"]:
            timestamp = float(sample["timestamp"])
            fitted_position = fit.position_at_reference + fit.velocity * (
                timestamp - fit.reference_time
            )
            predicted = _normalized(fitted_position - camera_position)
            observed = _normalized(np.asarray(sample["direction_ned"], dtype=float))
            residual_time.append(timestamp)
            residual_value.append(
                float(np.arccos(np.clip(predicted @ observed, -1.0, 1.0)) * 1000.0)
            )
            residual_camera.append(camera_id)

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9.4), constrained_layout=True)
    axis = axes[0, 0]
    all_times = np.linspace(
        min(float(times_a.min()), float(times_b.min())),
        max(float(times_a.max()), float(times_b.max())),
        80,
    )
    positions = np.asarray(
        [
            fit.position_at_reference + fit.velocity * (time - fit.reference_time)
            for time in all_times
        ]
    )
    axis.plot(positions[:, 0], positions[:, 1], color="#2E8B57", linewidth=2.4)
    for camera_id, marker, color in (
        ("Optical_A", "^", "#356A8A"),
        ("Optical_B", "^", "#C96D3B"),
    ):
        camera = camera_positions[camera_id]
        axis.scatter(camera[0], camera[1], marker=marker, s=90, color=color, zorder=4)
        axis.text(camera[0], camera[1] + 70, camera_id.replace("Optical_", "站"), ha="center")
        for sample_time in np.linspace(all_times.min(), all_times.max(), 3):
            point = fit.position_at_reference + fit.velocity * (
                sample_time - fit.reference_time
            )
            axis.plot(
                [camera[0], point[0]],
                [camera[1], point[1]],
                color=color,
                alpha=0.28,
                linewidth=1.0,
            )
    axis.scatter(positions[0, 0], positions[0, 1], s=45, color="#2E8B57")
    axis.annotate("起点", positions[0, :2], xytext=(6, 5), textcoords="offset points")
    axis.set_title("双站视线联合拟合的空间轨迹", fontsize=13, weight="bold")
    axis.set_xlabel("北向位置（米）")
    axis.set_ylabel("东向位置（米）")
    axis.grid(alpha=0.22)
    axis.set_aspect("equal", adjustable="datalim")

    for axis, times, observed, predicted, title, color in (
        (axes[0, 1], times_a, az_a, pred_az_a, "A站观测与重投影", "#356A8A"),
        (axes[1, 0], times_b, az_b, pred_az_b, "B站观测与重投影", "#C96D3B"),
    ):
        axis.scatter(times, observed, color=color, s=35, label="观测轨迹", zorder=3)
        axis.plot(times, predicted, color="#202833", linewidth=1.8, label="联合拟合重投影")
        axis.set_title(title, fontsize=13, weight="bold")
        axis.set_xlabel("测量时刻（秒）")
        axis.set_ylabel("方位角（度）")
        axis.grid(alpha=0.22)
        axis.legend(frameon=False)

    axis = axes[1, 1]
    for camera_id, color, label in (
        ("Optical_A", "#356A8A", "A站"),
        ("Optical_B", "#C96D3B", "B站"),
    ):
        selected = [
            (time, value)
            for time, value, camera in zip(
                residual_time, residual_value, residual_camera
            )
            if camera == camera_id
        ]
        axis.plot(
            [item[0] for item in selected],
            [item[1] for item in selected],
            marker="o",
            linewidth=1.6,
            color=color,
            label=label,
        )
    axis.axhline(
        fit.rms_angular_residual_mrad,
        color="#2E8B57",
        linestyle="--",
        linewidth=1.5,
        label=f"总体均方根 {fit.rms_angular_residual_mrad:.3f}毫弧度",
    )
    axis.set_title("联合拟合后的角残差", fontsize=13, weight="bold")
    axis.set_xlabel("测量时刻（秒）")
    axis.set_ylabel("角残差（毫弧度）")
    axis.grid(alpha=0.22)
    axis.legend(frameon=False, fontsize=9)

    speed = float(np.linalg.norm(fit.velocity))
    fig.suptitle("一组双站轨迹的联合拟合与重投影", fontsize=17, weight="bold")
    fig.text(
        0.5,
        0.005,
        f"匿名轨迹，图网络分数{score:.3f}，拟合速度{speed:.1f}米/秒，角残差均方根{fit.rms_angular_residual_mrad:.3f}毫弧度。",
        ha="center",
        fontsize=9.5,
        color="#555555",
    )
    output = FIGURES / "16_joint_track_fit_and_reprojection.png"
    fig.savefig(output, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output


def _draw_bipartite_panel(
    axis,
    aliases_a: dict[str, str],
    aliases_b: dict[str, str],
    edges: list[tuple[str, str]],
    selected_scores: dict[tuple[str, str], float],
    *,
    final_only: bool,
) -> None:
    axis.set_xlim(-0.12, 1.12)
    axis.set_ylim(-0.7, len(aliases_a) - 0.3)
    axis.axis("off")
    y_a = {track_id: len(aliases_a) - 1 - index for index, track_id in enumerate(aliases_a)}
    y_b = {track_id: len(aliases_b) - 1 - index for index, track_id in enumerate(aliases_b)}
    lines: list[list[tuple[float, float]]] = []
    for track_a, track_b in edges:
        if final_only and (track_a, track_b) not in selected_scores:
            continue
        lines.append([(0.08, y_a[track_a]), (0.92, y_b[track_b])])
    if not final_only:
        axis.add_collection(
            LineCollection(lines, colors="#AAB3BD", linewidths=0.8, alpha=0.32)
        )
    else:
        for line, edge_index in zip(lines, range(len(lines))):
            axis.plot(
                [line[0][0], line[1][0]],
                [line[0][1], line[1][1]],
                color=COLORS[edge_index % len(COLORS)],
                linewidth=2.0,
                alpha=0.9,
            )

    for track_id, alias in aliases_a.items():
        axis.scatter(0.05, y_a[track_id], s=170, color="#356A8A", zorder=3)
        axis.text(0.05, y_a[track_id], alias, color="white", ha="center", va="center", fontsize=8)
    for track_id, alias in aliases_b.items():
        axis.scatter(0.95, y_b[track_id], s=170, color="#C96D3B", zorder=3)
        axis.text(0.95, y_b[track_id], alias, color="white", ha="center", va="center", fontsize=8)
    axis.text(0.05, len(aliases_a) - 0.25, "A站轨迹", ha="center", weight="bold")
    axis.text(0.95, len(aliases_b) - 0.25, "B站轨迹", ha="center", weight="bold")


def draw_candidate_to_assignment(
    snapshot: dict[str, object], publication: dict[str, object]
) -> tuple[Path, int, int]:
    matches = list(publication["matches"][:10])
    aliases_a = {match["track_a_id"]: f"A{index + 1:02d}" for index, match in enumerate(matches)}
    aliases_b = {match["track_b_id"]: f"B{index + 1:02d}" for index, match in enumerate(matches)}
    candidate_edges = [
        (track_a, track_b)
        for track_a, track_b in snapshot["geometry_candidate_pairs"]
        if track_a in aliases_a and track_b in aliases_b
    ]
    selected_scores = {
        (match["track_a_id"], match["track_b_id"]): float(match["score"])
        for match in matches
    }
    selected_edges = [edge for edge in candidate_edges if edge in selected_scores]
    if len(selected_edges) != len(matches):
        raise RuntimeError("selected relations are missing from the candidate graph")

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 7.8), constrained_layout=True)
    _draw_bipartite_panel(
        axes[0],
        aliases_a,
        aliases_b,
        candidate_edges,
        selected_scores,
        final_only=False,
    )
    axes[0].set_title(
        f"候选筛选后：{len(candidate_edges)}条可能关系",
        fontsize=13,
        weight="bold",
    )
    _draw_bipartite_panel(
        axes[1],
        aliases_a,
        aliases_b,
        candidate_edges,
        selected_scores,
        final_only=True,
    )
    axes[1].set_title(
        f"图网络评分与一一选择后：{len(selected_edges)}条关系",
        fontsize=13,
        weight="bold",
    )
    fig.suptitle("候选关系收敛为一一配准结果", fontsize=17, weight="bold")
    fig.text(
        0.5,
        0.01,
        "局部编号只在本图中使用；左图灰线表示几何候选，右图彩线表示当前圈最终选择。",
        ha="center",
        fontsize=9.5,
        color="#555555",
    )
    output = FIGURES / "17_candidate_graph_to_assignment.png"
    fig.savefig(output, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output, len(candidate_edges), len(selected_edges)


def main() -> int:
    configure_font()
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    publication = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    evaluated = _evaluate_matches(snapshot, publication)
    selected = [
        row
        for row in evaluated
        if len(row["track_a"]["samples"]) >= 5
        and len(row["track_b"]["samples"]) >= 5
        and 30.0 <= float(np.linalg.norm(row["fit"].velocity)) <= 70.0
    ][:6]
    if len(selected) < 6:
        raise RuntimeError("insufficient mature matched trajectories for figures")
    joint_row = next(
        row
        for row in selected
        if len(row["track_a"]["samples"]) == 6
        and len(row["track_b"]["samples"]) == 6
    )
    camera_positions = {
        key: np.asarray(value, dtype=float)
        for key, value in snapshot["camera_positions_ned"].items()
    }

    outputs = [draw_local_trajectories(selected)]
    outputs.append(draw_joint_fit(joint_row, camera_positions))
    assignment_path, candidate_count, selected_count = draw_candidate_to_assignment(
        snapshot, publication
    )
    outputs.append(assignment_path)

    manifest = {
        "schema_version": "dual-optical-track-figure-manifest-v1",
        "source_snapshot": str(SNAPSHOT.relative_to(ROOT)),
        "source_publication": str(PUBLICATION.relative_to(ROOT)),
        "seed": int(snapshot["seed"]),
        "corruption_level": str(snapshot["corruption_level"]),
        "revolution_index": int(snapshot["revolution_index"]),
        "selected_local_pairs": [
            {
                "alias": f"relation_{index + 1}",
                "track_a_id": row["track_a"]["track_id"],
                "track_b_id": row["track_b"]["track_id"],
                "gnn_score": float(row["match"]["score"]),
                "joint_fit_rms_mrad": row["fit"].rms_angular_residual_mrad,
                "joint_fit_speed_mps": float(np.linalg.norm(row["fit"].velocity)),
            }
            for index, row in enumerate(selected)
        ],
        "joint_fit_example": {
            "track_a_id": joint_row["track_a"]["track_id"],
            "track_b_id": joint_row["track_b"]["track_id"],
            "gnn_score": float(joint_row["match"]["score"]),
            "rms_angular_residual_mrad": joint_row["fit"].rms_angular_residual_mrad,
            "speed_mps": float(np.linalg.norm(joint_row["fit"].velocity)),
            "design_condition_number": joint_row["fit"].design_condition_number,
        },
        "assignment_example": {
            "candidate_edge_count": candidate_count,
            "selected_edge_count": selected_count,
        },
        "figures": [str(path.relative_to(ROOT)) for path in outputs],
        "online_truth_used": False,
    }
    manifest_path = FIGURES / "track_registration_figure_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for output in outputs:
        print(output)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
