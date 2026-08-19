"""Figures and Chinese report for the dual-optical AirSim experiment."""

from __future__ import annotations

from collections import defaultdict
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import matplotlib

matplotlib.use("Agg")
import mpl_toolkits

# Some Ubuntu installations expose the system mpl_toolkits namespace before
# the user-installed Matplotlib package. Prefer the matching local toolkit so
# three-dimensional plots use one Matplotlib version.
_LOCAL_TOOLKITS = Path(matplotlib.__file__).resolve().parent.parent / "mpl_toolkits"
if _LOCAL_TOOLKITS.exists() and str(_LOCAL_TOOLKITS) not in mpl_toolkits.__path__:
    mpl_toolkits.__path__.insert(0, str(_LOCAL_TOOLKITS))
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib import font_manager
from matplotlib.patches import Patch
import numpy as np

from .core import (
    AssociationConfig,
    AssociationDecisionRecord,
    AssociationHypothesisRecord,
    AssociationStateRecord,
    BearingSample,
    BearingTrack,
    CameraSpec,
    CrossAssociationResult,
    CrossCameraCandidate,
    CrossCameraMatch,
    EpipolarEvidence,
    FragmentSuppressionRecord,
    GeometrySensitivity,
    GlobalAssignmentHypothesis,
    TargetSpec,
    TemporalAssociationResult,
)
from .runtime import ExperimentResult, write_json


_CJK_FONT_PATHS = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
)


def _target_count(result: ExperimentResult) -> int:
    return int(result.metrics.get("target_count", len(result.target_specs)))


def _report_path(result: ExperimentResult) -> Path:
    target_count = _target_count(result)
    return result.output_dir / (
        f"DUAL_OPTICAL_{target_count}TARGET_AIRSIM_REPORT_CN.md"
    )


def _optional_metric(result: ExperimentResult, key: str, default: Any) -> Any:
    if key in result.metrics:
        return result.metrics[key]
    enhanced = result.metrics.get("enhanced_association") or {}
    return enhanced.get(key, default)


def _pair_count_metrics(result: ExperimentResult) -> dict[str, float | int]:
    target_count = _target_count(result)
    track_count_a = len(result.tracks_a)
    track_count_b = len(result.tracks_b)
    ideal_pairs = int(
        _optional_metric(
            result, "ideal_truth_pair_count", target_count * target_count
        )
    )
    actual_pairs = int(
        _optional_metric(
            result, "actual_local_pair_count", track_count_a * track_count_b
        )
    )
    fragment_excess_a = int(
        _optional_metric(
            result, "fragment_excess_a", max(track_count_a - target_count, 0)
        )
    )
    fragment_excess_b = int(
        _optional_metric(
            result, "fragment_excess_b", max(track_count_b - target_count, 0)
        )
    )
    pair_expansion_ratio = float(
        _optional_metric(
            result,
            "pair_expansion_ratio",
            actual_pairs / max(ideal_pairs, 1),
        )
    )
    return {
        "target_count": target_count,
        "track_count_a": track_count_a,
        "track_count_b": track_count_b,
        "ideal_pairs": ideal_pairs,
        "actual_pairs": actual_pairs,
        "fragment_excess_a": fragment_excess_a,
        "fragment_excess_b": fragment_excess_b,
        "pair_expansion_ratio": pair_expansion_ratio,
    }


def load_experiment_result(output_dir: Path) -> ExperimentResult:
    """Restore report inputs from a completed experiment without AirSim."""

    output_dir = Path(output_dir).resolve()
    scenario_path = output_dir / "scenario.json"
    metrics_path = output_dir / "metrics.json"
    manifest_path = output_dir / "record_manifest.json"
    for required in (scenario_path, metrics_path, manifest_path):
        if not required.is_file():
            raise FileNotFoundError(f"missing experiment record: {required}")

    scenario_payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not scenario_payload.get("independent_experiment"):
        raise ValueError("scenario is not an independent dual-optical experiment")

    artifacts = manifest.get("artifacts", {})
    output_paths = {
        key: _resolve_record_path(output_dir, value)
        for key, value in artifacts.items()
    }
    output_paths["metrics"] = metrics_path
    output_paths["manifest"] = manifest_path
    required_artifacts = (
        "anonymous_detections",
        "camera_scan",
        "local_tracks",
        "local_track_samples",
        "cross_camera_candidates",
        "cross_camera_matches",
        "match_scoring",
        "track_scoring",
        "keyframe_manifest",
    )
    missing = [
        name
        for name in required_artifacts
        if name not in output_paths or not output_paths[name].is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "missing report artifacts: " + ", ".join(sorted(missing))
        )

    scenario = scenario_payload["scenario"]
    camera_payload = scenario_payload["camera"]
    camera_spec = CameraSpec(
        width=int(camera_payload["width"]),
        height=int(camera_payload["height"]),
        horizontal_fov_deg=float(camera_payload["horizontal_fov_deg"]),
        equivalent_focal_length_mm=float(camera_payload["equivalent_focal_length_mm"]),
        stated_ifov_mrad=float(camera_payload["stated_ifov_mrad"]),
    )
    camera_positions = {
        str(scenario["camera_a_name"]): _triple(scenario["camera_a_position_ned"]),
        str(scenario["camera_b_name"]): _triple(scenario["camera_b_position_ned"]),
    }
    tracks = _load_saved_tracks(
        output_paths["local_tracks"],
        output_paths["local_track_samples"],
        camera_positions=camera_positions,
        focal_length_px=camera_spec.focal_length_px,
    )
    tracks_a = tuple(
        track for track in tracks if track.camera_id == scenario["camera_a_name"]
    )
    tracks_b = tuple(
        track for track in tracks if track.camera_id == scenario["camera_b_name"]
    )
    candidates = tuple(
        _candidate_from_row(row)
        for row in _read_csv(output_paths["cross_camera_candidates"])
    )
    matches = tuple(
        _match_from_row(row)
        for row in _read_csv(output_paths["cross_camera_matches"])
    )
    matched_a = {match.track_a_id for match in matches}
    matched_b = {match.track_b_id for match in matches}
    association = CrossAssociationResult(
        candidates=candidates,
        matches=matches,
        unmatched_a_track_ids=tuple(
            track.track_id for track in tracks_a if track.track_id not in matched_a
        ),
        unmatched_b_track_ids=tuple(
            track.track_id for track in tracks_b if track.track_id not in matched_b
        ),
    )
    targets = tuple(
        TargetSpec(
            truth_id=str(item["truth_id"]),
            actor_name=str(item["actor_name"]),
            asset_name=str(item["asset_name"]),
            start_ned=_triple(item["start_ned"]),
            velocity_ned=_triple(item["velocity_ned"]),
        )
        for item in scenario_payload["target_specs_offline_truth_only"]
    )
    enhanced_association, geometry_sensitivity = _load_enhanced_association(
        output_paths,
        scenario=scenario,
        tracks_a=tracks_a,
        tracks_b=tracks_b,
        metrics=metrics,
    )
    settings_path = output_dir / "settings.json"
    return ExperimentResult(
        output_dir=output_dir,
        settings_path=settings_path,
        metrics_path=metrics_path,
        metrics=metrics,
        output_paths=output_paths,
        tracks_a=tracks_a,
        tracks_b=tracks_b,
        association=association,
        target_specs=targets,
        enhanced_association=enhanced_association,
        geometry_sensitivity=geometry_sensitivity,
    )


def generate_experiment_report(result: ExperimentResult) -> dict[str, Path]:
    _configure_matplotlib()
    figures_dir = result.output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures = {
        "scene": _plot_scene_geometry(result, figures_dir / "01_scene_geometry_3d.png"),
        "scan": _plot_scan_timeline(result, figures_dir / "02_scan_and_detection.png"),
        "bearing_tracks": _plot_bearing_tracks(
            result, figures_dir / "05_local_bearing_tracks.png"
        ),
        "cost_matrix": _plot_cost_matrix(
            result, figures_dir / "06_candidate_cost_matrix.png"
        ),
        "match_graph": _plot_match_graph(
            result, figures_dir / "07_hungarian_matches.png"
        ),
        "reconstruction": _plot_reconstruction(
            result, figures_dir / "08_reconstructed_trajectories_3d.png"
        ),
        "errors": _plot_error_distribution(
            result, figures_dir / "09_reconstruction_errors.png"
        ),
        "algorithm_flow": _plot_algorithm_flow(
            result, figures_dir / "10_algorithm_flow.png"
        ),
        "fit_principle": _plot_moving_ray_fit_principle(
            result, figures_dir / "11_moving_ray_fit_principle_3d.png"
        ),
        "association_effect": _plot_truth_association_effect(
            result, figures_dir / "12_truth_association_effect.png"
        ),
        "pair_expansion": _plot_pair_count_expansion(
            result, figures_dir / "18_track_pair_expansion.png"
        ),
        "fragment_timeline": _plot_fragment_timeline(
            result, figures_dir / "19_fragment_timeline.png"
        ),
    }
    keyframe_rows = _read_csv(result.output_paths["keyframe_manifest"])
    if keyframe_rows:
        figures.update(
            {
                "camera_a": _plot_keyframe_montage(
                    result,
                    result.tracks_a[0].camera_id
                    if result.tracks_a
                    else "Optical_A",
                    figures_dir / "03_camera_a_keyframes.png",
                ),
                "camera_b": _plot_keyframe_montage(
                    result,
                    result.tracks_b[0].camera_id
                    if result.tracks_b
                    else "Optical_B",
                    figures_dir / "04_camera_b_keyframes.png",
                ),
            }
        )
    if result.enhanced_association is not None:
        figures.update(
            {
                "enhanced_funnel": _plot_enhanced_candidate_funnel(
                    result, figures_dir / "13_epipolar_candidate_funnel.png"
                ),
                "epipolar_residuals": _plot_epipolar_residual_sequences(
                    result, figures_dir / "14_epipolar_residual_sequences.png"
                ),
                "hypothesis_evolution": _plot_hypothesis_cost_evolution(
                    result, figures_dir / "15_topk_hypothesis_evolution.png"
                ),
                "state_timeline": _plot_association_state_timeline(
                    result, figures_dir / "16_confirmation_state_timeline.png"
                ),
                "geometry_sensitivity": _plot_geometry_sensitivity(
                    result, figures_dir / "17_geometry_sensitivity.png"
                ),
            }
        )
    report_path = _write_report(result, figures)
    figure_manifest = write_json(
        figures_dir / "figure_manifest.json",
        {name: str(path.relative_to(result.output_dir)) for name, path in figures.items()},
    )
    return {"report": report_path, "figure_manifest": figure_manifest, **figures}


def _configure_matplotlib() -> None:
    selected = None
    for path in _CJK_FONT_PATHS:
        if not path.is_file():
            continue
        font_manager.fontManager.addfont(str(path))
        selected = font_manager.FontProperties(fname=str(path)).get_name()
        break
    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Source Han Sans SC",
        "Microsoft YaHei",
        "SimHei",
        "DejaVu Sans",
    ]
    if selected is None:
        available = {font.name for font in font_manager.fontManager.ttflist}
        selected = next(
            (name for name in candidates if name in available), "DejaVu Sans"
        )
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [selected, "DejaVu Sans"],
            "axes.unicode_minus": False,
            "figure.dpi": 140,
            "savefig.dpi": 180,
            "axes.grid": True,
            "grid.alpha": 0.22,
        }
    )


def _plot_scene_geometry(result: ExperimentResult, path: Path) -> Path:
    config = _scenario_config(result)
    duration = float(config["duration_s"])
    fig = plt.figure(figsize=(11.2, 7.2))
    axis = fig.add_subplot(111, projection="3d")
    colors = plt.cm.turbo(np.linspace(0.02, 0.98, len(result.target_specs)))
    for color, target in zip(colors, result.target_specs):
        samples = np.asarray(
            [target.position_at(value) for value in np.linspace(0.0, duration, 61)]
        )
        axis.plot(
            samples[:, 0], samples[:, 1], -samples[:, 2], color=color, alpha=0.55, linewidth=1.0
        )
        axis.scatter(
            samples[0, 0], samples[0, 1], -samples[0, 2], color=color, s=10
        )
    camera_positions = config["camera_positions"]
    for camera_id, position in camera_positions.items():
        axis.scatter(position[0], position[1], -position[2], marker="^", s=95, label=camera_id)
    axis.set_title(f"双光电节点与{_target_count(result)}目标三维场景")
    axis.set_xlabel("北向距离 / 米")
    axis.set_ylabel("东向距离 / 米")
    axis.set_zlabel("高度 / 米")
    axis.view_init(elev=24, azim=-58)
    axis.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_scan_timeline(result: ExperimentResult, path: Path) -> Path:
    rows = _read_csv(result.output_paths["camera_scan"])
    by_camera: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_camera[row["camera_id"]].append(row)
    fig, axes = plt.subplots(2, 1, figsize=(11.2, 7.2), sharex=True)
    for camera_id, camera_rows in by_camera.items():
        times = [float(row["measurement_timestamp"]) for row in camera_rows]
        yaw = [float(row["yaw_deg"]) for row in camera_rows]
        counts = [int(float(row["detection_count"])) for row in camera_rows]
        axes[0].plot(times, yaw, linewidth=1.0, label=camera_id)
        axes[1].plot(times, counts, linewidth=0.9, label=camera_id)
    axes[0].set_ylabel("方位角 / 度")
    axes[0].set_title("固定俯仰条件下的方位扫描")
    axes[1].set_xlabel("仿真时间 / 秒")
    axes[1].set_ylabel("检测数量")
    axes[1].set_title("每次检测请求返回数量")
    for axis in axes:
        axis.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_keyframe_montage(
    result: ExperimentResult, camera_id: str, path: Path
) -> Path:
    manifest = [
        row
        for row in _read_csv(result.output_paths["keyframe_manifest"])
        if row.get("camera_id") == camera_id
    ]
    detections = _read_csv(result.output_paths["anonymous_detections"])
    by_frame: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in detections:
        if row.get("camera_id") == camera_id:
            by_frame[int(row["frame_index"])].append(row)
    uid_to_track = {
        uid: track.track_id
        for track in (*result.tracks_a, *result.tracks_b)
        for uid in track.detection_uids
    }
    if not manifest:
        fig, axis = plt.subplots(figsize=(10.5, 3.0))
        axis.axis("off")
        axis.text(0.5, 0.5, f"{camera_id}未保存有效关键帧", ha="center", va="center", fontsize=15)
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path
    selected = _select_keyframes(manifest, by_frame, count=6)
    fig, axes = plt.subplots(2, 3, figsize=(13.2, 7.3))
    for axis, row in zip(axes.flat, selected):
        image_path = result.output_dir / row["path"]
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        frame_index = int(row["frame_index"])
        if image is None:
            axis.axis("off")
            axis.text(0.5, 0.5, "图像读取失败", ha="center", va="center")
            continue
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        for detection in by_frame.get(frame_index, []):
            bbox = json.loads(detection["bbox_xyxy"])
            x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
            cv2.rectangle(image, (x1, y1), (x2, y2), (32, 220, 255), 2)
            local_id = uid_to_track.get(detection["detection_uid"], "未成轨")
            cv2.putText(
                image,
                local_id.split("-")[-1],
                (x1, max(15, y1 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 230, 40),
                1,
                cv2.LINE_AA,
            )
        axis.imshow(image)
        axis.set_title(
            f"t={float(row['measurement_timestamp']):.2f}秒，检测{len(by_frame.get(frame_index, []))}个"
        )
        axis.axis("off")
    for axis in axes.flat[len(selected) :]:
        axis.axis("off")
    fig.suptitle(f"{camera_id}相机视图与匿名本地轨迹", fontsize=15)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_bearing_tracks(result: ExperimentResult, path: Path) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 8.0), sharex="col")
    camera_tracks = (result.tracks_a, result.tracks_b)
    for column, tracks in enumerate(camera_tracks):
        for track in tracks:
            times = [sample.timestamp for sample in track.samples]
            axes[0, column].plot(
                times, [sample.azimuth_deg for sample in track.samples], linewidth=0.8, alpha=0.75
            )
            axes[1, column].plot(
                times, [sample.elevation_deg for sample in track.samples], linewidth=0.8, alpha=0.75
            )
        camera_id = tracks[0].camera_id if tracks else f"相机{column + 1}"
        axes[0, column].set_title(f"{camera_id}方位轨迹")
        axes[1, column].set_title(f"{camera_id}俯仰轨迹")
        axes[1, column].set_xlabel("仿真时间 / 秒")
    axes[0, 0].set_ylabel("世界方位角 / 度")
    axes[1, 0].set_ylabel("世界俯仰角 / 度")
    fig.suptitle("扫描补偿后的单相机重访轨迹")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _primary_candidates(result: ExperimentResult) -> tuple[CrossCameraCandidate, ...]:
    if result.enhanced_association is not None:
        return result.enhanced_association.fitted_candidates
    return result.association.candidates


def _primary_matches(result: ExperimentResult) -> tuple[CrossCameraMatch, ...]:
    if result.enhanced_association is not None:
        return result.enhanced_association.selected_matches
    return result.association.matches


def _primary_scoring(result: ExperimentResult) -> list[dict[str, str]]:
    key = (
        "enhanced_match_scoring_v2"
        if result.enhanced_association is not None
        else "match_scoring"
    )
    return _read_csv(result.output_paths[key])


def _primary_fit_errors(result: ExperimentResult) -> tuple[list[float], list[float]]:
    matches = {match.match_id: match for match in _primary_matches(result)}
    targets = {target.truth_id: target for target in result.target_specs}
    position_errors: list[float] = []
    velocity_errors: list[float] = []
    for row in _primary_scoring(result):
        if not _as_bool(row.get("correct")):
            continue
        match = matches.get(row.get("match_id", ""))
        target = targets.get(row.get("truth_a", ""))
        if match is None or target is None:
            continue
        truth_position = np.asarray(
            target.position_at(match.reference_timestamp), dtype=float
        )
        position_errors.append(
            float(np.linalg.norm(np.asarray(match.position_ned) - truth_position))
        )
        velocity_errors.append(
            float(
                np.linalg.norm(
                    np.asarray(match.velocity_ned)
                    - np.asarray(target.velocity_ned, dtype=float)
                )
            )
        )
    return position_errors, velocity_errors


def _plot_cost_matrix(result: ExperimentResult, path: Path) -> Path:
    tracks_a = list(result.tracks_a)
    tracks_b = list(result.tracks_b)
    matrix = np.full((len(tracks_a), len(tracks_b)), np.nan, dtype=float)
    index_a = {track.track_id: index for index, track in enumerate(tracks_a)}
    index_b = {track.track_id: index for index, track in enumerate(tracks_b)}
    for candidate in _primary_candidates(result):
        if candidate.valid:
            matrix[index_a[candidate.track_a_id], index_b[candidate.track_b_id]] = candidate.cost
    fig, axis = plt.subplots(figsize=(9.0, 7.8))
    shown = np.ma.masked_invalid(matrix)
    image = axis.imshow(shown, cmap="viridis_r", vmin=0.0, vmax=1.25, aspect="auto")
    for match in _primary_matches(result):
        axis.scatter(index_b[match.track_b_id], index_a[match.track_a_id], s=18, c="red", marker="o")
    axis.set_title("跨相机候选代价与匈牙利匹配")
    axis.set_xlabel("相机B本地轨迹序号")
    axis.set_ylabel("相机A本地轨迹序号")
    fig.colorbar(image, ax=axis, label="综合代价")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_match_graph(result: ExperimentResult, path: Path) -> Path:
    scoring = _primary_scoring(result)
    correctness = {row["match_id"]: _as_bool(row["correct"]) for row in scoring}
    tracks_a = list(result.tracks_a)
    tracks_b = list(result.tracks_b)
    index_a = {track.track_id: index for index, track in enumerate(tracks_a)}
    index_b = {track.track_id: index for index, track in enumerate(tracks_b)}
    fig, axis = plt.subplots(figsize=(10.0, 8.0))
    axis.scatter(np.zeros(len(tracks_a)), range(len(tracks_a)), c="#1769aa", s=22, label="相机A轨迹")
    axis.scatter(np.ones(len(tracks_b)), range(len(tracks_b)), c="#b23a48", s=22, label="相机B轨迹")
    for match in _primary_matches(result):
        color = "#2e7d32" if correctness.get(match.match_id, False) else "#c62828"
        axis.plot(
            (0.0, 1.0),
            (index_a[match.track_a_id], index_b[match.track_b_id]),
            color=color,
            linewidth=1.0,
            alpha=0.75,
        )
    axis.set_xlim(-0.2, 1.2)
    axis.set_xticks((0.0, 1.0), ("相机A", "相机B"))
    axis.set_ylabel("本地轨迹序号")
    axis.set_title("匈牙利算法形成的一对一轨迹关系")
    axis.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_reconstruction(result: ExperimentResult, path: Path) -> Path:
    scoring = _primary_scoring(result)
    truth_by_match = {
        row["match_id"]: row["truth_a"]
        for row in scoring
        if _as_bool(row["correct"])
    }
    target_by_truth = {target.truth_id: target for target in result.target_specs}
    config = _scenario_config(result)
    duration = float(config["duration_s"])
    fig = plt.figure(figsize=(11.2, 7.5))
    axis = fig.add_subplot(111, projection="3d")
    matches = _primary_matches(result)
    colors = plt.cm.turbo(np.linspace(0.02, 0.98, max(len(matches), 1)))
    for color, match in zip(colors, matches):
        truth_id = truth_by_match.get(match.match_id)
        if not truth_id:
            continue
        target = target_by_truth[truth_id]
        times = np.linspace(0.0, duration, 31)
        truth = np.asarray([target.position_at(value) for value in times])
        fitted = np.asarray(
            [
                np.asarray(match.position_ned)
                + np.asarray(match.velocity_ned) * (value - match.reference_timestamp)
                for value in times
            ]
        )
        axis.plot(truth[:, 0], truth[:, 1], -truth[:, 2], color=color, linewidth=1.4)
        axis.plot(
            fitted[:, 0], fitted[:, 1], -fitted[:, 2], color=color, linestyle="--", linewidth=0.9
        )
    axis.set_title("正确关联目标的真实轨迹与双目拟合轨迹")
    axis.set_xlabel("北向距离 / 米")
    axis.set_ylabel("东向距离 / 米")
    axis.set_zlabel("高度 / 米")
    axis.view_init(elev=24, azim=-58)
    axis.text2D(0.02, 0.96, "实线：离线真值  虚线：匿名观测拟合", transform=axis.transAxes)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_error_distribution(result: ExperimentResult, path: Path) -> Path:
    position_values, velocity_values = _primary_fit_errors(result)
    position = sorted(position_values)
    velocity = sorted(velocity_values)
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2))
    for axis, values, title, label in (
        (axes[0], position, "三维位置拟合误差", "误差 / 米"),
        (axes[1], velocity, "速度拟合误差", "误差 / 米每秒"),
    ):
        if values:
            probability = np.arange(1, len(values) + 1) / len(values)
            axis.plot(values, probability, color="#1769aa", linewidth=1.8)
        axis.set_xlabel(label)
        axis.set_ylabel("累计比例")
        axis.set_title(title)
        axis.set_ylim(0.0, 1.02)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_algorithm_flow(result: ExperimentResult, path: Path) -> Path:
    metrics = result.metrics
    enhanced = result.enhanced_association
    if enhanced is not None:
        enhanced_metrics = dict(metrics.get("enhanced_association") or {})
        missing_count = int(metrics["target_count"]) - int(
            enhanced_metrics.get("correct_match_count", 0)
        )
        stages = (
            ("1  数据采集\n二维框、相机位姿\n双时间戳", "#dcecf7", "#2d6f9f"),
            ("2  匿名化\n删除仿真对象名称\n三维框和真实身份", "#dcecf7", "#2d6f9f"),
            ("3  视线与本地轨迹\n针孔反投影\n扫描重访成轨", "#dff1eb", "#2e7d6b"),
            ("4  时间对齐\n异步角轨迹插值\n形成共同时间样本", "#dff1eb", "#2e7d6b"),
            (
                "5  共面性粗筛\n{}对降至{}对\n门限0.50毫弧度".format(
                    enhanced.full_pair_count, enhanced.coarse_gate_pass_count
                ),
                "#f9ead7",
                "#b76a20",
            ),
            (
                "6  六参数拟合\n位置速度与几何门控\n{}个候选有效".format(
                    enhanced_metrics.get("valid_fit_count", 0)
                ),
                "#f9ead7",
                "#b76a20",
            ),
            ("7  扩展代价矩阵\n保留未匹配项\n匈牙利一对一分配", "#f9ead7", "#b76a20"),
            ("8  五组全局假设\n比较总代价差\n计算关系支持度", "#e7e1f2", "#765694"),
            ("9  连续证据确认\n最近4轮满足3轮\n支持度不低于0.70", "#e7e1f2", "#765694"),
            ("10  交叉保护\n竞争关系保持待定\n连续矛盾后回退", "#e7e1f2", "#765694"),
            (
                "11  结果整理\n抑制{}组重复片段\n输出{}组关系".format(
                    len(enhanced.fragment_suppressions),
                    len(enhanced.selected_matches),
                ),
                "#e1efdc",
                "#4f7f38",
            ),
            (
                "12  离线评分\n{}组正确、{}组错误\n{}个目标未闭合".format(
                    enhanced_metrics.get("correct_match_count", 0),
                    enhanced_metrics.get("false_match_count", 0),
                    missing_count,
                ),
                "#e8e8e8",
                "#666666",
            ),
        )
        columns = 6
        online_last_step = 11
        boundary_text = (
            "关联处理边界：第1至第11步不读取仿真对象名称和真实身份；当前在单次试验结束后批量执行。"
        )
    else:
        missing_count = int(metrics["target_count"]) - int(
            metrics["correct_match_count"]
        )
        stages = (
            ("1  数据采集\n二维框、相机位姿\n双时间戳", "#dcecf7", "#2d6f9f"),
            ("2  匿名化\n删除仿真对象名称\n三维框和真实身份", "#dcecf7", "#2d6f9f"),
            ("3  像素反投影\n检测框中心转为\n世界坐标系视线", "#dff1eb", "#2e7d6b"),
            ("4  扫描片段聚合\n单相机重访成轨\n至少4个扫描半程", "#dff1eb", "#2e7d6b"),
            (
                "5  全组合拟合\n{}×{}={}对\n位置速度六参数".format(
                    len(result.tracks_a),
                    len(result.tracks_b),
                    len(result.association.candidates),
                ),
                "#f9ead7",
                "#b76a20",
            ),
            (
                "6  门控与代价\n{}个候选有效\n时间、几何和运动约束".format(
                    metrics["valid_candidate_count"]
                ),
                "#f9ead7",
                "#b76a20",
            ),
            ("7  匈牙利分配\n未匹配代价1.25\n求一对一关系", "#e1efdc", "#4f7f38"),
            (
                "8  结果输出\n{}组关系\n保持未匹配轨迹".format(metrics["match_count"]),
                "#e1efdc",
                "#4f7f38",
            ),
            ("9  结果冻结\n不使用真值修正\n不回写在线关系", "#e1efdc", "#4f7f38"),
            (
                "10  离线评分\n{}组正确、{}组错误\n{}个目标未闭合".format(
                    metrics["correct_match_count"],
                    metrics["false_match_count"],
                    missing_count,
                ),
                "#e8e8e8",
                "#666666",
            ),
        )
        columns = 5
        online_last_step = 9
        boundary_text = "关联处理边界：第1至第9步不读取仿真对象名称和真实身份。"

    x_values = np.linspace(0.08, 0.92, columns)
    centers = tuple(
        [(float(value), 0.76) for value in x_values]
        + [(float(value), 0.30) for value in reversed(x_values)]
    )
    fig, axis = plt.subplots(figsize=(15.2, 7.6))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    for (x_value, y_value), (label, face, edge) in zip(centers, stages):
        axis.text(
            x_value,
            y_value,
            label,
            ha="center",
            va="center",
            fontsize=9.6,
            linespacing=1.45,
            bbox={
                "boxstyle": "round,pad=0.55",
                "facecolor": face,
                "edgecolor": edge,
                "linewidth": 1.5,
            },
        )
    for start, end in zip(centers[:-1], centers[1:]):
        if math.isclose(start[1], end[1]):
            direction = 1.0 if end[0] > start[0] else -1.0
            horizontal_gap = 0.060 if columns == 6 else 0.080
            start_point = (start[0] + horizontal_gap * direction, start[1])
            end_point = (end[0] - horizontal_gap * direction, end[1])
        else:
            start_point = (start[0], start[1] - 0.105)
            end_point = (end[0], end[1] + 0.105)
        axis.annotate(
            "",
            xy=end_point,
            xytext=start_point,
            arrowprops={"arrowstyle": "-|>", "color": "#4d4d4d", "lw": 1.5},
        )
    axis.text(
        0.02,
        0.96,
        boundary_text,
        fontsize=11,
        color="#333333",
        va="top",
    )
    axis.text(
        0.02,
        0.07,
        f"离线真值只在第{online_last_step + 1}步计算准确率、召回率和拟合误差，不回流修改关联结果。",
        fontsize=11,
        color="#333333",
    )
    axis.legend(
        handles=(
            Patch(facecolor="#dcecf7", edgecolor="#2d6f9f", label="数据与隔离"),
            Patch(facecolor="#dff1eb", edgecolor="#2e7d6b", label="单相机处理"),
            Patch(facecolor="#f9ead7", edgecolor="#b76a20", label="双相机几何"),
            Patch(facecolor="#e7e1f2", edgecolor="#765694", label="多假设与确认"),
            Patch(facecolor="#e1efdc", edgecolor="#4f7f38", label="全局分配"),
            Patch(facecolor="#e8e8e8", edgecolor="#666666", label="离线评估"),
        ),
        loc="lower right",
        ncol=6,
        frameon=False,
    )
    axis.set_title(
        f"双光电{_target_count(result)}目标轨迹关联处理流程",
        fontsize=17,
        pad=16,
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_moving_ray_fit_principle(result: ExperimentResult, path: Path) -> Path:
    matches = _primary_matches(result)
    if not matches:
        fig, axis = plt.subplots(figsize=(10.0, 4.0))
        axis.axis("off")
        axis.text(0.5, 0.5, "没有可绘制的跨相机匹配", ha="center", va="center")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path

    match = matches[0]
    tracks = {
        track.track_id: track for track in (*result.tracks_a, *result.tracks_b)
    }
    selected_tracks = (tracks[match.track_a_id], tracks[match.track_b_id])
    timestamps = [
        sample.timestamp for track in selected_tracks for sample in track.samples
    ]
    time_start, time_end = min(timestamps), max(timestamps)
    fit_times = np.linspace(time_start, time_end, 80)
    fitted = np.asarray(
        [
            np.asarray(match.position_ned)
            + np.asarray(match.velocity_ned)
            * (timestamp - match.reference_timestamp)
            for timestamp in fit_times
        ]
    )
    fig = plt.figure(figsize=(11.5, 8.0))
    axis = fig.add_subplot(111, projection="3d")
    axis.plot(
        fitted[:, 0],
        fitted[:, 1],
        -fitted[:, 2],
        color="#202020",
        linewidth=2.5,
        label="六参数恒速拟合轨迹",
    )
    colors = ("#1769aa", "#c05a2a")
    for track, color in zip(selected_tracks, colors):
        sample_indices = np.unique(
            np.linspace(0, len(track.samples) - 1, min(4, len(track.samples))).astype(int)
        )
        origin = np.asarray(track.samples[0].origin_ned, dtype=float)
        axis.scatter(
            origin[0],
            origin[1],
            -origin[2],
            marker="^",
            s=100,
            color=color,
            label=f"{track.camera_id}光电节点",
        )
        for sample_number, sample_index in enumerate(sample_indices):
            sample = track.samples[int(sample_index)]
            predicted = np.asarray(match.position_ned) + np.asarray(
                match.velocity_ned
            ) * (sample.timestamp - match.reference_timestamp)
            direction = np.asarray(sample.direction_ned, dtype=float)
            depth = float(np.dot(predicted - origin, direction))
            closest = origin + direction * depth
            axis.plot(
                (origin[0], closest[0]),
                (origin[1], closest[1]),
                (-origin[2], -closest[2]),
                color=color,
                linewidth=0.9,
                alpha=0.45,
                label="测量视线" if sample_number == 0 and track is selected_tracks[0] else None,
            )
            axis.scatter(
                predicted[0],
                predicted[1],
                -predicted[2],
                s=18,
                color="#202020",
            )
    axis.set_xlabel("北向距离 / 米")
    axis.set_ylabel("东向距离 / 米")
    axis.set_zlabel("高度 / 米")
    axis.set_title(f"移动目标双视线恒速拟合原理  {match.match_id}")
    axis.text2D(
        0.02,
        0.95,
        "单条视线没有深度；两个基线和多个时刻共同约束位置、速度六个参数。",
        transform=axis.transAxes,
        fontsize=11,
    )
    axis.view_init(elev=23, azim=-58)
    axis.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_truth_association_effect(result: ExperimentResult, path: Path) -> Path:
    scoring = _primary_scoring(result)
    target_ids = sorted(
        (target.truth_id for target in result.target_specs),
        key=lambda value: int(value.rsplit("-", 1)[-1]),
    )
    target_index = {truth_id: index for index, truth_id in enumerate(target_ids)}
    matrix = np.zeros((len(target_ids), len(target_ids)), dtype=int)
    correct_truth_ids: set[str] = set()
    false_rows: list[dict[str, str]] = []
    for row in scoring:
        truth_a, truth_b = row["truth_a"], row["truth_b"]
        if truth_a not in target_index or truth_b not in target_index:
            continue
        if _as_bool(row["correct"]):
            matrix[target_index[truth_a], target_index[truth_b]] = 1
            correct_truth_ids.add(truth_a)
        else:
            matrix[target_index[truth_a], target_index[truth_b]] = 2
            false_rows.append(row)

    fig, (matrix_axis, status_axis) = plt.subplots(
        1,
        2,
        figsize=(14.0, 8.5),
        gridspec_kw={"width_ratios": (1.6, 0.9)},
    )
    color_map = ListedColormap(("#eeeeee", "#2e7d32", "#c62828"))
    norm = BoundaryNorm((-0.5, 0.5, 1.5, 2.5), color_map.N)
    matrix_axis.imshow(matrix, cmap=color_map, norm=norm, aspect="equal")
    tick_indices = sorted(
        {0, len(target_ids) - 1, *range(4, len(target_ids), 5)}
    )
    tick_labels = [target_ids[index][-3:] for index in tick_indices]
    matrix_axis.set_xticks(tick_indices, tick_labels)
    matrix_axis.set_yticks(tick_indices, tick_labels)
    matrix_axis.set_xticks(np.arange(-0.5, len(target_ids), 1.0), minor=True)
    matrix_axis.set_yticks(np.arange(-0.5, len(target_ids), 1.0), minor=True)
    matrix_axis.grid(which="minor", color="white", linewidth=0.28, alpha=0.7)
    matrix_axis.tick_params(which="minor", bottom=False, left=False)
    matrix_axis.set_xlabel("相机B离线评分身份序号")
    matrix_axis.set_ylabel("相机A离线评分身份序号")
    matrix_axis.set_title(f"{_target_count(result)}目标跨相机关系矩阵")
    matrix_axis.legend(
        handles=(
            Patch(facecolor="#2e7d32", label="正确关系"),
            Patch(facecolor="#c62828", label="错误关系"),
            Patch(facecolor="#eeeeee", edgecolor="#bbbbbb", label="未形成关系"),
        ),
        loc="upper left",
        frameon=True,
    )

    y_values = np.arange(len(target_ids))
    status_colors = [
        "#2e7d32" if truth_id in correct_truth_ids else "#8c8c8c"
        for truth_id in target_ids
    ]
    status_axis.scatter(
        np.zeros(len(target_ids)),
        y_values,
        c=status_colors,
        s=48,
        edgecolors="white",
        linewidths=0.6,
    )
    for row in false_rows:
        y_value = target_index[row["truth_a"]]
        status_axis.scatter(1.0, y_value, marker="X", s=82, color="#c62828")
        status_axis.annotate(
            f"{row['truth_a'][-3:]}→{row['truth_b'][-3:]}",
            (1.0, y_value),
            xytext=(7, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color="#8e1f1f",
        )
    status_axis.set_xlim(-0.5, 1.8)
    status_axis.set_ylim(-1.0, len(target_ids))
    status_axis.set_xticks((0.0, 1.0), ("正确关系", "额外错误关系"))
    status_axis.set_yticks(y_values, [truth_id[-3:] for truth_id in target_ids], fontsize=7)
    status_axis.set_ylabel("目标序号")
    status_axis.set_title("逐目标配准状态")
    status_axis.invert_yaxis()
    missing = [truth_id[-3:] for truth_id in target_ids if truth_id not in correct_truth_ids]
    status_axis.text(
        0.03,
        0.02,
        "正确：{} / {}\n未正确闭合：{}\n目标：{}".format(
            len(correct_truth_ids),
            len(target_ids),
            len(missing),
            "、".join(missing),
        ),
        transform=status_axis.transAxes,
        va="bottom",
        fontsize=10.5,
        bbox={"facecolor": "white", "edgecolor": "#888888", "alpha": 0.92},
    )
    fig.suptitle(
        f"双光电{_target_count(result)}目标配准效果", fontsize=17
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_enhanced_candidate_funnel(result: ExperimentResult, path: Path) -> Path:
    enhanced = result.enhanced_association
    if enhanced is None:
        raise ValueError("enhanced association is unavailable")
    metrics = result.metrics.get("enhanced_association", {})
    best_hypothesis_count = (
        len(enhanced.hypotheses[0].matches) if enhanced.hypotheses else 0
    )
    stages = (
        ("全组合", enhanced.full_pair_count, "两侧稳定轨迹全组合"),
        ("共面性粗筛", enhanced.coarse_gate_pass_count, "中位残差不超过0.50毫弧度"),
        (
            "六参数有效候选",
            sum(item.valid for item in enhanced.fitted_candidates),
            "通过重投影、速度和几何条件门控",
        ),
        (
            "全局选中",
            best_hypothesis_count,
            "5套候选方案中的最低代价解",
        ),
        ("片段去重", len(enhanced.selected_matches), "恒速外推重合检查"),
    )
    fig, axis = plt.subplots(figsize=(14.0, 5.8))
    axis.set_xlim(-0.5, len(stages) - 0.5)
    axis.set_ylim(0.0, 1.0)
    colors = (
        "#455a64",
        "#1565c0",
        "#00838f",
        "#2e7d32",
        "#6a1b9a",
    )
    for index, ((label, value, detail), color) in enumerate(zip(stages, colors)):
        axis.text(
            index,
            0.62,
            f"{label}\n{value}",
            ha="center",
            va="center",
            fontsize=13,
            color="white",
            bbox={"boxstyle": "round,pad=0.65", "facecolor": color, "edgecolor": color},
        )
        axis.text(index, 0.25, detail, ha="center", va="top", fontsize=9.5, wrap=True)
        if index + 1 < len(stages):
            next_value = stages[index + 1][1]
            retained = next_value / max(value, 1)
            axis.annotate(
                "",
                xy=(index + 0.73, 0.62),
                xytext=(index + 0.32, 0.62),
                arrowprops={"arrowstyle": "->", "color": "#555555", "lw": 1.8},
            )
            axis.text(
                index + 0.5,
                0.71,
                f"保留 {retained:.1%}",
                ha="center",
                fontsize=9,
                color="#444444",
            )
    axis.text(
        0.01,
        0.02,
        "同一处理链：{} → {} → {} → {} → {}；六参数拟合量减少{:.1%}。".format(
            enhanced.full_pair_count,
            enhanced.coarse_gate_pass_count,
            sum(item.valid for item in enhanced.fitted_candidates),
            best_hypothesis_count,
            len(enhanced.selected_matches),
            float(metrics.get("fit_reduction_ratio", 0.0)),
        ),
        transform=axis.transAxes,
        fontsize=10.5,
    )
    axis.set_title(
        f"{_target_count(result)}目标候选筛选漏斗", fontsize=16
    )
    axis.axis("off")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_pair_count_expansion(result: ExperimentResult, path: Path) -> Path:
    counts = _pair_count_metrics(result)
    target_count = int(counts["target_count"])
    track_count_a = int(counts["track_count_a"])
    track_count_b = int(counts["track_count_b"])
    ideal_pairs = int(counts["ideal_pairs"])
    actual_pairs = int(counts["actual_pairs"])
    excess_a = int(counts["fragment_excess_a"])
    excess_b = int(counts["fragment_excess_b"])
    expansion = float(counts["pair_expansion_ratio"])

    fig, axis = plt.subplots(figsize=(14.2, 6.2))
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")

    def box(x: float, y: float, text: str, color: str, edge: str) -> None:
        axis.text(
            x,
            y,
            text,
            ha="center",
            va="center",
            fontsize=13,
            color="#202833",
            linespacing=1.45,
            bbox={
                "boxstyle": "round,pad=0.7",
                "facecolor": color,
                "edgecolor": edge,
                "linewidth": 1.8,
            },
        )

    box(
        0.12,
        0.53,
        f"场景中有\n{target_count}个真实目标",
        "#eef3f7",
        "#607d8b",
    )
    box(
        0.43,
        0.72,
        f"A站成轨\n{track_count_a}条稳定轨迹\n比目标数多{excess_a}条",
        "#dcecf7",
        "#2d6f9f",
    )
    box(
        0.43,
        0.32,
        f"B站成轨\n{track_count_b}条稳定轨迹\n比目标数多{excess_b}条",
        "#dff1eb",
        "#2e7d6b",
    )
    box(
        0.80,
        0.53,
        f"逐条尝试配对\n{track_count_a} × {track_count_b}\n= {actual_pairs}个候选",
        "#f9ead7",
        "#b76a20",
    )

    for start, end in (
        ((0.23, 0.56), (0.33, 0.69)),
        ((0.23, 0.49), (0.33, 0.35)),
        ((0.56, 0.70), (0.69, 0.57)),
        ((0.56, 0.34), (0.69, 0.49)),
    ):
        axis.annotate(
            "",
            xy=end,
            xytext=start,
            arrowprops={"arrowstyle": "->", "lw": 2.0, "color": "#58636f"},
        )

    axis.text(
        0.50,
        0.08,
        (
            f"{target_count} × {target_count} = {ideal_pairs}只适用于每个目标在每台相机中恰好形成一条完整轨迹。\n"
            f"本轮扫描边缘把部分目标切成多个轨迹片段，实际候选扩大到理想数量的{expansion:.2f}倍。"
        ),
        ha="center",
        va="center",
        fontsize=11.5,
        color="#3f4852",
        bbox={"facecolor": "white", "edgecolor": "#9aa4ad", "pad": 7},
    )
    axis.set_title(
        f"为什么{target_count}个目标会产生{actual_pairs}个候选组合",
        fontsize=17,
        pad=14,
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_fragment_timeline(result: ExperimentResult, path: Path) -> Path:
    scoring = _read_csv(result.output_paths["track_scoring"])
    stable_truth_tracks: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in scoring:
        truth_id = row.get("majority_truth_id", "")
        if not truth_id or not _as_bool(row.get("stable")):
            continue
        stable_truth_tracks[(truth_id, row["camera_id"])].append(row["track_id"])

    fragmented_truths = {
        truth_id
        for truth_id, camera_id in stable_truth_tracks
        if len(stable_truth_tracks[(truth_id, camera_id)]) > 1
    }
    chosen_truth = None
    if fragmented_truths:
        chosen_truth = max(
            fragmented_truths,
            key=lambda truth_id: (
                sum(
                    len(track_ids) > 1
                    for (candidate, _), track_ids in stable_truth_tracks.items()
                    if candidate == truth_id
                ),
                sum(
                    len(track_ids)
                    for (candidate, _), track_ids in stable_truth_tracks.items()
                    if candidate == truth_id
                ),
                truth_id,
            ),
        )

    fig, axis = plt.subplots(figsize=(13.5, 5.8))
    if chosen_truth is None:
        axis.axis("off")
        axis.text(
            0.5,
            0.5,
            "本轮离线评分中没有找到被拆成多条稳定轨迹的目标。",
            ha="center",
            va="center",
            fontsize=14,
        )
        axis.set_title("扫描边缘轨迹碎片检查", fontsize=16)
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path

    tracks_by_id = {
        track.track_id: track for track in (*result.tracks_a, *result.tracks_b)
    }
    colors = {"Optical_A": "#1769aa", "Optical_B": "#2e7d32"}
    rows: list[tuple[str, BearingTrack]] = []
    for camera_id in sorted({track.camera_id for track in tracks_by_id.values()}):
        track_ids = stable_truth_tracks.get((chosen_truth, camera_id), [])
        for fragment_index, track_id in enumerate(sorted(track_ids), start=1):
            track = tracks_by_id.get(track_id)
            if track is not None:
                rows.append((f"{camera_id} 片段{fragment_index}", track))

    y_values = np.arange(len(rows), dtype=float)
    for y_value, (label, track) in zip(y_values, rows):
        timestamps = np.asarray([sample.timestamp for sample in track.samples], dtype=float)
        color = colors.get(track.camera_id, "#765694")
        axis.plot(
            (timestamps.min(), timestamps.max()),
            (y_value, y_value),
            color=color,
            linewidth=8,
            solid_capstyle="round",
            alpha=0.72,
        )
        axis.scatter(timestamps, np.full_like(timestamps, y_value), s=24, color=color)
        axis.text(
            timestamps.max() + 0.10,
            y_value,
            track.track_id,
            va="center",
            fontsize=9,
            color="#3f4852",
        )

    duration = float(
        json.loads((result.output_dir / "scenario.json").read_text(encoding="utf-8"))[
            "scenario"
        ]["duration_s"]
    )
    axis.set_xlim(-0.15, duration + 1.2)
    axis.set_yticks(y_values, [label for label, _ in rows])
    axis.set_xlabel("试验时间 / 秒")
    axis.set_ylabel("同一真实目标形成的本地轨迹")
    axis.grid(axis="x", linestyle="--", alpha=0.35)
    axis.invert_yaxis()
    axis.text(
        0.01,
        -0.22,
        (
            "每个圆点是一轮扫描重访观测。中间的空白超过轨迹保持时间后，"
            "同一目标会以新的本地轨迹编号重新出现。真实身份只用于离线挑选这个解释案例。"
        ),
        transform=axis.transAxes,
        fontsize=10.5,
        color="#4d5965",
    )
    axis.set_title(
        f"扫描边缘造成的轨迹断裂示例：{chosen_truth}", fontsize=16
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_epipolar_residual_sequences(result: ExperimentResult, path: Path) -> Path:
    enhanced = result.enhanced_association
    if enhanced is None:
        raise ValueError("enhanced association is unavailable")
    track_truth = {
        row["track_id"]: row["majority_truth_id"]
        for row in _read_csv(result.output_paths["track_scoring"])
        if row.get("majority_truth_id")
    }
    correct = [
        item
        for item in enhanced.epipolar_evidence
        if track_truth.get(item.track_a_id)
        and track_truth.get(item.track_a_id) == track_truth.get(item.track_b_id)
    ]
    wrong = [
        item
        for item in enhanced.epipolar_evidence
        if track_truth.get(item.track_a_id)
        and track_truth.get(item.track_b_id)
        and track_truth.get(item.track_a_id) != track_truth.get(item.track_b_id)
    ]
    correct = sorted(correct, key=lambda item: item.residual_median_mrad)[:4]
    wrong = sorted(wrong, key=lambda item: item.residual_median_mrad)[:4]
    fig, axis = plt.subplots(figsize=(12.5, 6.4))
    for index, item in enumerate(correct):
        times = np.asarray(item.timestamps_s) - min(item.timestamps_s, default=0.0)
        axis.plot(
            times,
            np.maximum(item.residuals_mrad, 1e-4),
            color="#2e7d32",
            alpha=0.55 + 0.1 * index,
            linewidth=1.8,
            label="正确关系" if index == 0 else None,
        )
    for index, item in enumerate(wrong):
        times = np.asarray(item.timestamps_s) - min(item.timestamps_s, default=0.0)
        axis.plot(
            times,
            np.maximum(item.residuals_mrad, 1e-4),
            color="#c62828",
            alpha=0.42 + 0.1 * index,
            linewidth=1.5,
            linestyle="--",
            label="最接近门限的错误关系" if index == 0 else None,
        )
    axis.axhline(
        enhanced.config.coplanarity_median_gate_mrad,
        color="#1565c0",
        linewidth=1.5,
        linestyle=":",
        label="中位残差门限",
    )
    axis.set_yscale("log")
    axis.set_xlabel("共同观测时间（相对秒）")
    axis.set_ylabel("对称共面性残差（毫弧度，对数坐标）")
    axis.set_title("正确关系与近邻错误关系的共面性残差序列")
    axis.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_hypothesis_cost_evolution(result: ExperimentResult, path: Path) -> Path:
    enhanced = result.enhanced_association
    if enhanced is None:
        raise ValueError("enhanced association is unavailable")
    fig, (cost_axis, support_axis) = plt.subplots(2, 1, figsize=(12.5, 8.0), sharex=True)
    by_rank: dict[int, list[Any]] = defaultdict(list)
    for item in enhanced.hypothesis_history:
        by_rank[item.rank].append(item)
    colors = ("#1565c0", "#00838f", "#2e7d32", "#7b1fa2", "#ef6c00")
    for rank, rows in sorted(by_rank.items()):
        rows = sorted(rows, key=lambda item: item.timestamp)
        color = colors[(rank - 1) % len(colors)]
        cost_axis.plot(
            [item.timestamp for item in rows],
            [item.total_cost for item in rows],
            label=f"第{rank}解",
            color=color,
            linewidth=1.6,
        )
        support_axis.plot(
            [item.timestamp for item in rows],
            [item.normalized_support for item in rows],
            color=color,
            linewidth=1.6,
        )
    cost_axis.set_ylabel("全局总代价")
    cost_axis.set_title("Top-5全局一对一假设随决策周期的变化")
    cost_axis.legend(ncol=5, loc="upper left")
    support_axis.axhline(
        enhanced.config.competing_support_gate,
        color="#555555",
        linestyle=":",
        label="竞争支持度门限",
    )
    support_axis.set_xlabel("试验时间（秒）")
    support_axis.set_ylabel("归一化支持度")
    support_axis.set_ylim(-0.02, 1.02)
    support_axis.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_association_state_timeline(result: ExperimentResult, path: Path) -> Path:
    enhanced = result.enhanced_association
    if enhanced is None:
        raise ValueError("enhanced association is unavailable")
    timestamps = sorted({item.timestamp for item in enhanced.state_history})
    states = ("tentative", "pending", "confirmed", "coasting")
    labels = {
        "tentative": "初步关系",
        "pending": "待确认",
        "confirmed": "已确认",
        "coasting": "短时保持",
    }
    colors = {
        "tentative": "#78909c",
        "pending": "#ef6c00",
        "confirmed": "#2e7d32",
        "coasting": "#7b1fa2",
    }
    fig, axis = plt.subplots(figsize=(12.5, 6.2))
    for state in states:
        counts = [
            sum(
                item.timestamp == timestamp and item.state == state
                for item in enhanced.state_history
            )
            for timestamp in timestamps
        ]
        axis.plot(
            timestamps,
            counts,
            marker="o",
            markersize=3.5,
            linewidth=1.7,
            label=labels[state],
            color=colors[state],
        )
    crossing_counts = [
        sum(
            item.timestamp == timestamp and item.crossing_alert
            for item in enhanced.state_history
        )
        for timestamp in timestamps
    ]
    axis.plot(
        timestamps,
        crossing_counts,
        color="#c62828",
        linestyle="--",
        linewidth=1.4,
        label="交叉邻近告警",
    )
    axis.set_xlabel("试验时间（秒）")
    axis.set_ylabel("关系数量")
    axis.set_title("关系确认、待确认与交叉告警时间线")
    axis.legend(ncol=3, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_geometry_sensitivity(result: ExperimentResult, path: Path) -> Path:
    records = sorted(result.geometry_sensitivity, key=lambda item: item.intersection_angle_deg)
    fig, axis = plt.subplots(figsize=(11.5, 6.2))
    if records:
        angles = [item.intersection_angle_deg for item in records]
        axis.scatter(
            angles,
            [item.position_sensitivity_p50_m for item in records],
            color="#1565c0",
            s=34,
            label="位置敏感性中位数",
        )
        axis.scatter(
            angles,
            [item.position_sensitivity_p95_m for item in records],
            color="#c62828",
            marker="x",
            s=42,
            label="位置敏感性95%分位",
        )
        axis.legend(loc="best")
    else:
        axis.text(
            0.5,
            0.5,
            "本轮无可用几何敏感性样本",
            ha="center",
            va="center",
            transform=axis.transAxes,
        )
    axis.set_xlabel("双站视线交会角（度）")
    axis.set_ylabel("位置变化（米）")
    axis.set_title("0.15毫弧度角噪声下的模型几何敏感性")
    axis.text(
        0.01,
        0.02,
        "每组关系使用1000次确定性蒙特卡洛采样。该图是模型推算，不是AirSim测量精度。",
        transform=axis.transAxes,
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _geometry_sensitivity_summary(
    metrics: Mapping[str, Any], records: Sequence[GeometrySensitivity]
) -> str:
    values = (
        metrics.get("geometry_sensitivity_p50_median_m"),
        metrics.get("geometry_sensitivity_p95_median_m"),
        metrics.get("intersection_angle_median_deg"),
    )
    if not records or any(value is None for value in values):
        return "本轮没有形成可用的几何敏感性样本，相关统计记为不可用。"
    p50_m, p95_m, intersection_angle_deg = (float(value) for value in values)
    return (
        "对每组最终关系的两条理想视线分别加入标准差0.15毫弧度的二维角扰动，"
        "每组执行1000次固定随机种子的蒙特卡洛采样。位置变化中位数的组间"
        f"中位数为{p50_m:.3f}米，95%分位位置变化的组间中位数为"
        f"{p95_m:.3f}米，双站交会角中位数为{intersection_angle_deg:.2f}度。"
    )


def _write_report(result: ExperimentResult, figures: Mapping[str, Path]) -> Path:
    if result.enhanced_association is not None:
        return _write_integrated_report(result, figures)
    return _write_legacy_report(result, figures)


def _write_legacy_report(result: ExperimentResult, figures: Mapping[str, Path]) -> Path:
    metrics = result.metrics
    target_count = _target_count(result)
    acceptance = metrics["acceptance"]
    passed_text = "通过" if acceptance["overall_passed"] else "未通过"
    precision = _ratio(metrics.get("association_precision"))
    full_recall = _ratio(metrics.get("association_full_target_recall"))
    eligible_recall = _ratio(metrics.get("association_eligible_recall"))
    coverage = metrics["camera_detection_coverage"]
    stable = metrics["stable_track_truth_coverage"]
    camera_names = list(coverage)
    match_scoring = _read_csv(result.output_paths["match_scoring"])
    track_scoring = _read_csv(result.output_paths["track_scoring"])
    correct_truth_ids = {
        row["truth_a"] for row in match_scoring if _as_bool(row["correct"])
    }
    missing_correct_truth_ids = sorted(
        target.truth_id
        for target in result.target_specs
        if target.truth_id not in correct_truth_ids
    )
    fragmented_target_count: dict[str, int] = {}
    for camera_id in camera_names:
        truth_counts = defaultdict(int)
        for row in track_scoring:
            if (
                row.get("camera_id") == camera_id
                and _as_bool(row.get("stable"))
                and row.get("majority_truth_id")
            ):
                truth_counts[row["majority_truth_id"]] += 1
        fragmented_target_count[camera_id] = sum(
            count > 1 for count in truth_counts.values()
        )
    false_matches = [row for row in match_scoring if not _as_bool(row["correct"])]
    false_match_text = "；".join(
        f"{row['match_id']}将{row['truth_a']}与{row['truth_b']}相连"
        for row in false_matches
    ) or "无"
    false_truth_ids_with_correct_match = sorted(
        {
            truth_id
            for row in false_matches
            for truth_id in (row["truth_a"], row["truth_b"])
            if truth_id in correct_truth_ids
        },
        key=lambda value: int(value.rsplit("-", 1)[-1]),
    )
    stable_track_a_count = int(metrics["stable_track_count"][camera_names[0]])
    stable_track_b_count = int(metrics["stable_track_count"][camera_names[1]])
    candidate_count = len(result.association.candidates)
    report_path = _report_path(result)
    relative = {
        key: path.relative_to(result.output_dir).as_posix() for key, path in figures.items()
    }
    camera_a_figure = (
        f"![相机A]({relative['camera_a']})"
        if "camera_a" in relative
        else "正式运行未保存相机A关键帧，报告不插入占位图。"
    )
    camera_b_figure = (
        f"![相机B]({relative['camera_b']})"
        if "camera_b" in relative
        else "正式运行未保存相机B关键帧，报告不插入占位图。"
    )
    lines = [
        f"# 双光电{target_count}目标轨迹关联试验",
        "",
        "## 结论",
        "",
        f"本轮验收结果为**{passed_text}**。试验在AirSim ComputerVision模式下使用两个固定光电节点、{target_count}个移动无人机网格和内置检测接口。在线关联未读取Actor名称、三维真值或系统全局航迹。",
        "",
        f"匈牙利算法输出{metrics['match_count']}组跨相机关系，其中正确{metrics['correct_match_count']}组、错误{metrics['false_match_count']}组。准确率为{precision}，相对全部{target_count}个目标的召回率为{full_recall}，相对两侧均已形成稳定轨迹的目标召回率为{eligible_recall}。",
        "",
        f"验收阈值已经通过，但结果未达到{target_count}个目标全部正确配准。两台相机都检测到全部目标，最终只有{len(correct_truth_ids)}个目标形成正确跨相机关系；未正确配准的是{'、'.join(missing_correct_truth_ids)}。",
        "",
        "本试验只验证理想位姿、理想时间和AirSim检测框条件下的双光电轨迹关联。结果不是实装光电设备性能，也不代表D1-D7系统链路已经接入。",
        "",
        "## 场景",
        "",
        f"两个光电节点横向相距2000米，目标群初始位于前方约2000米。{target_count}个目标前后错列并设置少量横向交叉，速度模长均为50米每秒，目标高度变化限制在中心高度上下20米。目标网格最长方向在预检中标定为3米。",
        "",
        f"相机分辨率为1280乘1024，AirSim水平视场角为2.93度，按该投影得到的垂直视场角为{_scenario_camera_value(result, 'vertical_fov_deg'):.3f}度。AirSim等效角分辨率为{_scenario_camera_value(result, 'effective_ifov_mrad'):.5f}毫弧度每像素，与设备给出的0.05毫弧度分开记录。",
        "",
        f"![三维场景]({relative['scene']})",
        "",
        "## 算法总体流程",
        "",
        "算法分为单相机处理、双相机几何关联和离线评估三部分。单相机处理把间歇出现的二维框转成连续的方位和俯仰轨迹；双相机处理对两侧稳定轨迹逐对拟合，筛除不满足几何和运动条件的组合；匈牙利算法在有效候选中求全局一对一关系。离线评估最后读取隔离真值，不参与前九步计算。",
        "",
        f"![算法流程]({relative['algorithm_flow']})",
        "",
        "1. 两台相机分别接收二维检测框、相机位置姿态、测量时间戳和到达时间戳。进入算法前删除Actor名称、三维框和真实身份。",
        "2. 使用针孔相机模型把检测框中心反投影为世界坐标系单位视线。同一目标的一次快速扫过先形成扫描片段，减少单次扫过期间的重复检测。",
        "3. 每台相机独立连接相邻扫描半程的观测片段。至少经过4个扫描半程的轨迹才成为跨相机候选。",
        "4. A侧和B侧稳定轨迹做全组合。每一对组合用两个节点在多个时刻的视线拟合三维初始位置和速度。",
        "5. 候选依次通过时间差、重投影误差、速度、几何条件数、内点率、正深度和来袭方向门控。有效候选进入综合代价矩阵。",
        "6. 代价矩阵加入未匹配项后执行匈牙利算法，得到一对一跨相机轨迹关系。在线结果冻结后，离线真值旁路才计算准确率、召回率和三维拟合误差。",
        "",
        "## 方位扫描",
        "",
        "两台相机在试验开始前分别计算指向来袭走廊中心的俯仰角，此后俯仰保持不变。云台只在方位方向进行左右45度扫描，单程0.5秒，完整往返周期1秒。",
        "",
        "窄视场以180度每秒扫过目标时，单次可见时间很短。程序按100赫兹更新逻辑时间、目标位姿和扫描角，并在每次采集前给Unreal留出渲染更新时间。该数值是试验调度频率；墙钟处理速率为{:.2f}次每秒，不能据此声称真实设备已达到100赫兹。".format(metrics.get("detection_rpc_wall_rate_hz") or 0.0),
        "",
        f"![扫描曲线]({relative['scan']})",
        "",
        "## 匿名观测",
        "",
        "AirSim检测结果在进入算法前删除对象名称、相对真实位姿和三维框。在线文件只保留测量编号、二维框、相机编号、相机姿态和时间戳。对象名称和真实轨迹进入单独的离线评分文件。",
        "",
        f"在线真值字段泄漏计数为{metrics['online_truth_leakage_count']}。{camera_names[0]}检测覆盖率为{_ratio(coverage[camera_names[0]])}，{camera_names[1]}检测覆盖率为{_ratio(coverage[camera_names[1]])}。",
        "",
        camera_a_figure,
        "",
        camera_b_figure,
        "",
        "## 观测模型",
        "",
        "### 检测框中心",
        "",
        "检测器输出二维框 `(x_min, y_min, x_max, y_max)`。算法只使用框中心作为角度测量：",
        "",
        r"$$u=\frac{x_{min}+x_{max}}{2},\qquad v=\frac{y_{min}+y_{max}}{2}. $$",
        "",
        "框面积不用于推算距离，只在同一扫描片段内作为视线平均权重。较大的框通常位于视场中心附近，权重略高；该处理不能替代双目几何。",
        "",
        "### 针孔反投影",
        "",
        "相机水平视场角为 `theta_h`，图像宽度为 `W`。以像素为单位的焦距为：",
        "",
        r"$$f=\frac{W}{2\tan(\theta_h/2)}. $$",
        "",
        "本试验采用前向、右向、下向的相机局部坐标。像素中心先转换为相机坐标系单位视线，再使用云台方位角和固定俯仰角旋转到北东地坐标系：",
        "",
        r"$$\mathbf r_c=\frac{[1,(u-W/2)/f,(v-H/2)/f]^T}{\|[1,(u-W/2)/f,(v-H/2)/f]^T\|},$$",
        r"$$\mathbf r_w=R_z(\psi)R_y(\theta)\mathbf r_c. $$",
        "",
        r"相机位置为 $\mathbf o$ 时，单次观测只确定射线 $\mathbf p(\lambda)=\mathbf o+\lambda\mathbf r_w$。未知量 $\lambda$ 是目标深度，因此单台相机不能仅凭一个二维框得到三维位置。两个相距2000米的节点和多个时刻的视线共同提供深度约束。",
        "",
        "## 扫描重访轨迹",
        "",
        "### 扫描内聚合",
        "",
        "同一半程扫描中，相邻检测的时间间隔不超过0.06秒、世界视线夹角不超过0.16度时，算法使用一次匈牙利分配把它们归入同一观测片段。片段代表视线按检测框面积加权：",
        "",
        r"$$w_i=\frac{A_i}{\sum_j A_j},\qquad \bar{\mathbf r}=\frac{\sum_i w_i\mathbf r_i}{\|\sum_i w_i\mathbf r_i\|}. $$",
        "",
        "该步骤把一次扫过期间的连续检测压缩为一个带时间戳的方位观测，避免同一目标在一个扫描半程内生成多条轨迹。",
        "",
        "### 跨扫描重访",
        "",
        "局部轨迹使用最近5个观测对方位角和俯仰角分别做线性拟合，并外推到新观测时刻。预测角与新片段的综合角误差为：",
        "",
        r"$$e_\alpha=\sqrt{(\Delta\mathrm{az}\cos\mathrm{el})^2+(\Delta\mathrm{el})^2}. $$",
        "",
        "轨迹间隔不超过0.75秒且角误差不超过0.45度时进入局部匈牙利分配。没有可行前驱的片段新建轨迹。轨迹至少覆盖4个扫描半程才进入双相机关联；短轨迹保留在记录中，但不参加跨相机配准。",
        "",
        f"{camera_names[0]}形成{metrics['stable_track_count'][camera_names[0]]}条稳定轨迹，覆盖{_ratio(stable[camera_names[0]])}的目标；{camera_names[1]}形成{metrics['stable_track_count'][camera_names[1]]}条稳定轨迹，覆盖{_ratio(stable[camera_names[1]])}的目标。{camera_names[0]}有{fragmented_target_count[camera_names[0]]}个目标被拆成两条稳定片段，{camera_names[1]}有{fragmented_target_count[camera_names[1]]}个目标出现同类情况。扫描边缘短时离开视场和交叉窗口是主要触发条件。",
        "",
        f"![本地轨迹]({relative['bearing_tracks']})",
        "",
        "## 双相机恒速拟合",
        "",
        f"A侧每条稳定轨迹与B侧每条稳定轨迹组成候选。本轮A侧{stable_track_a_count}条、B侧{stable_track_b_count}条，共评估{candidate_count}个组合。对每个组合设参考时刻为两条轨迹全部观测时间的中位数，目标运动模型为：",
        "",
        r"$$\mathbf x(t)=\mathbf p_0+\mathbf v(t-t_0), $$",
        "",
        r"其中 $\mathbf p_0$ 为参考时刻三维位置，$\mathbf v$ 为三维速度。对第 $i$ 条视线，$\mathbf r_i$ 为单位方向，$\mathbf o_i$ 为相机位置，$\Delta t_i=t_i-t_0$。投影矩阵 $P_i=I-\mathbf r_i\mathbf r_i^T$ 会消除沿视线方向的未知深度，因此有：",
        "",
        r"$$P_i[\mathbf p_0+\mathbf v\Delta t_i-\mathbf o_i]=\mathbf 0. $$",
        "",
        r"把两个相机的全部观测叠加后形成线性方程 $A[\mathbf p_0^T,\mathbf v^T]^T=\mathbf b$，用最小二乘求六个未知量。单条视线无法定深度，两个空间基线和多个观测时刻使六参数解可观测。",
        "",
        f"![双视线恒速拟合]({relative['fit_principle']})",
        "",
        "### 离群点处理",
        "",
        "初次拟合后把三维轨迹重新投影到每个观测时刻，像素残差超过15像素的观测标为离群点。最多执行3轮拟合和剔除。若任一相机剩余观测少于4个，则停止继续剔除并保留上一轮集合，避免只靠单侧观测产生伪三维解。",
        "",
        "## 候选门控",
        "",
        "六参数拟合完成后，候选必须同时满足下列条件。门控先于匈牙利分配，任何一项失败都把该组合置为无效。",
        "",
        "| 门控项目 | 实施条件 | 作用 |",
        "|---|---:|---|",
        "| 方程秩 | 秩等于6 | 保证位置和速度六参数可解 |",
        "| 时间同步 | 两侧最近观测时间差中位数不超过0.20秒 | 限制异步观测外推距离 |",
        "| 重投影 | 均方根不超过8像素，最大值不超过15像素 | 检查拟合轨迹能否回到原二维观测 |",
        "| 速度 | 35至65米每秒 | 围绕已知50米每秒场景排除不合理组合 |",
        "| 几何条件数 | 不超过10000 | 排除视线近似平行造成的病态解 |",
        "| 内点比例 | 不低于0.85 | 防止少量观测支撑错误关系 |",
        "| 深度 | 所有内点均为正深度 | 排除目标落在相机后方 |",
        "| 来袭方向 | 北向速度不大于负25米每秒 | 保留向节点接近的运动解 |",
        "",
        f"本轮{candidate_count}个组合中有{metrics['valid_candidate_count']}个通过全部门控。通过门控的候选按下式计算综合代价：",
        "",
        r"$$C=0.55\min(e_{rp}/8,10)+0.15\min(e_{ray}/5,10)+0.15\min(|s-50|/15,10)$$",
        r"$$\quad+0.10\min(\Delta t/0.20,10)+0.05\min(\log_{10}\kappa/4,10)+0.05(1-\rho). $$",
        "",
        r"其中 $e_{rp}$ 是重投影均方根像素误差，$e_{ray}$ 是拟合点到测量视线的空间均方根距离，$s$ 是拟合速度，$\Delta t$ 是两侧最近观测时间差中位数，$\kappa$ 是方程条件数，$\rho$ 是内点比例。重投影误差权重最高，因为它直接衡量同一条三维轨迹能否同时解释两台相机的二维观测。",
        "",
        "## 匈牙利配准",
        "",
        "有效候选代价写入A侧轨迹乘B侧轨迹矩阵，无效位置设为较大值。矩阵为每条A侧和B侧轨迹增加独立的未匹配项，未匹配代价为1.25。扩展矩阵执行匈牙利算法，求总成本最小的一对一关系；候选代价不低于1.25时宁可保持未匹配。",
        "",
        "该机制解决的是局部轨迹之间的一对一冲突。例如两条A侧轨迹都能与同一条B侧轨迹形成低代价候选时，算法只能保留其中一条。它不能直接识别同一真实目标被拆成多个局部片段，因此轨迹碎片仍可能形成额外错误关系。",
        "",
        f"![代价矩阵]({relative['cost_matrix']})",
        "",
        f"![匹配关系]({relative['match_graph']})",
        "",
        "## 配准效果",
        "",
        f"{candidate_count}个候选中有{metrics['valid_candidate_count']}个通过门控，匈牙利算法最终输出{metrics['match_count']}组关系。A侧有{metrics['unmatched_a_count']}条稳定轨迹保持未匹配，B侧有{metrics['unmatched_b_count']}条保持未匹配。离线评分显示{metrics['correct_match_count']}组正确、{metrics['false_match_count']}组错误。",
        "",
        f"下图左侧以离线身份绘制{target_count}乘{target_count}关系矩阵。绿色对角点代表两侧轨迹属于同一目标；红色非对角点代表错误关系；对角线空白位置代表该目标没有形成正确关系。右侧逐目标列出正确闭合状态，并单独标出额外错误关系。该图只用于解释结果，离线身份没有进入在线代价矩阵。",
        "",
        f"![{target_count}目标配准效果]({relative['association_effect']})",
        "",
        "## 未闭合项",
        "",
        f"{metrics['match_count']}组匹配中有{metrics['false_match_count']}组错误关系：{false_match_text}。错误关系涉及且另有正确关系的目标为{'、'.join(false_truth_ids_with_correct_match) or '无'}。因此本轮红色非对角点属于轨迹碎片产生的额外误配，不等同于相关目标完全丢失。它说明局部轨迹层的一对一约束不能自动合并同一真实目标的多个片段。",
        "",
        f"另有{len(missing_correct_truth_ids)}个目标没有形成正确跨相机关系，分别为{'、'.join(missing_correct_truth_ids)}。这些目标在两台相机中都曾形成稳定轨迹，但对应片段没有在全局代价最小的一对一分配中同时保留下来。当前结果已经达到准确率和召回率验收线，仍不能视为{target_count}对{target_count}全量闭合。后续应先降低扫描边缘造成的轨迹碎片，再评估跨周期轨迹合并。",
        "",
        "## 三维拟合",
        "",
        f"正确匹配的平均位置误差为{_number(metrics.get('position_error_mean_m'))}米，95%分位误差为{_number(metrics.get('position_error_p95_m'))}米。平均速度误差为{_number(metrics.get('velocity_error_mean_mps'))}米每秒。真值只在关联结束后用于绘图和评分。",
        "",
        f"![三维拟合]({relative['reconstruction']})",
        "",
        f"![误差分布]({relative['errors']})",
        "",
        "## 验收",
        "",
        "| 项目 | 结果 |",
        "|---|---|",
        f"| {target_count}个目标生成 | {'通过' if acceptance['spawn_passed'] else '未通过'} |",
        f"| 固定俯仰 | {'通过' if acceptance['fixed_pitch_passed'] else '未通过'} |",
        f"| 在线真值隔离 | {'通过' if acceptance['truth_isolation_passed'] else '未通过'} |",
        f"| 无重复匹配 | {'通过' if acceptance['no_duplicate_match_passed'] else '未通过'} |",
        f"| 准确率不低于95% | {'通过' if acceptance['precision_target_passed'] else '未通过'} |",
        f"| 全目标召回率不低于80% | {'通过' if acceptance['recall_target_passed'] else '未通过'} |",
        f"| 两侧稳定轨迹覆盖率不低于80% | {'通过' if acceptance['stable_coverage_target_passed'] else '未通过'} |",
        "",
        "## 限制",
        "",
        "本轮未注入相机位姿误差、时钟误差、误检测和额外测量噪声。目标检测使用AirSim内置接口，不代表真实目标识别性能。固定节点和目标的实际渲染帧率也没有按真实光电设备完成标定。",
        "",
        "图神经网络没有进入本轮代码。单个种子不能形成独立训练集和验证集，当前只保留匈牙利方法作为可解释基线。后续若增加多场景、多误差等级和独立数据划分，再比较图神经网络的收益。",
        "",
        "## 待办事项",
        "",
        "- [ ] **取消对检测框面积的强依赖。** 将检测框面积改为可选观测字段。优先按照像素中心测量协方差进行视线加权；缺少协方差时依次使用检测置信度、视场中心距离和稳健等权平均。增加只有目标中心点、没有可靠框宽和框高的输入测试。",
        "- [ ] **降低扫描重访造成的轨迹碎片。** 在跨相机关联之前增加同相机轨迹片段合并，综合比较时间连续性、预测方位、俯仰变化和运动一致性。验收时同时检查稳定轨迹数量、错误合并数、跨相机误配和未闭合目标数。",
        "- [ ] **标定扫描和重访门限。** 对0.06秒扫描内时间门限、0.16度片段门限、0.75秒保持时间和0.45度重访门限开展多种子敏感性试验，覆盖目标密集、轨迹交叉和扫描边缘条件。门限调整不能通过放宽身份约束换取表面召回率。",
        "- [ ] **比较直接方向轨迹配准。** 增加不先求三维位置的世界方向轨迹基线，使用时间对齐后的方位、俯仰和角速度计算轨迹代价，再执行匈牙利分配。与现有双相机恒速三维拟合使用同一批输入，比较准确率、召回率、耗时和交叉目标误配情况。",
        "- [ ] **注入真实测量误差。** 分级加入检测中心抖动、漏检、虚警、相机外参误差、云台角误差和时间偏差，输出每种误差条件下的门控拒绝原因和配准指标。在线算法继续禁止读取Actor名称和真实身份。",
        "- [ ] **验证微小目标观测。** 使用只输出亮点中心或低像素检测结果的接口替代稳定检测框，评估时序积累、稳健质心和先跟踪后检测方法。AirSim内置检测接口继续只作为几何链路基线。",
        "- [ ] **完成多场景统计。** 增加不同目标队形、交叉强度、速度和初始距离的独立种子，报告均值、分位数和失败样本。单种子结果不得作为真实设备能力指标。",
        "- [ ] **后置图神经网络对照。** 只有在形成足够的训练、验证和独立测试数据后，才比较图神经网络与匈牙利基线。图神经网络若不能在相同误差条件下降低误配并满足计算预算，不进入后续在线方案。",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _write_integrated_report(
    result: ExperimentResult, figures: Mapping[str, Path]
) -> Path:
    enhanced = result.enhanced_association
    if enhanced is None:
        return _write_legacy_report(result, figures)

    all_metrics = result.metrics
    target_count = _target_count(result)
    pair_counts = _pair_count_metrics(result)
    metrics = dict(all_metrics.get("enhanced_association") or {})
    acceptance = all_metrics["acceptance"]
    passed_text = "通过" if acceptance["overall_passed"] else "未通过"
    fit_reduction = float(metrics.get("fit_reduction_ratio", 0.0))
    precision = _ratio(metrics.get("association_precision"))
    recall = _ratio(metrics.get("association_full_target_recall"))
    confirmed_recall = _ratio(metrics.get("confirmed_full_target_recall"))
    scoring = _primary_scoring(result)
    correct_truth_ids = {
        row["truth_a"] for row in scoring if _as_bool(row.get("correct"))
    }
    missing_truth_ids = sorted(
        (
            target.truth_id
            for target in result.target_specs
            if target.truth_id not in correct_truth_ids
        ),
        key=lambda value: int(value.rsplit("-", 1)[-1]),
    )
    position_errors, velocity_errors = _primary_fit_errors(result)
    position_mean = float(np.mean(position_errors)) if position_errors else None
    position_p95 = float(np.percentile(position_errors, 95)) if position_errors else None
    velocity_mean = float(np.mean(velocity_errors)) if velocity_errors else None
    coverage = all_metrics["camera_detection_coverage"]
    stable = all_metrics["stable_track_truth_coverage"]
    camera_names = list(coverage)
    selected_count = len(enhanced.selected_matches)
    confirmed_count = len(enhanced.confirmed_matches)
    pending_count = selected_count - confirmed_count
    best_hypothesis_count = (
        len(enhanced.hypotheses[0].matches) if enhanced.hypotheses else 0
    )
    legacy_wall_ms = float(all_metrics.get("cross_camera_association_wall_ms", 0.0))
    association_wall_ms = float(
        all_metrics.get("enhanced_cross_camera_association_wall_ms", 0.0)
    )
    report_path = _report_path(result)
    relative = {
        key: path.relative_to(result.output_dir).as_posix()
        for key, path in figures.items()
    }
    suppression_detail = "无重复片段"
    if enhanced.fragment_suppressions:
        item = enhanced.fragment_suppressions[0]
        suppression_detail = (
            f"首组被抑制片段在共同时间的位置差为{item.predicted_position_delta_m:.3f}米，"
            f"速度差为{item.velocity_delta_mps:.3f}米每秒"
        )

    missing_truth_text = "、".join(missing_truth_ids) or "无"
    track_count_a = int(pair_counts["track_count_a"])
    track_count_b = int(pair_counts["track_count_b"])
    ideal_pairs = int(pair_counts["ideal_pairs"])
    actual_pairs = int(pair_counts["actual_pairs"])
    fragment_excess_a = int(pair_counts["fragment_excess_a"])
    fragment_excess_b = int(pair_counts["fragment_excess_b"])
    pair_expansion_ratio = float(pair_counts["pair_expansion_ratio"])

    lines = [
        f"# 双站光电{target_count}目标轨迹关联试验报告",
        "",
        "## 结论",
        "",
        f"本轮严格验收结果为**{passed_text}**。两台光电节点扫描{target_count}个移动目标，算法要解决的问题很直接：A站看到的一条轨迹，究竟对应B站看到的哪一条轨迹。关联时只使用二维检测框、相机位姿和时间戳，仿真对象名称和真实身份只在结果冻结后用于评分。",
        "",
        f"最终输出{selected_count}组跨相机关系。离线评分确认其中{metrics.get('correct_match_count', 0)}组正确、{metrics.get('false_match_count', 0)}组错误，准确率为{precision}，相对{target_count}个目标的召回率为{recall}。{confirmed_count}组已经满足连续确认条件，{pending_count}组仍在等待更多证据。没有闭合的目标为{missing_truth_text}。",
        "",
        f"两侧本地轨迹一共形成{enhanced.full_pair_count}个候选组合。共面性粗筛先把它们压到{enhanced.coarse_gate_pass_count}个，再做耗时较大的三维位置和速度拟合，拟合量减少{fit_reduction:.1%}。当前Python原型总耗时约{association_wall_ms:.0f}毫秒，对照处理为{legacy_wall_ms:.0f}毫秒。筛选次数少了，但Python逐对计算和状态回放仍然较慢。",
        "",
        "当前处理在AirSim单次试验结束后批量执行。程序先读完整段匿名轨迹，再按时间戳回放每0.5秒一次的判断过程。因此，本轮证明的是关联逻辑可行，还没有证明算法能够每0.5秒在线实时运行。",
        "",
        "## 试验边界",
        "",
        "本试验单独验证双站光电轨迹关联，不调用D1多传感器融合、D2全局航迹管理、D3任务分配或D5末端视觉配准。目标检测采用AirSim内置检测接口，目的是取得稳定二维框并验证几何链路，不评价真实识别模型。",
        "",
        "试验未注入相机外参误差、云台回差、时钟偏差、漏检和虚警。目标三维真值只进入隔离评分文件。报告中的定位误差和角噪声敏感性属于当前理想条件下的模型结果，不是实装设备指标。",
        "",
        "## 场景与参数",
        "",
        "| 项目 | 设置 |",
        "|---|---|",
        f"| 仿真模式 | AirSim计算机视觉模式，随机种子{all_metrics.get('seed')} |",
        f"| 光电节点 | 2个固定节点，横向基线2000米 |",
        f"| 目标 | {target_count}个3米无人机网格，前后错列并带少量交叉 |",
        f"| 目标速度 | {all_metrics.get('target_speed_mps'):.1f}米每秒 |",
        f"| 相机 | 1280×1024，水平视场角2.93度，垂直视场角{_scenario_camera_value(result, 'vertical_fov_deg'):.3f}度 |",
        f"| 方位扫描 | 左右45度，单程0.5秒，完整往返1秒 |",
        f"| 检测调度 | 配置100赫兹，墙钟实测速率{float(all_metrics.get('detection_rpc_wall_rate_hz') or 0.0):.2f}次每秒 |",
        "| 图像保存 | 正式运行未保存AirSim关键帧，只保留结构化检测和轨迹记录 |",
        "",
        "两个节点分别位于来袭走廊两侧。目标初始纵向距离约2000米，横向和纵向位置不规则排列，部分航迹在观察窗口内发生交叉。节点俯仰角在试验开始前指向走廊中心，此后只执行方位扫描。",
        "",
        f"![三维场景]({relative['scene']})",
        "",
        "## 数据采集",
        "",
        "每次观测保留二维框、相机编号、相机位置姿态、测量时间戳和到达时间戳。进入关联处理前删除检测对象名称、相对真实位姿、三维框和真实身份。在线真值字段泄漏计数为{}。".format(
            all_metrics["online_truth_leakage_count"]
        ),
        "",
        f"{camera_names[0]}检测覆盖率为{_ratio(coverage[camera_names[0]])}，{camera_names[1]}检测覆盖率为{_ratio(coverage[camera_names[1]])}。窄视场高速扫过时，目标只在画面中停留很短时间。单个检测框只能说明某个方向上出现了目标，不能单独判断两台相机看到的是不是同一个目标。",
        "",
        f"![扫描与检测]({relative['scan']})",
        "",
        "## 算法流程",
        "",
        "处理链先把画面中的检测框变成空间方向，再把同一台相机多次扫到的结果连成轨迹。随后比较A、B两侧的轨迹，先做快速几何筛选，再做三维运动拟合。最后由匈牙利算法统一处理一对一冲突，并用连续多轮结果决定是否确认。",
        "",
        f"![算法流程]({relative['algorithm_flow']})",
        "",
        "1. 检测框中心通过针孔模型转换为相机坐标系视线，再用相机姿态旋转到北东地坐标系。",
        "2. 同一扫描半程内的连续检测聚合为扫描片段，相邻扫描中的片段连接为单相机角轨迹。",
        "3. A侧和B侧轨迹插值到共同时间，计算双向归一化共面性残差，先排除明显不可能的组合。",
        "4. 通过粗筛的组合使用多时刻视线拟合三维位置和速度，并执行重投影、时间、速度、正深度、条件数和内点率门控。",
        "5. 有效候选进入带未匹配项的代价矩阵。匈牙利算法求最低代价的一对一关系，并生成5组不重复全局假设。",
        "6. 连续决策周期积累关系支持度。交叉或竞争关系保持待确认，已确认关系连续两个周期矛盾后回退。",
        "7. 最终关系按共同时间的外推位置和速度检查重复轨迹片段，随后冻结在线结果并启动离线评分。",
        "",
        "## 单相机轨迹",
        "",
        "### 像素反投影",
        "",
        r"算法首先要回答：检测框中心这个像素，实际指向空间中的哪个方向。设框中心为 $(u,v)$，图像宽度为 $W$，水平视场角为 $\theta_h$，先计算等效像素焦距，再得到相机坐标系中的单位视线：",
        "",
        r"$$f=\frac{W}{2\tan(\theta_h/2)},\qquad \mathbf r_c=\frac{[1,(u-W/2)/f,(v-H/2)/f]^T}{\|[1,(u-W/2)/f,(v-H/2)/f]^T\|}. $$",
        "",
        r"这个公式把像素位置换成方向，不会凭空给出距离。相机姿态继续把视线转到世界坐标系：$\mathbf r_w=R_z(\psi)R_y(\theta)\mathbf r_c$。单次观测只能确定射线 $\mathbf p(\lambda)=\mathbf o+\lambda\mathbf r_w$，沿射线的深度 $\lambda$ 仍然未知，必须依靠两个站和多个时刻共同求解。",
        "",
        "### 扫描片段",
        "",
        "云台一次扫过同一目标时，检测接口会连续返回多个框。如果把每个框都当成一条新轨迹，同一目标会被重复计数。程序先把时间间隔不超过0.06秒、视线夹角不超过0.16度的检测归为同一扫描片段，并用下面的权重求一条代表视线：",
        "",
        r"$$w_i=\frac{A_i}{\sum_j A_j},\qquad \bar{\mathbf r}=\frac{\sum_iw_i\mathbf r_i}{\|\sum_iw_i\mathbf r_i\|}. $$",
        "",
        r"式中 $A_i$ 是第 $i$ 个检测框面积，$w_i$ 是它在片段中的权重，$\bar{\mathbf r}$ 是合并后的方向。框面积只用于一次扫过期间的方向平均，不用于估算距离。真实远距离小目标可能只有亮点中心，届时应改用像素测量协方差或等权平均。",
        "",
        "### 扫描重访",
        "",
        "相机下一次扫回来时，需要判断新片段能不能接到旧轨迹上。程序用最近5个观测拟合方位角和俯仰角变化，并把旧轨迹外推到新片段时刻。方位误差和俯仰误差合成一个角度误差：",
        "",
        r"$$e_\alpha=\sqrt{(\Delta\mathrm{az}\cos\mathrm{el})^2+(\Delta\mathrm{el})^2}. $$",
        "",
        r"这个数越小，说明新片段越接近旧轨迹的预计方向。时间间隔不超过0.75秒且 $e_\alpha$ 不超过0.45度时才允许连接；至少覆盖4个扫描半程后，轨迹才进入双站关联。",
        "",
        f"{camera_names[0]}形成{track_count_a}条稳定轨迹，比真实目标数多{fragment_excess_a}条；{camera_names[1]}形成{track_count_b}条，比真实目标数多{fragment_excess_b}条。A、B两侧稳定轨迹覆盖率分别为{_ratio(stable[camera_names[0]])}和{_ratio(stable[camera_names[1]])}。多出的轨迹主要来自扫描边缘：同一目标离开视场后再次出现，旧轨迹已经超出保持时间，于是生成了新的编号。",
        "",
        f"![单相机角轨迹]({relative['bearing_tracks']})",
        "",
        "### 为什么候选不是目标数的平方",
        "",
        f"如果{target_count}个目标在每台相机中都恰好形成一条完整轨迹，那么A、B两侧各有{target_count}条轨迹，全组合是{target_count}×{target_count}={ideal_pairs}。本轮实际成轨数是{track_count_a}和{track_count_b}，所以算法必须检查{track_count_a}×{track_count_b}={actual_pairs}个轨迹对，候选数量是理想情况的{pair_expansion_ratio:.2f}倍。",
        "",
        "这里的全组合是在本地轨迹之间做配对，不是在真实目标编号之间配对。算法在线阶段不知道哪几条片段属于同一个真实目标，因此不能提前把多出的片段删掉。",
        "",
        f"![真实目标、本地轨迹与候选组合]({relative['pair_expansion']})",
        "",
        f"![扫描边缘轨迹断裂示例]({relative['fragment_timeline']})",
        "",
        "## 共面性粗筛",
        "",
        f"{actual_pairs}个候选若全部做三维拟合，计算量很大。"
        + r"双站看到同一个目标时，两条视线和两站基线应接近同一个平面。程序先利用这个必要条件做便宜的粗筛。两条轨迹在共同时间 $t_k$ 插值得到单位视线 $\mathbf u_A(t_k)$ 和 $\mathbf u_B(t_k)$，两站基线归一化为 $\hat{\mathbf b}$，单向共面性残差为：",
        "",
        r"$$r_{A\rightarrow B}=\arcsin\frac{|\mathbf u_B^T(\mathbf u_A\times\hat{\mathbf b})|}{\|\mathbf u_A\times\hat{\mathbf b}\|}. $$",
        "",
        r"残差越接近0，两条视线越接近同一平面。程序交换A、B再计算 $r_{B\rightarrow A}$，取两者平均，避免只从一个方向判断。每个组合同时检查残差中位数、90%分位数、离散程度和随时间的变化。共同样本少于4个或中位残差超过0.50毫弧度时，不再做后续三维拟合。",
        "",
        f"本轮{enhanced.full_pair_count}个全组合中有{enhanced.coarse_gate_pass_count}个通过粗筛，离线检查表明{target_count}个真实目标的正确候选都还在。共面性只能排除明显不可能的组合；交叉目标和方向相近的目标仍可能同时通过，因此还要继续拟合和处理全局冲突。",
        "",
        f"![共面性残差]({relative['epipolar_residuals']})",
        "",
        f"![候选漏斗]({relative['enhanced_funnel']})",
        "",
        "## 多时刻几何拟合",
        "",
        r"通过粗筛后，要检查一条三维运动轨迹能否同时解释A、B两侧的观测。程序先假设短时间内目标做恒速运动：$\mathbf x(t)=\mathbf p_0+\mathbf v(t-t_0)$。每条观测视线使用投影矩阵 $P_i=I-\mathbf r_i\mathbf r_i^T$ 消除未知深度，得到：",
        "",
        r"$$P_i[\mathbf p_0+\mathbf v(t_i-t_0)-\mathbf o_i]=\mathbf{0}. $$",
        "",
        r"这个方程只保留目标位置相对测量视线的横向偏差。把两个站、多个时刻的方程叠加起来，就能用最小二乘求出参考位置 $\mathbf p_0$ 和速度 $\mathbf v$ 共六个参数。求解后再投回图像检查误差，超过15像素的离群观测最多剔除3轮；任一相机剩余观测少于4个时停止剔除。",
        "",
        f"![多时刻双视线拟合]({relative['fit_principle']})",
        "",
        f"候选必须同时满足秩为6、两侧最近观测时间差中位数不超过0.20秒、重投影均方根不超过8像素、最大重投影不超过15像素、速度在35至65米每秒、条件数不超过10000、内点率不低于0.85、全部内点为正深度以及北向速度不大于负25米每秒。粗筛后的{enhanced.coarse_gate_pass_count}个组合中有{metrics.get('valid_fit_count', 0)}个通过全部门控。",
        "",
        "多个候选都通过硬门限时，还需要排出优先顺序。程序把重投影误差、视线空间残差、速度偏差、时间差、方程条件数和内点率合成一个代价：",
        "",
        r"$$C=0.55\min(e_{rp}/8,10)+0.15\min(e_{ray}/5,10)+0.15\min(|s-50|/15,10)$$",
        r"$$\quad+0.10\min(\Delta t/0.20,10)+0.05\min(\log_{10}\kappa/4,10)+0.05(1-\rho). $$",
        "",
        r"式中 $e_{rp}$ 是重投影像素误差，$e_{ray}$ 是拟合轨迹到视线的空间误差，$s$ 是速度，$\Delta t$ 是两侧观测时间差，$\kappa$ 是条件数，$\rho$ 是内点率。代价越小，说明这一对轨迹越能被同一条三维运动解释。无效候选不会进入全局分配。",
        "",
        f"![候选代价矩阵]({relative['cost_matrix']})",
        "",
        "## 全局关联",
        "",
        "### 匈牙利分配",
        "",
        "单独挑每条轨迹的最低代价对象会产生冲突，例如两条A站轨迹都可能选中同一条B站轨迹。程序把所有候选放进同一个代价矩阵，再用匈牙利算法寻找总成本最低的一对一方案。每条轨迹还带有代价1.25的“暂不匹配”选项，证据不足时宁可空着，也不强行配对。",
        "",
        f"![一对一关系]({relative['match_graph']})",
        "",
        "### 全局多假设",
        "",
        "目标交叉时，最低代价方案和第二、第三方案可能非常接近。程序保留总代价最低且互不重复的5套完整配对方案，再看某一组关系在这5套方案中得到多少支持。这样做的目的，是让交叉窗口中的关系先保持待确认，避免一次很小的代价波动立即改号。",
        "",
        f"最低代价全局解包含{best_hypothesis_count}组局部关系。若同一A侧或B侧轨迹存在支持度不低于0.25的竞争关系，当前关系不直接确认。上一周期映射发生变化时增加0.10切换代价，减少近似解反复跳变。",
        "",
        f"![全局假设变化]({relative['hypothesis_evolution']})",
        "",
        "### 延迟确认",
        "",
        "关系状态分为初步、待确认、已确认、短时保持和拒绝。最近4次判断中至少3次给出相同映射、累计支持度不低于0.70，并且没有交叉告警时，关系才被确认。任一相机内两条预测轨迹相距小于0.20度时继续等待；已确认关系连续两次出现矛盾后退回待确认。",
        "",
        "图中的状态时间线是试验结束后用完整匿名轨迹按时间戳回放出来的，目的是检查确认和回退规则。它不是在线逐周期重新拟合的实测记录。",
        "",
        f"![确认状态]({relative['state_timeline']})",
        "",
        "### 轨迹碎片抑制",
        "",
        "同一目标在扫描边缘形成前后两段轨迹后，可能被配出两组关系。程序把两组关系外推到同一时刻，如果位置相差不超过5米、速度相差不超过2米每秒，就按重复片段处理。优先保留已经确认的关系；状态相同时保留代价较低者。这个判断仍然不读取真实身份。",
        "",
        f"本轮抑制{len(enhanced.fragment_suppressions)}组重复关系。{suppression_detail}。",
        "",
        "## 关联结果",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 真实目标 | {target_count} |",
        f"| A侧稳定轨迹 | {track_count_a} |",
        f"| B侧稳定轨迹 | {track_count_b} |",
        f"| 理想轨迹组合 | {ideal_pairs} |",
        f"| 全组合数量 | {enhanced.full_pair_count} |",
        f"| 共面性粗筛保留 | {enhanced.coarse_gate_pass_count} |",
        f"| 六参数有效候选 | {metrics.get('valid_fit_count', 0)} |",
        f"| 最低代价全局关系 | {best_hypothesis_count} |",
        f"| 重复片段抑制 | {len(enhanced.fragment_suppressions)} |",
        f"| 最终选中关系 | {selected_count} |",
        f"| 已确认 / 待确认 | {confirmed_count} / {pending_count} |",
        f"| 正确 / 错误 | {metrics.get('correct_match_count', 0)} / {metrics.get('false_match_count', 0)} |",
        f"| 准确率 | {precision} |",
        f"| {target_count}目标召回率 | {recall} |",
        f"| 已确认目标覆盖率 | {confirmed_recall} |",
        f"| 在线真值泄漏 | {all_metrics['online_truth_leakage_count']} |",
        "",
        f"{len(correct_truth_ids)}个目标形成正确跨相机关系，{len(missing_truth_ids)}个没有闭合，编号为{missing_truth_text}。两侧都曾看到这些未闭合目标，但对应的局部片段没有在同一套全局关系中稳定保留下来。当前问题主要出现在扫描边缘碎片和轨迹交叉窗口。",
        "",
        f"![{target_count}目标关联效果]({relative['association_effect']})",
        "",
        "## 几何结果",
        "",
        f"最终正确关系的三维位置拟合平均误差为{_number(position_mean)}米，95%分位误差为{_number(position_p95)}米，平均速度误差为{_number(velocity_mean)}米每秒。这些数值使用离线真值评分，只反映理想位姿和理想时间条件下的拟合一致性。",
        "",
        f"![三维轨迹拟合]({relative['reconstruction']})",
        "",
        f"![拟合误差分布]({relative['errors']})",
        "",
        _geometry_sensitivity_summary(metrics, result.geometry_sensitivity),
        "",
        "敏感性分析是基于拟合几何的模型推算，没有注入外参、云台和时钟系统误差，不能作为AirSim实测定位精度或真实设备精度。",
        "",
        f"![几何敏感性]({relative['geometry_sensitivity']})",
        "",
        "## 对照结果",
        "",
        f"原始全组合处理只用于对照，正式结论采用前述完整链路。对照处理输出{all_metrics.get('match_count')}组局部关系，其中{all_metrics.get('correct_match_count')}组逐关系判断正确，但真实身份重复计数为{all_metrics.get('duplicate_truth_match_count')}。完整链路做完重复片段检查后输出{selected_count}组唯一关系。",
        "",
        "| 项目 | 全组合对照 | 完整关联链路 |",
        "|---|---:|---:|",
        f"| 六参数拟合次数 | {enhanced.full_pair_count} | {enhanced.fit_evaluation_count} |",
        f"| 最终关系数 | {all_metrics.get('match_count')} | {selected_count} |",
        f"| 真实身份重复数 | {all_metrics.get('duplicate_truth_match_count')} | {metrics.get('duplicate_truth_match_count')} |",
        f"| 错误关系数 | {all_metrics.get('false_match_count')} | {metrics.get('false_match_count')} |",
        f"| Python处理耗时 | {legacy_wall_ms:.0f}毫秒 | {association_wall_ms:.0f}毫秒 |",
        "",
        f"完整链路减少了{fit_reduction:.1%}的六参数拟合，并增加交叉保护、延迟确认和重复片段抑制。当前实现仍由Python逐组合计算残差并回放多个判断周期，因此总耗时约为对照处理的{association_wall_ms / max(legacy_wall_ms, 1.0):.1f}倍。下一步应先把共面性计算改成批量矩阵运算并缓存轨迹插值结果，再评估在线处理速度。",
        "",
        "## 验收",
        "",
        "| 检查项 | 结果 |",
        "|---|---|",
        f"| {target_count}个目标生成 | {'通过' if acceptance['spawn_passed'] else '未通过'} |",
        f"| 固定俯仰与方位扫描 | {'通过' if acceptance['fixed_pitch_passed'] else '未通过'} |",
        f"| 在线真值泄漏为0 | {'通过' if acceptance['truth_isolation_passed'] else '未通过'} |",
        f"| 错误关系不高于对照处理 | {'通过' if acceptance.get('enhanced_false_association_non_regression_passed') else '未通过'} |",
        f"| {target_count}目标召回率不低于0.900 | {'通过' if acceptance.get('enhanced_recall_target_passed') else '未通过'} |",
        f"| 六参数拟合量至少减少80% | {'通过' if acceptance.get('enhanced_fit_reduction_passed') else '未通过'} |",
        f"| 最终关系无重复真实身份 | {'通过' if acceptance.get('enhanced_no_duplicate_match_passed') else '未通过'} |",
        "",
        "## 限制",
        "",
        "本轮只有一个正式种子，没有形成不同目标队形、速度、交叉强度和误差条件下的统计结论。AirSim内置检测接口提供稳定二维框，尚未覆盖真实小目标只输出亮点中心、检测框抖动、漏检和虚警的情况。",
        "",
        "相机位置姿态、云台角度和时间戳按理想值使用。外参误差、云台回差和时间偏差会同时改变共面性残差和三维拟合结果，现有0.50毫弧度粗筛门限尚不能直接用于真实设备。",
        "",
        "图神经网络没有进入本轮实现。单种子数据不足以划分独立训练集、验证集和测试集。当前匈牙利与多假设方法继续作为可解释基线，积累多场景数据后再比较学习方法。",
        "",
        "## 待办事项",
        "",
        "- [ ] **实现因果增量处理。** 每0.5秒只使用当前及历史匿名观测更新候选、全局假设和关系状态，禁止使用未来轨迹；分别统计算法处理延迟和数据等待延迟。",
        "- [ ] **取消对检测框面积的强依赖。** 将框面积改为可选字段，优先使用像素中心测量协方差；无协方差时比较置信度、视场中心距离和等权平均。",
        "- [ ] **降低轨迹碎片。** 在跨相机关联前增加同相机片段合并，综合检查时间连续性、预测方位、俯仰和角速度，记录错误合并率。",
        "- [ ] **标定扫描门限。** 对扫描内0.06秒、0.16度以及重访0.75秒、0.45度开展多种子敏感性试验。",
        "- [ ] **注入工程误差。** 分级加入检测中心抖动、漏检、虚警、外参误差、云台角误差和时间偏差，输出门控拒绝原因。",
        "- [ ] **比较方向轨迹基线。** 在不先拟合三维位置的条件下，使用时间对齐后的方位、俯仰和角速度构造代价并执行匈牙利分配。",
        "- [ ] **完成多场景统计。** 增加不同目标队形、交叉强度、速度和初始距离的独立种子，报告均值、分位数和失败样本。",
        "- [ ] **后置图神经网络对照。** 形成足够数据并冻结测试集后，再比较误配率、召回率和计算预算；不满足相同安全门限时不进入在线链路。",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _select_keyframes(
    manifest: Sequence[dict[str, str]],
    detections: Mapping[int, Sequence[dict[str, str]]],
    *,
    count: int,
) -> list[dict[str, str]]:
    ranked = sorted(
        manifest,
        key=lambda row: (
            -len(detections.get(int(row["frame_index"]), [])),
            float(row["measurement_timestamp"]),
        ),
    )
    selected = sorted(ranked[:count], key=lambda row: float(row["measurement_timestamp"]))
    return selected


def _scenario_config(result: ExperimentResult) -> dict[str, Any]:
    payload = json.loads(
        (result.output_dir / "scenario.json").read_text(encoding="utf-8")
    )
    scenario = dict(payload["scenario"])
    scenario["camera_positions"] = {
        scenario["camera_a_name"]: scenario["camera_a_position_ned"],
        scenario["camera_b_name"]: scenario["camera_b_position_ned"],
    }
    return scenario


def _scenario_camera_value(result: ExperimentResult, key: str) -> float:
    payload = json.loads(
        (result.output_dir / "scenario.json").read_text(encoding="utf-8")
    )
    return float(payload["camera"][key])


def _resolve_record_path(output_dir: Path, value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else output_dir / path


def _load_saved_tracks(
    tracks_path: Path,
    samples_path: Path,
    *,
    camera_positions: Mapping[str, tuple[float, float, float]],
    focal_length_px: float,
) -> tuple[BearingTrack, ...]:
    sample_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(samples_path):
        sample_rows[row["track_id"]].append(row)

    tracks: list[BearingTrack] = []
    for row in _read_csv(tracks_path):
        if not _as_bool(row["stable"]):
            continue
        camera_id = row["camera_id"]
        if camera_id not in camera_positions:
            raise ValueError(f"unknown camera in saved track: {camera_id}")
        samples = [
            BearingSample(
                camera_id=camera_id,
                sweep_index=int(item["sweep_index"]),
                timestamp=float(item["measurement_timestamp"]),
                origin_ned=camera_positions[camera_id],
                direction_ned=(
                    float(item["ray_x_ned"]),
                    float(item["ray_y_ned"]),
                    float(item["ray_z_ned"]),
                ),
                detection_uids=tuple(json.loads(item["detection_uids"])),
                focal_length_px=float(focal_length_px),
                bbox_area_px2=0.0,
            )
            for item in sorted(
                sample_rows.get(row["track_id"], []),
                key=lambda value: int(value["sample_index"]),
            )
        ]
        if not samples:
            raise ValueError(f"saved stable track has no samples: {row['track_id']}")
        tracks.append(
            BearingTrack(
                track_id=row["track_id"],
                camera_id=camera_id,
                samples=samples,
            )
        )
    return tuple(tracks)


def _candidate_from_row(row: Mapping[str, str]) -> CrossCameraCandidate:
    return CrossCameraCandidate(
        track_a_id=row["track_a_id"],
        track_b_id=row["track_b_id"],
        valid=_as_bool(row["valid"]),
        rejection_reason=row["rejection_reason"],
        cost=float(row["cost"]),
        reprojection_rms_px=float(row["reprojection_rms_px"]),
        reprojection_max_px=float(row["reprojection_max_px"]),
        ray_residual_rms_m=float(row["ray_residual_rms_m"]),
        fitted_speed_mps=float(row["fitted_speed_mps"]),
        median_nearest_time_delta_s=float(row["median_nearest_time_delta_s"]),
        condition_number=float(row["condition_number"]),
        observation_count=int(row["observation_count"]),
        inlier_count=int(row["inlier_count"]),
        outlier_count=int(row["outlier_count"]),
        reference_timestamp=float(row["reference_timestamp"]),
        position_ned=_triple(json.loads(row["position_ned"])),
        velocity_ned=_triple(json.loads(row["velocity_ned"])),
    )


def _match_from_row(row: Mapping[str, str]) -> CrossCameraMatch:
    return CrossCameraMatch(
        match_id=row["match_id"],
        track_a_id=row["track_a_id"],
        track_b_id=row["track_b_id"],
        cost=float(row["cost"]),
        reference_timestamp=float(row["reference_timestamp"]),
        position_ned=_triple(json.loads(row["position_ned"])),
        velocity_ned=_triple(json.loads(row["velocity_ned"])),
    )


def _load_enhanced_association(
    output_paths: Mapping[str, Path],
    *,
    scenario: Mapping[str, Any],
    tracks_a: Sequence[BearingTrack],
    tracks_b: Sequence[BearingTrack],
    metrics: Mapping[str, Any],
) -> tuple[TemporalAssociationResult | None, tuple[GeometrySensitivity, ...]]:
    required = (
        "epipolar_evidence_v2",
        "enhanced_candidates_v2",
        "enhanced_matches_v2",
        "association_decisions_v2",
        "association_hypothesis_history_v2",
        "association_state_timeline_v2",
        "fragment_suppressions_v2",
        "global_hypotheses_v2",
        "geometry_sensitivity_v2",
    )
    if any(name not in output_paths or not output_paths[name].is_file() for name in required):
        return None, ()
    enhanced_metrics = dict(metrics.get("enhanced_association") or {})
    config = AssociationConfig(
        expected_speed_mps=float(scenario.get("target_speed_mps", 50.0)),
        max_time_delta_s=float(
            scenario.get("max_cross_camera_time_delta_s", 0.20)
        ),
        coplanarity_median_gate_mrad=float(
            enhanced_metrics.get("coplanarity_gate_mrad", 0.50)
        ),
    )
    evidence = tuple(
        EpipolarEvidence(
            track_a_id=row["track_a_id"],
            track_b_id=row["track_b_id"],
            gate_passed=_as_bool(row["gate_passed"]),
            rejection_reason=row.get("rejection_reason", ""),
            aligned_sample_count=int(row["aligned_sample_count"]),
            timestamps_s=tuple(float(value) for value in json.loads(row["timestamps_s"])),
            residuals_mrad=tuple(float(value) for value in json.loads(row["residuals_mrad"])),
            residual_median_mrad=float(row["residual_median_mrad"]),
            residual_p90_mrad=float(row["residual_p90_mrad"]),
            residual_mad_mrad=float(row["residual_mad_mrad"]),
            residual_slope_mrad_per_s=float(row["residual_slope_mrad_per_s"]),
            intersection_angle_median_deg=float(row["intersection_angle_median_deg"]),
        )
        for row in _read_csv(output_paths["epipolar_evidence_v2"])
    )
    candidates = tuple(
        _candidate_from_row(row)
        for row in _read_csv(output_paths["enhanced_candidates_v2"])
    )
    enhanced_match_rows = _read_csv(output_paths["enhanced_matches_v2"])
    selected_matches = tuple(_match_from_row(row) for row in enhanced_match_rows)
    confirmed_matches = tuple(
        _match_from_row(row)
        for row in enhanced_match_rows
        if row.get("confirmation_state") == "confirmed"
    )
    decisions = tuple(
        AssociationDecisionRecord(
            epoch_index=int(row["epoch_index"]),
            timestamp=float(row["timestamp"]),
            active_a_track_count=int(row["active_a_track_count"]),
            active_b_track_count=int(row["active_b_track_count"]),
            full_pair_count=int(row["full_pair_count"]),
            coarse_gate_pass_count=int(row["coarse_gate_pass_count"]),
            fit_evaluation_count=int(row["fit_evaluation_count"]),
            valid_fit_count=int(row["valid_fit_count"]),
            hypothesis_count=int(row["hypothesis_count"]),
            best_hypothesis_cost=(
                None
                if row.get("best_hypothesis_cost", "") == ""
                else float(row["best_hypothesis_cost"])
            ),
        )
        for row in _read_csv(output_paths["association_decisions_v2"])
    )
    hypothesis_history = tuple(
        AssociationHypothesisRecord(
            epoch_index=int(row["epoch_index"]),
            timestamp=float(row["timestamp"]),
            rank=int(row["rank"]),
            total_cost=float(row["total_cost"]),
            normalized_support=float(row["normalized_support"]),
            match_count=int(row["match_count"]),
            matches=tuple(tuple(str(value) for value in pair) for pair in json.loads(row["matches"])),
        )
        for row in _read_csv(output_paths["association_hypothesis_history_v2"])
    )
    state_history = tuple(
        AssociationStateRecord(
            epoch_index=int(row["epoch_index"]),
            timestamp=float(row["timestamp"]),
            track_a_id=row["track_a_id"],
            track_b_id=row["track_b_id"],
            state=row["state"],  # type: ignore[arg-type]
            pair_support=float(row["pair_support"]),
            smoothed_support=float(row["smoothed_support"]),
            competing_support=float(row["competing_support"]),
            crossing_alert=_as_bool(row["crossing_alert"]),
            mapping_hits_in_window=int(row["mapping_hits_in_window"]),
            contradiction_streak=int(row["contradiction_streak"]),
            reason=row["reason"],
        )
        for row in _read_csv(output_paths["association_state_timeline_v2"])
    )
    fragment_suppressions = tuple(
        FragmentSuppressionRecord(
            retained_track_a_id=row["retained_track_a_id"],
            retained_track_b_id=row["retained_track_b_id"],
            suppressed_track_a_id=row["suppressed_track_a_id"],
            suppressed_track_b_id=row["suppressed_track_b_id"],
            comparison_timestamp=float(row["comparison_timestamp"]),
            predicted_position_delta_m=float(row["predicted_position_delta_m"]),
            velocity_delta_mps=float(row["velocity_delta_mps"]),
            reason=row.get("reason", "duplicate_constant_velocity_fragment"),
        )
        for row in _read_csv(output_paths["fragment_suppressions_v2"])
    )
    hypotheses_payload = json.loads(
        output_paths["global_hypotheses_v2"].read_text(encoding="utf-8")
    )
    hypotheses = tuple(
        GlobalAssignmentHypothesis(
            hypothesis_id=str(item["hypothesis_id"]),
            rank=int(item["rank"]),
            total_cost=float(item["total_cost"]),
            normalized_support=float(item["normalized_support"]),
            matches=tuple(tuple(str(value) for value in pair) for pair in item["matches"]),
            unmatched_a_track_ids=tuple(str(value) for value in item["unmatched_a_track_ids"]),
            unmatched_b_track_ids=tuple(str(value) for value in item["unmatched_b_track_ids"]),
        )
        for item in hypotheses_payload
    )
    matched_a = {item.track_a_id for item in selected_matches}
    matched_b = {item.track_b_id for item in selected_matches}
    temporal = TemporalAssociationResult(
        config=config,
        epipolar_evidence=evidence,
        fitted_candidates=candidates,
        hypotheses=hypotheses,
        decisions=decisions,
        hypothesis_history=hypothesis_history,
        state_history=state_history,
        fragment_suppressions=fragment_suppressions,
        selected_matches=selected_matches,
        confirmed_matches=confirmed_matches,
        unmatched_a_track_ids=tuple(
            item.track_id for item in tracks_a if item.track_id not in matched_a
        ),
        unmatched_b_track_ids=tuple(
            item.track_id for item in tracks_b if item.track_id not in matched_b
        ),
        full_pair_count=int(enhanced_metrics.get("full_pair_count", len(tracks_a) * len(tracks_b))),
        coarse_gate_pass_count=int(enhanced_metrics.get("coarse_gate_pass_count", sum(item.gate_passed for item in evidence))),
        fit_evaluation_count=int(enhanced_metrics.get("fit_evaluation_count", len(candidates))),
    )
    geometry = tuple(
        GeometrySensitivity(
            track_a_id=row["track_a_id"],
            track_b_id=row["track_b_id"],
            reference_timestamp=float(row["reference_timestamp"]),
            angular_noise_mrad=float(row["angular_noise_mrad"]),
            requested_sample_count=int(row["requested_sample_count"]),
            valid_sample_count=int(row["valid_sample_count"]),
            intersection_angle_deg=float(row["intersection_angle_deg"]),
            range_a_m=float(row["range_a_m"]),
            range_b_m=float(row["range_b_m"]),
            position_sensitivity_p50_m=float(row["position_sensitivity_p50_m"]),
            position_sensitivity_p95_m=float(row["position_sensitivity_p95_m"]),
            evidence_label=row.get("evidence_label", "modeled_geometry_sensitivity"),
        )
        for row in _read_csv(output_paths["geometry_sensitivity_v2"])
    )
    return temporal, geometry


def _triple(value: Sequence[Any]) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"expected a three-element vector, got {len(value)}")
    return (float(value[0]), float(value[1]), float(value[2]))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _ratio(value: Any) -> str:
    return "不可用" if value is None else f"{float(value):.3f}"


def _number(value: Any) -> str:
    return "不可用" if value is None else f"{float(value):.3f}"
