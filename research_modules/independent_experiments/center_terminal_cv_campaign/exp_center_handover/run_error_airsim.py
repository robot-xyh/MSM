#!/usr/bin/env python3
"""Collect one reset-separated AirSim handover replay at 20/40/60 scale."""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
for relative in (
    "research_modules",
    "research_modules/independent_experiments",
    "research_modules/d1_sensor_fusion/src",
    "research_modules/d2_data_association",
    "research_modules/d3_assignment_planner/src",
    "research_modules/d4_distributed_fallback",
    "research_modules/d5_terminal_association/src",
    "research_modules/d6_evaluation_metrics",
    "research_modules/d7_proportional_guidance",
):
    path = str(REPOSITORY_ROOT / relative)
    if path not in sys.path:
        sys.path.insert(0, path)

from airsim_runtime.blocks import BlocksProcessManager  # noqa: E402
from airsim_runtime.real_runtime import RealAirSimRuntimeClient  # noqa: E402
from center_terminal_cv_campaign.actor_controller import CampaignActorClientProxy  # noqa: E402
from center_terminal_cv_campaign.common.airsim_settings import (  # noqa: E402
    INTERCEPTOR_HORIZONTAL_FOV_DEG,
    interceptor_camera_names,
    write_campaign_settings,
)
from center_terminal_cv_campaign.common.io import write_json, write_jsonl  # noqa: E402
from center_terminal_cv_campaign.exp_center_handover.airsim_adapter import (  # noqa: E402
    AirSimDetectionAdapter,
    AirSimOfflineDetectionLabel,
)
from center_terminal_cv_campaign.exp_center_handover.association import (  # noqa: E402
    CenterHandoverAssociator,
)
from center_terminal_cv_campaign.exp_center_handover.error_campaign import (  # noqa: E402
    SearchTerminalErrorConfig,
    SearchTerminalFixture,
    build_search_terminal_fixture,
)
from center_terminal_cv_campaign.exp_center_handover.fixture import (  # noqa: E402
    HandoverFixture,
    LocalTrackTruthLabel,
)
from center_terminal_cv_campaign.exp_center_handover.geometry import (  # noqa: E402
    yaw_pitch_roll_from_matrix,
)
from center_terminal_cv_campaign.exp_center_handover.gnn import (  # noqa: E402
    SparseGNNScorer,
    load_model,
)
from center_terminal_cv_campaign.exp_center_handover.reporting import (  # noqa: E402
    write_experiment_outputs,
)
from center_terminal_cv_campaign.exp_center_handover.run_error_matrix import (  # noqa: E402
    DEFAULT_MODEL_PATH,
    association_config,
)


CAMPAIGN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = (
    CAMPAIGN_ROOT / "outputs" / "center_handover_sensor_error_airsim_20260820"
)
DEFAULT_BLOCKS_SCRIPT = Path(
    "/home/linux/Downloads/Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh"
)
TARGET_COUNTS = (20, 40, 60)
FRAME_TIMESTAMPS = (0.2, 0.3, 0.4, 0.5, 0.6)
PROFILES = (
    ("satellite_normal", "satellite", "normal"),
    ("visual_navigation_degraded", "visual_navigation", "degraded"),
)


def run_airsim_campaign(
    *,
    output_dir: Path,
    blocks_script: Path = DEFAULT_BLOCKS_SCRIPT,
    model_path: Path = DEFAULT_MODEL_PATH,
    seed: int = 20260820,
    target_counts: Sequence[int] = TARGET_COUNTS,
    api_port: int = 41451,
    connection_timeout_s: float = 150.0,
) -> Path:
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    maximum_count = max(int(value) for value in target_counts)
    settings_path = write_campaign_settings(
        output_dir / "settings.json",
        interceptor_count=maximum_count,
        api_port=api_port,
        clock_speed=0.1,
    )
    model, model_metadata = load_model(Path(model_path))
    scorer = SparseGNNScorer(model)
    process_manager = BlocksProcessManager(
        blocks_script=Path(blocks_script),
        settings_path=settings_path,
        output_dir=output_dir / "blocks_process",
        extra_args=(
            "-windowed",
            "-ResX=1280",
            "-ResY=720",
            "-NoVSync",
            "-NoHMD",
            "-NoSound",
        ),
    )
    runtime = RealAirSimRuntimeClient(
        ip="127.0.0.1",
        port=api_port,
        timeout_value=15.0,
        client_kind="vehicle",
    )
    rows: list[dict[str, Any]] = []
    launched = False
    try:
        process_manager.start()
        launched = True
        runtime.wait_for_connection(connection_timeout_s)
        for episode_index, target_count in enumerate(target_counts, start=1):
            _prepare_episode_runtime(
                runtime,
                reset_before_episode=episode_index > 1,
                connection_timeout_s=connection_timeout_s,
            )
            fov_path = _apply_and_audit_fov(
                runtime,
                camera_count=maximum_count,
                output_path=output_dir
                / "blocks_process"
                / f"episode_{episode_index:02d}_n{target_count}_fov_audit.json",
            )
            episode_rows = _run_episode(
                runtime=runtime,
                output_dir=output_dir / f"n{target_count}_seed{seed}",
                target_count=int(target_count),
                seed=seed,
                scorer=scorer,
                model_metadata=model_metadata,
            )
            for row in episode_rows:
                row["fov_audit"] = str(fov_path.relative_to(output_dir))
            rows.extend(episode_rows)
    finally:
        process_manager.write_diagnostics()
        if launched:
            process_manager.stop()
    _write_csv(output_dir / "summary_metrics.csv", rows)
    write_json(
        output_dir / "summary.json",
        {
            "schema_version": "center-terminal-sensor-error-airsim-v1",
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": "AirSim ComputerVision",
            "target_counts": list(target_counts),
            "resource_counts": list(target_counts),
            "seed": seed,
            "frame_timestamps_s": list(FRAME_TIMESTAMPS),
            "screenshots_saved": False,
            "truth_policy": "actor names only in truth files and offline scoring",
            "results": rows,
        },
    )
    report_path = output_dir / "AIRSIM_REPRESENTATIVE_REPORT_CN.md"
    report_path.write_text(_build_report(rows), encoding="utf-8")
    print(f"report={report_path.resolve()}", flush=True)
    return report_path


def _prepare_episode_runtime(
    runtime: Any,
    *,
    reset_before_episode: bool,
    connection_timeout_s: float,
) -> None:
    """Reset only between episodes, never immediately after Blocks startup."""

    if not reset_before_episode:
        return
    runtime.reset()
    runtime.wait_for_connection(connection_timeout_s)


def _run_episode(
    *,
    runtime: RealAirSimRuntimeClient,
    output_dir: Path,
    target_count: int,
    seed: int,
    scorer: SparseGNNScorer,
    model_metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    collection_bundle = build_search_terminal_fixture(
        SearchTerminalErrorConfig(
            target_count=target_count,
            seed=seed,
            navigation_mode="satellite",
            attitude_mode="normal",
            detection_mode="ideal",
            handover_mode="anonymous",
        )
    )
    proxy = CampaignActorClientProxy(
        runtime.client,
        runtime.airsim,
        collection_bundle.handover_fixture.target_truth,
    )
    try:
        proxy.setup_targets()
        camera_ids = tuple(sorted(collection_bundle.true_camera_models))
        _pose_cameras(proxy, runtime.airsim, collection_bundle.true_camera_models)
        _configure_detection_filters(proxy, runtime.airsim, camera_ids)
        adapter = AirSimDetectionAdapter(collection_bundle.true_camera_models)
        frames, labels, all_tracks = _collect_locked_frames(
            proxy,
            adapter,
            camera_ids=camera_ids,
        )
        write_jsonl(output_dir / "online" / "all_detected_local_tracks.jsonl", all_tracks)
        write_jsonl(output_dir / "online" / "locked_local_tracks.jsonl", _flatten(frames))
        write_jsonl(output_dir / "truth" / "airsim_detection_labels.jsonl", labels)
        write_json(output_dir / "truth" / "actor_audit.json", proxy.actor_audit())
        write_jsonl(output_dir / "truth" / "actor_motion.jsonl", proxy.motion_rows)

        result_rows: list[dict[str, Any]] = []
        for profile_name, navigation_mode, attitude_mode in PROFILES:
            profile_bundle = build_search_terminal_fixture(
                SearchTerminalErrorConfig(
                    target_count=target_count,
                    seed=seed,
                    navigation_mode=navigation_mode,
                    attitude_mode=attitude_mode,
                    detection_mode="ideal",
                    handover_mode="anonymous",
                )
            )
            replay_fixture = _build_replay_fixture(profile_bundle, frames, labels)
            write_jsonl(
                output_dir / profile_name / "truth" / "camera_error_truth.jsonl",
                profile_bundle.camera_error_truth,
            )
            for backend in ("geometry", "gnn"):
                started = time.perf_counter()
                associator = CenterHandoverAssociator(
                    replay_fixture.camera_models,
                    config=association_config(),
                    candidate_scorer=scorer if backend == "gnn" else None,
                )
                frame_results = tuple(
                    associator.process_frame(replay_fixture.source_cues, frame)
                    for frame in replay_fixture.frames
                )
                run_dir = output_dir / profile_name / backend
                metrics, _ = write_experiment_outputs(
                    output_dir=run_dir,
                    fixture=replay_fixture,
                    frames=replay_fixture.frames,
                    results=frame_results,
                    mode="airsim",
                    backend=backend,
                    model_metadata=model_metadata if backend == "gnn" else None,
                )
                result_rows.append(
                    {
                        "target_count": target_count,
                        "resource_count": target_count,
                        "seed": seed,
                        "profile": profile_name,
                        "backend": backend,
                        "binding_precision": metrics.get("binding_precision"),
                        "binding_recall": metrics.get("binding_recall"),
                        "true_binding_count": metrics.get("true_binding_count"),
                        "false_binding_count": metrics.get("false_binding_count"),
                        "locked_track_count": len(replay_fixture.local_truth),
                        "final_frame_local_track_count": metrics.get(
                            "final_frame_local_track_count"
                        ),
                        "runtime_s": time.perf_counter() - started,
                        "gnn_scale_status": (
                            "unseen_scale"
                            if backend == "gnn" and target_count == 60
                            else "trained_scale"
                            if backend == "gnn"
                            else "not_applicable"
                        ),
                    }
                )
        return result_rows
    finally:
        proxy.teardown_targets()


def _collect_locked_frames(
    proxy: CampaignActorClientProxy,
    adapter: AirSimDetectionAdapter,
    *,
    camera_ids: Sequence[str],
) -> tuple[
    tuple[tuple[Any, ...], ...],
    tuple[AirSimOfflineDetectionLabel, ...],
    tuple[Any, ...],
]:
    locks: dict[str, str] = {}
    frames: list[tuple[Any, ...]] = []
    selected_labels: list[AirSimOfflineDetectionLabel] = []
    all_tracks: list[Any] = []
    for frame_index, timestamp in enumerate(FRAME_TIMESTAMPS):
        proxy.set_logical_time(timestamp)
        if frame_index == 0:
            time.sleep(0.25)
        batch = adapter.collect_frame(
            proxy,
            measurement_timestamp=timestamp,
            arrival_timestamp=timestamp + 0.02,
            camera_ids=camera_ids,
        )
        all_tracks.extend(batch.local_tracks)
        label_lookup = {
            (label.camera_id, label.local_track_id): label
            for label in batch.offline_labels
        }
        selected: list[Any] = []
        for camera_id in camera_ids:
            candidates = [
                track
                for track in batch.local_tracks
                if track.camera_id == camera_id and track.recognized
            ]
            if not candidates:
                continue
            locked_id = locks.get(camera_id)
            chosen = next(
                (track for track in candidates if track.local_track_id == locked_id),
                None,
            )
            if chosen is None:
                chosen = min(
                    candidates,
                    key=lambda track: (
                        (track.center_px[0] - 960.0) ** 2
                        + (track.center_px[1] - 540.0) ** 2,
                        track.local_track_id,
                    ),
                )
                locks[camera_id] = chosen.local_track_id
            selected.append(chosen)
            label = label_lookup.get((chosen.camera_id, chosen.local_track_id))
            if label is not None:
                selected_labels.append(label)
        frames.append(tuple(sorted(selected, key=lambda track: track.camera_id)))
    return tuple(frames), tuple(selected_labels), tuple(all_tracks)


def _build_replay_fixture(
    bundle: SearchTerminalFixture,
    raw_frames: Sequence[Sequence[Any]],
    labels: Sequence[AirSimOfflineDetectionLabel],
) -> HandoverFixture:
    reported_models = bundle.handover_fixture.camera_models
    converted_frames: list[tuple[Any, ...]] = []
    for frame in raw_frames:
        converted: list[Any] = []
        for local in frame:
            camera = reported_models[local.camera_id]
            metadata = {
                **dict(local.metadata),
                "detection_source": "simGetDetections_locked_after_search",
                "reported_camera_pose": {
                    "body_position_ned_m": camera.body_position_ned_m,
                    "body_yaw_pitch_roll_deg": camera.body_yaw_pitch_roll_deg,
                    "gimbal_yaw_pitch_roll_deg": camera.gimbal_yaw_pitch_roll_deg,
                },
                "projection_uncertainty": next(
                    track.metadata["projection_uncertainty"]
                    for track in bundle.handover_fixture.frames[0]
                    if track.camera_id == local.camera_id
                ),
                "search_status": "target_already_found",
            }
            converted.append(
                replace(
                    local,
                    ray_origin_ned_m=tuple(
                        float(value) for value in camera.camera_position_ned_m
                    ),
                    ray_direction_ned=tuple(
                        float(value)
                        for value in camera.pixel_to_world_ray(local.center_px)
                    ),
                    camera_yaw_pitch_roll_deg=yaw_pitch_roll_from_matrix(
                        camera.rotation_ned_from_camera
                    ),
                    metadata=metadata,
                )
            )
        converted_frames.append(tuple(converted))
    actor_to_truth = {
        target.actor_name: target.truth_target_id
        for target in bundle.handover_fixture.target_truth
    }
    truth_sets: dict[tuple[str, str], set[str]] = {}
    for label in labels:
        truth_id = _actor_to_truth_id(label.raw_detection_name, actor_to_truth)
        if truth_id is None:
            continue
        key = (label.camera_id, label.local_track_id)
        truth_sets.setdefault(key, set()).add(truth_id)
    local_truth = {
        key: LocalTrackTruthLabel(
            camera_id=key[0],
            local_track_id=key[1],
            truth_target_id=next(iter(truth_ids)),
        )
        for key, truth_ids in truth_sets.items()
        if len(truth_ids) == 1
    }
    return replace(
        bundle.handover_fixture,
        frames=tuple(converted_frames),
        local_truth=tuple(local_truth[key] for key in sorted(local_truth)),
    )


def _pose_cameras(
    client: Any,
    airsim_module: Any,
    camera_models: Mapping[str, Any],
) -> None:
    for camera_id, model in camera_models.items():
        yaw, pitch, roll = model.body_yaw_pitch_roll_deg
        pose = airsim_module.Pose(
            airsim_module.Vector3r(*model.body_position_ned_m),
            airsim_module.to_quaternion(
                math.radians(pitch),
                math.radians(roll),
                math.radians(yaw),
            ),
        )
        result = client.simSetVehiclePose(
            pose,
            ignore_collision=True,
            vehicle_name=camera_id,
        )
        if result is False:
            raise RuntimeError(f"AirSim failed to pose camera {camera_id}")


def _configure_detection_filters(
    client: Any,
    airsim_module: Any,
    camera_ids: Sequence[str],
) -> None:
    for camera_id in camera_ids:
        client.simClearDetectionMeshNames(
            "0",
            airsim_module.ImageType.Scene,
            vehicle_name=camera_id,
        )
        client.simSetDetectionFilterRadius(
            "0",
            airsim_module.ImageType.Scene,
            10_000_000.0,
            vehicle_name=camera_id,
        )
        for pattern in ("MSM_TargetActor_*", "MSM_TargetActor*"):
            client.simAddDetectionFilterMeshName(
                "0",
                airsim_module.ImageType.Scene,
                pattern,
                vehicle_name=camera_id,
            )


def _apply_and_audit_fov(
    runtime: RealAirSimRuntimeClient,
    *,
    camera_count: int,
    output_path: Path,
) -> Path:
    rows: list[dict[str, Any]] = []
    for camera_id in interceptor_camera_names(camera_count):
        command = runtime.set_cv_camera_fov(
            vehicle_name=camera_id,
            camera_name="0",
            horizontal_fov_deg=INTERCEPTOR_HORIZONTAL_FOV_DEG,
        )
        info = runtime.client.simGetCameraInfo("0", vehicle_name=camera_id)
        reported = float(info.fov)
        rows.append(
            {
                **command,
                "reported_fov_deg": reported,
                "verified": abs(reported - INTERCEPTOR_HORIZONTAL_FOV_DEG) <= 0.1,
            }
        )
    payload = {
        "schema_version": "center-terminal-error-camera-fov-audit-v1",
        "all_verified": all(row["verified"] and row.get("ok", True) for row in rows),
        "rows": rows,
    }
    write_json(output_path, payload)
    if not payload["all_verified"]:
        raise RuntimeError("AirSim camera FOV verification failed")
    return output_path


def _actor_to_truth_id(raw_name: str, actor_to_truth: Mapping[str, str]) -> str | None:
    matches = [
        name
        for name in actor_to_truth
        if raw_name == name or raw_name.startswith(f"{name}_")
    ]
    if not matches:
        return None
    return actor_to_truth[max(matches, key=len)]


def _flatten(frames: Sequence[Sequence[Any]]) -> tuple[Any, ...]:
    return tuple(track for frame in frames for track in frame)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ()
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _build_report(rows: Sequence[Mapping[str, Any]]) -> str:
    target_counts = tuple(sorted({int(row["target_count"]) for row in rows}))
    scale_text = "、".join(str(value) for value in target_counts)
    lifecycle_text = (
        f"本轮使用一个AirSim Blocks进程完成{scale_text}目标试验。"
        if len(target_counts) == 1
        else f"本轮使用一个AirSim Blocks进程，按{scale_text}目标依次复位运行。"
    )
    lines = [
        "| 规模 | 误差档 | 方法 | 准确度 | 覆盖度 | 正确绑定 | 错误绑定 |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        precision = row["binding_precision"]
        recall = row["binding_recall"]
        lines.append(
            "| {target_count} | {profile} | {backend} | {precision} | {recall} | "
            "{true_binding_count} | {false_binding_count} |".format(
                **row,
                precision="待补" if precision is None else f"{float(precision):.1%}",
                recall="待补" if recall is None else f"{float(recall):.1%}",
            )
        )
    table = "\n".join(lines)
    return f"""# AirSim中心航迹与拦截无人机配准代表性试验

## 试验说明

{lifecycle_text}目标为3米静态网格无人机模型，按50米/秒更新位置；每个目标配置一台ComputerVision相机，相机位于约700米处，分辨率1920×1080、水平视场19度。相机只保存 `simGetDetections` 检测框和相机位姿，不保存PNG图像。

协同搜索视为已经完成。每台相机在第一帧选择最靠近画面中心且达到10像素的目标，后续优先保持同一本地航迹编号。Actor名称只写入离线评分文件，不进入候选筛选、代价计算和一一匹配。

## 结果

{table}

本轮AirSim数据用于确认真实检测接口、相机视场、目标网格和多相机读取链路能够进入同一配准算法。导航、姿态和云台误差仍由离线回放按95%包络注入，因此该结果是接口代表组，不替代10种子的960组离线统计。
"""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--blocks-script", type=Path, default=DEFAULT_BLOCKS_SCRIPT)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--target-counts", type=int, nargs="+", default=TARGET_COUNTS)
    parser.add_argument("--api-port", type=int, default=41451)
    parser.add_argument("--connection-timeout-s", type=float, default=150.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run_airsim_campaign(
        output_dir=args.output_dir,
        blocks_script=args.blocks_script,
        model_path=args.model_path,
        seed=args.seed,
        target_counts=tuple(args.target_counts),
        api_port=args.api_port,
        connection_timeout_s=args.connection_timeout_s,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
