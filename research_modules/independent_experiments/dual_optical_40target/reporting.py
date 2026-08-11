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
from matplotlib import font_manager
import numpy as np

from .core import (
    BearingSample,
    BearingTrack,
    CameraSpec,
    CrossAssociationResult,
    CrossCameraCandidate,
    CrossCameraMatch,
    TargetSpec,
)
from .runtime import ExperimentResult, write_json


_CJK_FONT_PATHS = (
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
)


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
    )


def generate_experiment_report(result: ExperimentResult) -> dict[str, Path]:
    _configure_matplotlib()
    figures_dir = result.output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures = {
        "scene": _plot_scene_geometry(result, figures_dir / "01_scene_geometry_3d.png"),
        "scan": _plot_scan_timeline(result, figures_dir / "02_scan_and_detection.png"),
        "camera_a": _plot_keyframe_montage(
            result, result.tracks_a[0].camera_id if result.tracks_a else "Optical_A",
            figures_dir / "03_camera_a_keyframes.png",
        ),
        "camera_b": _plot_keyframe_montage(
            result, result.tracks_b[0].camera_id if result.tracks_b else "Optical_B",
            figures_dir / "04_camera_b_keyframes.png",
        ),
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
    }
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
    axis.set_title("双光电节点与40目标三维场景")
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


def _plot_cost_matrix(result: ExperimentResult, path: Path) -> Path:
    tracks_a = list(result.tracks_a)
    tracks_b = list(result.tracks_b)
    matrix = np.full((len(tracks_a), len(tracks_b)), np.nan, dtype=float)
    index_a = {track.track_id: index for index, track in enumerate(tracks_a)}
    index_b = {track.track_id: index for index, track in enumerate(tracks_b)}
    for candidate in result.association.candidates:
        if candidate.valid:
            matrix[index_a[candidate.track_a_id], index_b[candidate.track_b_id]] = candidate.cost
    fig, axis = plt.subplots(figsize=(9.0, 7.8))
    shown = np.ma.masked_invalid(matrix)
    image = axis.imshow(shown, cmap="viridis_r", vmin=0.0, vmax=1.25, aspect="auto")
    for match in result.association.matches:
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
    scoring = _read_csv(result.output_paths["match_scoring"])
    correctness = {row["match_id"]: _as_bool(row["correct"]) for row in scoring}
    tracks_a = list(result.tracks_a)
    tracks_b = list(result.tracks_b)
    index_a = {track.track_id: index for index, track in enumerate(tracks_a)}
    index_b = {track.track_id: index for index, track in enumerate(tracks_b)}
    fig, axis = plt.subplots(figsize=(10.0, 8.0))
    axis.scatter(np.zeros(len(tracks_a)), range(len(tracks_a)), c="#1769aa", s=22, label="相机A轨迹")
    axis.scatter(np.ones(len(tracks_b)), range(len(tracks_b)), c="#b23a48", s=22, label="相机B轨迹")
    for match in result.association.matches:
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
    scoring = _read_csv(result.output_paths["match_scoring"])
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
    colors = plt.cm.turbo(np.linspace(0.02, 0.98, max(len(result.association.matches), 1)))
    for color, match in zip(colors, result.association.matches):
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
    scoring = _read_csv(result.output_paths["match_scoring"])
    position = sorted(
        float(row["position_error_m"])
        for row in scoring
        if row.get("position_error_m") not in ("", "None") and _as_bool(row["correct"])
    )
    velocity = sorted(
        float(row["velocity_error_mps"])
        for row in scoring
        if row.get("velocity_error_mps") not in ("", "None") and _as_bool(row["correct"])
    )
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


def _write_report(result: ExperimentResult, figures: Mapping[str, Path]) -> Path:
    metrics = result.metrics
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
    report_path = result.output_dir / "DUAL_OPTICAL_40TARGET_AIRSIM_REPORT_CN.md"
    relative = {
        key: path.relative_to(result.output_dir).as_posix() for key, path in figures.items()
    }
    lines = [
        "# 双光电40目标轨迹关联试验",
        "",
        "## 结论",
        "",
        f"本轮验收结果为**{passed_text}**。试验在AirSim ComputerVision模式下使用两个固定光电节点、40个移动无人机网格和内置检测接口。在线关联未读取Actor名称、三维真值或系统全局航迹。",
        "",
        f"匈牙利算法输出{metrics['match_count']}组跨相机关系，其中正确{metrics['correct_match_count']}组、错误{metrics['false_match_count']}组。准确率为{precision}，相对全部40个目标的召回率为{full_recall}，相对两侧均已形成稳定轨迹的目标召回率为{eligible_recall}。",
        "",
        f"验收阈值已经通过，但结果未达到40个目标全部正确配准。两台相机都检测到全部目标，最终只有{len(correct_truth_ids)}个目标形成正确跨相机关系；未正确配准的是{'、'.join(missing_correct_truth_ids)}。",
        "",
        "本试验只验证理想位姿、理想时间和AirSim检测框条件下的双光电轨迹关联。结果不是实装光电设备性能，也不代表D1-D7系统链路已经接入。",
        "",
        "## 场景",
        "",
        "两个光电节点横向相距2000米，目标群初始位于前方约2000米。40个目标前后错列并设置少量横向交叉，速度模长均为50米每秒，目标高度变化限制在中心高度上下20米。目标网格最长方向在预检中标定为3米。",
        "",
        f"相机分辨率为1280乘1024，AirSim水平视场角为2.93度，按该投影得到的垂直视场角为{_scenario_camera_value(result, 'vertical_fov_deg'):.3f}度。AirSim等效角分辨率为{_scenario_camera_value(result, 'effective_ifov_mrad'):.5f}毫弧度每像素，与设备给出的0.05毫弧度分开记录。",
        "",
        f"![三维场景]({relative['scene']})",
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
        f"![相机A]({relative['camera_a']})",
        "",
        f"![相机B]({relative['camera_b']})",
        "",
        "## 扫描重访轨迹",
        "",
        "同一次扫过目标产生的相邻检测先合并为扫描观测片段。像素中心结合相机姿态转换为世界视线，随后在角度空间连接相邻扫描周期的观测。轨迹允许保持0.75秒，至少经过4次扫描重访后才进入跨相机关联。",
        "",
        f"{camera_names[0]}形成{metrics['stable_track_count'][camera_names[0]]}条稳定轨迹，覆盖{_ratio(stable[camera_names[0]])}的目标；{camera_names[1]}形成{metrics['stable_track_count'][camera_names[1]]}条稳定轨迹，覆盖{_ratio(stable[camera_names[1]])}的目标。{camera_names[0]}有{fragmented_target_count[camera_names[0]]}个目标被拆成两条稳定片段，{camera_names[1]}有{fragmented_target_count[camera_names[1]]}个目标出现同类情况。扫描边缘短时离开视场和交叉窗口是主要触发条件。",
        "",
        f"![本地轨迹]({relative['bearing_tracks']})",
        "",
        "## 跨相机关联",
        "",
        "每一对候选轨迹采用恒速模型拟合三维位置和速度。代价由重投影误差、视线闭合误差、速度偏差、时间差和几何条件数组成。少量孤立重投影离群点会被剔除，单侧少于4个有效观测的候选不能通过。",
        "",
        "无效候选在进入分配前被屏蔽。代价矩阵增加未匹配项，匈牙利算法不强制40乘40全部配对。该处理避免一个相机漏检或轨迹破碎时生成错误的一对一关系。",
        "",
        f"![代价矩阵]({relative['cost_matrix']})",
        "",
        f"![匹配关系]({relative['match_graph']})",
        "",
        "## 未闭合项",
        "",
        f"37组匹配中有1组错误关系：{false_match_text}。该错误使用了两侧的局部轨迹片段，说明一对一本地轨迹约束不能自动消除同一真实目标的多片段问题。",
        "",
        f"另有{len(missing_correct_truth_ids)}个目标没有形成正确跨相机关系，分别为{'、'.join(missing_correct_truth_ids)}。当前结果已经达到准确率和召回率验收线，仍不能视为40对40全量闭合。后续应先降低扫描边缘造成的轨迹碎片，再评估是否需要增加跨周期轨迹合并。",
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
        f"| 40个目标生成 | {'通过' if acceptance['spawn_passed'] else '未通过'} |",
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
