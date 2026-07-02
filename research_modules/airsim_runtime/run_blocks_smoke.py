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
from airsim_runtime.models import BlocksSmokeConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-id", default="blocks_smoke_001")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--dt", type=float, default=0.5)
    parser.add_argument("--output-root", default="research_modules/airsim_runtime/outputs")
    parser.add_argument("--blocks-script", default="Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh")
    parser.add_argument(
        "--settings",
        default="research_modules/airsim_runtime/settings/blocks_smoke_settings.json",
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
    config = BlocksSmokeConfig(
        episode_id=args.episode_id,
        duration_s=args.duration,
        dt_s=args.dt,
        output_root=Path(args.output_root),
        blocks_script=Path(args.blocks_script),
        settings_path=Path(args.settings),
        blocks_args=tuple(args.blocks_arg)
        if args.blocks_arg is not None
        else BlocksSmokeConfig().blocks_args,
        prefer_nvidia_offload=not args.no_nvidia_offload,
        launch_blocks=not args.no_launch,
        connection_timeout_s=args.connection_timeout,
        client_timeout_s=args.client_timeout,
        client_kind=args.client_kind,
        camera_vehicle_name=args.camera_vehicle_name,
        camera_name=args.camera_name,
        lidar_vehicle_name=args.lidar_vehicle_name,
        lidar_name=args.lidar_name,
        target_vehicle_names=_parse_csv(args.target_vehicles),
        resource_vehicle_names=_parse_csv(args.resource_vehicles),
        include_integrated_pipeline=not args.no_integrated_pipeline,
    )
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
