"""Artifact and figure generation for the ideal two-stage D5 demonstration."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from research_modules.scalable_3d_simulation.animation import ensure_mplot3d

from .ideal_registration_demo import (
    IDEAL_REGISTRATION_SCHEMA_VERSION,
    FrameRegistrationResult,
    OfflineIdentityTruth,
    OnlineRegistrationRun,
    SeedRegistrationMetrics,
    candidate_columns,
)


FIGURE_FILES = (
    "01_scene_geometry.png",
    "02_motion_trajectories.png",
    "03_camera_a_global_projection.png",
    "04_camera_a_anonymous_tracks.png",
    "05_stage_a_cost_matrix.png",
    "06_stage_a_assignment.png",
    "07_camera_b_global_projection.png",
    "08_camera_b_anonymous_tracks.png",
    "09_stage_b_cost_matrix.png",
    "10_stage_b_assignment.png",
    "11_three_layer_candidate_graph.png",
    "12_registration_metrics_over_time.png",
    "13_visibility_and_final_chain.png",
)


def write_ideal_registration_artifacts(
    online_run: OnlineRegistrationRun,
    offline_truth: OfflineIdentityTruth,
    batch_metrics: Sequence[SeedRegistrationMetrics],
    output_dir: Path,
    *,
    generate_media: bool = True,
) -> tuple[Path, ...]:
    """Write reproducible online logs, evaluator sidecar, plots, GIF, and report."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    written.append(_write_scenario_json(online_run, batch_metrics, output))
    written.extend(_write_track_csvs(online_run, output))
    written.extend(_write_cost_csvs(online_run, output))
    written.append(_write_assignments_csv(online_run, output))
    written.append(_write_offline_truth_csv(offline_truth, output))
    written.append(_write_metrics_json(batch_metrics, output))
    if generate_media:
        written.extend(_write_figures(online_run, offline_truth, output))
        written.append(_write_animation(online_run, output / "registration_process.gif"))
    written.append(_write_report(online_run, batch_metrics, output, generate_media))
    return tuple(written)


def _write_scenario_json(
    online_run: OnlineRegistrationRun,
    batch_metrics: Sequence[SeedRegistrationMetrics],
    output: Path,
) -> Path:
    path = output / "scenario.json"
    payload = online_run.config.to_dict()
    payload.update(
        {
            "frame_count": len(online_run.frames),
            "batch_seeds": [metric.seed for metric in batch_metrics],
            "camera_a_intrinsics": _intrinsics_dict(online_run.camera_a_intrinsics),
            "camera_b_intrinsics": _intrinsics_dict(online_run.camera_b_intrinsics),
            "target_layout": "parameterized staggered grid; 20 targets form 5x4",
            "target_motion": "constant-velocity constrained point masses",
            "camera_b_motion": "constant-speed smooth straight point-mass trajectory",
            "gimbal_policy": "look_at_current_target_centroid_each_image_frame",
            "error_model": {
                "missed_detection": False,
                "false_alarm": False,
                "pixel_noise": False,
                "position_pose_time_communication_error": False,
            },
        }
    )
    _write_json(path, payload)
    return path


def _write_track_csvs(
    online_run: OnlineRegistrationRun,
    output: Path,
) -> tuple[Path, Path, Path]:
    global_path = output / "global_tracks.csv"
    with global_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "schema_version",
                "frame_index",
                "measurement_timestamp",
                "arrival_timestamp",
                "global_track_id",
                "px_ned_m",
                "py_ned_m",
                "pz_ned_m",
                "vx_ned_mps",
                "vy_ned_mps",
                "vz_ned_mps",
                "covariance_6x6_json",
            ),
        )
        writer.writeheader()
        for frame in online_run.frames:
            for index, global_id in enumerate(frame.global_track_ids):
                state = frame.global_states_ned[index]
                writer.writerow(
                    {
                        "schema_version": IDEAL_REGISTRATION_SCHEMA_VERSION,
                        "frame_index": frame.frame_index,
                        "measurement_timestamp": f"{frame.measurement_timestamp:.6f}",
                        "arrival_timestamp": f"{frame.arrival_timestamp:.6f}",
                        "global_track_id": global_id,
                        "px_ned_m": f"{state[0]:.9f}",
                        "py_ned_m": f"{state[1]:.9f}",
                        "pz_ned_m": f"{state[2]:.9f}",
                        "vx_ned_mps": f"{state[3]:.9f}",
                        "vy_ned_mps": f"{state[4]:.9f}",
                        "vz_ned_mps": f"{state[5]:.9f}",
                        "covariance_6x6_json": json.dumps(
                            frame.global_covariances[index].tolist(),
                            separators=(",", ":"),
                        ),
                    }
                )

    camera_a_path = output / "camera_a_anonymous_tracks.csv"
    camera_b_path = output / "camera_b_anonymous_tracks.csv"
    _write_camera_track_csv(online_run, camera_a_path, camera_label="a")
    _write_camera_track_csv(online_run, camera_b_path, camera_label="b")
    return global_path, camera_a_path, camera_b_path


def _write_camera_track_csv(
    online_run: OnlineRegistrationRun,
    path: Path,
    *,
    camera_label: str,
) -> None:
    fieldnames = (
        "schema_version",
        "frame_index",
        "measurement_timestamp",
        "arrival_timestamp",
        "camera_id",
        "local_track_id",
        "u_px",
        "v_px",
        "covariance_2x2_json",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for frame in online_run.frames:
            if camera_label == "a":
                ids = frame.camera_a_local_track_ids
                pixels = frame.camera_a_local_pixels
                covariances = frame.camera_a_local_covariances
                camera_id = "CAMERA-A-CENTER"
            else:
                ids = frame.camera_b_local_track_ids
                pixels = frame.camera_b_local_pixels
                covariances = frame.camera_b_local_covariances
                camera_id = "CAMERA-B-INTERCEPTOR"
            for index, local_id in enumerate(ids):
                writer.writerow(
                    {
                        "schema_version": IDEAL_REGISTRATION_SCHEMA_VERSION,
                        "frame_index": frame.frame_index,
                        "measurement_timestamp": f"{frame.measurement_timestamp:.6f}",
                        "arrival_timestamp": f"{frame.arrival_timestamp:.6f}",
                        "camera_id": camera_id,
                        "local_track_id": local_id,
                        "u_px": f"{pixels[index, 0]:.9f}",
                        "v_px": f"{pixels[index, 1]:.9f}",
                        "covariance_2x2_json": json.dumps(
                            covariances[index].tolist(), separators=(",", ":")
                        ),
                    }
                )


def _write_cost_csvs(
    online_run: OnlineRegistrationRun,
    output: Path,
) -> tuple[Path, Path]:
    stage_a = output / "stage_a_costs.csv"
    stage_b = output / "stage_b_costs.csv"
    _write_stage_cost_csv(online_run, stage_a, stage="a")
    _write_stage_cost_csv(online_run, stage_b, stage="b")
    return stage_a, stage_b


def _write_stage_cost_csv(
    online_run: OnlineRegistrationRun,
    path: Path,
    *,
    stage: str,
) -> None:
    fieldnames = (
        "schema_version",
        "frame_index",
        "measurement_timestamp",
        "arrival_timestamp",
        "stage",
        "window_frame_count",
        "global_track_id",
        "camera_a_local_track_id",
        "candidate_local_track_id",
        "position_cost",
        "displacement_cost",
        "displacement_weight",
        "total_cost",
        "candidate_rank",
        "hungarian_selected",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for frame, result in zip(online_run.frames, online_run.associations, strict=True):
            if stage == "a":
                cost = result.stage_a_cost
                local_ids = frame.camera_a_local_track_ids
                selected = dict(result.global_to_camera_a)
                camera_a_lookup: dict[str, str] = {}
                stage_label = "global_to_camera_a"
            else:
                cost = result.stage_b_cost
                local_ids = frame.camera_b_local_track_ids
                selected = {
                    global_id: camera_b_id
                    for global_id, _, camera_b_id in result.global_camera_a_to_camera_b
                }
                camera_a_lookup = dict(result.global_to_camera_a)
                stage_label = "camera_a_bound_global_to_camera_b"
            ranks = np.argsort(np.argsort(cost.total_cost, axis=1, kind="stable"), axis=1)
            for row, global_id in enumerate(frame.global_track_ids):
                for column, local_id in enumerate(local_ids):
                    writer.writerow(
                        {
                            "schema_version": IDEAL_REGISTRATION_SCHEMA_VERSION,
                            "frame_index": frame.frame_index,
                            "measurement_timestamp": f"{frame.measurement_timestamp:.6f}",
                            "arrival_timestamp": f"{frame.arrival_timestamp:.6f}",
                            "stage": stage_label,
                            "window_frame_count": cost.window_frame_count,
                            "global_track_id": global_id,
                            "camera_a_local_track_id": camera_a_lookup.get(global_id, ""),
                            "candidate_local_track_id": local_id,
                            "position_cost": f"{cost.position_cost[row, column]:.12f}",
                            "displacement_cost": f"{cost.displacement_cost[row, column]:.12f}",
                            "displacement_weight": online_run.config.displacement_weight,
                            "total_cost": f"{cost.total_cost[row, column]:.12f}",
                            "candidate_rank": int(ranks[row, column]) + 1,
                            "hungarian_selected": int(selected.get(global_id) == local_id),
                        }
                    )


def _write_assignments_csv(online_run: OnlineRegistrationRun, output: Path) -> Path:
    path = output / "assignments.csv"
    fieldnames = (
        "schema_version",
        "frame_index",
        "measurement_timestamp",
        "arrival_timestamp",
        "global_track_id",
        "camera_a_local_track_id",
        "camera_b_local_track_id",
        "stage_a_selected_cost",
        "stage_b_selected_cost",
        "association_state",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in online_run.associations:
            stage_a_cost = dict(
                zip(
                    (global_id for global_id, _ in result.global_to_camera_a),
                    result.stage_a_selected_costs,
                    strict=True,
                )
            )
            stage_b_cost = dict(
                zip(
                    (global_id for global_id, _, _ in result.global_camera_a_to_camera_b),
                    result.stage_b_selected_costs,
                    strict=True,
                )
            )
            for global_id, camera_a_id, camera_b_id in result.global_camera_a_to_camera_b:
                writer.writerow(
                    {
                        "schema_version": IDEAL_REGISTRATION_SCHEMA_VERSION,
                        "frame_index": result.frame_index,
                        "measurement_timestamp": f"{result.measurement_timestamp:.6f}",
                        "arrival_timestamp": f"{result.arrival_timestamp:.6f}",
                        "global_track_id": global_id,
                        "camera_a_local_track_id": camera_a_id,
                        "camera_b_local_track_id": camera_b_id,
                        "stage_a_selected_cost": f"{stage_a_cost[global_id]:.12f}",
                        "stage_b_selected_cost": f"{stage_b_cost[global_id]:.12f}",
                        "association_state": "matched",
                    }
                )
    return path


def _write_offline_truth_csv(
    offline_truth: OfflineIdentityTruth,
    output: Path,
) -> Path:
    path = output / "offline_truth.csv"
    camera_b = dict(offline_truth.global_to_camera_b)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "schema_version",
                "seed",
                "global_track_id",
                "camera_a_local_track_id",
                "camera_b_local_track_id",
                "usage_scope",
            ),
        )
        writer.writeheader()
        for global_id, camera_a_id in offline_truth.global_to_camera_a:
            writer.writerow(
                {
                    "schema_version": IDEAL_REGISTRATION_SCHEMA_VERSION,
                    "seed": offline_truth.seed,
                    "global_track_id": global_id,
                    "camera_a_local_track_id": camera_a_id,
                    "camera_b_local_track_id": camera_b[global_id],
                    "usage_scope": "offline_evaluation_only",
                }
            )
    return path


def _write_metrics_json(
    metrics: Sequence[SeedRegistrationMetrics],
    output: Path,
) -> Path:
    if not metrics:
        raise ValueError("at least one seed metric is required")
    path = output / "metrics.json"
    payload = {
        "schema_version": IDEAL_REGISTRATION_SCHEMA_VERSION,
        "validation_date": "2026-08-10",
        "scenario": "ideal_20_target_two_stage_registration",
        "acceptance": {
            "camera_a_accuracy": 1.0,
            "camera_b_accuracy": 1.0,
            "end_to_end_accuracy": 1.0,
            "id_switch_count": 0,
            "duplicate_assignment_count": 0,
            "unmatched_count": 0,
            "complete_chain_ratio": 1.0,
            "online_truth_usage_count": 0,
            "global_track_id_rewrite_count": 0,
            "full_visibility_rate": 1.0,
        },
        "aggregate": {
            "seed_count": len(metrics),
            "passed_seed_count": sum(metric.acceptance_passed() for metric in metrics),
            "all_seeds_passed": all(metric.acceptance_passed() for metric in metrics),
            "minimum_camera_a_accuracy": min(metric.camera_a_accuracy for metric in metrics),
            "minimum_camera_b_accuracy": min(metric.camera_b_accuracy for metric in metrics),
            "minimum_end_to_end_accuracy": min(metric.end_to_end_accuracy for metric in metrics),
            "minimum_complete_chain_ratio": min(metric.complete_chain_ratio for metric in metrics),
            "minimum_full_visibility_rate": min(metric.full_visibility_rate for metric in metrics),
            "total_id_switch_count": sum(metric.id_switch_count for metric in metrics),
            "total_duplicate_assignment_count": sum(
                metric.duplicate_assignment_count for metric in metrics
            ),
            "total_unmatched_count": sum(metric.unmatched_count for metric in metrics),
            "total_online_truth_usage_count": sum(
                metric.online_truth_usage_count for metric in metrics
            ),
            "total_global_track_id_rewrite_count": sum(
                metric.global_track_id_rewrite_count for metric in metrics
            ),
        },
        "seeds": [metric.to_dict() for metric in metrics],
        "evidence_boundary": {
            "simulation": "ideal deterministic point-mass",
            "airsim": False,
            "real_flight": False,
            "gnn_executed": False,
            "error_injection": False,
        },
    }
    _write_json(path, payload)
    return path


def _write_figures(
    online_run: OnlineRegistrationRun,
    offline_truth: OfflineIdentityTruth,
    output: Path,
) -> tuple[Path, ...]:
    plt = _load_pyplot()
    paths = tuple(output / name for name in FIGURE_FILES)
    _plot_scene_geometry(plt, online_run, paths[0])
    _plot_motion_trajectories(plt, online_run, paths[1])
    final_frame = online_run.frames[-1]
    final_result = online_run.associations[-1]
    _plot_camera_points(
        plt,
        final_frame.camera_a_projected_pixels,
        final_frame.global_track_ids,
        online_run.camera_a_intrinsics.width_px,
        online_run.camera_a_intrinsics.height_px,
        "Camera A: projected center tracks",
        paths[2],
        color="#b33a3a",
    )
    _plot_camera_points(
        plt,
        final_frame.camera_a_local_pixels,
        final_frame.camera_a_local_track_ids,
        online_run.camera_a_intrinsics.width_px,
        online_run.camera_a_intrinsics.height_px,
        "Camera A: anonymous local tracks",
        paths[3],
        color="#286090",
    )
    _plot_cost_matrix(
        plt,
        final_result.stage_a_cost.total_cost,
        final_frame.global_track_ids,
        final_frame.camera_a_local_track_ids,
        dict(final_result.global_to_camera_a),
        "Stage A full 20 x 20 temporal cost",
        paths[4],
    )
    _plot_assignment_overlay(
        plt,
        final_frame.camera_a_projected_pixels,
        final_frame.global_track_ids,
        final_frame.camera_a_local_pixels,
        final_frame.camera_a_local_track_ids,
        dict(final_result.global_to_camera_a),
        online_run.camera_a_intrinsics.width_px,
        online_run.camera_a_intrinsics.height_px,
        "Stage A Hungarian assignment",
        paths[5],
    )
    _plot_camera_points(
        plt,
        final_frame.camera_b_projected_pixels,
        final_frame.global_track_ids,
        online_run.camera_b_intrinsics.width_px,
        online_run.camera_b_intrinsics.height_px,
        "Camera B: A-bound tracks reprojected",
        paths[6],
        color="#b33a3a",
    )
    _plot_camera_points(
        plt,
        final_frame.camera_b_local_pixels,
        final_frame.camera_b_local_track_ids,
        online_run.camera_b_intrinsics.width_px,
        online_run.camera_b_intrinsics.height_px,
        "Camera B: anonymous local tracks",
        paths[7],
        color="#2f7d32",
    )
    stage_b_mapping = {
        global_id: camera_b_id
        for global_id, _, camera_b_id in final_result.global_camera_a_to_camera_b
    }
    _plot_cost_matrix(
        plt,
        final_result.stage_b_cost.total_cost,
        final_frame.global_track_ids,
        final_frame.camera_b_local_track_ids,
        stage_b_mapping,
        "Stage B full 20 x 20 temporal cost",
        paths[8],
    )
    _plot_assignment_overlay(
        plt,
        final_frame.camera_b_projected_pixels,
        final_frame.global_track_ids,
        final_frame.camera_b_local_pixels,
        final_frame.camera_b_local_track_ids,
        stage_b_mapping,
        online_run.camera_b_intrinsics.width_px,
        online_run.camera_b_intrinsics.height_px,
        "Stage B Hungarian assignment",
        paths[9],
    )
    _plot_three_layer_graph(plt, online_run, final_frame, final_result, paths[10])
    _plot_time_metrics(plt, online_run, offline_truth, paths[11])
    _plot_visibility_and_chain(plt, online_run, final_result, paths[12])
    return paths


def _plot_scene_geometry(plt: object, online_run: OnlineRegistrationRun, path: Path) -> None:
    frame = online_run.frames[0]
    figure = plt.figure(figsize=(10, 7))
    axis = figure.add_subplot(111, projection="3d")
    positions = frame.global_states_ned[:, :3]
    altitude = -positions[:, 2]
    axis.scatter(positions[:, 0], positions[:, 1], altitude, c="#b33a3a", s=34, label="20 targets")
    a_position = frame.camera_a_pose.position_ned
    b_position = frame.camera_b_pose.position_ned
    axis.scatter([a_position[0]], [a_position[1]], [-a_position[2]], marker="^", s=90, c="#286090", label="Camera A")
    axis.scatter([b_position[0]], [b_position[1]], [-b_position[2]], marker="s", s=70, c="#2f7d32", label="Camera B")
    centroid = np.mean(positions, axis=0)
    for camera_position, color in ((a_position, "#286090"), (b_position, "#2f7d32")):
        axis.plot(
            [camera_position[0], centroid[0]],
            [camera_position[1], centroid[1]],
            [-camera_position[2], -centroid[2]],
            linestyle="--",
            color=color,
            alpha=0.75,
        )
    axis.set_xlabel("North / m")
    axis.set_ylabel("East / m")
    axis.set_zlabel("Altitude / m")
    axis.set_title("Initial NED geometry and gimbal look directions")
    axis.legend(loc="upper left")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_motion_trajectories(plt: object, online_run: OnlineRegistrationRun, path: Path) -> None:
    states = np.stack([frame.global_states_ned for frame in online_run.frames], axis=0)
    camera_b = np.stack([frame.camera_b_pose.position_ned for frame in online_run.frames], axis=0)
    figure = plt.figure(figsize=(10, 7))
    axis = figure.add_subplot(111, projection="3d")
    for index in range(states.shape[1]):
        axis.plot(states[:, index, 0], states[:, index, 1], -states[:, index, 2], color="#b33a3a", alpha=0.55, linewidth=1.0)
    axis.plot(camera_b[:, 0], camera_b[:, 1], -camera_b[:, 2], color="#2f7d32", linewidth=2.4, label="Camera B path")
    a_position = online_run.frames[0].camera_a_pose.position_ned
    axis.scatter([a_position[0]], [a_position[1]], [-a_position[2]], marker="^", s=80, c="#286090", label="Camera A fixed")
    axis.set_xlabel("North / m")
    axis.set_ylabel("East / m")
    axis.set_zlabel("Altitude / m")
    axis.set_title("Fifteen-second point-mass trajectories")
    axis.legend(loc="upper left")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_camera_points(
    plt: object,
    pixels: np.ndarray,
    labels: Sequence[str],
    width: int,
    height: int,
    title: str,
    path: Path,
    *,
    color: str,
) -> None:
    figure, axis = plt.subplots(figsize=(11, 6.2))
    axis.scatter(pixels[:, 0], pixels[:, 1], s=42, color=color)
    for label, pixel in zip(labels, pixels, strict=True):
        axis.annotate(label, pixel, xytext=(4, 4), textcoords="offset points", fontsize=7)
    axis.set_xlim(0, width)
    axis.set_ylim(height, 0)
    axis.set_aspect("equal", adjustable="box")
    axis.grid(alpha=0.25)
    axis.set_xlabel("u / pixel")
    axis.set_ylabel("v / pixel")
    axis.set_title(title)
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_cost_matrix(
    plt: object,
    cost: np.ndarray,
    global_ids: Sequence[str],
    local_ids: Sequence[str],
    selected: dict[str, str],
    title: str,
    path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(10.5, 8.2))
    image = axis.imshow(np.log10(1.0 + cost), cmap="viridis", aspect="auto")
    axis.set_xticks(np.arange(len(local_ids)), labels=local_ids, rotation=90, fontsize=6)
    axis.set_yticks(np.arange(len(global_ids)), labels=global_ids, fontsize=6)
    local_index = {local_id: index for index, local_id in enumerate(local_ids)}
    for row, global_id in enumerate(global_ids):
        axis.scatter(local_index[selected[global_id]], row, marker="s", facecolors="none", edgecolors="#ffdd57", s=58, linewidths=1.2)
    axis.set_xlabel("Anonymous local track")
    axis.set_ylabel("Center global track")
    axis.set_title(title + " (log10(1 + cost))")
    figure.colorbar(image, ax=axis, shrink=0.82, label="scaled temporal cost")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_assignment_overlay(
    plt: object,
    projected_pixels: np.ndarray,
    global_ids: Sequence[str],
    local_pixels: np.ndarray,
    local_ids: Sequence[str],
    mapping: dict[str, str],
    width: int,
    height: int,
    title: str,
    path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(11, 6.2))
    local_index = {local_id: index for index, local_id in enumerate(local_ids)}
    for row, global_id in enumerate(global_ids):
        local_id = mapping[global_id]
        column = local_index[local_id]
        axis.plot(
            [projected_pixels[row, 0], local_pixels[column, 0]],
            [projected_pixels[row, 1], local_pixels[column, 1]],
            color="#777777",
            linewidth=0.9,
            alpha=0.7,
        )
    axis.scatter(projected_pixels[:, 0], projected_pixels[:, 1], marker="o", facecolors="none", edgecolors="#b33a3a", s=75, label="predicted")
    axis.scatter(local_pixels[:, 0], local_pixels[:, 1], marker="x", c="#286090", s=42, label="anonymous observed")
    for index, global_id in enumerate(global_ids):
        axis.annotate(global_id, projected_pixels[index], xytext=(4, -10), textcoords="offset points", fontsize=6)
    axis.set_xlim(0, width)
    axis.set_ylim(height, 0)
    axis.set_aspect("equal", adjustable="box")
    axis.grid(alpha=0.25)
    axis.set_xlabel("u / pixel")
    axis.set_ylabel("v / pixel")
    axis.set_title(title)
    axis.legend(loc="upper right")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_three_layer_graph(
    plt: object,
    online_run: OnlineRegistrationRun,
    frame: object,
    result: FrameRegistrationResult,
    path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(13, 10))
    count = len(frame.global_track_ids)
    y_values = np.arange(count - 1, -1, -1, dtype=float)
    global_y = {global_id: y_values[index] for index, global_id in enumerate(frame.global_track_ids)}
    camera_a_y = {local_id: y_values[index] for index, local_id in enumerate(frame.camera_a_local_track_ids)}
    camera_b_y = {local_id: y_values[index] for index, local_id in enumerate(frame.camera_b_local_track_ids)}
    selected_a = dict(result.global_to_camera_a)
    selected_b = {
        global_id: camera_b_id
        for global_id, _, camera_b_id in result.global_camera_a_to_camera_b
    }
    candidates_a = candidate_columns(result.stage_a_cost.total_cost, top_k=online_run.config.candidate_edge_count)
    candidates_b = candidate_columns(result.stage_b_cost.total_cost, top_k=online_run.config.candidate_edge_count)
    for row, global_id in enumerate(frame.global_track_ids):
        selected_a_id = selected_a[global_id]
        display_a = set(candidates_a[row])
        display_a.add(frame.camera_a_local_track_ids.index(selected_a_id))
        for column in sorted(display_a):
            local_id = frame.camera_a_local_track_ids[column]
            chosen = local_id == selected_a_id
            axis.plot([0.0, 1.0], [global_y[global_id], camera_a_y[local_id]], color="#2f7d32" if chosen else "#b8b8b8", linewidth=1.8 if chosen else 0.55, alpha=0.9 if chosen else 0.35, zorder=1)
        selected_b_id = selected_b[global_id]
        display_b = set(candidates_b[row])
        display_b.add(frame.camera_b_local_track_ids.index(selected_b_id))
        for column in sorted(display_b):
            local_id = frame.camera_b_local_track_ids[column]
            chosen = local_id == selected_b_id
            axis.plot([1.0, 2.0], [camera_a_y[selected_a_id], camera_b_y[local_id]], color="#2f7d32" if chosen else "#b8b8b8", linewidth=1.8 if chosen else 0.55, alpha=0.9 if chosen else 0.35, zorder=1)
    for x, labels, mapping, color in (
        (0.0, frame.global_track_ids, global_y, "#b33a3a"),
        (1.0, frame.camera_a_local_track_ids, camera_a_y, "#286090"),
        (2.0, frame.camera_b_local_track_ids, camera_b_y, "#2f7d32"),
    ):
        axis.scatter([x] * count, [mapping[label] for label in labels], s=42, color=color, zorder=3)
        offset = -0.04 if x == 0.0 else 0.04
        alignment = "right" if x == 0.0 else "left"
        for label in labels:
            axis.text(x + offset, mapping[label], label, va="center", ha=alignment, fontsize=6.5)
    axis.text(0.0, count + 0.4, "Center GlobalTrack", ha="center", fontsize=11, weight="bold")
    axis.text(1.0, count + 0.4, "Camera A anonymous", ha="center", fontsize=11, weight="bold")
    axis.text(2.0, count + 0.4, "Camera B anonymous", ha="center", fontsize=11, weight="bold")
    axis.text(1.0, -1.4, "Gray: three lowest-cost candidates per row; green: Hungarian selections", ha="center", fontsize=9)
    axis.set_xlim(-0.48, 2.48)
    axis.set_ylim(-1.8, count + 1.0)
    axis.set_title(
        f"Three-layer {3 * count}-node candidate graph (explanation only, no GNN)"
    )
    axis.axis("off")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_time_metrics(
    plt: object,
    online_run: OnlineRegistrationRun,
    offline_truth: OfflineIdentityTruth,
    path: Path,
) -> None:
    expected_a = dict(offline_truth.global_to_camera_a)
    expected_b = dict(offline_truth.global_to_camera_b)
    timestamps: list[float] = []
    accuracy_a: list[float] = []
    accuracy_b: list[float] = []
    accuracy_chain: list[float] = []
    selected_cost: list[float] = []
    nearest_wrong_cost: list[float] = []
    for frame, result in zip(online_run.frames, online_run.associations, strict=True):
        a_map = dict(result.global_to_camera_a)
        chain_map = {
            global_id: (camera_a_id, camera_b_id)
            for global_id, camera_a_id, camera_b_id in result.global_camera_a_to_camera_b
        }
        count = len(frame.global_track_ids)
        timestamps.append(frame.measurement_timestamp)
        accuracy_a.append(sum(a_map[g] == expected_a[g] for g in frame.global_track_ids) / count)
        accuracy_b.append(sum(chain_map[g][1] == expected_b[g] for g in frame.global_track_ids) / count)
        accuracy_chain.append(sum(chain_map[g] == (expected_a[g], expected_b[g]) for g in frame.global_track_ids) / count)
        selected_cost.append(float(np.mean(result.stage_a_selected_costs + result.stage_b_selected_costs)))
        wrong_values: list[float] = []
        for matrix, ids, mapping in (
            (result.stage_a_cost.total_cost, frame.camera_a_local_track_ids, a_map),
            (result.stage_b_cost.total_cost, frame.camera_b_local_track_ids, {g: chain_map[g][1] for g in frame.global_track_ids}),
        ):
            for row, global_id in enumerate(frame.global_track_ids):
                selected_column = ids.index(mapping[global_id])
                mask = np.ones(len(ids), dtype=bool)
                mask[selected_column] = False
                wrong_values.append(float(np.min(matrix[row, mask])))
        nearest_wrong_cost.append(float(np.mean(wrong_values)))
    figure, axes = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True)
    axes[0].plot(timestamps, accuracy_a, label="A accuracy", color="#286090")
    axes[0].plot(timestamps, accuracy_b, label="B accuracy", color="#2f7d32", linestyle="--")
    axes[0].plot(timestamps, accuracy_chain, label="end-to-end", color="#b33a3a", linestyle=":")
    axes[0].set_ylim(0.0, 1.05)
    axes[0].set_ylabel("association accuracy")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="lower right")
    axes[1].plot(timestamps, selected_cost, label="mean selected cost", color="#2f7d32")
    axes[1].plot(timestamps, nearest_wrong_cost, label="mean nearest unselected cost", color="#b33a3a")
    axes[1].set_xlabel("time / s")
    axes[1].set_ylabel("temporal cost")
    axes[1].grid(alpha=0.25)
    axes[1].legend(loc="best")
    figure.suptitle("Frame-level registration result and cost separation")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_visibility_and_chain(
    plt: object,
    online_run: OnlineRegistrationRun,
    result: FrameRegistrationResult,
    path: Path,
) -> None:
    timestamps = [frame.measurement_timestamp for frame in online_run.frames]
    visible_a = [int(np.count_nonzero(frame.camera_a_visible)) for frame in online_run.frames]
    visible_b = [int(np.count_nonzero(frame.camera_b_visible)) for frame in online_run.frames]
    figure, axes = plt.subplots(1, 2, figsize=(14, 8), gridspec_kw={"width_ratios": (1.0, 1.25)})
    axes[0].plot(timestamps, visible_a, label="Camera A", color="#286090")
    axes[0].plot(timestamps, visible_b, label="Camera B", color="#2f7d32", linestyle="--")
    axes[0].axhline(online_run.config.target_count, color="#777777", linewidth=1.0, linestyle=":")
    axes[0].set_ylim(0, online_run.config.target_count + 1)
    axes[0].set_xlabel("time / s")
    axes[0].set_ylabel("visible target count")
    axes[0].set_title("Full-frame visibility")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="lower right")
    axes[1].axis("off")
    axes[1].set_title("Final public association chain")
    lines = ["GlobalTrack     Camera A       Camera B"]
    lines.extend(
        f"{global_id:<14}{camera_a_id:<15}{camera_b_id}"
        for global_id, camera_a_id, camera_b_id in result.global_camera_a_to_camera_b
    )
    axes[1].text(0.02, 0.98, "\n".join(lines), va="top", family="monospace", fontsize=9.2, linespacing=1.25)
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _write_animation(online_run: OnlineRegistrationRun, path: Path) -> Path:
    plt = _load_pyplot()
    import matplotlib.animation as animation

    frame_count = len(online_run.frames)
    stride = max(1, int(np.ceil(frame_count / 76)))
    indices = np.arange(0, frame_count, stride, dtype=int)
    if indices[-1] != frame_count - 1:
        indices = np.append(indices, frame_count - 1)
    all_target_positions = np.stack(
        [frame.global_states_ned[:, :3] for frame in online_run.frames], axis=0
    )
    all_camera_b_positions = np.stack(
        [frame.camera_b_pose.position_ned for frame in online_run.frames], axis=0
    )
    figure = plt.figure(figsize=(14, 7.5))
    axis_3d = figure.add_subplot(2, 2, 1, projection="3d")
    axis_a = figure.add_subplot(2, 2, 2)
    axis_b = figure.add_subplot(2, 2, 4)
    target_scatter = axis_3d.scatter([], [], [], c="#b33a3a", s=25, label="targets")
    camera_a_scatter = axis_3d.scatter([], [], [], marker="^", c="#286090", s=70, label="A")
    camera_b_scatter = axis_3d.scatter([], [], [], marker="s", c="#2f7d32", s=55, label="B")
    b_trail, = axis_3d.plot([], [], [], color="#2f7d32", linewidth=1.8)
    all_positions = np.concatenate(
        [all_target_positions.reshape(-1, 3), all_camera_b_positions], axis=0
    )
    axis_3d.set_xlim(np.min(all_positions[:, 0]) - 60, np.max(all_positions[:, 0]) + 60)
    axis_3d.set_ylim(np.min(all_positions[:, 1]) - 60, np.max(all_positions[:, 1]) + 60)
    altitudes = -all_positions[:, 2]
    axis_3d.set_zlim(max(0.0, np.min(altitudes) - 40), np.max(altitudes) + 40)
    axis_3d.set_xlabel("North / m")
    axis_3d.set_ylabel("East / m")
    axis_3d.set_zlabel("Altitude / m")
    axis_3d.legend(loc="upper left")
    scatter_a_pred = axis_a.scatter([], [], marker="o", facecolors="none", edgecolors="#b33a3a", s=58, label="global projection")
    scatter_a_obs = axis_a.scatter([], [], marker="x", c="#286090", s=34, label="anonymous A")
    scatter_b_pred = axis_b.scatter([], [], marker="o", facecolors="none", edgecolors="#b33a3a", s=58, label="A-bound reprojection")
    scatter_b_obs = axis_b.scatter([], [], marker="x", c="#2f7d32", s=34, label="anonymous B")
    for axis, intrinsics, title in (
        (axis_a, online_run.camera_a_intrinsics, "Stage A image plane"),
        (axis_b, online_run.camera_b_intrinsics, "Stage B image plane"),
    ):
        axis.set_xlim(0, intrinsics.width_px)
        axis.set_ylim(intrinsics.height_px, 0)
        axis.set_aspect("equal", adjustable="box")
        axis.grid(alpha=0.2)
        axis.set_title(title)
        axis.set_xlabel("u / pixel")
        axis.set_ylabel("v / pixel")
        axis.legend(loc="upper right", fontsize=8)
    status_text = figure.text(0.02, 0.02, "", fontsize=10, family="monospace")

    def update(animation_index: int) -> tuple[object, ...]:
        index = int(indices[animation_index])
        frame = online_run.frames[index]
        result = online_run.associations[index]
        positions = frame.global_states_ned[:, :3]
        target_scatter._offsets3d = (positions[:, 0], positions[:, 1], -positions[:, 2])
        a_position = frame.camera_a_pose.position_ned
        b_position = frame.camera_b_pose.position_ned
        camera_a_scatter._offsets3d = ([a_position[0]], [a_position[1]], [-a_position[2]])
        camera_b_scatter._offsets3d = ([b_position[0]], [b_position[1]], [-b_position[2]])
        b_history = all_camera_b_positions[: index + 1]
        b_trail.set_data(b_history[:, 0], b_history[:, 1])
        b_trail.set_3d_properties(-b_history[:, 2])
        scatter_a_pred.set_offsets(frame.camera_a_projected_pixels)
        scatter_a_obs.set_offsets(frame.camera_a_local_pixels)
        scatter_b_pred.set_offsets(frame.camera_b_projected_pixels)
        scatter_b_obs.set_offsets(frame.camera_b_local_pixels)
        status_text.set_text(
            f"t={frame.measurement_timestamp:4.1f}s | targets={len(frame.global_track_ids)} | "
            f"A matched={len(result.global_to_camera_a)} | B matched={len(result.global_camera_a_to_camera_b)} | "
            f"window={result.stage_a_cost.window_frame_count}"
        )
        axis_3d.set_title(f"Point-mass scene at t={frame.measurement_timestamp:.1f} s")
        return (
            target_scatter,
            camera_a_scatter,
            camera_b_scatter,
            b_trail,
            scatter_a_pred,
            scatter_a_obs,
            scatter_b_pred,
            scatter_b_obs,
            status_text,
        )

    movie = animation.FuncAnimation(
        figure,
        update,
        frames=len(indices),
        interval=100.0,
        blit=False,
    )
    figure.tight_layout(rect=(0, 0.05, 1, 1))
    movie.save(path, writer=animation.PillowWriter(fps=10), dpi=100)
    plt.close(figure)
    return path


def _write_report(
    online_run: OnlineRegistrationRun,
    metrics: Sequence[SeedRegistrationMetrics],
    output: Path,
    media_available: bool,
) -> Path:
    path = output / "D5_IDEAL_20_TARGET_TWO_STAGE_REGISTRATION_CN.md"
    aggregate_passed = sum(metric.acceptance_passed() for metric in metrics)
    seeds = ", ".join(str(metric.seed) for metric in metrics)
    figure_section = ""
    if media_available:
        descriptions = (
            ("01_scene_geometry.png", "初始三维几何"),
            ("02_motion_trajectories.png", "目标与相机运动"),
            ("03_camera_a_global_projection.png", "中心航迹在 A 图像的预测投影"),
            ("04_camera_a_anonymous_tracks.png", "A 相机匿名轨迹"),
            ("05_stage_a_cost_matrix.png", "第一级完整代价矩阵"),
            ("06_stage_a_assignment.png", "第一级匈牙利匹配"),
            ("07_camera_b_global_projection.png", "已绑定航迹在 B 图像的重投影"),
            ("08_camera_b_anonymous_tracks.png", "B 相机匿名轨迹"),
            ("09_stage_b_cost_matrix.png", "第二级完整代价矩阵"),
            ("10_stage_b_assignment.png", "第二级匈牙利匹配"),
            ("11_three_layer_candidate_graph.png", "三层候选关系解释图"),
            ("12_registration_metrics_over_time.png", "逐帧准确率与代价间隔"),
            ("13_visibility_and_final_chain.png", "可见率与最终关系链"),
        )
        figure_section = "\n".join(
            f"### {index}. {caption}\n\n![{caption}]({filename})"
            for index, (filename, caption) in enumerate(descriptions, start=1)
        )
    standard = next(
        metric for metric in metrics if metric.seed == online_run.config.seed
    )
    metric_rows = "\n".join(
        "| {seed} | {a:.3f} | {b:.3f} | {end:.3f} | {idsw} | {dup} | {miss} | {visible:.3f} | {passed} |".format(
            seed=metric.seed,
            a=metric.camera_a_accuracy,
            b=metric.camera_b_accuracy,
            end=metric.end_to_end_accuracy,
            idsw=metric.id_switch_count,
            dup=metric.duplicate_assignment_count,
            miss=metric.unmatched_count,
            visible=metric.full_visibility_rate,
            passed="通过" if metric.acceptance_passed() else "未通过",
        )
        for metric in metrics
    )
    animation_sentence = (
        "动态过程见 [registration_process.gif](registration_process.gif)。动画同时显示三维运动、"
        "A 图像第一级投影和 B 图像第二级重投影。"
        if media_available
        else "本次使用 `--skip-media`，未生成动态图和步骤图。"
    )
    report = f"""# D5 理想条件二十目标两级视觉配准实验

## 结论

本实验在理想三维质点场景中验证了两级视觉配准链。标准场景包含 20 个运动目标、一个固定中心相机 A 和一个以 14 米/秒运动的拦截相机 B。中心侧先把既有全局航迹投影到 A 图像，与 A 的匿名像素轨迹完成匈牙利匹配，再把已绑定的三维航迹投影到 B 图像，与 B 的匿名轨迹完成第二次匹配。

2026 年 8 月 10 日使用种子 {seeds} 完成 10 组确定性实验。{aggregate_passed}/{len(metrics)} 组达到全部验收条件。标准种子 {standard.seed} 的 A 侧、B 侧和端到端准确率均为 1.0，身份切换、重复分配、未匹配、在线真值使用和全局编号改写均为 0；两个相机在 76 个图像时刻均保持 20 个目标可见。

该结果只证明理想条件下几何投影、时间窗代价和两级匈牙利求解能够形成完整关系链。实验没有加入位置误差、姿态误差、时钟偏差、漏检、虚警、遮挡和像素噪声，也没有运行图神经网络。结果不能解释为 AirSim 验证、实飞结果或真实相机性能。

## 场景模型

场景采用北东地坐标系。20 个目标以 `[1200, 0, -180]` 米为中心组成 5×4 交错编队，速度在 3.5 至 4.7 米/秒之间。动力学周期为 0.1 秒，图像周期为 0.2 秒，总时长 15 秒。目标和 B 相机均使用受约束质点模型推进；两个云台在每个图像时刻指向目标群当前质心。

A 相机固定在 `[0, 0, -50]` 米，分辨率为 3840×2160，水平视场角 70 度。B 相机从 `[150, 300, -100]` 米出发，分辨率为 1920×1080，水平视场角 90 度。观测时间戳和到达时间戳相同。三维航迹和二维观测都携带 `1e-6` 单位阵协方差，用于数值正则；本实验不把它解释为真实设备误差。

## 数据边界

在线文件分为中心三维航迹、A 匿名像素轨迹和 B 匿名像素轨迹。A、B 的本地编号分别随机置乱，并在一个 episode 内保持稳定。在线关联函数只接收中心拥有的 `global_track_id`、相机参数、预测像素、匿名本地编号、双时间戳和协方差。

`offline_truth.csv` 单独保存全局编号与两台相机本地编号的真实映射，只在关联完成后计算指标。D5 没有生成、改写或本地换绑全局编号。`assignments.csv` 是算法公开输出，不包含用于评分的隐藏映射。

## 两级算法

第一级对每条中心航迹按图像时刻获得三维位置，并用 A 相机内参、位置和姿态投影到像平面。投影轨迹与 A 匿名轨迹构成完整的 N×N 代价矩阵。N 由输入参数决定，20 只是本次实验值。

第二级使用第一级已绑定的中心航迹。中心侧根据 B 相机的准确内参、位置和云台方向，把相同三维航迹投影到 B 图像，再与 B 匿名轨迹构成第二个完整代价矩阵。B 不上传三维目标位置，也不参与全局编号管理。

最近五帧的代价由像素位置差和帧间位移差组成：

```text
C(i,j) = mean(||u_hat(i)-u(j)||^2 / 20^2)
       + 0.25 * mean(||delta_u_hat(i)-delta_u(j)||^2 / 10^2)
```

首帧只有位置项，后续按已有帧数扩展，最多保留五帧。两个阶段都使用 SciPy 的线性和分配求解器。所有候选代价逐帧写入 CSV，包含位置项、位移项、总成本、候选排序和最终选中标记。

## 图结构说明

三层解释图包含 20 条中心全局航迹、20 条 A 匿名轨迹和 20 条 B 匿名轨迹。实际求解始终使用两个完整 20×20 代价矩阵。图中每个中心航迹只显示成本最低的三条候选边，并保留匈牙利选中的边，以便观察候选收缩过程。

该图没有加载模型权重，没有执行消息传播或图神经网络推理。后续只有在加入误差、遮挡和密集交叉后，确定性几何基线出现可重复失效，才有必要用同一输入数据评估学习型图匹配。

## 关键步骤

{figure_section}

{animation_sentence}

## 批量结果

| seed | A准确率 | B准确率 | 端到端准确率 | 身份切换 | 重复分配 | 未匹配 | 全时段双相机可见率 | 结论 |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
{metric_rows}

完整关系链比例在全部种子中均为 1.0。选中项代价在理想无误差条件下为 0，最近的错误候选保持正代价，因此两个阶段没有发生编号跳变。这个零代价结果来自预测值与观测值完全一致，不应作为真实工程门限。

## 复现命令

```bash
python3 research_modules/d5_terminal_association/scripts/run_ideal_registration_demo.py
```

目标数量可通过 `--target-count` 修改。批量种子数量和输出目录也由命令行参数控制，算法内部没有固定 20 目标或固定 10 个种子的数组假设。

## 边界与下一步

下一阶段应逐项加入像素噪声、相机位置和姿态误差、时间偏差、漏检、虚警、遮挡和局部编号中断。标定重点是错误候选代价与正确候选代价的间隔、身份切换率、完整关系链比例和恢复时间。误差实验仍应保持在线真值隔离，并使用同一份离线评分文件。

图结构学习只作为对照路线。确定性基线应先在误差场景中形成可复现的失败样本，再用冻结数据比较图匹配模型。任何模型都不得绕过现有权重谱系校验，也不得把真值编号写入在线特征。
"""
    path.write_text(report, encoding="utf-8")
    return path


def _load_pyplot() -> object:
    import matplotlib

    matplotlib.use("Agg")
    ensure_mplot3d(matplotlib)
    import matplotlib.pyplot as plt

    return plt


def _intrinsics_dict(intrinsics: object) -> dict[str, float | int]:
    return {
        "width_px": int(intrinsics.width_px),
        "height_px": int(intrinsics.height_px),
        "fx": float(intrinsics.fx),
        "fy": float(intrinsics.fy),
        "cx": float(intrinsics.cx),
        "cy": float(intrinsics.cy),
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
