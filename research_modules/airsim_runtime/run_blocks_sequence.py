#!/usr/bin/env python3
"""Run staged real Blocks episodes under one AirSim process."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
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

from airsim_runtime.models import BlocksSmokeConfig, default_2v2_actor_target_specs
from airsim_runtime.sequence import DEFAULT_BLOCKS_EPISODES, run_blocks_sequence

DEFAULT_SETTINGS = "research_modules/airsim_runtime/settings/blocks_smoke_settings.json"
ACTOR_2V2_SETTINGS = "research_modules/airsim_runtime/settings/blocks_2v2_actor_settings.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence-id", default="blocks_sequence_001")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--dt", type=float, default=0.5)
    parser.add_argument("--output-root", default="research_modules/airsim_runtime/outputs")
    parser.add_argument("--blocks-script", default="Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh")
    parser.add_argument(
        "--settings",
        default=DEFAULT_SETTINGS,
    )
    parser.add_argument(
        "--actor-2v2",
        action="store_true",
        help="Run two SimpleFlight interceptor resources against two moving non-vehicle actor targets.",
    )
    parser.add_argument("--connection-timeout", type=float, default=90.0)
    parser.add_argument("--client-timeout", type=float, default=2.0)
    parser.add_argument(
        "--blocks-arg",
        action="append",
        default=None,
        help="Extra argument passed to Blocks.sh. Can be repeated.",
    )
    parser.add_argument("--no-nvidia-offload", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings_path = Path(args.settings)
    if args.actor_2v2 and args.settings == DEFAULT_SETTINGS:
        settings_path = Path(ACTOR_2V2_SETTINGS)
    scenario_name = "blocks_actor_2v2" if args.actor_2v2 else "blocks_readonly_smoke"
    actor_config = (
        {
            "camera_vehicle_name": "Interceptor1",
            "camera_vehicle_names": ("Interceptor1", "Interceptor2"),
            "lidar_vehicle_name": "Interceptor1",
            "lidar_vehicle_names": ("Interceptor1", "Interceptor2"),
            "target_vehicle_names": (),
            "resource_vehicle_names": ("Interceptor1", "Interceptor2"),
            "target_actor_specs": default_2v2_actor_target_specs(),
            "detection_filter_names": ("MSM_TargetActor_*",),
            "metadata": {"runtime_mode": "actor_2v2"},
        }
        if args.actor_2v2
        else {}
    )
    base_config = BlocksSmokeConfig(
        scenario_name=scenario_name,
        duration_s=args.duration,
        dt_s=args.dt,
        output_root=Path(args.output_root),
        blocks_script=Path(args.blocks_script),
        settings_path=settings_path,
        blocks_args=tuple(args.blocks_arg)
        if args.blocks_arg is not None
        else BlocksSmokeConfig().blocks_args,
        prefer_nvidia_offload=not args.no_nvidia_offload,
        connection_timeout_s=args.connection_timeout,
        client_timeout_s=args.client_timeout,
        **actor_config,
    )
    episode_specs = tuple(
        replace(spec, scenario_name=scenario_name, duration_s=args.duration, dt_s=args.dt)
        for spec in DEFAULT_BLOCKS_EPISODES
    )
    result = run_blocks_sequence(
        base_config,
        sequence_id=args.sequence_id,
        episode_specs=episode_specs,
    )
    print(f"sequence_id={result.sequence_id}")
    print(f"connected={result.connected}")
    print(f"episode_count={len(result.episode_results)}")
    for episode in result.episode_results:
        print(
            f"{episode.episode_id}: frames={episode.frame_count} "
            f"vehicles={','.join(episode.vehicle_names)} "
            f"image_ok={episode.image_ok_count} lidar_ok={episode.lidar_ok_count} "
            f"integrated={episode.integrated_result is not None}"
        )
    print(f"summary={result.output_paths['blocks_sequence_summary'].resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
