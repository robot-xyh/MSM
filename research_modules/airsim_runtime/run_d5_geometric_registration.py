#!/usr/bin/env python3
"""Run a real AirSim ComputerVision N-v-N D5 geometric registration validation."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
for rel in (
    "research_modules",
    "research_modules/d1_sensor_fusion/src",
    "research_modules/d2_data_association",
    "research_modules/d3_assignment_planner/src",
    "research_modules/d4_distributed_fallback",
    "research_modules/d5_terminal_association/src",
    "research_modules/d6_evaluation_metrics",
    "research_modules/d7_proportional_guidance",
):
    path = str(ROOT / rel)
    if path not in sys.path:
        sys.path.insert(0, path)

from airsim_dryrun.models import (  # noqa: E402
    AirSimCameraInfo,
    AirSimDetectionBox,
    AirSimFrame,
    AirSimResourceState,
    AirSimTruthObject,
)
from airsim_runtime import run_blocks_smoke  # noqa: E402
from airsim_runtime.adapters import (  # noqa: E402
    geometric_local_visual_tracks_from_blocks_frame,
    offline_truth_map_from_blocks_frame,
)
from airsim_runtime.models import (  # noqa: E402
    BlocksSmokeConfig,
    default_actor_target_specs,
    default_cv_camera_vehicle_names,
    write_dynamic_computer_vision_settings,
)
from d5_terminal_association import (  # noqa: E402
    AssociationConfig,
    GlobalTrack,
    associate_tracks_to_detections_geometrically,
    camera_model_from_airsim_camera_info,
    evaluate_associations_offline,
)


DEFAULT_SETTINGS = "research_modules/airsim_runtime/settings/blocks_cv_2v2_geometric_settings.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-id", default="d5_cv_2v2_geometric_001")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--dt", type=float, default=0.5)
    parser.add_argument("--output-root", default="research_modules/airsim_runtime/outputs")
    parser.add_argument("--blocks-script", default="Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh")
    parser.add_argument("--settings", default=DEFAULT_SETTINGS)
    parser.add_argument("--connection-timeout", type=float, default=90.0)
    parser.add_argument("--client-timeout", type=float, default=2.0)
    parser.add_argument("--drone-count", type=int, default=2)
    parser.add_argument("--camera-spacing", type=float, default=20.0)
    parser.add_argument("--follow-distance", type=float, default=25.0)
    parser.add_argument("--target-distance", type=float, default=50.0)
    parser.add_argument("--target-spacing", type=float, default=16.0)
    parser.add_argument("--target-scale-m", type=float, default=6.0)
    parser.add_argument("--target-speed", type=float, default=0.4)
    parser.add_argument("--gate-chi2", type=float, default=16.0)
    parser.add_argument("--measurement-sigma-px", type=float, default=18.0)
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--blocks-arg", action="append", default=None)
    parser.add_argument("--no-nvidia-offload", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.drone_count <= 0:
        raise SystemExit("--drone-count must be positive")
    camera_names = default_cv_camera_vehicle_names(args.drone_count, prefix="D5_Cam_")
    settings_path = Path(args.settings)
    if args.drone_count != 2 or args.settings == DEFAULT_SETTINGS:
        settings_path = write_dynamic_computer_vision_settings(
            Path(args.output_root) / args.episode_id / "generated_settings" / f"blocks_cv_n{args.drone_count}.json",
            camera_vehicle_names=camera_names,
            secondary_vehicle_names=(),
            camera_spacing_m=args.camera_spacing,
            camera_z=-10.0,
            target_z=-10.0,
            fov_degrees=120.0,
            width=640,
            height=480,
        )
    target_specs = _target_specs(
        count=args.drone_count,
        target_distance=args.target_distance,
        target_spacing=args.target_spacing,
        target_scale_m=args.target_scale_m,
        target_speed=args.target_speed,
    )
    config = BlocksSmokeConfig(
        episode_id=args.episode_id,
        scenario_name=f"blocks_cv_{args.drone_count}v{args.drone_count}_geometric_registration",
        duration_s=args.duration,
        dt_s=args.dt,
        output_root=Path(args.output_root),
        blocks_script=Path(args.blocks_script),
        settings_path=settings_path,
        blocks_args=tuple(args.blocks_arg)
        if args.blocks_arg is not None
        else ("-windowed", "-ResX=640", "-ResY=480", "-NoVSync", "-NoHMD", "-NoSound"),
        prefer_nvidia_offload=not args.no_nvidia_offload,
        launch_blocks=not args.no_launch,
        connection_timeout_s=args.connection_timeout,
        client_timeout_s=args.client_timeout,
        client_kind="vehicle",
        camera_vehicle_name=camera_names[0],
        camera_vehicle_names=camera_names,
        capture_lidar=False,
        cv_camera_follow_assignments=True,
        cv_camera_follow_distance_m=args.follow_distance,
        cv_secondary_look_at_enabled=False,
        target_vehicle_names=(),
        resource_vehicle_names=camera_names,
        target_actor_specs=target_specs,
        detection_filter_names=("MSM_TargetActor_*",),
        detection_radius_cm=int(max(args.target_distance + args.follow_distance + 30.0, 100.0) * 100),
        include_integrated_pipeline=False,
        metadata={
            "runtime_mode": "computer_vision_nvN_geometric_registration",
            "drone_count": args.drone_count,
            "online_association_uses_truth_id": False,
            "offline_truth_id_for_evaluation_only": True,
            "target_scale_m": args.target_scale_m,
            "target_distance_m": args.target_distance,
            "target_spacing_m": args.target_spacing,
            "follow_distance_m": args.follow_distance,
        },
    )
    result = run_blocks_smoke(config)
    frames_path = result.output_paths["blocks_frames_jsonl"]
    frames = _load_frames(frames_path)
    analysis = analyze_frames(
        frames,
        gate_chi2=args.gate_chi2,
        measurement_sigma_px=args.measurement_sigma_px,
    )
    output_dir = config.output_dir
    pair_csv = _write_pair_csv(output_dir / "d5_geometric_pairs.csv", analysis["pairs"])
    metrics_path = _write_json(output_dir / "d5_geometric_metrics.json", analysis["metrics"])
    report_path = _write_report(
        output_dir / f"D5_CV_{args.drone_count}V{args.drone_count}_GEOMETRIC_REGISTRATION_REPORT.md",
        config=config,
        result=result,
        analysis=analysis,
        pair_csv=pair_csv,
        metrics_path=metrics_path,
    )
    print(f"episode_id={result.episode_id}")
    print(f"connected={result.connected}")
    print(f"frame_count={result.frame_count}")
    print(f"detection_count={result.metadata.get('detection_count', 0)}")
    print(f"association_accuracy={analysis['metrics']['association_accuracy']}")
    print(f"evaluated_count={analysis['metrics']['evaluated_count']}")
    print(f"id_mismatch_count={analysis['metrics']['id_mismatch_count']}")
    print(f"mean_pixel_error={analysis['metrics']['mean_pixel_error']}")
    print(f"p95_pixel_error={analysis['metrics']['p95_pixel_error']}")
    print(f"gate_pass_rate={analysis['metrics']['gate_pass_rate']}")
    print(f"output_dir={output_dir.resolve()}")
    print(f"report={report_path.resolve()}")
    return 0


def analyze_frames(
    frames: Iterable[AirSimFrame],
    *,
    gate_chi2: float,
    measurement_sigma_px: float,
) -> dict[str, Any]:
    pair_rows: list[dict[str, Any]] = []
    evaluated_count = 0
    correct_count = 0
    mismatch_count = 0
    ambiguous_count = 0
    selected_errors: list[float] = []
    all_pair_errors: list[float] = []
    gate_pass_count = 0
    total_pair_count = 0
    assignment_count = 0
    missing_detection_frames = 0
    non_identity_camera_frames = 0
    camera_count = 0
    detection_count = 0
    config = AssociationConfig(gate_chi2=float(gate_chi2), min_lock_margin=1.0)

    for frame in frames:
        global_tracks = _global_tracks_from_frame(frame)
        d2_tracks = [
            SimpleNamespace(truth_id=truth.object_id, global_track_id=_global_id(truth.object_id))
            for truth in frame.truth_objects
        ]
        detections_by_camera: dict[str, list[AirSimDetectionBox]] = {}
        for detection in frame.visual_detections:
            detections_by_camera.setdefault(detection.camera_id, []).append(detection)
        if not frame.visual_detections:
            missing_detection_frames += 1
        detection_count += len(frame.visual_detections)

        for camera_info in frame.cameras:
            camera_count += 1
            rotation = np.asarray(camera_info.rotation_world_to_camera, dtype=float)
            if not np.allclose(rotation, np.eye(3)):
                non_identity_camera_frames += 1
            camera_detections = tuple(detections_by_camera.get(camera_info.camera_id, ()))
            if not camera_detections:
                continue
            camera_frame = replace(frame, visual_detections=camera_detections)
            local_tracks = geometric_local_visual_tracks_from_blocks_frame(camera_frame)
            camera = camera_model_from_airsim_camera_info(
                camera_info,
                measurement_sigma_px=measurement_sigma_px,
            )
            result = associate_tracks_to_detections_geometrically(
                global_tracks,
                local_tracks,
                camera,
                config=config,
                timestamp=frame.timestamp,
                frame_id=f"{frame.episode_id}:{frame.frame_index:04d}:{camera_info.camera_id}",
            )
            truth_map = offline_truth_map_from_blocks_frame(camera_frame, d2_tracks)
            metrics = evaluate_associations_offline(result, truth_map)
            evaluated_count += metrics.evaluated_count
            mismatch_count += metrics.id_mismatch_count
            correct_count += (
                0
                if metrics.association_accuracy is None
                else round(metrics.association_accuracy * metrics.evaluated_count)
            )
            ambiguous_count += metrics.ambiguous_count
            assignment_count += len(result.assignments)

            for pair in result.pairs:
                total_pair_count += 1
                if pair.gate_pass:
                    gate_pass_count += 1
                if pair.pixel_error is not None and math.isfinite(pair.pixel_error):
                    all_pair_errors.append(float(pair.pixel_error))
                    if pair.assignment_selected:
                        selected_errors.append(float(pair.pixel_error))
                truth_track_id = truth_map.get(pair.local_track_id)
                pair_rows.append(
                    {
                        "frame_index": frame.frame_index,
                        "timestamp": frame.timestamp,
                        "camera_id": camera_info.camera_id,
                        "track_id": pair.track_id,
                        "local_track_id": pair.local_track_id,
                        "truth_track_id": truth_track_id,
                        "projected_px": pair.projected_px,
                        "bbox_center_px": pair.bbox_center_px,
                        "pixel_error": pair.pixel_error,
                        "mahalanobis_d2": pair.mahalanobis_d2,
                        "gate_pass": pair.gate_pass,
                        "assignment_selected": pair.assignment_selected,
                        "id_match": None
                        if not pair.assignment_selected or truth_track_id is None
                        else pair.track_id == truth_track_id,
                    }
                )

    metrics_payload = {
        "frame_count": len(list(frames)) if not isinstance(frames, list) else len(frames),
        "camera_count": camera_count,
        "non_identity_camera_frame_count": non_identity_camera_frames,
        "detection_count": detection_count,
        "missing_detection_frame_count": missing_detection_frames,
        "assignment_count": assignment_count,
        "evaluated_count": evaluated_count,
        "association_accuracy": correct_count / evaluated_count if evaluated_count else None,
        "id_mismatch_count": mismatch_count,
        "ambiguous_count": ambiguous_count,
        "gate_pass_rate": gate_pass_count / total_pair_count if total_pair_count else None,
        "mean_pixel_error": _mean(selected_errors),
        "p50_pixel_error": _percentile(selected_errors, 50),
        "p95_pixel_error": _percentile(selected_errors, 95),
        "mean_all_pair_pixel_error": _mean(all_pair_errors),
        "online_truth_id_used": False,
        "offline_truth_id_for_evaluation_only": True,
    }
    return {"metrics": metrics_payload, "pairs": pair_rows}


def _target_specs(
    *,
    count: int,
    target_distance: float,
    target_spacing: float,
    target_scale_m: float,
    target_speed: float,
) -> tuple[Any, ...]:
    return default_actor_target_specs(
        count=count,
        target_z=-10.0,
        target_distance_m=target_distance,
        target_spacing_m=target_spacing,
        asset_name="1M_Cube_Chamfer",
        target_scale_m=target_scale_m,
        target_speed_scale=1.0,
        x_spacing_m=0.0,
        x_speed_base_mps=target_speed,
        x_speed_step_mps=0.0,
        y_speed_span_mps=0.15,
    )


def _global_tracks_from_frame(frame: AirSimFrame) -> list[GlobalTrack]:
    tracks: list[GlobalTrack] = []
    for obj in frame.truth_objects:
        tracks.append(
            GlobalTrack(
                global_track_id=_global_id(obj.object_id),
                position=np.asarray(obj.position_ned, dtype=float),
                velocity=np.asarray(obj.velocity_ned, dtype=float),
                covariance=np.asarray(obj.covariance_ned, dtype=float) + np.eye(3) * 0.01,
                category=obj.classification_hint or "uav",
                timestamp=frame.timestamp,
                track_version=1,
            )
        )
    return tracks


def _global_id(truth_id: str) -> str:
    return f"G-{truth_id}"


def _load_frames(path: Path) -> list[AirSimFrame]:
    frames: list[AirSimFrame] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            payload = json.loads(line)
            frames.append(
                AirSimFrame(
                    episode_id=payload["episode_id"],
                    scenario_name=payload["scenario_name"],
                    frame_index=int(payload["frame_index"]),
                    timestamp=float(payload["timestamp"]),
                    truth_objects=tuple(AirSimTruthObject(**item) for item in payload.get("truth_objects", [])),
                    resources=tuple(AirSimResourceState(**item) for item in payload.get("resources", [])),
                    cameras=tuple(AirSimCameraInfo(**item) for item in payload.get("cameras", [])),
                    visual_detections=tuple(
                        AirSimDetectionBox(**item) for item in payload.get("visual_detections", [])
                    ),
                    center_node_alive=bool(payload.get("center_node_alive", True)),
                    secondary_nodes_alive=bool(payload.get("secondary_nodes_alive", True)),
                    metadata=dict(payload.get("metadata", {})),
                )
            )
    return frames


def _write_pair_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "frame_index",
        "timestamp",
        "camera_id",
        "track_id",
        "local_track_id",
        "truth_track_id",
        "projected_px",
        "bbox_center_px",
        "pixel_error",
        "mahalanobis_d2",
        "gate_pass",
        "assignment_selected",
        "id_match",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
    return path


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_report(
    path: Path,
    *,
    config: BlocksSmokeConfig,
    result: Any,
    analysis: dict[str, Any],
    pair_csv: Path,
    metrics_path: Path,
) -> Path:
    metrics = analysis["metrics"]
    first_pair = next((row for row in analysis["pairs"] if row.get("assignment_selected")), None)
    lines = [
        "# D5 ComputerVision N-v-N Geometric Registration Report",
        "",
        "## 测试目标",
        "",
        "验证 D5 在真实 AirSim ComputerVision 采集链路中，能否不依赖 `simGetDetections` 的真实 `object_id` 完成几何配准。",
        "",
        "## 场景设置",
        "",
        f"- episode_id: `{config.episode_id}`",
        f"- settings: `{config.settings_path}`",
        f"- SimMode: `ComputerVision`",
        f"- 相机节点: `{', '.join(config.camera_vehicle_names)}`",
        f"- 目标数量: `{len(config.target_actor_specs)}`",
        f"- 无人机/相机数量 N: `{config.metadata.get('drone_count')}`",
        f"- 目标初始距离: `{config.metadata.get('target_distance_m')}` m",
        f"- 目标间距: `{config.metadata.get('target_spacing_m')}` m",
        f"- 目标视觉尺度: `{config.metadata.get('target_scale_m')}` m",
        f"- 相机跟随距离: `{config.metadata.get('follow_distance_m')}` m",
        f"- 保存截图: `False`",
        "",
        "## 关键约束",
        "",
        "- 在线输入使用 `GlobalTrack`、真实相机 `K/R/t`、bbox center。",
        "- 在线关联入口使用 `geometric_local_visual_tracks_from_blocks_frame()`。",
        "- AirSim `object_id` 只在 `offline_truth_map_from_blocks_frame()` 中用于离线评分。",
        "",
        "## 结果摘要",
        "",
        f"- AirSim connected: `{result.connected}`",
        f"- frame_count: `{result.frame_count}`",
        f"- detection_count: `{metrics['detection_count']}`",
        f"- assignment_count: `{metrics['assignment_count']}`",
        f"- evaluated_count: `{metrics['evaluated_count']}`",
        f"- association_accuracy: `{metrics['association_accuracy']}`",
        f"- id_mismatch_count: `{metrics['id_mismatch_count']}`",
        f"- ambiguous_count: `{metrics['ambiguous_count']}`",
        f"- gate_pass_rate: `{metrics['gate_pass_rate']}`",
        f"- mean_pixel_error: `{metrics['mean_pixel_error']}`",
        f"- p95_pixel_error: `{metrics['p95_pixel_error']}`",
        f"- non_identity_camera_frame_count: `{metrics['non_identity_camera_frame_count']}`",
        "",
        "## 代表样本",
        "",
    ]
    if first_pair is None:
        lines.append("- 没有选中的几何关联样本。")
    else:
        lines.extend(
            [
                f"- frame_index: `{first_pair['frame_index']}`",
                f"- camera_id: `{first_pair['camera_id']}`",
                f"- track_id: `{first_pair['track_id']}`",
                f"- local_track_id: `{first_pair['local_track_id']}`",
                f"- projected_px: `{first_pair['projected_px']}`",
                f"- bbox_center_px: `{first_pair['bbox_center_px']}`",
                f"- pixel_error: `{first_pair['pixel_error']}`",
                f"- mahalanobis_d2: `{first_pair['mahalanobis_d2']}`",
                f"- id_match: `{first_pair['id_match']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            f"- metrics: `{metrics_path}`",
            f"- pair csv: `{pair_csv}`",
            f"- raw frames: `{result.output_paths['blocks_frames_jsonl']}`",
            "",
            "## 当前解释",
            "",
            "- 若 `association_accuracy` 高而 `mean_pixel_error` 可解释，说明相机内外参与 bbox 几何门控已能支撑 N-v-N 基线。",
            "- 若 `association_accuracy` 低但 detections 存在，优先检查 NED 到 OpenCV camera frame 轴向、AirSim quaternion 方向、FOV 口径和 bbox 中心偏差。",
            "- 若 detection_count 为 0，说明本轮失败在 AirSim actor 可见性或 `simGetDetections` 过滤器，不是 D5 几何算法本身。",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.mean(np.asarray(values, dtype=float)))


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), percentile))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    return value


if __name__ == "__main__":
    raise SystemExit(main())
