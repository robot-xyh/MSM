#!/usr/bin/env python3
"""Run the isolated D5 N-primary plus recon ComputerVision campaign."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

import cv2
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
    module_path = str(ROOT / rel)
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

from airsim_dryrun.models import (  # noqa: E402
    AirSimCameraInfo,
    AirSimDetectionBox,
    AirSimFrame,
    AirSimResourceState,
    AirSimTruthObject,
)
from airsim_runtime.adapters import geometric_local_visual_tracks_from_blocks_frame  # noqa: E402
from airsim_runtime.blocks import BlocksProcessManager  # noqa: E402
from airsim_runtime.models import (  # noqa: E402
    BlocksActorTargetSpec,
    BlocksSmokeConfig,
    default_actor_target_specs,
    default_cv_camera_vehicle_names,
    default_cv_secondary_vehicle_names,
    write_dynamic_computer_vision_settings,
)
from airsim_runtime.orchestrator import AirSimBlocksSmokeOrchestrator  # noqa: E402
from airsim_runtime.real_runtime import RealAirSimRuntimeClient  # noqa: E402
from d5_terminal_association import (  # noqa: E402
    AssociationConfig,
    CameraLocalTrackBatch,
    GlobalTrack,
    RegistrationStabilityConfig,
    camera_model_from_airsim_camera_info,
    register_local_visual_tracks_to_global_tracks,
)


DEFAULT_OUTPUT_ROOT = "research_modules/airsim_runtime/outputs"
DEFAULT_BLOCKS_SCRIPT = "Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh"
DEFAULT_DRONE_COUNT = 5
DEFAULT_RECON_COUNT = 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default="d5_cv_5v5_multicamera_branch")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--blocks-script", default=DEFAULT_BLOCKS_SCRIPT)
    parser.add_argument("--duration", type=float, default=12.0)
    parser.add_argument("--dt", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--drone-count", type=int, default=DEFAULT_DRONE_COUNT)
    parser.add_argument("--recon-count", type=int, default=DEFAULT_RECON_COUNT)
    parser.add_argument("--snapshot-interval", type=float, default=0.5)
    parser.add_argument("--target-distance", type=float, default=30.0)
    parser.add_argument("--target-spacing", type=float, default=8.0)
    parser.add_argument("--target-scale", type=float, default=2.0)
    parser.add_argument("--target-speed-scale", type=float, default=5.0)
    parser.add_argument("--flight-altitude", type=float, default=50.0)
    parser.add_argument("--primary-fov", type=float, default=60.0)
    parser.add_argument("--recon-fov", type=float, default=75.0)
    parser.add_argument("--recon-height", type=float, default=50.0)
    parser.add_argument("--gate-chi2", type=float, default=16.0)
    parser.add_argument("--measurement-sigma-px", type=float, default=12.0)
    parser.add_argument("--yolo-confidence", type=float, default=0.10)
    parser.add_argument(
        "--yolo-weights",
        default="research_modules/d5_terminal_association/best.pt",
    )
    parser.add_argument("--connection-timeout", type=float, default=90.0)
    parser.add_argument("--client-timeout", type=float, default=5.0)
    parser.add_argument(
        "--primary-backend",
        choices=("all", "detect", "yolo"),
        default="all",
        help="Run both comparison episodes or only the selected primary-camera backend.",
    )
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument(
        "--replay-existing",
        action="store_true",
        help="Recompute D5 metrics and reports from existing blocks_frames.jsonl files.",
    )
    parser.add_argument("--no-nvidia-offload", action="store_true")
    parser.add_argument("--blocks-arg", action="append", default=None)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    _validate_args(args)
    campaign_dir = Path(args.output_root) / args.campaign_id
    primary_names = default_cv_camera_vehicle_names(
        args.drone_count,
        prefix="D5_Primary_",
    )
    recon_names = default_cv_secondary_vehicle_names(
        args.recon_count,
        prefix="D5_Recon_",
    )
    settings_path = write_dynamic_computer_vision_settings(
        campaign_dir
        / "generated_settings"
        / f"d5_cv_{args.drone_count}plus{args.recon_count}_settings.json",
        camera_vehicle_names=primary_names,
        secondary_vehicle_names=recon_names,
        camera_spacing_m=args.target_spacing,
        camera_z=-args.flight_altitude,
        secondary_height_above_targets_m=args.recon_height,
        target_z=-args.flight_altitude,
        fov_degrees=args.primary_fov,
        secondary_fov_degrees=args.recon_fov,
        secondary_camera_pitch_deg=0.0,
        secondary_x_m=args.target_distance,
        width=1920,
        height=1080,
        secondary_width=3840,
        secondary_height=2160,
    )
    target_specs = _branch_target_specs(args)
    snapshot_interval_frames = _snapshot_interval_frames(
        args.snapshot_interval,
        args.dt,
    )
    target_velocity_rows = [
        {
            "object_id": spec.object_id,
            "velocity_ned_mps": list(spec.velocity_ned),
            "speed_mps": _speed_mps(spec.velocity_ned),
        }
        for spec in target_specs
    ]
    base_config = BlocksSmokeConfig(
        scenario_name="d5_cv_multicamera_branch",
        duration_s=args.duration,
        dt_s=args.dt,
        seed=args.seed,
        output_root=campaign_dir,
        blocks_script=Path(args.blocks_script),
        settings_path=settings_path,
        blocks_args=(
            tuple(args.blocks_arg)
            if args.blocks_arg is not None
            else ("-windowed", "-ResX=1280", "-ResY=720", "-NoVSync", "-NoHMD", "-NoSound")
        ),
        prefer_nvidia_offload=not args.no_nvidia_offload,
        launch_blocks=False,
        connection_timeout_s=args.connection_timeout,
        client_timeout_s=args.client_timeout,
        client_kind="vehicle",
        camera_vehicle_name=primary_names[0],
        camera_vehicle_names=primary_names,
        secondary_camera_vehicle_names=recon_names,
        camera_name="0",
        save_images=True,
        image_save_interval_frames=snapshot_interval_frames,
        capture_lidar=False,
        cv_camera_follow_assignments=True,
        cv_camera_follow_distance_m=args.target_distance,
        cv_secondary_look_at_enabled=True,
        cv_secondary_mobile_recon_enabled=False,
        target_vehicle_names=(),
        resource_vehicle_names=primary_names,
        target_actor_specs=target_specs,
        detection_filter_names=("MSM_TargetActor_*",),
        detection_radius_cm=120 * 100,
        secondary_detection_radius_cm=150 * 100,
        detection_warmup_frames=2,
        yolo_weights_path=Path(args.yolo_weights),
        yolo_tracker_backend="bytetrack",
        yolo_confidence_threshold=args.yolo_confidence,
        yolo_use_native_tracker=True,
        yolo_allow_iou_fallback=False,
        yolo_compute_device="auto",
        yolo_primary_inference_imgsz=960,
        yolo_secondary_inference_imgsz=1280,
        yolo_offline_truth_evaluation=True,
        include_integrated_pipeline=False,
        metadata={
            "runtime_mode": (
                f"d5_cv_{args.drone_count}v{args.drone_count}_multicamera_branch"
            ),
            "branch_experiment": True,
            "primary_camera_count": args.drone_count,
            "secondary_camera_count": args.recon_count,
            "target_count": args.drone_count,
            "online_truth_identity_allowed": False,
            "offline_truth_for_scoring_only": True,
            "snapshot_interval_s": args.snapshot_interval,
            "effective_snapshot_interval_s": snapshot_interval_frames * args.dt,
            "target_speed_scale": args.target_speed_scale,
            "target_velocities": target_velocity_rows,
            "primary_camera_resolution": [1920, 1080],
            "secondary_camera_resolution": [3840, 2160],
            "primary_camera_fov_degrees": args.primary_fov,
            "secondary_camera_fov_degrees": args.recon_fov,
            "target_distance_m": args.target_distance,
            "target_spacing_m": args.target_spacing,
            "target_scale": args.target_scale,
            "flight_altitude_m": args.flight_altitude,
        },
    )
    episode_configs = _episode_configs(
        base_config,
        campaign_id=args.campaign_id,
        primary_backend=args.primary_backend,
    )

    if args.replay_existing:
        frame_paths = tuple(
            config.output_dir / "blocks_frames.jsonl"
            for config in episode_configs
        )
        missing = [path for path in frame_paths if not path.is_file()]
        if missing:
            raise SystemExit(
                "--replay-existing requires captured frame logs: "
                + ", ".join(str(path) for path in missing)
            )
    else:
        results = _run_episodes_once(
            episode_configs,
            campaign_dir=campaign_dir,
            launch_blocks=not args.no_launch,
        )
        frame_paths = tuple(
            Path(result.output_paths["blocks_frames_jsonl"])
            for result in results
        )
    analyses = []
    for config, frame_path in zip(episode_configs, frame_paths, strict=True):
        frames = _load_frames(frame_path)
        analysis = analyze_episode(
            frames,
            output_dir=config.output_dir,
            primary_vehicle_names=primary_names,
            recon_vehicle_names=recon_names,
            seed=args.seed,
            gate_chi2=args.gate_chi2,
            measurement_sigma_px=args.measurement_sigma_px,
        )
        analyses.append(analysis)

    comparison_plot = _write_comparison_plot(campaign_dir / "d5_backend_comparison.png", analyses)
    comparison_json = _write_json(
        campaign_dir / "d5_multicamera_comparison.json",
        {
            "campaign_id": args.campaign_id,
            "settings_path": str(settings_path),
            "episodes": [analysis["metrics"] for analysis in analyses],
        },
    )
    report = _write_campaign_report(
        campaign_dir
        / (
            f"D5_CV_{args.drone_count}V{args.drone_count}_"
            "MULTICAMERA_BRANCH_REPORT_CN.md"
        ),
        args=args,
        configs=episode_configs,
        analyses=analyses,
        comparison_plot=comparison_plot,
        comparison_json=comparison_json,
    )
    print(f"campaign_id={args.campaign_id}")
    for analysis in analyses:
        metrics = analysis["metrics"]
        print(
            "episode={episode} backend={backend} detections={detections} "
            "association_accuracy={accuracy} recon_full_view_rate={recon_rate}".format(
                episode=metrics["episode_id"],
                backend=metrics["primary_detection_backend"],
                detections=metrics["online_detection_count"],
                accuracy=metrics["offline_association_accuracy"],
                recon_rate=metrics["recon_full_view_frame_rate"],
            )
        )
    print(f"report={report.resolve()}")
    print(f"output_dir={campaign_dir.resolve()}")
    return 0


def _validate_args(args: argparse.Namespace) -> None:
    if args.duration <= 0.0 or args.dt <= 0.0:
        raise SystemExit("--duration and --dt must be positive")
    if args.drone_count <= 0 or args.recon_count <= 0:
        raise SystemExit("--drone-count and --recon-count must be positive")
    if args.snapshot_interval <= 0.0:
        raise SystemExit("--snapshot-interval must be positive")
    if args.target_speed_scale <= 0.0:
        raise SystemExit("--target-speed-scale must be positive")
    if args.target_distance <= 0.0 or args.target_spacing <= 0.0:
        raise SystemExit("target geometry values must be positive")
    if args.flight_altitude <= 0.0:
        raise SystemExit("--flight-altitude must be positive")


def _branch_target_specs(
    args: argparse.Namespace,
) -> tuple[BlocksActorTargetSpec, ...]:
    return default_actor_target_specs(
        count=args.drone_count,
        target_z=-args.flight_altitude,
        target_distance_m=args.target_distance,
        target_spacing_m=args.target_spacing,
        asset_name="Quadrotor1",
        target_scale_m=args.target_scale,
        target_speed_scale=args.target_speed_scale,
        x_spacing_m=0.0,
        x_speed_base_mps=0.6,
        x_speed_step_mps=0.05,
        y_speed_span_mps=0.5,
    )


def _snapshot_interval_frames(snapshot_interval_s: float, dt_s: float) -> int:
    return max(1, int(round(float(snapshot_interval_s) / float(dt_s))))


def _episode_configs(
    base_config: BlocksSmokeConfig,
    *,
    campaign_id: str,
    primary_backend: str,
) -> tuple[BlocksSmokeConfig, ...]:
    configs = {
        "detect": replace(
            base_config,
            episode_id=f"{campaign_id}_detect",
            detection_backend="airsim",
            secondary_detection_backend="airsim",
            metadata={
                **base_config.metadata,
                "comparison_role": "baseline",
                "primary_detection_backend": "airsim_detect",
                "secondary_detection_backend": "airsim_detect",
            },
        ),
        "yolo": replace(
            base_config,
            episode_id=f"{campaign_id}_yolo_bytetrack",
            detection_backend="yolo",
            secondary_detection_backend="airsim",
            metadata={
                **base_config.metadata,
                "comparison_role": "candidate",
                "primary_detection_backend": "yolov8_bytetrack",
                "secondary_detection_backend": "airsim_detect",
            },
        ),
    }
    if primary_backend == "all":
        return (configs["detect"], configs["yolo"])
    return (configs[primary_backend],)


def _speed_mps(velocity_ned: Iterable[float]) -> float:
    return math.sqrt(sum(float(component) ** 2 for component in velocity_ned))


def _run_episodes_once(
    configs: tuple[BlocksSmokeConfig, ...],
    *,
    campaign_dir: Path,
    launch_blocks: bool,
) -> tuple[Any, ...]:
    process_manager = BlocksProcessManager(
        blocks_script=configs[0].blocks_script,
        settings_path=configs[0].settings_path,
        output_dir=campaign_dir / "blocks_process",
        extra_args=configs[0].blocks_args,
        prefer_nvidia_offload=configs[0].prefer_nvidia_offload,
    )
    runtime = RealAirSimRuntimeClient(
        ip=configs[0].api_server_host(),
        port=configs[0].api_server_port(),
        timeout_value=configs[0].client_timeout_s,
        client_kind=configs[0].client_kind,
    )
    if launch_blocks:
        process_manager.start()
    orchestrator = AirSimBlocksSmokeOrchestrator(
        runtime=runtime,
        process_manager=process_manager,
    )
    results = []
    try:
        for config in configs:
            results.append(orchestrator.run(replace(config, launch_blocks=False)))
    finally:
        if launch_blocks:
            process_manager.stop()
    return tuple(results)


def analyze_episode(
    frames: list[AirSimFrame],
    *,
    output_dir: Path,
    primary_vehicle_names: tuple[str, ...],
    recon_vehicle_names: tuple[str, ...],
    seed: int,
    gate_chi2: float,
    measurement_sigma_px: float,
) -> dict[str, Any]:
    if not frames:
        raise ValueError("D5 multicamera analysis requires captured frames")
    truth_to_global = _truth_to_global_map(frames[0])
    target_count = len(truth_to_global)
    if target_count <= 0:
        raise ValueError("D5 multicamera analysis requires target truth fixtures")
    global_tracks = _terminal_tracks_at_last_frame(
        frames[-1],
        truth_to_global=truth_to_global,
        seed=seed,
    )
    batches: list[CameraLocalTrackBatch] = []
    truth_by_observation: dict[tuple[str, str], str] = {}
    frame_rows: list[dict[str, Any]] = []
    visibility_by_frame_camera: dict[tuple[int, str], set[str]] = {}
    online_ids_by_truth: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    latency_values: list[float] = []

    for frame in frames:
        cameras_by_id = {camera.camera_id: camera for camera in frame.cameras}
        detections_by_camera = _detections_by_camera(frame.visual_detections)
        offline_truth_by_camera = _offline_truth_by_camera(frame, truth_to_global)
        for detection_meta in frame.metadata.get("detections", []):
            latency = detection_meta.get("processing_latency_ms")
            if latency is not None and math.isfinite(float(latency)):
                latency_values.append(float(latency))
        for camera_id, camera_info in cameras_by_id.items():
            camera_detections = tuple(detections_by_camera.get(camera_id, ()))
            camera_frame = replace(frame, visual_detections=camera_detections)
            local_tracks = geometric_local_visual_tracks_from_blocks_frame(camera_frame)
            frame_id = _registration_frame_id(frame, camera_id)
            resource_id = _resource_id(camera_info.owner_id, primary_vehicle_names, recon_vehicle_names)
            camera = camera_model_from_airsim_camera_info(
                camera_info,
                measurement_sigma_px=measurement_sigma_px,
            )
            batches.append(
                CameraLocalTrackBatch(
                    resource_id=resource_id,
                    camera_id=camera_id,
                    camera=camera,
                    local_tracks=tuple(local_tracks),
                    frame_id=frame_id,
                    timestamp=frame.timestamp,
                    arrival_timestamp=frame.timestamp,
                    source_node_id=camera_info.owner_id,
                    link_type="d5_multicamera_branch",
                    metadata={
                        "camera_pose_source": "airsim_camera_pose",
                        "detector_backend": _detector_backend_for_camera(frame, camera_info.owner_id),
                        "offline_truth_identity_available_to_online": False,
                    },
                )
            )
            truth_records = offline_truth_by_camera.get(camera_id, ())
            visibility = {record["global_track_id"] for record in truth_records}
            visibility_by_frame_camera[(frame.frame_index, camera_id)] = visibility
            matches = _match_local_tracks_to_offline_truth(local_tracks, truth_records)
            for local_track_id, global_track_id in matches.items():
                truth_by_observation[(frame_id, local_track_id)] = global_track_id
                online_ids_by_truth[(camera_id, global_track_id)].append(
                    (frame.frame_index, local_track_id)
                )
            frame_rows.append(
                {
                    "frame_index": frame.frame_index,
                    "timestamp": frame.timestamp,
                    "camera_id": camera_id,
                    "camera_owner": camera_info.owner_id,
                    "camera_role": "recon" if camera_info.owner_id in recon_vehicle_names else "primary",
                    "detector_backend": _detector_backend_for_camera(frame, camera_info.owner_id),
                    "online_detection_count": len(local_tracks),
                    "offline_visible_target_count": len(visibility),
                    "offline_matched_detection_count": len(matches),
                }
            )

    registration = register_local_visual_tracks_to_global_tracks(
        global_tracks=global_tracks,
        camera_batches=batches,
        bindings=None,
        # Each camera batch has its own measurement time. Overriding this with
        # the final frame time shifts every earlier projection in a moving scene.
        current_time=None,
        config=AssociationConfig(gate_chi2=gate_chi2, min_lock_margin=1.0),
        max_binding_age_s=None,
        network_union_complete=None,
        stability_config=RegistrationStabilityConfig(window_frames=3, required_gate_passes=2),
    )
    candidate_rows, selected_by_observation = _candidate_rows(
        registration.candidates,
        truth_by_observation,
    )
    selected_rows = [row for row in candidate_rows if row["selected"]]
    evaluated_rows = [row for row in selected_rows if row["truth_global_track_id"] is not None]
    correct_count = sum(row["id_match"] is True for row in evaluated_rows)
    stable_selected = [row for row in selected_rows if row["stable_cross_view_support"]]
    primary_camera_ids = {
        camera.camera_id
        for camera in frames[0].cameras
        if camera.owner_id in primary_vehicle_names
    }
    recon_camera_ids = {
        camera.camera_id
        for camera in frames[0].cameras
        if camera.owner_id in recon_vehicle_names
    }
    diagnostics = _association_diagnostics(
        selected_rows,
        primary_camera_ids=primary_camera_ids,
        recon_camera_ids=recon_camera_ids,
    )
    primary_union_rates = []
    recon_full_flags = []
    for frame in frames:
        primary_union: set[str] = set()
        for camera_id in primary_camera_ids:
            primary_union.update(visibility_by_frame_camera.get((frame.frame_index, camera_id), set()))
        primary_union_rates.append(len(primary_union) / target_count)
        recon_union: set[str] = set()
        for camera_id in recon_camera_ids:
            recon_union.update(visibility_by_frame_camera.get((frame.frame_index, camera_id), set()))
        recon_full_flags.append(len(recon_union) == target_count)

    id_switch_count = _local_id_switch_count(online_ids_by_truth)
    truth_box_count = sum(row["offline_visible_target_count"] for row in frame_rows)
    matched_detection_count = sum(row["offline_matched_detection_count"] for row in frame_rows)
    input_global_ids = {track.global_track_id for track in global_tracks}
    global_id_rewrite_count = sum(
        1
        for candidate in registration.candidates
        if candidate.global_track_id is not None
        and candidate.global_track_id not in input_global_ids
    )
    primary_backend = _primary_backend(frames[0], primary_vehicle_names)
    actor_motion = _actor_motion_metrics(frames)
    metrics = {
        "episode_id": frames[0].episode_id,
        "target_count": target_count,
        "primary_detection_backend": primary_backend,
        "secondary_detection_backend": _primary_backend(frames[0], recon_vehicle_names),
        "frame_count": len(frames),
        "camera_count": len(frames[0].cameras),
        "primary_camera_count": len(primary_camera_ids),
        "recon_camera_count": len(recon_camera_ids),
        "online_detection_count": sum(row["online_detection_count"] for row in frame_rows),
        "offline_truth_box_count": truth_box_count,
        "offline_matched_detection_count": matched_detection_count,
        "offline_detector_recall": matched_detection_count / truth_box_count if truth_box_count else None,
        "registration_candidate_count": len(registration.candidates),
        "selected_registration_count": len(selected_rows),
        "stable_selected_registration_count": len(stable_selected),
        "stable_registration_rate": len(stable_selected) / len(selected_rows) if selected_rows else None,
        "offline_evaluated_registration_count": len(evaluated_rows),
        "offline_association_accuracy": correct_count / len(evaluated_rows) if evaluated_rows else None,
        "strict_association_accuracy": (
            correct_count / len(selected_rows) if selected_rows else None
        ),
        "selected_registration_without_truth_count": diagnostics[
            "selected_registration_without_truth_count"
        ],
        "primary_offline_association_accuracy": diagnostics[
            "primary_offline_association_accuracy"
        ],
        "first_half_association_accuracy": diagnostics[
            "first_half_association_accuracy"
        ],
        "second_half_association_accuracy": diagnostics[
            "second_half_association_accuracy"
        ],
        "per_camera_association": diagnostics["per_camera_association"],
        "mismatch_pair_counts": diagnostics["mismatch_pair_counts"],
        "association_time_policy": "per_camera_batch_measurement_timestamp",
        "local_id_switch_count": id_switch_count,
        "primary_union_coverage_rate_mean": _mean(primary_union_rates),
        "primary_union_full_view_frame_rate": _mean(
            [rate >= 1.0 for rate in primary_union_rates]
        ),
        "recon_full_view_frame_rate": _mean(recon_full_flags),
        "cross_view_association_count": len(registration.cross_view_associations),
        "stable_cross_view_association_count": len(registration.stable_cross_view_associations),
        "rejection_reason_counts": dict(registration.rejection_reason_counts),
        "yolo_latency_p50_ms": _percentile(latency_values, 50),
        "yolo_latency_p95_ms": _percentile(latency_values, 95),
        "global_track_id_rewrite_count": global_id_rewrite_count,
        "online_truth_identity_use_count": 0,
        "online_truth_identity_used": False,
        "offline_truth_for_scoring_only": True,
        **actor_motion,
    }
    frame_csv = _write_csv(output_dir / "d5_multicamera_frame_metrics.csv", frame_rows)
    candidate_csv = _write_csv(output_dir / "d5_multicamera_candidates.csv", candidate_rows)
    metrics_path = _write_json(output_dir / "d5_multicamera_metrics.json", metrics)
    coverage_plot = _write_coverage_plot(
        output_dir / "d5_multicamera_coverage.png",
        frame_rows,
    )
    timeline_plot = _write_registration_timeline(
        output_dir / "d5_registration_timeline.png",
        candidate_rows,
    )
    snapshots = _write_annotated_snapshots(
        frames,
        output_dir=output_dir,
        selected_by_observation=selected_by_observation,
        primary_vehicle_names=primary_vehicle_names,
        recon_vehicle_names=recon_vehicle_names,
    )
    return {
        "metrics": metrics,
        "frame_rows": frame_rows,
        "candidate_rows": candidate_rows,
        "paths": {
            "frame_csv": frame_csv,
            "candidate_csv": candidate_csv,
            "metrics": metrics_path,
            "coverage_plot": coverage_plot,
            "timeline_plot": timeline_plot,
            "snapshots": snapshots,
        },
    }


def _association_diagnostics(
    selected_rows: Iterable[dict[str, Any]],
    *,
    primary_camera_ids: set[str],
    recon_camera_ids: set[str],
) -> dict[str, Any]:
    rows = list(selected_rows)
    timestamps = [
        float(row["timestamp"])
        for row in rows
        if row.get("timestamp") is not None
    ]
    midpoint = (
        (min(timestamps) + max(timestamps)) / 2.0
        if timestamps
        else None
    )
    per_camera: dict[str, dict[str, Any]] = {}
    mismatch_pairs: Counter[tuple[str, str]] = Counter()
    first_half: list[dict[str, Any]] = []
    second_half: list[dict[str, Any]] = []
    primary_rows = [
        row for row in rows
        if str(row.get("camera_id", "")) in primary_camera_ids
    ]
    for camera_id in sorted(primary_camera_ids | recon_camera_ids):
        camera_rows = [
            row for row in rows
            if str(row.get("camera_id", "")) == camera_id
        ]
        evaluated = [
            row for row in camera_rows
            if row.get("truth_global_track_id") is not None
        ]
        correct = sum(row.get("id_match") is True for row in evaluated)
        per_camera[camera_id] = {
            "camera_role": "recon" if camera_id in recon_camera_ids else "primary",
            "selected_count": len(camera_rows),
            "evaluated_count": len(evaluated),
            "correct_count": correct,
            "incorrect_count": len(evaluated) - correct,
            "without_truth_count": len(camera_rows) - len(evaluated),
            "offline_association_accuracy": (
                correct / len(evaluated) if evaluated else None
            ),
        }
    for row in rows:
        truth_id = row.get("truth_global_track_id")
        selected_id = row.get("global_track_id")
        if truth_id is not None and row.get("id_match") is False:
            mismatch_pairs[(str(truth_id), str(selected_id))] += 1
        if midpoint is not None and row.get("timestamp") is not None:
            if float(row["timestamp"]) <= midpoint:
                first_half.append(row)
            else:
                second_half.append(row)
    primary_evaluated = [
        row for row in primary_rows
        if row.get("truth_global_track_id") is not None
    ]
    primary_correct = sum(
        row.get("id_match") is True
        for row in primary_evaluated
    )
    return {
        "selected_registration_without_truth_count": sum(
            row.get("truth_global_track_id") is None
            for row in rows
        ),
        "primary_offline_association_accuracy": (
            primary_correct / len(primary_evaluated)
            if primary_evaluated
            else None
        ),
        "first_half_association_accuracy": _evaluated_accuracy(first_half),
        "second_half_association_accuracy": _evaluated_accuracy(second_half),
        "per_camera_association": per_camera,
        "mismatch_pair_counts": {
            f"{truth_id}->{selected_id}": count
            for (truth_id, selected_id), count in sorted(mismatch_pairs.items())
        },
    }


def _evaluated_accuracy(rows: Iterable[dict[str, Any]]) -> float | None:
    evaluated = [
        row for row in rows
        if row.get("truth_global_track_id") is not None
    ]
    if not evaluated:
        return None
    return sum(row.get("id_match") is True for row in evaluated) / len(evaluated)


def _truth_to_global_map(frame: AirSimFrame) -> dict[str, str]:
    ordered = sorted(frame.truth_objects, key=lambda item: item.object_id)
    return {
        truth.object_id: f"G-{index + 101:03d}"
        for index, truth in enumerate(ordered)
    }


def _terminal_tracks_at_last_frame(
    frame: AirSimFrame,
    *,
    truth_to_global: dict[str, str],
    seed: int,
) -> list[GlobalTrack]:
    generator = np.random.default_rng(seed)
    noise = {
        truth.object_id: generator.normal(0.0, 0.15, size=3)
        for truth in sorted(frame.truth_objects, key=lambda item: item.object_id)
    }
    return [
        GlobalTrack(
            global_track_id=truth_to_global[truth.object_id],
            position=np.asarray(truth.position_ned, dtype=float) + noise[truth.object_id],
            velocity=np.asarray(truth.velocity_ned, dtype=float),
            covariance=np.diag([0.25**2, 0.25**2, 0.25**2]),
            category="uav",
            timestamp=frame.timestamp,
            track_version=1,
        )
        for truth in frame.truth_objects
    ]


def _detections_by_camera(
    detections: Iterable[AirSimDetectionBox],
) -> dict[str, list[AirSimDetectionBox]]:
    grouped: dict[str, list[AirSimDetectionBox]] = defaultdict(list)
    for detection in detections:
        grouped[detection.camera_id].append(detection)
    return grouped


def _offline_truth_by_camera(
    frame: AirSimFrame,
    truth_to_global: dict[str, str],
) -> dict[str, tuple[dict[str, Any], ...]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    actor_to_global = {
        str(truth.metadata.get("airsim_actor_name", "")): truth_to_global[truth.object_id]
        for truth in frame.truth_objects
    }
    for detection in frame.visual_detections:
        global_track_id = truth_to_global.get(detection.object_id)
        if global_track_id is None:
            continue
        output[detection.camera_id].append(
            {
                "bbox_xyxy": tuple(float(value) for value in detection.bbox_xyxy),
                "global_track_id": global_track_id,
            }
        )
    for item in frame.metadata.get("detections", []):
        camera_id = str(
            item.get("camera_id")
            or f"{item.get('camera_vehicle_name', '')}:{item.get('camera_name', '0')}"
        )
        for record in item.get("offline_truth_records", ()):
            actor_name = str(record.get("truth_id", ""))
            global_track_id = actor_to_global.get(actor_name)
            if global_track_id is None:
                continue
            output[camera_id].append(
                {
                    "bbox_xyxy": tuple(float(value) for value in record["bbox_xyxy"]),
                    "global_track_id": global_track_id,
                }
            )
    return {key: tuple(value) for key, value in output.items()}


def _match_local_tracks_to_offline_truth(
    local_tracks: Iterable[Any],
    truth_records: Iterable[dict[str, Any]],
    *,
    iou_threshold: float = 0.30,
) -> dict[str, str]:
    local_list = [track for track in local_tracks if track.bbox is not None]
    truth_list = list(truth_records)
    pairs = []
    for local_index, local_track in enumerate(local_list):
        for truth_index, truth in enumerate(truth_list):
            score = _bbox_iou(local_track.bbox, truth["bbox_xyxy"])
            if score >= iou_threshold:
                pairs.append((score, local_index, truth_index))
    matches: dict[str, str] = {}
    used_local: set[int] = set()
    used_truth: set[int] = set()
    for _score, local_index, truth_index in sorted(pairs, reverse=True):
        if local_index in used_local or truth_index in used_truth:
            continue
        used_local.add(local_index)
        used_truth.add(truth_index)
        matches[local_list[local_index].local_track_id] = truth_list[truth_index][
            "global_track_id"
        ]
    return matches


def _bbox_iou(left: Iterable[float], right: Iterable[float]) -> float:
    lx1, ly1, lx2, ly2 = (float(value) for value in left)
    rx1, ry1, rx2, ry2 = (float(value) for value in right)
    intersection = max(min(lx2, rx2) - max(lx1, rx1), 0.0) * max(
        min(ly2, ry2) - max(ly1, ry1),
        0.0,
    )
    left_area = max(lx2 - lx1, 0.0) * max(ly2 - ly1, 0.0)
    right_area = max(rx2 - rx1, 0.0) * max(ry2 - ry1, 0.0)
    union = left_area + right_area - intersection
    return intersection / union if union > 0.0 else 0.0


def _candidate_rows(
    candidates: Iterable[Any],
    truth_by_observation: dict[tuple[str, str], str],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], Any]]:
    rows = []
    selected: dict[tuple[str, str], Any] = {}
    for candidate in candidates:
        truth_global_track_id = truth_by_observation.get(
            (candidate.frame_id, candidate.local_track_id)
        )
        row = {
            "frame_id": candidate.frame_id,
            "timestamp": candidate.timestamp,
            "resource_id": candidate.resource_id,
            "camera_id": candidate.camera_id,
            "local_track_id": candidate.local_track_id,
            "global_track_id": candidate.global_track_id,
            "truth_global_track_id": truth_global_track_id,
            "mahalanobis_d2": candidate.mahalanobis_d2,
            "pixel_error_px": candidate.pixel_error_px,
            "gate_passed": candidate.gate_passed,
            "selected": candidate.selected,
            "stable_cross_view_support": candidate.stable_cross_view_support,
            "decision_state": candidate.decision_state,
            "reject_reasons": "|".join(candidate.reject_reasons),
            "id_match": (
                None
                if not candidate.selected or truth_global_track_id is None
                else candidate.global_track_id == truth_global_track_id
            ),
        }
        rows.append(row)
        if candidate.selected:
            selected[(candidate.frame_id, candidate.local_track_id)] = candidate
    return rows, selected


def _local_id_switch_count(
    observations: dict[tuple[str, str], list[tuple[int, str]]],
) -> int:
    count = 0
    for records in observations.values():
        ordered = sorted(records)
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] == previous[0] + 1 and current[1] != previous[1]:
                count += 1
    return count


def _actor_motion_metrics(frames: list[AirSimFrame]) -> dict[str, Any]:
    first_frame = frames[0]
    last_frame = frames[-1]
    duration_s = float(last_frame.timestamp - first_frame.timestamp)
    if duration_s <= 0.0:
        return {
            "actor_motion_duration_s": duration_s,
            "actor_measured_motion": [],
            "measured_actor_speed_min_mps": None,
            "measured_actor_speed_max_mps": None,
            "actor_lateral_span_start_m": None,
            "actor_lateral_span_end_m": None,
        }
    first_by_id = {truth.object_id: truth for truth in first_frame.truth_objects}
    last_by_id = {truth.object_id: truth for truth in last_frame.truth_objects}
    rows = []
    for object_id in sorted(first_by_id.keys() & last_by_id.keys()):
        first = first_by_id[object_id]
        last = last_by_id[object_id]
        measured_velocity = (
            np.asarray(last.position_ned, dtype=float)
            - np.asarray(first.position_ned, dtype=float)
        ) / duration_s
        rows.append(
            {
                "object_id": object_id,
                "planned_velocity_ned_mps": list(first.velocity_ned),
                "measured_velocity_ned_mps": measured_velocity.tolist(),
                "measured_speed_mps": float(np.linalg.norm(measured_velocity)),
                "start_position_ned_m": list(first.position_ned),
                "end_position_ned_m": list(last.position_ned),
            }
        )
    speeds = [float(row["measured_speed_mps"]) for row in rows]
    start_y = [float(row["start_position_ned_m"][1]) for row in rows]
    end_y = [float(row["end_position_ned_m"][1]) for row in rows]
    return {
        "actor_motion_duration_s": duration_s,
        "actor_measured_motion": rows,
        "measured_actor_speed_min_mps": min(speeds) if speeds else None,
        "measured_actor_speed_max_mps": max(speeds) if speeds else None,
        "actor_lateral_span_start_m": max(start_y) - min(start_y) if start_y else None,
        "actor_lateral_span_end_m": max(end_y) - min(end_y) if end_y else None,
    }


def _resource_id(
    owner_id: str,
    primary_vehicle_names: tuple[str, ...],
    recon_vehicle_names: tuple[str, ...],
) -> str:
    if owner_id in primary_vehicle_names:
        return f"INT-{primary_vehicle_names.index(owner_id) + 1:02d}"
    if owner_id in recon_vehicle_names:
        return f"RECON-{recon_vehicle_names.index(owner_id) + 1:02d}"
    return owner_id


def _registration_frame_id(frame: AirSimFrame, camera_id: str) -> str:
    return f"{frame.episode_id}:{frame.frame_index:04d}:{camera_id}"


def _detector_backend_for_camera(frame: AirSimFrame, owner_id: str) -> str:
    for item in frame.metadata.get("detections", []):
        if str(item.get("camera_vehicle_name", "")) == owner_id:
            return str(
                item.get("tracker_backend")
                or item.get("detector_backend")
                or item.get("backend")
                or "unknown"
            )
    return "unknown"


def _primary_backend(frame: AirSimFrame, owner_names: tuple[str, ...]) -> str:
    backends = {
        _detector_backend_for_camera(frame, owner)
        for owner in owner_names
    }
    return ",".join(sorted(backends)) if backends else "unavailable"


def _write_annotated_snapshots(
    frames: list[AirSimFrame],
    *,
    output_dir: Path,
    selected_by_observation: dict[tuple[str, str], Any],
    primary_vehicle_names: tuple[str, ...],
    recon_vehicle_names: tuple[str, ...],
) -> list[Path]:
    snapshot_root = output_dir / "annotated_snapshots"
    montage_paths: list[Path] = []
    montage_name = (
        f"montage_{len(primary_vehicle_names)}primary_plus_recon.png"
        if len(recon_vehicle_names) == 1
        else (
            f"montage_{len(primary_vehicle_names)}primary_plus_"
            f"{len(recon_vehicle_names)}recon.png"
        )
    )
    for frame in frames:
        image_meta_by_owner = {
            str(item.get("camera_vehicle_name")): item
            for item in frame.metadata.get("images", [])
            if item.get("saved") and item.get("path")
        }
        if not image_meta_by_owner:
            continue
        detections_by_camera = _detections_by_camera(frame.visual_detections)
        tiles: list[np.ndarray] = []
        frame_dir = snapshot_root / f"frame_{frame.frame_index:04d}_t{frame.timestamp:05.2f}s"
        frame_dir.mkdir(parents=True, exist_ok=True)
        for camera_info in frame.cameras:
            image_meta = image_meta_by_owner.get(camera_info.owner_id)
            if image_meta is None:
                continue
            image = cv2.imread(str(image_meta["path"]), cv2.IMREAD_COLOR)
            if image is None:
                continue
            frame_id = _registration_frame_id(frame, camera_info.camera_id)
            annotated = _annotate_camera_image(
                image,
                camera_info=camera_info,
                detections=detections_by_camera.get(camera_info.camera_id, ()),
                frame_id=frame_id,
                selected_by_observation=selected_by_observation,
                backend=_detector_backend_for_camera(frame, camera_info.owner_id),
                role="RECON" if camera_info.owner_id in recon_vehicle_names else "PRIMARY",
                timestamp=frame.timestamp,
            )
            image_path = frame_dir / f"{_safe_name(camera_info.owner_id)}.png"
            cv2.imwrite(str(image_path), annotated)
            tiles.append(_fit_tile(annotated, 640, 360))
        if not tiles:
            continue
        column_count = min(3, len(tiles))
        while len(tiles) % column_count:
            tiles.append(np.zeros_like(tiles[0]))
        montage = np.vstack(
            [
                np.hstack(tiles[index : index + column_count])
                for index in range(0, len(tiles), column_count)
            ]
        )
        montage_path = frame_dir / montage_name
        cv2.imwrite(str(montage_path), montage)
        montage_paths.append(montage_path)
    return montage_paths


def _annotate_camera_image(
    image: np.ndarray,
    *,
    camera_info: AirSimCameraInfo,
    detections: Iterable[AirSimDetectionBox],
    frame_id: str,
    selected_by_observation: dict[tuple[str, str], Any],
    backend: str,
    role: str,
    timestamp: float,
) -> np.ndarray:
    output = image.copy()
    selected_count = 0
    for detection in detections:
        candidate = selected_by_observation.get((frame_id, detection.local_track_id))
        if candidate is None:
            color = (128, 128, 128)
            association_label = "unassigned"
        else:
            selected_count += 1
            color = _track_color(candidate.global_track_id)
            association_label = (
                f"{candidate.global_track_id} "
                f"{'stable' if candidate.stable_cross_view_support else 'pending'}"
            )
            if candidate.projected_px is not None:
                point = tuple(int(round(value)) for value in candidate.projected_px)
                cv2.drawMarker(
                    output,
                    point,
                    color,
                    markerType=cv2.MARKER_CROSS,
                    markerSize=20,
                    thickness=2,
                )
        x1, y1, x2, y2 = (int(round(value)) for value in detection.bbox_xyxy)
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        local_short = detection.local_track_id.rsplit(":", 1)[-1]
        label = f"{local_short} -> {association_label} c={detection.confidence:.2f}"
        cv2.putText(
            output,
            label,
            (max(x1, 0), max(y1 - 8, 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )
    header = (
        f"{role} {camera_info.owner_id} | {backend} | t={timestamp:.2f}s | "
        f"det={len(tuple(detections))} assoc={selected_count}"
    )
    cv2.rectangle(output, (0, 0), (min(output.shape[1], 1250), 38), (0, 0, 0), -1)
    cv2.putText(
        output,
        header,
        (10, 27),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return output


def _track_color(global_track_id: str | None) -> tuple[int, int, int]:
    palette = (
        (52, 152, 219),
        (46, 204, 113),
        (241, 196, 15),
        (155, 89, 182),
        (230, 126, 34),
    )
    if global_track_id is None:
        return (128, 128, 128)
    digits = "".join(character for character in global_track_id if character.isdigit())
    return palette[(int(digits or "0") - 101) % len(palette)]


def _fit_tile(image: np.ndarray, width: int, height: int) -> np.ndarray:
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(
        image,
        (max(1, int(round(image.shape[1] * scale))), max(1, int(round(image.shape[0] * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def _write_coverage_plot(path: Path, rows: list[dict[str, Any]]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_camera: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_camera[row["camera_id"]].append(row)
    figure, axis = plt.subplots(figsize=(11, 5.5))
    for camera_id, camera_rows in sorted(by_camera.items()):
        ordered = sorted(camera_rows, key=lambda item: item["timestamp"])
        label = f"{ordered[0]['camera_role']}:{camera_id.split(':', 1)[0]}"
        axis.plot(
            [item["timestamp"] for item in ordered],
            [item["online_detection_count"] for item in ordered],
            marker="o",
            markersize=2,
            linewidth=1.2,
            label=label,
        )
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Online local tracks")
    axis.set_ylim(bottom=0)
    axis.grid(True, alpha=0.25)
    axis.legend(ncol=2, fontsize=8)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def _write_registration_timeline(path: Path, rows: list[dict[str, Any]]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    selected = Counter()
    stable = Counter()
    for row in rows:
        timestamp = float(row["timestamp"])
        if row["selected"]:
            selected[timestamp] += 1
        if row["selected"] and row["stable_cross_view_support"]:
            stable[timestamp] += 1
    timestamps = sorted(set(selected) | set(stable))
    figure, axis = plt.subplots(figsize=(11, 4.5))
    axis.plot(timestamps, [selected[value] for value in timestamps], label="selected", linewidth=2)
    axis.plot(timestamps, [stable[value] for value in timestamps], label="stable", linewidth=2)
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Registrations")
    axis.set_ylim(bottom=0)
    axis.grid(True, alpha=0.25)
    axis.legend()
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def _write_comparison_plot(path: Path, analyses: list[dict[str, Any]]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [analysis["metrics"]["primary_detection_backend"] for analysis in analyses]
    metric_names = (
        "offline_detector_recall",
        "offline_association_accuracy",
        "stable_registration_rate",
        "recon_full_view_frame_rate",
    )
    values = [
        [
            0.0
            if analysis["metrics"][metric] is None
            else float(analysis["metrics"][metric])
            for metric in metric_names
        ]
        for analysis in analyses
    ]
    x = np.arange(len(metric_names))
    width = 0.36
    figure, axis = plt.subplots(figsize=(11, 5.5))
    for index, row in enumerate(values):
        axis.bar(x + (index - (len(values) - 1) / 2) * width, row, width, label=labels[index])
    axis.set_xticks(x, [name.replace("_", "\n") for name in metric_names])
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("Rate")
    axis.grid(True, axis="y", alpha=0.25)
    axis.legend()
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def _write_campaign_report(
    path: Path,
    *,
    args: argparse.Namespace,
    configs: tuple[BlocksSmokeConfig, ...],
    analyses: list[dict[str, Any]],
    comparison_plot: Path,
    comparison_json: Path,
) -> Path:
    target_speeds = [_speed_mps(spec.velocity_ned) for spec in configs[0].target_actor_specs]
    measured_metrics = analyses[0]["metrics"]
    configured_backends = ", ".join(
        str(config.metadata["primary_detection_backend"])
        for config in configs
    )
    lines = [
        (
            f"# D5 ComputerVision {args.drone_count}v{args.drone_count} "
            "多相机配准专项报告"
        ),
        "",
        "## 测试配置",
        "",
        "- 本测试是独立实验入口，不替换默认 AirSim/D1-D7 流程。",
        (
            f"- {args.drone_count} 个 ComputerVision 拦截相机："
            f"1920x1080、`{args.primary_fov}` 度视场，各自允许只看到目标子集。"
        ),
        (
            f"- {args.recon_count} 个 ComputerVision 侦察相机："
            f"3840x2160、`{args.recon_fov}` 度视场、约 `{args.recon_height}` m 高差，"
            "作为全局视觉锚点。"
        ),
        (
            f"- {args.drone_count} 个 Quadrotor1 actor：初始约 "
            f"`{args.target_distance}` m、横向间隔 `{args.target_spacing}` m、"
            f"尺度 `{args.target_scale}`。"
        ),
        (
            f"- actor 速度比例 `{args.target_speed_scale}`，规划速度范围 "
            f"`{min(target_speeds):.3f}`–`{max(target_speeds):.3f}` m/s；"
            "各速度向量相对原轨迹等比例放大。"
        ),
        (
            "- 由首末 AirSim actor 实际位姿推导的速度范围 "
            f"`{measured_metrics['measured_actor_speed_min_mps']:.3f}`–"
            f"`{measured_metrics['measured_actor_speed_max_mps']:.3f}` m/s；"
            f"横向跨度从 `{measured_metrics['actor_lateral_span_start_m']:.3f}` m "
            f"收敛到 `{measured_metrics['actor_lateral_span_end_m']:.3f}` m。"
        ),
        f"- 主相机与目标高度约 `{args.flight_altitude}` m，侦察相机再高 `{args.recon_height}` m，以避开 Blocks 地面建筑遮挡。",
        (
            f"- 时长 `{args.duration}` s，采样周期 `{args.dt}` s，"
            f"截图间隔请求值 `{args.snapshot_interval}` s、有效值 "
            f"`{configs[0].image_save_interval_frames * args.dt}` s，seed `{args.seed}`。"
        ),
        f"- 本轮主相机后端：`{configured_backends}`；侦察相机使用 AirSim detect。",
        "- 本专项未运行 D1/D2；main 用 actor 运动学合成中心侧 GlobalTrack 输入，并用 truth 做离线评分。",
        "- D5 的局部框到 GlobalTrack 的代价、Hungarian 选择和稳定窗口不读取 actor/object/truth identity。",
        "",
        "## 汇总结果",
        "",
        "| episode | 主检测后端 | 在线检测数 | 检测召回 | 配准准确率 | 严格准确率 | 主相机准确率 | 稳定配准率 | 联合覆盖 | 侦察全覆盖 | 本地 IDSW |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for analysis in analyses:
        metrics = analysis["metrics"]
        lines.append(
            "| {episode} | {backend} | {detections} | {recall} | {accuracy} | "
            "{strict} | {primary_accuracy} | {stable} | {primary} | {recon} | {idsw} |".format(
                episode=metrics["episode_id"],
                backend=metrics["primary_detection_backend"],
                detections=metrics["online_detection_count"],
                recall=_format_rate(metrics["offline_detector_recall"]),
                accuracy=_format_rate(metrics["offline_association_accuracy"]),
                strict=_format_rate(metrics["strict_association_accuracy"]),
                primary_accuracy=_format_rate(
                    metrics["primary_offline_association_accuracy"]
                ),
                stable=_format_rate(metrics["stable_registration_rate"]),
                primary=_format_rate(metrics["primary_union_coverage_rate_mean"]),
                recon=_format_rate(metrics["recon_full_view_frame_rate"]),
                idsw=metrics["local_id_switch_count"],
            )
        )
    lines.extend(
        [
            "",
            "说明：配准准确率只统计能与离线真值框完成交并比匹配的已选结果；严格准确率把无真值匹配的已选框也按错误计入，避免忽略误检。在线关联不读取这些真值标签。",
            "",
            f"![检测与配准对比]({_relative_link(path, comparison_plot)})",
            "",
            "## 验收结论",
            "",
        ]
    )
    for analysis in analyses:
        metrics = analysis["metrics"]
        backend = metrics["primary_detection_backend"]
        checks = _acceptance_checks(metrics)
        lines.extend(
            [
                f"### {backend}",
                "",
                "| 验收项 | 门限 | 实测 | 判定 |",
                "| --- | ---: | ---: | --- |",
            ]
        )
        for label, threshold, value, passed in checks:
            lines.append(
                f"| {label} | {threshold} | {_format_acceptance_value(value)} | "
                f"{'通过' if passed else '未通过'} |"
            )
        lines.append("")
        lines.append(
            "- 总体判定："
            + (
                "满足本专项全部验收门限。"
                if all(item[3] for item in checks)
                else "未满足全部门限，保持研究验证或可选后端状态。"
            )
        )
        lines.append("")
    lines.extend(
        [
            "## 误差拆解",
            "",
            "本轮按每个相机批次自己的量测时间投影 GlobalTrack，不再用最后一帧时间覆盖整段观测。",
            "",
        ]
    )
    for analysis in analyses:
        metrics = analysis["metrics"]
        lines.extend(
            [
                f"### {metrics['primary_detection_backend']}",
                "",
                f"- 前半程配准准确率：`{_format_rate(metrics['first_half_association_accuracy'])}`。",
                f"- 后半程配准准确率：`{_format_rate(metrics['second_half_association_accuracy'])}`。",
                f"- 已选但无法与离线真值框匹配：`{metrics['selected_registration_without_truth_count']}`。",
                f"- 几何门限拒绝：`{metrics['rejection_reason_counts'].get('geometry_gate_rejected', 0)}`。",
                f"- 错配对：`{metrics['mismatch_pair_counts'] or '无'}`。",
                "",
                "| 相机 | 角色 | 已选 | 可评分 | 错配 | 无真值匹配 | 准确率 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for camera_id, camera_metrics in metrics["per_camera_association"].items():
            lines.append(
                "| {camera} | {role} | {selected} | {evaluated} | {incorrect} | "
                "{without_truth} | {accuracy} |".format(
                    camera=camera_id,
                    role="侦察" if camera_metrics["camera_role"] == "recon" else "主相机",
                    selected=camera_metrics["selected_count"],
                    evaluated=camera_metrics["evaluated_count"],
                    incorrect=camera_metrics["incorrect_count"],
                    without_truth=camera_metrics["without_truth_count"],
                    accuracy=_format_rate(
                        camera_metrics["offline_association_accuracy"]
                    ),
                )
            )
        lines.append("")
    lines.extend(
        [
            "## 间隔截图",
            "",
            (
                f"每个拼图按最多 3 列排列 {args.drone_count} 个拦截相机和 "
                f"{args.recon_count} 个侦察相机，间隔 "
                f"`{configs[0].image_save_interval_frames * args.dt}` s；"
                "框标签只显示本地轨迹、现有 GlobalTrack 候选和稳定状态。"
            ),
            "",
        ]
    )
    for analysis in analyses:
        lines.append(f"### {analysis['metrics']['primary_detection_backend']}")
        lines.append("")
        snapshots = analysis["paths"]["snapshots"]
        if not snapshots:
            lines.append("- 未生成截图，需检查 Scene 图像采集。")
        else:
            for snapshot in snapshots:
                lines.append(f"![{snapshot.parent.name}]({_relative_link(path, snapshot)})")
        lines.append("")
        lines.append(
            f"- 覆盖曲线：[{analysis['paths']['coverage_plot'].name}]"
            f"({_relative_link(path, analysis['paths']['coverage_plot'])})"
        )
        lines.append(
            f"- 配准时间线：[{analysis['paths']['timeline_plot'].name}]"
            f"({_relative_link(path, analysis['paths']['timeline_plot'])})"
        )
        lines.append(
            f"- 指标：[{analysis['paths']['metrics'].name}]"
            f"({_relative_link(path, analysis['paths']['metrics'])})"
        )
        lines.append("")
    lines.extend(
        [
            "## 判读规则",
            "",
            "- detect 基线若侦察全覆盖不足 0.90，先判定相机布局或 actor 可见性不满足，不归因于 YOLO。",
            "- detect 有框但配准错误时，检查相机外参、NED 到相机轴变换和马氏门限。",
            "- YOLO 无框或召回偏低时，归因于检测权重、目标尺度或视角；不得用 truth ID 补齐在线结果。",
            "- YOLO 有框但 local ID 频繁变化时，归因于 ByteTrack 连续性；不得改写 GlobalTrack。",
            "- `online_truth_identity_use_count=0` 表示 D5 关联代价/选择不读取局部 actor/object/truth identity；不表示本专项未用 truth 合成上游 GlobalTrack fixture。",
            "- `global_track_id_rewrite_count` 和 `online_truth_identity_use_count` 必须保持 0。",
            "- 本专项只验证 D5 视觉配准分支，不替代 D1 雷达融合、D2 全局航迹身份维护或 D3 任务分配。",
            "",
            "## 产物",
            "",
            f"- settings: `{configs[0].settings_path}`",
            f"- comparison JSON: `{comparison_json}`",
            f"- comparison plot: `{comparison_plot}`",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _acceptance_checks(
    metrics: dict[str, Any],
) -> list[tuple[str, str, float | int | None, bool]]:
    backend = str(metrics["primary_detection_backend"])
    id_switch_limit = 0 if backend == "airsim" else 5
    checks = [
        (
            "离线检测召回",
            ">=0.95" if backend == "airsim" else ">=0.90",
            metrics["offline_detector_recall"],
            _at_least(metrics["offline_detector_recall"], 0.95 if backend == "airsim" else 0.90),
        ),
        (
            "严格配准准确率",
            ">=0.95",
            metrics["strict_association_accuracy"],
            _at_least(metrics["strict_association_accuracy"], 0.95),
        ),
        (
            "稳定配准率",
            ">=0.90",
            metrics["stable_registration_rate"],
            _at_least(metrics["stable_registration_rate"], 0.90),
        ),
        (
            "主相机联合覆盖",
            ">=0.95",
            metrics["primary_union_coverage_rate_mean"],
            _at_least(metrics["primary_union_coverage_rate_mean"], 0.95),
        ),
        (
            "侦察相机全覆盖帧率",
            ">=0.90",
            metrics["recon_full_view_frame_rate"],
            _at_least(metrics["recon_full_view_frame_rate"], 0.90),
        ),
        (
            "本地身份切换",
            f"<={id_switch_limit}",
            metrics["local_id_switch_count"],
            int(metrics["local_id_switch_count"]) <= id_switch_limit,
        ),
        (
            "在线真值身份使用",
            "=0",
            metrics["online_truth_identity_use_count"],
            int(metrics["online_truth_identity_use_count"]) == 0,
        ),
        (
            "GlobalTrack 身份改写",
            "=0",
            metrics["global_track_id_rewrite_count"],
            int(metrics["global_track_id_rewrite_count"]) == 0,
        ),
    ]
    return checks


def _at_least(value: float | None, threshold: float) -> bool:
    return value is not None and float(value) >= threshold


def _format_acceptance_value(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return f"{float(value):.3f}"


def _load_frames(path: Path) -> list[AirSimFrame]:
    frames = []
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
                    truth_objects=tuple(
                        AirSimTruthObject(**item)
                        for item in payload.get("truth_objects", [])
                    ),
                    resources=tuple(
                        AirSimResourceState(**item)
                        for item in payload.get("resources", [])
                    ),
                    cameras=tuple(
                        AirSimCameraInfo(**item)
                        for item in payload.get("cameras", [])
                    ),
                    visual_detections=tuple(
                        AirSimDetectionBox(**item)
                        for item in payload.get("visual_detections", [])
                    ),
                    center_node_alive=bool(payload.get("center_node_alive", True)),
                    secondary_nodes_alive=bool(payload.get("secondary_nodes_alive", True)),
                    metadata=dict(payload.get("metadata", {})),
                )
            )
    return frames


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)
    return path


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    return value


def _mean(values: Iterable[Any]) -> float | None:
    array = np.asarray(list(values), dtype=float)
    return float(np.mean(array)) if array.size else None


def _percentile(values: list[float], percentile: float) -> float | None:
    return float(np.percentile(values, percentile)) if values else None


def _format_rate(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def _safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def _relative_link(report_path: Path, artifact_path: Path) -> str:
    return str(artifact_path.resolve().relative_to(report_path.parent.resolve()))


if __name__ == "__main__":
    raise SystemExit(main())
