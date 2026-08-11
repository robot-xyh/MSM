"""Artifacts and figures for the irregular crossing narrow-FOV scan scenario."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from research_modules.scalable_3d_simulation.animation import ensure_mplot3d

from .ideal_irregular_crossing_demo import (
    IRREGULAR_CROSSING_SCHEMA_VERSION,
    IrregularCrossingRun,
    IrregularOfflineTruth,
    ScanAssociationEvent,
    ScanModeMetrics,
)


FIGURE_FILES = (
    "01_irregular_3d_geometry.png",
    "02_projected_crossings_a_b.png",
    "03_mechanical_coverage_timeline.png",
    "04_coverage_safe_timeline.png",
    "05_gimbal_angle_comparison.png",
    "06_cumulative_discovery_curves.png",
    "07_mode_metrics_comparison.png",
    "08_stage_a_event_costs.png",
    "09_stage_b_event_costs.png",
    "10_final_relationship_chain.png",
)


def write_irregular_crossing_artifacts(
    online_run: IrregularCrossingRun,
    offline_truth: IrregularOfflineTruth,
    standard_metrics: Sequence[ScanModeMetrics],
    coverage_safe_batch_metrics: Sequence[ScanModeMetrics],
    output_dir: Path,
    *,
    generate_media: bool = True,
) -> tuple[Path, ...]:
    """Write the complete reproducible artifact set."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    written.append(_write_scenario(online_run, output))
    written.append(_write_global_tracks(online_run, output))
    written.extend(_write_crossing_csvs(online_run, output))
    written.extend(_write_timeline_csvs(online_run, output))
    written.append(_write_observations(online_run, output))
    written.append(_write_event_costs(online_run, output))
    written.append(_write_assignments(online_run, output))
    written.append(_write_offline_truth(offline_truth, output))
    written.append(_write_mode_metrics(standard_metrics, output))
    written.append(
        _write_metrics_json(
            online_run,
            standard_metrics,
            coverage_safe_batch_metrics,
            output,
        )
    )
    if generate_media:
        written.extend(_write_figures(online_run, standard_metrics, output))
        written.append(_write_animation(online_run, output / "scan_registration_process.gif"))
    written.append(
        _write_report(
            online_run,
            standard_metrics,
            coverage_safe_batch_metrics,
            output,
            media_available=generate_media,
        )
    )
    return tuple(written)


def _write_scenario(online_run: IrregularCrossingRun, output: Path) -> Path:
    path = output / "scenario.json"
    payload = online_run.config.to_dict()
    payload.update(
        {
            "camera_a_intrinsics": _intrinsics_payload(online_run.camera_a_intrinsics),
            "camera_b_intrinsics": _intrinsics_payload(online_run.camera_b_intrinsics),
            "camera_a_vertical_fov_deg": _vertical_fov(online_run.camera_a_intrinsics),
            "camera_b_vertical_fov_deg": _vertical_fov(online_run.camera_b_intrinsics),
            "camera_a_ifov_rad_per_pixel": (
                np.deg2rad(online_run.config.camera_a_horizontal_fov_deg)
                / online_run.config.camera_a_width_px
            ),
            "camera_b_ifov_rad_per_pixel": (
                np.deg2rad(online_run.config.camera_b_horizontal_fov_deg)
                / online_run.config.camera_b_width_px
            ),
            "crossing_definition": (
                "unordered pair counted when reference-image polylines intersect or "
                "minimum segment distance <= 0.025 * image width"
            ),
            "association_execution": "event_only_after_five_100hz_confirmation_frames",
            "media_sampling": "0.1_s",
            "error_model": "ideal_no_noise_no_miss_no_false_alarm_exact_pose_and_time",
        }
    )
    _write_json(path, payload)
    return path


def _write_global_tracks(online_run: IrregularCrossingRun, output: Path) -> Path:
    path = output / "global_tracks.csv"
    fields = (
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
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for frame_index, timestamp in enumerate(online_run.geometry.physics_timestamps):
            for target_index, global_id in enumerate(
                online_run.geometry.global_track_ids
            ):
                state = online_run.geometry.target_state_history_ned[
                    frame_index, target_index
                ]
                writer.writerow(
                    {
                        "schema_version": IRREGULAR_CROSSING_SCHEMA_VERSION,
                        "frame_index": frame_index,
                        "measurement_timestamp": f"{timestamp:.6f}",
                        "arrival_timestamp": f"{timestamp:.6f}",
                        "global_track_id": global_id,
                        "px_ned_m": f"{state[0]:.9f}",
                        "py_ned_m": f"{state[1]:.9f}",
                        "pz_ned_m": f"{state[2]:.9f}",
                        "vx_ned_mps": f"{state[3]:.9f}",
                        "vy_ned_mps": f"{state[4]:.9f}",
                        "vz_ned_mps": f"{state[5]:.9f}",
                        "covariance_6x6_json": json.dumps(
                            online_run.geometry.global_covariances[
                                frame_index, target_index
                            ].tolist(),
                            separators=(",", ":"),
                        ),
                    }
                )
    return path


def _write_crossing_csvs(
    online_run: IrregularCrossingRun, output: Path
) -> tuple[Path, Path]:
    paths = (output / "projected_crossing_pairs_a.csv", output / "projected_crossing_pairs_b.csv")
    for path, camera, pairs in (
        (paths[0], "A", online_run.geometry.projected_crossing_pairs_a),
        (paths[1], "B", online_run.geometry.projected_crossing_pairs_b),
    ):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "schema_version",
                    "camera",
                    "first_global_track_id",
                    "second_global_track_id",
                    "minimum_segment_distance_px",
                    "normalized_distance_by_width",
                    "exact_segment_intersection",
                    "minimum_3d_separation_m",
                    "definition",
                ),
            )
            writer.writeheader()
            for pair in pairs:
                writer.writerow(
                    {
                        "schema_version": IRREGULAR_CROSSING_SCHEMA_VERSION,
                        "camera": camera,
                        "first_global_track_id": pair.first_global_track_id,
                        "second_global_track_id": pair.second_global_track_id,
                        "minimum_segment_distance_px": f"{pair.minimum_segment_distance_px:.9f}",
                        "normalized_distance_by_width": f"{pair.normalized_distance_by_width:.12f}",
                        "exact_segment_intersection": int(pair.exact_segment_intersection),
                        "minimum_3d_separation_m": f"{_minimum_3d_separation_for_pair(online_run, pair.first_global_track_id, pair.second_global_track_id):.9f}",
                        "definition": "segment_intersection_or_distance_le_0.025_image_width",
                    }
                )
    return paths


def _write_timeline_csvs(
    online_run: IrregularCrossingRun, output: Path
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for mode in online_run.modes:
        path = output / f"{mode.mode}_scan_timeline.csv"
        paths.append(path)
        fields = tuple(mode.timeline[0].__dataclass_fields__)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in mode.timeline:
                writer.writerow(
                    {
                        name: getattr(record, name) if getattr(record, name) is not None else ""
                        for name in fields
                    }
                )
    return tuple(paths)


def _write_observations(online_run: IrregularCrossingRun, output: Path) -> Path:
    path = output / "anonymous_observations.csv"
    fields = (
        "schema_version",
        "mode",
        "stage",
        "camera_id",
        "local_track_id",
        "measurement_timestamp",
        "arrival_timestamp",
        "u_px",
        "v_px",
        "covariance_2x2_json",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mode in online_run.modes:
            for observation in mode.observations:
                writer.writerow(
                    {
                        "schema_version": IRREGULAR_CROSSING_SCHEMA_VERSION,
                        "mode": mode.mode,
                        "stage": observation.stage,
                        "camera_id": observation.camera_id,
                        "local_track_id": observation.local_track_id,
                        "measurement_timestamp": f"{observation.measurement_timestamp:.6f}",
                        "arrival_timestamp": f"{observation.arrival_timestamp:.6f}",
                        "u_px": f"{observation.center_px[0]:.9f}",
                        "v_px": f"{observation.center_px[1]:.9f}",
                        "covariance_2x2_json": json.dumps(
                            observation.covariance_px.tolist(), separators=(",", ":")
                        ),
                    }
                )
    return path


def _write_event_costs(online_run: IrregularCrossingRun, output: Path) -> Path:
    path = output / "association_event_costs.csv"
    fields = (
        "schema_version",
        "mode",
        "stage",
        "event_index",
        "measurement_timestamp",
        "arrival_timestamp",
        "window_frame_count",
        "global_track_id",
        "candidate_local_track_id",
        "position_cost",
        "displacement_cost",
        "total_cost",
        "selected",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mode in online_run.modes:
            for stage, events in (
                ("stage_a", mode.stage_a_events),
                ("stage_b", mode.stage_b_events),
            ):
                for event_index, event in enumerate(events):
                    selected = dict(event.selected_pairs)
                    for row, global_id in enumerate(event.global_track_ids):
                        for column, local_id in enumerate(event.local_track_ids):
                            writer.writerow(
                                {
                                    "schema_version": IRREGULAR_CROSSING_SCHEMA_VERSION,
                                    "mode": mode.mode,
                                    "stage": stage,
                                    "event_index": event_index,
                                    "measurement_timestamp": f"{event.measurement_timestamp:.6f}",
                                    "arrival_timestamp": f"{event.arrival_timestamp:.6f}",
                                    "window_frame_count": event.cost.window_frame_count,
                                    "global_track_id": global_id,
                                    "candidate_local_track_id": local_id,
                                    "position_cost": f"{event.cost.position_cost[row, column]:.12f}",
                                    "displacement_cost": f"{event.cost.displacement_cost[row, column]:.12f}",
                                    "total_cost": f"{event.cost.total_cost[row, column]:.12f}",
                                    "selected": int(selected.get(global_id) == local_id),
                                }
                            )
    return path


def _write_assignments(online_run: IrregularCrossingRun, output: Path) -> Path:
    path = output / "assignments.csv"
    fields = (
        "schema_version",
        "mode",
        "global_track_id",
        "camera_a_local_track_id",
        "camera_b_local_track_id",
        "center_confirmation_timestamp",
        "camera_b_confirmation_timestamp",
        "association_state",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mode in online_run.modes:
            center_time = dict(mode.center_detection_event_times)
            b_time = dict(mode.camera_b_detection_event_times)
            chains = {
                global_id: (a_id, b_id)
                for global_id, a_id, b_id in mode.global_camera_a_to_camera_b
            }
            stage_a = dict(mode.global_to_camera_a)
            for global_id in online_run.geometry.global_track_ids:
                chain = chains.get(global_id)
                writer.writerow(
                    {
                        "schema_version": IRREGULAR_CROSSING_SCHEMA_VERSION,
                        "mode": mode.mode,
                        "global_track_id": global_id,
                        "camera_a_local_track_id": stage_a.get(global_id, ""),
                        "camera_b_local_track_id": chain[1] if chain else "",
                        "center_confirmation_timestamp": center_time.get(global_id, ""),
                        "camera_b_confirmation_timestamp": b_time.get(global_id, ""),
                        "association_state": (
                            "complete_chain"
                            if chain
                            else ("center_only" if global_id in stage_a else "undiscovered")
                        ),
                    }
                )
    return path


def _write_offline_truth(truth: IrregularOfflineTruth, output: Path) -> Path:
    path = output / "offline_truth.csv"
    b_lookup = dict(truth.global_to_camera_b)
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
        for global_id, camera_a_id in truth.global_to_camera_a:
            writer.writerow(
                {
                    "schema_version": IRREGULAR_CROSSING_SCHEMA_VERSION,
                    "seed": truth.seed,
                    "global_track_id": global_id,
                    "camera_a_local_track_id": camera_a_id,
                    "camera_b_local_track_id": b_lookup[global_id],
                    "usage_scope": "offline_evaluation_only",
                }
            )
    return path


def _write_mode_metrics(
    metrics: Sequence[ScanModeMetrics], output: Path
) -> Path:
    path = output / "mode_metrics.csv"
    fields = tuple(metrics[0].to_dict())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for metric in metrics:
            writer.writerow(metric.to_dict())
    return path


def _write_metrics_json(
    online_run: IrregularCrossingRun,
    standard_metrics: Sequence[ScanModeMetrics],
    batch_metrics: Sequence[ScanModeMetrics],
    output: Path,
) -> Path:
    path = output / "metrics.json"
    payload = {
        "schema_version": IRREGULAR_CROSSING_SCHEMA_VERSION,
        "validation_date": "2026-08-10",
        "scenario": "ideal_20_target_irregular_crossing_narrow_fov_scan",
        "geometry": {
            "initial_radial_span_m": online_run.geometry.initial_radial_span_m,
            "initial_altitude_span_m": online_run.geometry.initial_altitude_span_m,
            "minimum_pairwise_3d_separation_m": (
                online_run.geometry.minimum_pairwise_3d_separation_m
            ),
            "projected_crossing_pair_count_A": len(
                online_run.geometry.projected_crossing_pairs_a
            ),
            "projected_crossing_pair_count_B": len(
                online_run.geometry.projected_crossing_pairs_b
            ),
            "crossing_definition": (
                "polyline segment intersection or minimum segment distance <= 2.5% image width"
            ),
        },
        "standard_seed_modes": [metric.to_dict() for metric in standard_metrics],
        "coverage_safe_batch": {
            "seed_count": len(batch_metrics),
            "passed_seed_count": sum(
                metric.coverage_safe_acceptance_passed() for metric in batch_metrics
            ),
            "all_seeds_passed": all(
                metric.coverage_safe_acceptance_passed() for metric in batch_metrics
            ),
            "minimum_center_discovery_ratio": min(
                metric.center_discovery_ratio for metric in batch_metrics
            ),
            "minimum_camera_b_cued_observation_ratio": min(
                metric.camera_b_cued_observation_ratio for metric in batch_metrics
            ),
            "minimum_complete_chain_ratio": min(
                metric.complete_chain_ratio for metric in batch_metrics
            ),
            "minimum_stage_a_accuracy": min(
                float(metric.stage_a_association_accuracy) for metric in batch_metrics
            ),
            "minimum_stage_b_accuracy": min(
                float(metric.stage_b_association_accuracy) for metric in batch_metrics
            ),
            "total_id_switch_count": sum(metric.id_switch_count for metric in batch_metrics),
            "total_duplicate_assignment_count": sum(
                metric.duplicate_assignment_count for metric in batch_metrics
            ),
            "total_online_truth_usage_count": sum(
                metric.online_truth_usage_count for metric in batch_metrics
            ),
            "total_global_track_id_rewrite_count": sum(
                metric.global_track_id_rewrite_count for metric in batch_metrics
            ),
            "seeds": [metric.to_dict() for metric in batch_metrics],
        },
        "evidence_boundary": {
            "point_mass": True,
            "error_injection": False,
            "airsim": False,
            "real_flight": False,
            "gnn_executed": False,
            "scan_visibility_rate_hz": 100.0,
            "hungarian_execution_rate": "event_driven_after_confirmation_not_100hz",
        },
    }
    _write_json(path, payload)
    return path


def _write_figures(
    online_run: IrregularCrossingRun,
    metrics: Sequence[ScanModeMetrics],
    output: Path,
) -> tuple[Path, ...]:
    plt = _load_pyplot()
    paths = tuple(output / name for name in FIGURE_FILES)
    _plot_geometry(plt, online_run, paths[0])
    _plot_crossings(plt, online_run, paths[1])
    _plot_coverage_timeline(plt, online_run, "mechanical_2s", paths[2])
    _plot_coverage_timeline(plt, online_run, "coverage_safe", paths[3])
    _plot_gimbal_angles(plt, online_run, paths[4])
    _plot_cumulative(plt, online_run, paths[5])
    _plot_mode_metrics(plt, metrics, paths[6])
    _plot_event_costs(plt, online_run, "stage_a", paths[7])
    _plot_event_costs(plt, online_run, "stage_b", paths[8])
    _plot_final_chain(plt, online_run, metrics, paths[9])
    return paths


def _plot_geometry(plt: object, online_run: IrregularCrossingRun, path: Path) -> None:
    initial = online_run.geometry.target_state_history_ned[0, :, :3]
    camera_a = np.asarray(online_run.config.camera_a_position_ned)
    camera_b = online_run.geometry.camera_b_position_history_ned[0]
    ranges = np.linalg.norm(initial - camera_a[None, :], axis=1)
    figure = plt.figure(figsize=(11, 8))
    axis = figure.add_subplot(111, projection="3d")
    scatter = axis.scatter(
        initial[:, 0], initial[:, 1], -initial[:, 2], c=ranges, cmap="viridis", s=45
    )
    for index, global_id in enumerate(online_run.geometry.global_track_ids):
        axis.text(initial[index, 0], initial[index, 1], -initial[index, 2], global_id, fontsize=6)
    axis.scatter([camera_a[0]], [camera_a[1]], [-camera_a[2]], marker="^", s=95, color="#286090", label="Camera A")
    axis.scatter([camera_b[0]], [camera_b[1]], [-camera_b[2]], marker="s", s=70, color="#2f7d32", label="Camera B")
    axis.set_xlabel("North / m")
    axis.set_ylabel("East / m")
    axis.set_zlabel("Altitude / m")
    axis.set_title("Irregular radial and altitude staggering at t=0")
    axis.legend(loc="upper left")
    figure.colorbar(scatter, ax=axis, shrink=0.65, label="range from A / m")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_crossings(plt: object, online_run: IrregularCrossingRun, path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(14, 6.5))
    for axis, pixels, pairs, title in (
        (
            axes[0],
            online_run.geometry.camera_a_reference_pixels,
            online_run.geometry.projected_crossing_pairs_a,
            "A reference image plane",
        ),
        (
            axes[1],
            online_run.geometry.camera_b_reference_pixels,
            online_run.geometry.projected_crossing_pairs_b,
            "B translating reference image plane",
        ),
    ):
        crossing_ids = {
            value
            for pair in pairs
            for value in (pair.first_global_track_id, pair.second_global_track_id)
        }
        for index, global_id in enumerate(online_run.geometry.global_track_ids):
            color = "#b33a3a" if global_id in crossing_ids else "#aaaaaa"
            axis.plot(pixels[:, index, 0], pixels[:, index, 1], color=color, linewidth=1.5, alpha=0.8)
            axis.text(pixels[0, index, 0], pixels[0, index, 1], global_id, fontsize=5.5)
        pair_details = []
        for pair in pairs[:6]:
            separation = _minimum_3d_separation_for_pair(
                online_run,
                pair.first_global_track_id,
                pair.second_global_track_id,
            )
            crossing_kind = "cross" if pair.exact_segment_intersection else "near"
            pair_details.append(
                f"{pair.first_global_track_id}/{pair.second_global_track_id}: "
                f"min 3D {separation:.1f} m ({crossing_kind})"
            )
        axis.text(
            0.01,
            0.02,
            "\n".join(pair_details),
            transform=axis.transAxes,
            va="bottom",
            fontsize=6.2,
            bbox={"facecolor": "white", "edgecolor": "#888888", "alpha": 0.88},
        )
        axis.invert_yaxis()
        axis.grid(alpha=0.2)
        axis.set_xlabel("u / pixel")
        axis.set_ylabel("v / pixel")
        axis.set_title(f"{title}: crossing/near pairs={len(pairs)}")
    figure.suptitle("Projected trajectory intersections; paired targets remain separated in 3D")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _minimum_3d_separation_for_pair(
    online_run: IrregularCrossingRun,
    first_global_track_id: str,
    second_global_track_id: str,
) -> float:
    index_by_id = {
        global_id: index
        for index, global_id in enumerate(online_run.geometry.global_track_ids)
    }
    first_index = index_by_id[first_global_track_id]
    second_index = index_by_id[second_global_track_id]
    positions = online_run.geometry.target_state_history_ned[:, :, :3]
    separation = np.linalg.norm(
        positions[:, first_index] - positions[:, second_index], axis=1
    )
    return float(np.min(separation))


def _plot_coverage_timeline(
    plt: object, online_run: IrregularCrossingRun, mode_name: str, path: Path
) -> None:
    mode = online_run.mode(mode_name)
    time = np.array([record.measurement_timestamp for record in mode.timeline])
    boresight = np.array(
        [record.center_boresight_relative_azimuth_deg for record in mode.timeline]
    )
    visible = np.array([record.center_visible_anonymous_count for record in mode.timeline])
    confirmed = np.array([record.center_confirmed_count for record in mode.timeline])
    figure, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(time, boresight, color="#286090", linewidth=0.9)
    half_fov = 0.5 * online_run.config.camera_a_horizontal_fov_deg
    axes[0].fill_between(time, boresight - half_fov, boresight + half_fov, color="#286090", alpha=0.18, label="instantaneous FOV")
    axes[0].set_ylabel("relative azimuth / deg")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.2)
    axes[1].step(time, visible, where="post", color="#b33a3a")
    axes[1].set_ylabel("visible anonymous tracks")
    axes[1].grid(alpha=0.2)
    axes[2].step(time, confirmed, where="post", color="#2f7d32")
    axes[2].set_ylabel("confirmed center bindings")
    axes[2].set_xlabel("analytic scan time / s")
    axes[2].grid(alpha=0.2)
    figure.suptitle(f"{mode_name}: 100 Hz visibility timeline")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_gimbal_angles(plt: object, online_run: IrregularCrossingRun, path: Path) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True)
    colors = {"mechanical_2s": "#b33a3a", "coverage_safe": "#286090"}
    for mode in online_run.modes:
        time = [record.measurement_timestamp for record in mode.timeline]
        axes[0].plot(time, [record.center_boresight_relative_azimuth_deg for record in mode.timeline], label=mode.mode, color=colors[mode.mode], linewidth=0.9)
        axes[1].plot(time, [record.camera_b_boresight_azimuth_deg for record in mode.timeline], label=mode.mode, color=colors[mode.mode], linewidth=0.9)
    axes[0].set_ylabel("A relative azimuth / deg")
    axes[1].set_ylabel("B absolute azimuth / deg")
    axes[1].set_xlabel("time / s")
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.legend(loc="upper right")
    figure.suptitle("Center search gimbal and cued B gimbal angles")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_cumulative(plt: object, online_run: IrregularCrossingRun, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(11, 6.5))
    for mode, color in ((online_run.mode("mechanical_2s"), "#b33a3a"), (online_run.mode("coverage_safe"), "#286090")):
        time = [record.measurement_timestamp for record in mode.timeline]
        axis.step(time, [record.center_confirmed_count for record in mode.timeline], where="post", color=color, label=f"{mode.mode} A")
        axis.step(time, [record.camera_b_confirmed_count for record in mode.timeline], where="post", color=color, linestyle="--", label=f"{mode.mode} B")
    axis.axhline(online_run.config.target_count, color="#777777", linestyle=":", linewidth=1.0)
    axis.set_xlabel("time / s")
    axis.set_ylabel("cumulative confirmed target count")
    axis.set_ylim(-0.5, online_run.config.target_count + 1)
    axis.grid(alpha=0.2)
    axis.legend(loc="lower right")
    axis.set_title("Cumulative center discovery and B cued observation")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_mode_metrics(plt: object, metrics: Sequence[ScanModeMetrics], path: Path) -> None:
    labels = [metric.mode for metric in metrics]
    values = np.array(
        [
            [metric.center_discovery_ratio, metric.camera_b_cued_observation_ratio, metric.complete_chain_ratio]
            for metric in metrics
        ]
    )
    figure, axis = plt.subplots(figsize=(10, 6.5))
    x = np.arange(len(labels))
    width = 0.22
    for offset, name, color in (
        (-width, "center discovery", "#286090"),
        (0.0, "B cued observation", "#2f7d32"),
        (width, "complete chain", "#b33a3a"),
    ):
        column = {"center discovery": 0, "B cued observation": 1, "complete chain": 2}[name]
        axis.bar(x + offset, values[:, column], width=width, label=name, color=color)
    axis.set_xticks(x, labels=labels)
    axis.set_ylim(0.0, 1.08)
    axis.set_ylabel("ratio")
    axis.grid(axis="y", alpha=0.2)
    axis.legend(loc="upper left")
    axis.set_title("Observed scan-mode result; mechanical coverage is not forced")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_event_costs(
    plt: object, online_run: IrregularCrossingRun, stage: str, path: Path
) -> None:
    mode = online_run.mode("coverage_safe")
    events = mode.stage_a_events if stage == "stage_a" else mode.stage_b_events
    global_ids = online_run.geometry.global_track_ids
    local_ids = sorted(
        {
            local_id
            for event in events
            for local_id in event.local_track_ids
        }
    )
    matrix = np.full((len(global_ids), len(local_ids)), np.nan)
    selected_cells: list[tuple[int, int]] = []
    global_index = {value: index for index, value in enumerate(global_ids)}
    local_index = {value: index for index, value in enumerate(local_ids)}
    for event in events:
        selected = dict(event.selected_pairs)
        for row, global_id in enumerate(event.global_track_ids):
            for column, local_id in enumerate(event.local_track_ids):
                matrix[global_index[global_id], local_index[local_id]] = event.cost.total_cost[row, column]
            if global_id in selected:
                selected_cells.append((global_index[global_id], local_index[selected[global_id]]))
    figure, axis = plt.subplots(figsize=(10.5, 8))
    masked = np.ma.masked_invalid(np.log10(1.0 + matrix))
    image = axis.imshow(masked, cmap="viridis", aspect="auto")
    for row, column in selected_cells:
        axis.scatter(column, row, marker="s", facecolors="none", edgecolors="#ffdd57", s=55)
    axis.set_xticks(np.arange(len(local_ids)), labels=local_ids, rotation=90, fontsize=6)
    axis.set_yticks(np.arange(len(global_ids)), labels=global_ids, fontsize=6)
    axis.set_xlabel("anonymous local track")
    axis.set_ylabel("available center GlobalTrack")
    axis.set_title(f"coverage_safe {stage} event costs; blank cells were already unavailable")
    figure.colorbar(image, ax=axis, shrink=0.82, label="log10(1 + cost)")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _plot_final_chain(
    plt: object,
    online_run: IrregularCrossingRun,
    metrics: Sequence[ScanModeMetrics],
    path: Path,
) -> None:
    safe = online_run.mode("coverage_safe")
    safe_metric = next(metric for metric in metrics if metric.mode == "coverage_safe")
    figure, axes = plt.subplots(1, 2, figsize=(14, 8), gridspec_kw={"width_ratios": (1.0, 1.2)})
    axes[0].axis("off")
    summary = (
        f"initial radial span: {safe_metric.initial_radial_span_m:.1f} m\n"
        f"initial altitude span: {safe_metric.initial_altitude_span_m:.1f} m\n"
        f"minimum 3D separation: {safe_metric.minimum_pairwise_3d_separation_m:.1f} m\n"
        f"projected crossing pairs A/B: {safe_metric.projected_crossing_pair_count_a}/{safe_metric.projected_crossing_pair_count_b}\n"
        f"safe scan completion: {safe_metric.scan_actual_duration_s:.2f} s\n"
        f"confirmation dwell: {safe_metric.confirmation_dwell_time_s:.2f} s\n"
        f"observed revisit interval: {safe_metric.revisit_interval_s:.2f} s\n"
        f"complete chain ratio: {safe_metric.complete_chain_ratio:.2f}"
    )
    axes[0].text(0.05, 0.95, summary, va="top", fontsize=12, linespacing=1.7)
    axes[0].set_title("Geometry and scan result")
    axes[1].axis("off")
    lines = ["GlobalTrack     Camera A       Camera B"]
    lines.extend(
        f"{global_id:<14}{camera_a_id:<15}{camera_b_id}"
        for global_id, camera_a_id, camera_b_id in safe.global_camera_a_to_camera_b
    )
    axes[1].text(0.02, 0.98, "\n".join(lines), va="top", family="monospace", fontsize=9.2, linespacing=1.25)
    axes[1].set_title("coverage_safe final public chain")
    figure.tight_layout()
    figure.savefig(path, dpi=170)
    plt.close(figure)


def _write_animation(online_run: IrregularCrossingRun, path: Path) -> Path:
    plt = _load_pyplot()
    import matplotlib.animation as animation
    from matplotlib.patches import Rectangle

    media_times = online_run.geometry.physics_timestamps[::2]
    figure = plt.figure(figsize=(14, 8))
    axis_3d = figure.add_subplot(2, 2, 1, projection="3d")
    axis_mechanical = figure.add_subplot(2, 2, 2)
    axis_safe = figure.add_subplot(2, 2, 4)
    axis_count = figure.add_subplot(2, 2, 3)
    initial = online_run.geometry.target_state_history_ned[0, :, :3]
    all_positions = online_run.geometry.target_state_history_ned[:, :, :3]
    target_scatter = axis_3d.scatter([], [], [], color="#b33a3a", s=25)
    camera_a = np.asarray(online_run.config.camera_a_position_ned)
    camera_a_scatter = axis_3d.scatter([camera_a[0]], [camera_a[1]], [-camera_a[2]], marker="^", s=75, color="#286090")
    camera_b_scatter = axis_3d.scatter([], [], [], marker="s", s=55, color="#2f7d32")
    axis_3d.set_xlim(np.min(all_positions[:, :, 0]) - 200, np.max(all_positions[:, :, 0]) + 100)
    axis_3d.set_ylim(np.min(all_positions[:, :, 1]) - 80, np.max(all_positions[:, :, 1]) + 80)
    axis_3d.set_zlim(np.min(-all_positions[:, :, 2]) - 20, np.max(-all_positions[:, :, 2]) + 20)
    axis_3d.set_xlabel("North / m")
    axis_3d.set_ylabel("East / m")
    axis_3d.set_zlabel("Altitude / m")
    mode_axes = {
        "mechanical_2s": axis_mechanical,
        "coverage_safe": axis_safe,
    }
    mode_scatter: dict[str, object] = {}
    mode_rectangles: dict[str, Rectangle] = {}
    for mode_name, axis in mode_axes.items():
        axis.set_xlim(-7.0, 7.0)
        axis.set_ylim(-0.3, 0.3)
        axis.set_xlabel("relative azimuth / deg")
        axis.set_ylabel("relative elevation / deg")
        axis.set_title(mode_name)
        axis.grid(alpha=0.2)
        mode_scatter[mode_name] = axis.scatter([], [], s=32, color="#aaaaaa")
        rectangle = Rectangle((0, 0), online_run.config.camera_a_horizontal_fov_deg, _vertical_fov(online_run.camera_a_intrinsics), fill=False, edgecolor="#286090", linewidth=1.5)
        axis.add_patch(rectangle)
        mode_rectangles[mode_name] = rectangle
    count_lines: dict[tuple[str, str], object] = {}
    for mode_name, color in (("mechanical_2s", "#b33a3a"), ("coverage_safe", "#286090")):
        count_lines[(mode_name, "A")], = axis_count.plot([], [], color=color, label=f"{mode_name} A")
        count_lines[(mode_name, "B")], = axis_count.plot([], [], color=color, linestyle="--", label=f"{mode_name} B")
    axis_count.set_xlim(0, online_run.config.duration_s)
    axis_count.set_ylim(0, online_run.config.target_count + 1)
    axis_count.set_xlabel("time / s")
    axis_count.set_ylabel("confirmed count")
    axis_count.grid(alpha=0.2)
    axis_count.legend(fontsize=7, loc="lower right")
    time_text = figure.text(0.02, 0.02, "", family="monospace")

    def update(frame_number: int) -> tuple[object, ...]:
        timestamp = float(media_times[frame_number])
        physics_index = int(round(timestamp / online_run.config.physics_dt_s))
        positions = online_run.geometry.target_state_history_ned[physics_index, :, :3]
        target_scatter._offsets3d = (positions[:, 0], positions[:, 1], -positions[:, 2])
        b_position = online_run.geometry.camera_b_position_history_ned[physics_index]
        camera_b_scatter._offsets3d = ([b_position[0]], [b_position[1]], [-b_position[2]])
        axis_3d.set_title(f"Irregular 3D scene t={timestamp:.1f} s")
        center = np.mean(positions, axis=0)
        center_vector = center - camera_a
        center_azimuth = np.degrees(np.arctan2(center_vector[1], center_vector[0]))
        center_elevation = np.degrees(np.arctan2(-center_vector[2], np.hypot(center_vector[0], center_vector[1])))
        delta = positions - camera_a[None, :]
        relative_azimuth = np.degrees(np.arctan2(delta[:, 1], delta[:, 0])) - center_azimuth
        relative_elevation = np.degrees(np.arctan2(-delta[:, 2], np.hypot(delta[:, 0], delta[:, 1]))) - center_elevation
        scan_index = int(round(timestamp / online_run.config.scan_dt_s))
        for mode_name in mode_axes:
            mode = online_run.mode(mode_name)
            record = mode.timeline[min(scan_index, len(mode.timeline) - 1)]
            confirmed = {global_id for global_id, event_time in mode.center_detection_event_times if event_time <= timestamp}
            colors = ["#2f7d32" if global_id in confirmed else "#aaaaaa" for global_id in online_run.geometry.global_track_ids]
            mode_scatter[mode_name].set_offsets(np.column_stack((relative_azimuth, relative_elevation)))
            mode_scatter[mode_name].set_color(colors)
            rectangle = mode_rectangles[mode_name]
            rectangle.set_xy((record.center_boresight_relative_azimuth_deg - 0.5 * online_run.config.camera_a_horizontal_fov_deg, -0.5 * _vertical_fov(online_run.camera_a_intrinsics)))
            timeline_time = np.array([item.measurement_timestamp for item in mode.timeline[: scan_index + 1]])
            count_lines[(mode_name, "A")].set_data(timeline_time, [item.center_confirmed_count for item in mode.timeline[: scan_index + 1]])
            count_lines[(mode_name, "B")].set_data(timeline_time, [item.camera_b_confirmed_count for item in mode.timeline[: scan_index + 1]])
        time_text.set_text(f"scan visibility=100 Hz | assignment=confirmation events | media t={timestamp:.1f}s")
        return (target_scatter, camera_a_scatter, camera_b_scatter, *mode_scatter.values(), *mode_rectangles.values(), *count_lines.values(), time_text)

    movie = animation.FuncAnimation(figure, update, frames=len(media_times), interval=100, blit=False)
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    movie.save(path, writer=animation.PillowWriter(fps=10), dpi=100)
    plt.close(figure)
    return path


def _write_report(
    online_run: IrregularCrossingRun,
    standard_metrics: Sequence[ScanModeMetrics],
    batch_metrics: Sequence[ScanModeMetrics],
    output: Path,
    *,
    media_available: bool,
) -> Path:
    path = output / "D5_IDEAL_IRREGULAR_CROSSING_SCAN_REPORT_CN.md"
    mechanical = next(metric for metric in standard_metrics if metric.mode == "mechanical_2s")
    safe = next(metric for metric in standard_metrics if metric.mode == "coverage_safe")
    seed_rows = "\n".join(
        f"| {metric.seed} | {metric.center_discovery_ratio:.3f} | {metric.camera_b_cued_observation_ratio:.3f} | {metric.complete_chain_ratio:.3f} | {metric.stage_a_association_accuracy:.3f} | {metric.stage_b_association_accuracy:.3f} | {metric.id_switch_count} |"
        for metric in batch_metrics
    )
    images = ""
    if media_available:
        captions = (
            "不规则三维初始几何",
            "A/B 参考像面交叉航迹",
            "机械扫描覆盖时间线",
            "安全覆盖扫描时间线",
            "A/B 云台角度",
            "累计发现曲线",
            "两模式结果比较",
            "A 侧事件代价",
            "B 侧事件代价",
            "最终关系链",
        )
        images = "\n\n".join(
            f"### {index}. {caption}\n\n![{caption}]({file_name})"
            for index, (caption, file_name) in enumerate(
                zip(captions, FIGURE_FILES, strict=True), start=1
            )
        )
    animation_text = (
        "动态过程见 [scan_registration_process.gif](scan_registration_process.gif)。"
        if media_available
        else "本次使用跳过媒体选项，未生成图像和 GIF。"
    )
    report = f"""# D5 不规则三维交叉目标窄视场扫描实验

## 结论

本实验把原有全时段可见的两级配准基线改为窄视场扫描。标准 seed `20260810` 的 20 个目标初始径向跨度为 `{safe.initial_radial_span_m:.1f}` 米，高度跨度为 `{safe.initial_altitude_span_m:.1f}` 米，全时段最小三维间距为 `{safe.minimum_pairwise_3d_separation_m:.1f}` 米。A、B 参考像面的交叉或明确近距交叉分别为 `{safe.projected_crossing_pair_count_a}` 对和 `{safe.projected_crossing_pair_count_b}` 对。

机械模式的 100 Hz 相邻光轴间隔为 1.8 度，明显大于 A 相机 0.621 度水平视场。标准场景中的目标位于离散采样间隙，15 秒内中心发现率为 `{mechanical.center_discovery_ratio:.3f}`，完整链比例为 `{mechanical.complete_chain_ratio:.3f}`。该结果是本次目标角位置、采样相位和视场共同作用的实际值，没有强制补齐覆盖。

安全覆盖模式按 20% 视场重叠把速度限制为 49.68 度/秒。中心发现率、B 提示观测率和完整关系链比例均为 `1.0`，完成时间为 `{safe.scan_actual_duration_s:.2f}` 秒。seed `20260810-20260819` 共 10 组全部通过，A、B 关联准确率和完整链均为 `1.0`，身份切换、重复分配、在线 truth 使用和全局编号改写均为 0。

结果来自无误差质点和解析相机模型。它不是 AirSim、实飞或真实检测性能。候选关系和代价图没有执行图神经网络。

## 三维场景

中心节点 A 固定。目标距 A 为约 2.8 至 3.2 千米，方位位于 45 度搜索扇区中央，初始角范围小于 12 度。目标以不同距离和高度错列，不构成矩形或单一平面。每对目标设置约 0.3 米/秒的相向横向速度，其余速度沿径向，使总速度保持 3.5 至 4.7 米/秒。配对目标的像面轨迹发生交叉，但通过约 30 米径向错层保持实体分离。

B 位于目标群质心后方 500 米，并保持固定相对偏置随质心平移。B 只接收 A 已完成绑定的中心航迹提示，按当前云台角度选择最近的下一目标，不参与拦截。

## 相机模型

A 使用 2600×2160 针孔相机，水平视场 0.621 度，按相同焦距换算的垂直视场约 `{_vertical_fov(online_run.camera_a_intrinsics):.3f}` 度，水平瞬时视场约 `{np.deg2rad(online_run.config.camera_a_horizontal_fov_deg) / online_run.config.camera_a_width_px * 1e6:.2f}` 微弧度/像素。B 使用 1920×1080 针孔相机，水平视场 2.750979 度，垂直视场约 `{_vertical_fov(online_run.camera_b_intrinsics):.3f}` 度，水平瞬时视场约 `{np.deg2rad(online_run.config.camera_b_horizontal_fov_deg) / online_run.config.camera_b_width_px * 1e6:.2f}` 微弧度/像素。

投影交叉按无序目标对统计。若两条参考像面折线的任一线段相交，或两条线段的最小距离不超过图像宽度的 2.5%，则记为一对交叉或明确近距交叉。A 阈值为 65 像素，B 阈值为 48 像素。该指标描述图像关联难度，不表示目标在三维空间相撞。

## 扫描状态机

扫描可见性在 0.01 秒解析时间轴上计算，即 100 Hz。质点动力学定义周期仍为 0.1 秒，两个动力学节点之间使用常速度解析传播。关联算法不按 100 Hz 连续求解，只在目标连续凝视 5 帧、累计 0.05 秒后执行一次时间窗代价和匈牙利匹配。图表和 GIF 按 0.1 秒抽样。

`mechanical_2s` 以 180 度/秒往返扫描。`coverage_safe` 把相邻帧光轴间隔限制为 0.4968 度，保留 20% 水平视场重叠。两种模式发现目标后都保持 5 帧确认，再从原扫描位置继续。安全覆盖模式实测目标重访间隔中位数为 `{safe.revisit_interval_s:.2f}` 秒。

B 只处理 A 已确认的中心航迹。云台最大速度为 180 度/秒，按当前位置选择转角最小的待观察目标；进入 B 视场后同样凝视 5 帧。B 的本地像素轨迹保持匿名，中心使用已绑定三维航迹重投影完成第二级匈牙利匹配。

## 时间窗配准

两级配准复用原理想基线的最近五帧代价：

```text
C(i,j) = mean(||u_hat(i)-u(j)||^2 / 20^2)
       + 0.25 * mean(||delta_u_hat(i)-delta_u(j)||^2 / 10^2)
```

A 每次确认时只对尚未绑定的中心航迹和当前匿名轨迹求解。B 每次确认时只对 A 已绑定、B 尚未绑定的中心航迹求解。每个事件的完整矩阵、双时间戳、协方差和选中项均写入 CSV。离线真值只在算法输出形成后计算准确率。

## 图表

{images}

{animation_text}

## 十组结果

| seed | 中心发现率 | B提示观测率 | 完整链 | A准确率 | B准确率 | ID切换 |
|---:|---:|---:|---:|---:|---:|---:|
{seed_rows}

## 边界

本实验没有加入漏检、虚警、遮挡、像素噪声、位置姿态误差、时间偏差、通信丢包和本地轨迹中断。机械模式漏区证明离散扫描速度不能只按机械转速确定，不能据此推导真实吊舱检测率。安全覆盖 20/20 是解析模型结果，后续仍需在误差注入、AirSim 图像和真实吊舱回放中重新标定。

三维交叉图和事件代价图只解释几何候选与匈牙利选择。没有加载图神经网络权重，也没有绕过现有权重谱系校验。
"""
    path.write_text(report, encoding="utf-8")
    return path


def _load_pyplot() -> object:
    import matplotlib

    matplotlib.use("Agg")
    ensure_mplot3d(matplotlib)
    import matplotlib.pyplot as plt

    return plt


def _intrinsics_payload(intrinsics: object) -> dict[str, float | int]:
    return {
        "width_px": int(intrinsics.width_px),
        "height_px": int(intrinsics.height_px),
        "fx": float(intrinsics.fx),
        "fy": float(intrinsics.fy),
        "cx": float(intrinsics.cx),
        "cy": float(intrinsics.cy),
    }


def _vertical_fov(intrinsics: object) -> float:
    return float(np.degrees(2.0 * np.arctan(0.5 * intrinsics.height_px / intrinsics.fy)))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
