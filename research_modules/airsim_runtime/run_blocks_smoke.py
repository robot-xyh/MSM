#!/usr/bin/env python3
"""Run the real Blocks read-only AirSim smoke workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


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

from airsim_runtime import run_blocks_smoke
from airsim_runtime.models import (
    BlocksSmokeConfig,
    default_cv_5v5_actor_target_specs,
    default_cv_5v5_camera_vehicle_names,
    default_cv_5v5_secondary_vehicle_names,
)

DEFAULT_SETTINGS = "research_modules/airsim_runtime/settings/blocks_smoke_settings.json"
CV_5V5_SETTINGS = "research_modules/airsim_runtime/settings/blocks_cv_5v5_settings.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-id", default="blocks_smoke_001")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--dt", type=float, default=0.5)
    parser.add_argument("--output-root", default="research_modules/airsim_runtime/outputs")
    parser.add_argument("--blocks-script", default="Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh")
    parser.add_argument(
        "--settings",
        default=DEFAULT_SETTINGS,
    )
    parser.add_argument(
        "--cv-5v5",
        action="store_true",
        help="Run one ComputerVision 5v5 actor-target replay episode.",
    )
    parser.add_argument("--cv-camera-follow-distance", type=float, default=14.0)
    parser.add_argument(
        "--cv-reassignment-time",
        type=float,
        default=None,
        help="ComputerVision 5v5 secondary reassignment time. Defaults to half the duration.",
    )
    parser.add_argument("--connection-timeout", type=float, default=90.0)
    parser.add_argument("--client-timeout", type=float, default=2.0)
    parser.add_argument(
        "--client-kind",
        choices=("vehicle", "multirotor"),
        default="vehicle",
        help="AirSim Python client class. Use vehicle for read-only smoke tests.",
    )
    parser.add_argument("--camera-vehicle-name", default="Interceptor")
    parser.add_argument("--camera-name", default="0")
    parser.add_argument(
        "--detection-backend",
        choices=("airsim", "yolo"),
        default="airsim",
        help="Use AirSim simGetDetections metadata or D5 YOLOv8+MOT image detection.",
    )
    parser.add_argument(
        "--yolo-weights",
        default="research_modules/d5_terminal_association/best.pt",
        help="YOLOv8 weights path used when --detection-backend yolo.",
    )
    parser.add_argument(
        "--yolo-tracker-backend",
        choices=("bytetrack", "botsort", "iou_fallback"),
        default="bytetrack",
        help="D5 MOT backend requested for YOLO detections.",
    )
    parser.add_argument("--yolo-confidence", type=float, default=0.25)
    parser.add_argument("--no-yolo-native-tracker", action="store_true")
    parser.add_argument("--no-yolo-iou-fallback", action="store_true")
    parser.add_argument("--save-images", action="store_true", help="Persist sampled Scene PNG frames.")
    parser.add_argument("--lidar-vehicle-name", default="Interceptor")
    parser.add_argument("--lidar-name", default="LidarSensor1")
    parser.add_argument("--target-vehicles", default="Intruder")
    parser.add_argument("--resource-vehicles", default="Interceptor")
    parser.add_argument(
        "--blocks-arg",
        action="append",
        default=None,
        help="Extra argument passed to Blocks.sh. Can be repeated.",
    )
    parser.add_argument("--no-nvidia-offload", action="store_true")
    parser.add_argument("--no-launch", action="store_true", help="Connect to an already running Blocks instance.")
    parser.add_argument("--no-integrated-pipeline", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings_path = Path(args.settings)
    mode_config = {
        "target_vehicle_names": _parse_csv(args.target_vehicles),
        "resource_vehicle_names": _parse_csv(args.resource_vehicles),
    }
    if args.cv_5v5:
        if args.settings == DEFAULT_SETTINGS:
            settings_path = Path(CV_5V5_SETTINGS)
        cv_resources = default_cv_5v5_camera_vehicle_names()
        cv_secondaries = default_cv_5v5_secondary_vehicle_names()
        mode_config = {
            "scenario_name": "blocks_cv_5v5",
            "camera_vehicle_name": cv_resources[0],
            "camera_vehicle_names": cv_resources,
            "secondary_camera_vehicle_names": cv_secondaries,
            "capture_lidar": False,
            "cv_camera_follow_assignments": True,
            "cv_camera_follow_distance_m": args.cv_camera_follow_distance,
            "cv_secondary_look_at_enabled": True,
            "cv_reassignment_time_s": (
                args.cv_reassignment_time
                if args.cv_reassignment_time is not None
                else max(args.dt, args.duration * 0.5)
            ),
            "lidar_vehicle_name": cv_resources[0],
            "lidar_vehicle_names": (),
            "target_vehicle_names": (),
            "resource_vehicle_names": cv_resources,
            "target_actor_specs": default_cv_5v5_actor_target_specs(target_z=-10.0),
            "detection_filter_names": ("MSM_TargetActor_*",),
            "detection_radius_cm": 160 * 100,
            "metadata": {
                "runtime_mode": "computer_vision_5v5",
                "secondary_camera_vehicle_names": cv_secondaries,
            },
        }
    config_kwargs = {
        "episode_id": args.episode_id,
        "duration_s": args.duration,
        "dt_s": args.dt,
        "output_root": Path(args.output_root),
        "blocks_script": Path(args.blocks_script),
        "settings_path": settings_path,
        "blocks_args": tuple(args.blocks_arg)
        if args.blocks_arg is not None
        else BlocksSmokeConfig().blocks_args,
        "prefer_nvidia_offload": not args.no_nvidia_offload,
        "launch_blocks": not args.no_launch,
        "connection_timeout_s": args.connection_timeout,
        "client_timeout_s": args.client_timeout,
        "client_kind": args.client_kind,
        "camera_vehicle_name": args.camera_vehicle_name,
        "camera_name": args.camera_name,
        "detection_backend": args.detection_backend,
        "yolo_weights_path": Path(args.yolo_weights),
        "yolo_tracker_backend": args.yolo_tracker_backend,
        "yolo_confidence_threshold": args.yolo_confidence,
        "yolo_use_native_tracker": not args.no_yolo_native_tracker,
        "yolo_allow_iou_fallback": not args.no_yolo_iou_fallback,
        "save_images": args.save_images,
        "lidar_vehicle_name": args.lidar_vehicle_name,
        "lidar_name": args.lidar_name,
        "include_integrated_pipeline": not args.no_integrated_pipeline,
    }
    config_kwargs.update(mode_config)
    config = BlocksSmokeConfig(**config_kwargs)
    result = run_blocks_smoke(config)
    print(f"episode_id={result.episode_id}")
    print(f"connected={result.connected}")
    print(f"frame_count={result.frame_count}")
    print(f"vehicles={','.join(result.vehicle_names)}")
    print(f"image_ok_count={result.image_ok_count}")
    print(f"lidar_ok_count={result.lidar_ok_count}")
    print(f"real_airsim_used={result.metadata['real_airsim_used']}")
    print(f"control_api_used={result.metadata['control_api_used']}")
    print(f"output_dir={config.output_dir.resolve()}")
    return 0


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


if __name__ == "__main__":
    raise SystemExit(main())
