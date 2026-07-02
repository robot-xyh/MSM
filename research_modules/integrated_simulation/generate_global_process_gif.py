#!/usr/bin/env python3
"""Generate a 2D GIF that explains the integrated D1-D7 process flow.

The animation is an offline explanatory visualization. It uses synthetic
point-mass trajectories and abstract assignment lines; it does not model real
vehicle control, hardware behavior, or automatic disposition.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.patches import Circle, Ellipse, Polygon, Wedge
import numpy as np


@dataclass(frozen=True)
class MovingObject:
    object_id: str
    start: np.ndarray
    velocity: np.ndarray
    color: str

    def position(self, t: float) -> np.ndarray:
        return self.start + self.velocity * t


TARGETS = [
    MovingObject("T1", np.array([-105.0, 66.0]), np.array([1.15, -0.42]), "#D62728"),
    MovingObject("T2", np.array([-120.0, 30.0]), np.array([1.35, -0.12]), "#D62728"),
    MovingObject("T3", np.array([-108.0, -8.0]), np.array([1.18, 0.18]), "#D62728"),
    MovingObject("T4", np.array([-95.0, -44.0]), np.array([1.02, 0.38]), "#D62728"),
    MovingObject("T5", np.array([-82.0, -75.0]), np.array([0.90, 0.55]), "#D62728"),
]

RESOURCES = [
    MovingObject("R1", np.array([95.0, 58.0]), np.array([-0.35, -0.12]), "#2CA02C"),
    MovingObject("R2", np.array([104.0, 28.0]), np.array([-0.38, -0.03]), "#2CA02C"),
    MovingObject("R3", np.array([105.0, -4.0]), np.array([-0.36, 0.06]), "#2CA02C"),
    MovingObject("R4", np.array([101.0, -35.0]), np.array([-0.34, 0.13]), "#2CA02C"),
    MovingObject("R5", np.array([92.0, -64.0]), np.array([-0.32, 0.19]), "#2CA02C"),
]

RADAR_POS = np.array([-128.0, -86.0])
ACOUSTIC_POS = np.array([-132.0, 82.0])
EO_POS = np.array([-118.0, 0.0])
CENTER_POS = np.array([15.0, -94.0])
SECONDARY_POS = np.array([35.0, 92.0])


def phase_for_frame(frame: int) -> tuple[str, str]:
    if frame < 16:
        return "D1 Multi-sensor observations", "Radar points, acoustic bearings, and EO field-of-view are asynchronous."
    if frame < 30:
        return "D1 Fusion + D2 association", "Noisy observations become covariance-aware GlobalTracks with stable IDs."
    if frame < 42:
        return "D3 Central assignment", "The center node computes a versioned 5v5 assignment plan."
    if frame < 58:
        return "D7 Radar PN midcourse", "Assigned resources follow GlobalTrack estimates with classical proportional navigation."
    if frame < 70:
        return "D4 Secondary reassignment", "Center plan is degraded; a secondary node swaps an ambiguous local assignment."
    return "D7 Vision PN terminal", "Terminal visual LOS evidence refines PN guidance after reassignment."


def target_positions(frame: int) -> dict[str, np.ndarray]:
    t = frame * 0.75
    positions: dict[str, np.ndarray] = {}
    for idx, target in enumerate(TARGETS):
        pos = target.position(t)
        if frame > 38 and target.object_id in {"T2", "T3"}:
            # A small crossing maneuver creates an association/reassignment event.
            pos = pos + np.array([0.0, 12.0 * np.sin((frame - 38) / 8.0 + idx)])
        positions[target.object_id] = pos
    return positions


def resource_positions(frame: int) -> dict[str, np.ndarray]:
    t = frame * 0.75
    positions: dict[str, np.ndarray] = {}
    assignments = current_assignment(frame)
    targets = target_positions(frame)
    for idx, resource in enumerate(RESOURCES):
        base = resource.position(t)
        target_id = assignments.get(resource.object_id)
        if target_id is not None:
            target = targets[target_id]
            if frame < 42:
                alpha = 0.10
                base = (1.0 - alpha) * base + alpha * target
            elif frame < 62:
                progress = np.clip((frame - 42) / 22.0, 0.0, 0.72)
                base = _guided_curve(resource.start, target, progress, bend=0.18 * (-1) ** idx)
            else:
                progress = np.clip((frame - 62) / 26.0, 0.18, 0.90)
                secondary_start = _guided_curve(resource.start, targets.get(current_assignment(50).get(resource.object_id, target_id), target), 0.55, bend=0.16 * (-1) ** idx)
                base = _guided_curve(secondary_start, target, progress, bend=0.11 * (-1) ** (idx + 1))
        positions[resource.object_id] = base
    return positions


def current_assignment(frame: int) -> dict[str, str]:
    if frame < 30:
        return {}
    if frame < 62:
        return {"R1": "T1", "R2": "T2", "R3": "T3", "R4": "T4", "R5": "T5"}
    # Secondary reassignment after an ID/geometry ambiguity around T2/T3.
    return {"R1": "T1", "R2": "T3", "R3": "T2", "R4": "T4", "R5": "T5"}


def _guided_curve(start: np.ndarray, target: np.ndarray, progress: float, bend: float) -> np.ndarray:
    progress = float(np.clip(progress, 0.0, 1.0))
    delta = target - start
    distance = max(float(np.linalg.norm(delta)), 1.0)
    normal = np.array([-delta[1], delta[0]], dtype=float) / distance
    control = 0.5 * (start + target) + normal * bend * distance
    return (1.0 - progress) ** 2 * start + 2.0 * (1.0 - progress) * progress * control + progress**2 * target


def fused_track_position(target_id: str, pos: np.ndarray, frame: int) -> np.ndarray:
    rng = np.random.default_rng(1000 + frame * 17 + int(target_id[-1]))
    sigma = max(1.0, 9.5 - 0.12 * frame)
    return pos + rng.normal(0.0, sigma, size=2)


def observation_position(pos: np.ndarray, target_id: str, frame: int) -> np.ndarray:
    rng = np.random.default_rng(3000 + frame * 23 + int(target_id[-1]))
    return pos + rng.normal(0.0, 5.5, size=2)


def covariance_size(frame: int, target_index: int) -> tuple[float, float, float]:
    width = max(8.0, 28.0 - 0.32 * frame + target_index * 0.6)
    height = max(5.0, 18.0 - 0.22 * frame + target_index * 0.4)
    angle = 15.0 + target_index * 22.0
    return width, height, angle


def draw_static_context(ax: plt.Axes, frame: int) -> None:
    ax.set_xlim(-145, 130)
    ax.set_ylim(-105, 110)
    ax.set_aspect("equal")
    ax.grid(True, color="#E5E7EB", linewidth=0.7)
    ax.set_xlabel("Global X")
    ax.set_ylabel("Global Y")

    phase, note = phase_for_frame(frame)
    ax.set_title(f"2D Global C-UAS Research Flow | {phase}", fontsize=13, loc="left")
    ax.text(-143, 101, note, fontsize=9, color="#374151", va="top")
    ax.text(
        72,
        -101,
        "Offline explanatory simulation only",
        fontsize=8,
        color="#6B7280",
        ha="left",
        va="bottom",
    )

    # Sensors.
    ax.scatter(*RADAR_POS, marker="s", s=95, color="#1F77B4", edgecolor="black", zorder=5)
    ax.text(*(RADAR_POS + np.array([3, 4])), "Radar", fontsize=8, color="#1F77B4")
    for radius in (45, 85, 125):
        ax.add_patch(Circle(RADAR_POS, radius, fill=False, linestyle=":", linewidth=0.9, color="#1F77B4", alpha=0.35))

    ax.scatter(*ACOUSTIC_POS, marker="^", s=95, color="#9467BD", edgecolor="black", zorder=5)
    ax.text(*(ACOUSTIC_POS + np.array([3, -8])), "Acoustic", fontsize=8, color="#9467BD")

    ax.scatter(*EO_POS, marker="D", s=85, color="#FF7F0E", edgecolor="black", zorder=5)
    ax.text(*(EO_POS + np.array([4, 4])), "EO/IR", fontsize=8, color="#FF7F0E")
    ax.add_patch(Wedge(EO_POS, 135, -34, 34, fill=True, color="#FF7F0E", alpha=0.08))
    ax.add_patch(Wedge(EO_POS, 135, -34, 34, fill=False, color="#FF7F0E", alpha=0.45, linewidth=1.2))

    # Nodes.
    ax.scatter(*CENTER_POS, marker="P", s=130, color="#111827", zorder=6)
    ax.text(*(CENTER_POS + np.array([4, -2])), "Center C2", fontsize=8, color="#111827")
    ax.scatter(*SECONDARY_POS, marker="*", s=180, color="#E377C2", edgecolor="black", zorder=6)
    ax.text(*(SECONDARY_POS + np.array([4, -2])), "Secondary node", fontsize=8, color="#9B287B")

    if frame >= 58:
        ax.plot(
            [CENTER_POS[0] - 5, CENTER_POS[0] + 5],
            [CENTER_POS[1] - 5, CENTER_POS[1] + 5],
            color="#B91C1C",
            linewidth=2.4,
            zorder=7,
        )
        ax.plot(
            [CENTER_POS[0] - 5, CENTER_POS[0] + 5],
            [CENTER_POS[1] + 5, CENTER_POS[1] - 5],
            color="#B91C1C",
            linewidth=2.4,
            zorder=7,
        )

    _draw_defense_bands(ax)


def _draw_defense_bands(ax: plt.Axes) -> None:
    for radius, label, color in [
        (120, "outer sensing", "#CBD5E1"),
        (80, "handover", "#BFDBFE"),
        (42, "terminal view", "#BBF7D0"),
    ]:
        ax.add_patch(Circle((0, 0), radius, fill=False, color=color, linewidth=1.0, linestyle="--", alpha=0.8))
        ax.text(radius - 25, 2.5, label, fontsize=7, color="#64748B")


def draw_sensor_observations(ax: plt.Axes, targets: dict[str, np.ndarray], frame: int) -> None:
    if frame >= 32:
        alpha = 0.35
    else:
        alpha = 0.75
    for target_id, pos in targets.items():
        obs = observation_position(pos, target_id, frame)
        ax.scatter(*obs, marker="x", s=42, color="#1F77B4", linewidth=1.3, alpha=alpha, zorder=4)
        ax.plot([RADAR_POS[0], obs[0]], [RADAR_POS[1], obs[1]], color="#1F77B4", alpha=0.12, linewidth=0.9)
        bearing_end = ACOUSTIC_POS + 135.0 * (pos - ACOUSTIC_POS) / max(np.linalg.norm(pos - ACOUSTIC_POS), 1.0)
        ax.plot([ACOUSTIC_POS[0], bearing_end[0]], [ACOUSTIC_POS[1], bearing_end[1]], color="#9467BD", alpha=0.14, linewidth=1.0)
        if frame < 32:
            ax.plot([EO_POS[0], pos[0]], [EO_POS[1], pos[1]], color="#FF7F0E", alpha=0.12, linewidth=1.0)


def draw_tracks(ax: plt.Axes, targets: dict[str, np.ndarray], frame: int) -> dict[str, np.ndarray]:
    fused: dict[str, np.ndarray] = {}
    for idx, (target_id, pos) in enumerate(targets.items(), start=1):
        track_pos = fused_track_position(target_id, pos, frame)
        fused[target_id] = track_pos
        if frame >= 12:
            width, height, angle = covariance_size(frame, idx)
            ax.add_patch(
                Ellipse(
                    track_pos,
                    width=width,
                    height=height,
                    angle=angle,
                    fill=False,
                    edgecolor="#2563EB",
                    linewidth=1.4,
                    alpha=0.80,
                    zorder=5,
                )
            )
            ax.scatter(*track_pos, s=65, color="#2563EB", edgecolor="white", linewidth=0.8, zorder=8)
            ax.text(track_pos[0] + 3.0, track_pos[1] + 3.0, f"G{idx}", fontsize=8, color="#1D4ED8")
        if frame >= 16:
            obs = observation_position(pos, target_id, frame)
            ax.plot([obs[0], track_pos[0]], [obs[1], track_pos[1]], color="#2563EB", linestyle="--", alpha=0.55, linewidth=1.0)
    return fused


def draw_truth_and_resources(
    ax: plt.Axes,
    targets: dict[str, np.ndarray],
    resources: dict[str, np.ndarray],
    frame: int,
) -> None:
    for target_id, pos in targets.items():
        ax.scatter(*pos, marker="o", s=55, color="#D62728", edgecolor="black", linewidth=0.6, zorder=9)
        ax.text(pos[0] + 2.5, pos[1] - 5.5, target_id, fontsize=8, color="#991B1B")
        trail = np.array([TARGETS[int(target_id[-1]) - 1].position(max(0, frame * 0.75 - k * 2.0)) for k in range(10)])
        ax.plot(trail[:, 0], trail[:, 1], color="#D62728", linewidth=1.0, alpha=0.25)

    for resource_id, pos in resources.items():
        ax.scatter(*pos, marker="s", s=55, color="#2CA02C", edgecolor="black", linewidth=0.6, zorder=9)
        ax.text(pos[0] + 2.5, pos[1] + 2.5, resource_id, fontsize=8, color="#166534")


def draw_assignment(ax: plt.Axes, fused: dict[str, np.ndarray], resources: dict[str, np.ndarray], frame: int) -> None:
    assignment = current_assignment(frame)
    if not assignment:
        return
    secondary_mode = frame >= 58
    for resource_id, target_id in assignment.items():
        if target_id not in fused:
            continue
        resource_pos = resources[resource_id]
        target_pos = fused[target_id]
        if frame < 42:
            color = "#16A34A"
            style = "-"
        elif frame < 58:
            color = "#2563EB"
            style = "-"
        elif frame < 70:
            color = "#DB2777"
            style = "--"
        else:
            color = "#059669"
            style = "-"
        ax.annotate(
            "",
            xy=target_pos,
            xytext=resource_pos,
            arrowprops=dict(arrowstyle="->", color=color, linewidth=1.7, linestyle=style, alpha=0.82),
            zorder=6,
        )
        mid = 0.52 * resource_pos + 0.48 * target_pos
        label = f"{resource_id}->{target_id}"
        if frame >= 42:
            label = f"PN {label}"
        ax.text(mid[0], mid[1], label, fontsize=6.8, color=color)

    if frame >= 42:
        draw_guidance_overlay(ax, fused, resources, assignment, frame)

    if frame >= 58:
        ax.annotate(
            "secondary reassignment\nT2/T3 plan swap",
            xy=SECONDARY_POS,
            xytext=(58, 76),
            arrowprops=dict(arrowstyle="->", color="#DB2777", linewidth=1.5),
            fontsize=8,
            color="#9B287B",
            bbox=dict(facecolor="white", edgecolor="#E377C2", alpha=0.9, boxstyle="round,pad=0.25"),
        )


def draw_guidance_overlay(
    ax: plt.Axes,
    fused: dict[str, np.ndarray],
    resources: dict[str, np.ndarray],
    assignment: dict[str, str],
    frame: int,
) -> None:
    if frame < 42:
        return
    if frame < 58:
        label = "Radar PN: GlobalTrack LOS rate"
        color = "#2563EB"
        text_xy = (-137, 91)
    elif frame < 70:
        label = "Secondary plan: PN task reset"
        color = "#DB2777"
        text_xy = (-137, 91)
    else:
        label = "Vision PN: terminal pixel/LOS refinement"
        color = "#059669"
        text_xy = (-137, 91)
    ax.text(
        text_xy[0],
        text_xy[1],
        label,
        fontsize=9,
        color=color,
        bbox=dict(facecolor="white", edgecolor=color, alpha=0.85, boxstyle="round,pad=0.25"),
        zorder=12,
    )
    for index, (resource_id, target_id) in enumerate(assignment.items()):
        if target_id not in fused:
            continue
        resource_pos = resources[resource_id]
        target_pos = fused[target_id]
        ax.plot(
            [resource_pos[0], target_pos[0]],
            [resource_pos[1], target_pos[1]],
            color=color,
            alpha=0.18,
            linewidth=5.0,
            solid_capstyle="round",
            zorder=3,
        )
        if index in {0, 2}:
            rel = target_pos - resource_pos
            los = np.degrees(np.arctan2(rel[1], rel[0]))
            ax.text(
                resource_pos[0] - 8,
                resource_pos[1] + 8,
                f"LOS {los:.0f} deg\nN=3",
                fontsize=6.7,
                color=color,
                ha="right",
            )


def draw_flow_panel(ax: plt.Axes, frame: int) -> None:
    steps = [
        ("D1", "Fusion", frame >= 8),
        ("D2", "Assoc", frame >= 16),
        ("D3", "Assign", frame >= 30),
        ("D7", "Radar PN", frame >= 42),
        ("D4", "Replan", frame >= 58),
        ("D7", "Vision PN", frame >= 70),
    ]
    x0, y0 = -139, -97
    for index, (code, label, active) in enumerate(steps):
        x = x0 + index * 44
        color = "#111827" if active else "#9CA3AF"
        face = "#E0F2FE" if active else "#F3F4F6"
        rect = Polygon(
            [[x, y0], [x + 36, y0], [x + 42, y0 + 8], [x + 36, y0 + 16], [x, y0 + 16]],
            closed=True,
            facecolor=face,
            edgecolor=color,
            linewidth=1.0,
            alpha=0.95,
            zorder=10,
        )
        ax.add_patch(rect)
        ax.text(x + 3, y0 + 9, f"{code} {label}", fontsize=7, color=color, va="center", zorder=11)


def update(frame: int, ax: plt.Axes) -> None:
    ax.clear()
    draw_static_context(ax, frame)
    targets = target_positions(frame)
    resources = resource_positions(frame)
    draw_sensor_observations(ax, targets, frame)
    fused = draw_tracks(ax, targets, frame)
    draw_truth_and_resources(ax, targets, resources, frame)
    draw_assignment(ax, fused, resources, frame)
    draw_flow_panel(ax, frame)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="research_modules/integrated_simulation/outputs/global_process_2d.gif",
        help="Path to the generated GIF.",
    )
    parser.add_argument("--frames", type=int, default=96)
    parser.add_argument("--fps", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11.5, 8.0), dpi=105)
    animation = FuncAnimation(fig, update, frames=args.frames, fargs=(ax,), interval=1000 / args.fps)
    animation.save(output, writer=PillowWriter(fps=args.fps))
    plt.close(fig)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
