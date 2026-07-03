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

from airsim_runtime.models import (
    BlocksSmokeConfig,
    default_2v2_actor_target_specs,
    default_cv_5v5_actor_target_specs,
    default_cv_5v5_d4d5_stress_actor_target_specs,
    default_cv_5v5_camera_vehicle_names,
    default_cv_5v5_secondary_vehicle_names,
)
from airsim_runtime.sequence import D4D5_STRESS_EPISODES, DEFAULT_BLOCKS_EPISODES, run_blocks_sequence

DEFAULT_SETTINGS = "research_modules/airsim_runtime/settings/blocks_smoke_settings.json"
ACTOR_2V2_SETTINGS = "research_modules/airsim_runtime/settings/blocks_2v2_actor_settings.json"
CV_5V5_SETTINGS = "research_modules/airsim_runtime/settings/blocks_cv_5v5_settings.json"
CV_5V5_D4D5_STRESS_SETTINGS = (
    "research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_settings.json"
)
ACTOR_2V2_TUNED_SETTINGS = (
    "research_modules/airsim_runtime/settings/blocks_2v2_actor_tuned_settings.json"
)
CV_5V5_D4D5_STRESS_200M_SETTINGS = (
    "research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_200m_settings.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence-id", default="blocks_sequence_001")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--batch-seeds",
        default=None,
        help="Comma-separated seeds. Runs one sequence per seed using '<sequence-id>_seedNNN'.",
    )
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
    parser.add_argument(
        "--cv-5v5",
        action="store_true",
        help="Run five ComputerVision camera resources against five moving actor targets.",
    )
    parser.add_argument(
        "--cv-5v5-d4d5-stress",
        action="store_true",
        help="Run the dedicated 5v5 D5 terminal association and D4 degradation stress sequence.",
    )
    parser.add_argument(
        "--terminal-handoff-tuned",
        action="store_true",
        help="Use the 2v2 tuned terminal visual handoff settings and look-at-target yaw.",
    )
    parser.add_argument(
        "--cv-5v5-d4d5-stress-200m",
        action="store_true",
        help="Run the D4/D5 stress sequence with secondary recon cameras 200 m above targets.",
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
        "--execute-intercept",
        action="store_true",
        help="Execute SimpleFlight PN control in episode_006_full_flow.",
    )
    parser.add_argument("--control-dt", type=float, default=0.1)
    parser.add_argument("--intercept-speed", type=float, default=6.0)
    parser.add_argument("--intercept-altitude-z", type=float, default=-2.0)
    parser.add_argument("--intercept-radius", type=float, default=0.75)
    parser.add_argument("--intercept-max-duration", type=float, default=8.0)
    parser.add_argument("--intercept-terminal-range", type=float, default=8.0)
    parser.add_argument("--intercept-detection-timeout", type=float, default=1.0)
    parser.add_argument(
        "--intercept-yaw-mode",
        choices=("velocity", "look_at_target"),
        default=None,
        help="Velocity yaw is the legacy mode; look_at_target keeps the camera pointed at the assigned target.",
    )
    parser.add_argument("--target-asset-name", default="1M_Cube_Chamfer")
    parser.add_argument("--target-scale-m", type=float, default=None)
    parser.add_argument("--target-detection-filter", default="MSM_TargetActor_*")
    parser.add_argument("--save-images", action="store_true", help="Persist sampled Scene PNG frames.")
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
    if args.terminal_handoff_tuned:
        args.actor_2v2 = True
        args.execute_intercept = True
    if args.cv_5v5_d4d5_stress_200m:
        args.cv_5v5_d4d5_stress = True
    selected_modes = [args.actor_2v2, args.cv_5v5, args.cv_5v5_d4d5_stress]
    if sum(1 for selected in selected_modes if selected) > 1:
        raise SystemExit("--actor-2v2, --cv-5v5, and --cv-5v5-d4d5-stress are mutually exclusive")
    if (args.cv_5v5 or args.cv_5v5_d4d5_stress) and args.execute_intercept:
        raise SystemExit("ComputerVision 5v5 modes are read-only and cannot be combined with --execute-intercept")
    seeds = _parse_batch_seeds(args.batch_seeds, default=args.seed)
    results = []
    for seed in seeds:
        sequence_id = args.sequence_id if len(seeds) == 1 else f"{args.sequence_id}_seed{seed:03d}"
        result = _run_one_sequence(args, seed=seed, sequence_id=sequence_id)
        results.append(result)
        _print_sequence_result(result)
    if len(results) > 1:
        _write_batch_summary(args, seeds, results)
    return 0


def _run_one_sequence(args: argparse.Namespace, *, seed: int, sequence_id: str):
    settings_path = Path(args.settings)
    if args.actor_2v2 and args.settings == DEFAULT_SETTINGS:
        settings_path = Path(ACTOR_2V2_TUNED_SETTINGS if args.terminal_handoff_tuned else ACTOR_2V2_SETTINGS)
    if args.cv_5v5 and args.settings == DEFAULT_SETTINGS:
        settings_path = Path(CV_5V5_SETTINGS)
    if args.cv_5v5_d4d5_stress and args.settings == DEFAULT_SETTINGS:
        settings_path = Path(
            CV_5V5_D4D5_STRESS_200M_SETTINGS
            if args.cv_5v5_d4d5_stress_200m
            else CV_5V5_D4D5_STRESS_SETTINGS
        )
    scenario_name = (
        "blocks_actor_2v2"
        if args.actor_2v2
        else "blocks_cv_5v5"
        if args.cv_5v5
        else "blocks_cv_5v5_d4d5_stress"
        if args.cv_5v5_d4d5_stress
        else "blocks_readonly_smoke"
    )
    target_scale_m = (
        args.target_scale_m
        if args.target_scale_m is not None
        else 2.0
        if args.terminal_handoff_tuned
        else None
    )
    detection_filters = tuple(
        dict.fromkeys(
            item
            for item in (args.target_detection_filter, "MSM_TargetActor_*", "Intruder*")
            if item
        )
    )
    actor_config = (
        {
            "camera_vehicle_name": "Interceptor1",
            "camera_vehicle_names": ("Interceptor1", "Interceptor2"),
            "lidar_vehicle_name": "Interceptor1",
            "lidar_vehicle_names": ("Interceptor1", "Interceptor2"),
            "target_vehicle_names": (),
            "resource_vehicle_names": ("Interceptor1", "Interceptor2"),
            "target_actor_specs": default_2v2_actor_target_specs(
                target_z=args.intercept_altitude_z if args.execute_intercept else -2.0,
                asset_name=args.target_asset_name,
                target_scale_m=target_scale_m or 1.0,
            ),
            "detection_filter_names": detection_filters,
            "metadata": {
                "runtime_mode": "actor_2v2",
                "terminal_handoff_tuned": bool(args.terminal_handoff_tuned),
                "target_asset_name": args.target_asset_name,
            },
        }
        if args.actor_2v2
        else {}
    )
    if args.cv_5v5 or args.cv_5v5_d4d5_stress:
        cv_resources = default_cv_5v5_camera_vehicle_names()
        cv_secondaries = default_cv_5v5_secondary_vehicle_names()
        target_specs = (
            default_cv_5v5_d4d5_stress_actor_target_specs(
                target_z=-10.0,
                target_scale_m=target_scale_m or 10.0,
                asset_name=args.target_asset_name,
            )
            if args.cv_5v5_d4d5_stress
            else default_cv_5v5_actor_target_specs(
                target_z=-10.0,
                asset_name=args.target_asset_name,
                target_scale_m=target_scale_m or 1.0,
            )
        )
        follow_distance = 50.0 if args.cv_5v5_d4d5_stress else args.cv_camera_follow_distance
        actor_config = {
            "camera_vehicle_name": cv_resources[0],
            "camera_vehicle_names": cv_resources,
            "secondary_camera_vehicle_names": cv_secondaries,
            "capture_lidar": False,
            "cv_camera_follow_assignments": True,
            "cv_camera_follow_distance_m": follow_distance,
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
            "target_actor_specs": target_specs,
            "detection_filter_names": detection_filters,
            "detection_radius_cm": (260 if args.cv_5v5_d4d5_stress else 160) * 100,
            "metadata": {
                "runtime_mode": (
                    "computer_vision_5v5_d4d5_stress"
                    if args.cv_5v5_d4d5_stress
                    else "computer_vision_5v5"
                ),
                "secondary_camera_vehicle_names": cv_secondaries,
                "d4d5_stress_enabled": bool(args.cv_5v5_d4d5_stress),
                "secondary_height_target_m": 200.0 if args.cv_5v5_d4d5_stress_200m else 50.0,
                "target_asset_name": args.target_asset_name,
            },
        }
    base_config = BlocksSmokeConfig(
        scenario_name=scenario_name,
        duration_s=args.duration,
        dt_s=args.dt,
        seed=seed,
        output_root=Path(args.output_root),
        blocks_script=Path(args.blocks_script),
        settings_path=settings_path,
        blocks_args=tuple(args.blocks_arg)
        if args.blocks_arg is not None
        else BlocksSmokeConfig().blocks_args,
        prefer_nvidia_offload=not args.no_nvidia_offload,
        connection_timeout_s=args.connection_timeout,
        client_timeout_s=args.client_timeout,
        client_kind="multirotor" if args.execute_intercept else "vehicle",
        save_images=args.save_images,
        execute_intercept=args.execute_intercept,
        control_dt_s=args.control_dt,
        intercept_speed_mps=args.intercept_speed,
        intercept_altitude_ned_z=args.intercept_altitude_z,
        intercept_radius_m=args.intercept_radius,
        intercept_max_duration_s=args.intercept_max_duration,
        intercept_terminal_switch_range_m=args.intercept_terminal_range,
        intercept_detection_timeout_s=args.intercept_detection_timeout,
        intercept_yaw_mode=(
            args.intercept_yaw_mode
            or ("look_at_target" if args.terminal_handoff_tuned else "velocity")
        ),
        target_asset_name=args.target_asset_name,
        target_detection_filter=args.target_detection_filter,
        **actor_config,
    )
    selected_episode_specs = D4D5_STRESS_EPISODES if args.cv_5v5_d4d5_stress else DEFAULT_BLOCKS_EPISODES
    episode_specs = tuple(
        replace(spec, scenario_name=scenario_name, duration_s=args.duration, dt_s=args.dt)
        for spec in selected_episode_specs
    )
    result = run_blocks_sequence(
        base_config,
        sequence_id=sequence_id,
        episode_specs=episode_specs,
    )
    return result


def _print_sequence_result(result) -> None:
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


def _parse_batch_seeds(raw: str | None, *, default: int) -> list[int]:
    if raw is None or not raw.strip():
        return [int(default)]
    seeds = [int(item.strip()) for item in raw.split(",") if item.strip()]
    if not seeds:
        raise SystemExit("--batch-seeds did not contain any integer seeds")
    return seeds


def _write_batch_summary(args: argparse.Namespace, seeds: list[int], results: list[object]) -> Path:
    import json

    output_dir = Path(args.output_root) / args.sequence_id
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "blocks_batch_summary.json"
    payload = {
        "sequence_id": args.sequence_id,
        "seed_count": len(seeds),
        "seeds": seeds,
        "results": [
            {
                "sequence_id": result.sequence_id,
                "connected": result.connected,
                "episode_count": len(result.episode_results),
                "summary": str(result.output_paths["blocks_sequence_summary"]),
            }
            for result in results
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    report = output_dir / "BATCH_AIRSIM_REPORT.md"
    lines = [
        "# AirSim Batch Report",
        "",
        f"- Sequence prefix: `{args.sequence_id}`",
        f"- Seed count: {len(seeds)}",
        f"- Seeds: {', '.join(str(seed) for seed in seeds)}",
        "",
        "| Run | Connected | Episodes | Summary |",
        "| --- | --- | ---: | --- |",
    ]
    for result in results:
        lines.append(
            f"| `{result.sequence_id}` | {result.connected} | {len(result.episode_results)} | "
            f"`{result.output_paths['blocks_sequence_summary']}` |"
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
