#!/usr/bin/env python3
"""Run the D5 long-range ComputerVision scan and registration campaign."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
root_path = str(ROOT)
if root_path not in sys.path:
    sys.path.insert(0, root_path)
for relative in (
    "research_modules",
    "research_modules/d1_sensor_fusion/src",
    "research_modules/d2_data_association",
    "research_modules/d3_assignment_planner/src",
    "research_modules/d4_distributed_fallback",
    "research_modules/d5_terminal_association/src",
    "research_modules/d6_evaluation_metrics",
    "research_modules/d7_proportional_guidance",
):
    candidate = str(ROOT / relative)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from airsim_runtime.long_range_cv_scan import (  # noqa: E402
    LongRangeCVScenario,
    SUPPORTED_GEOMETRY_PROFILES,
    run_long_range_cv_campaign,
)


DEFAULT_OUTPUT = Path(
    "research_modules/airsim_runtime/outputs/d5_cv_long_range_20target_20260810"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument("--duration", type=float, default=12.0)
    parser.add_argument("--logic-rate-hz", type=float, default=100.0)
    parser.add_argument(
        "--target-speed",
        type=float,
        default=50.0,
        help="Magnitude of every inbound actor velocity in metres per second.",
    )
    parser.add_argument(
        "--snapshot-interval",
        type=float,
        default=2.0,
        help="Logical seconds between authorized center/interceptor PNG snapshots.",
    )
    parser.add_argument(
        "--mode",
        choices=("mechanical_2s", "coverage_safe", "both"),
        default="both",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--blocks-script",
        type=Path,
        default=Path("Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh"),
    )
    parser.add_argument("--api-port", type=int, default=41451)
    parser.add_argument("--connection-timeout", type=float, default=90.0)
    parser.add_argument("--client-timeout", type=float, default=5.0)
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--no-nvidia-offload", action="store_true")
    parser.add_argument("--blocks-arg", action="append", default=None)
    parser.add_argument(
        "--diagnostic-target-scale",
        type=float,
        default=1.0,
        help="Use 2.0 only for an explicitly labeled long-range visibility diagnostic.",
    )
    parser.add_argument(
        "--geometry-profile",
        choices=SUPPORTED_GEOMETRY_PROFILES,
        default="baseline_v1",
        help="Keep baseline_v1 for paired comparison; use crossing_calibration_v1 for crossing coverage.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.target_count <= 0:
        raise SystemExit("--target-count must be positive")
    if args.target_speed <= 0.0:
        raise SystemExit("--target-speed must be positive")
    if args.snapshot_interval <= 0.0:
        raise SystemExit("--snapshot-interval must be positive")
    if args.diagnostic_target_scale <= 0.0:
        raise SystemExit("--diagnostic-target-scale must be positive")
    if args.diagnostic_target_scale not in {1.0, 2.0}:
        raise SystemExit("--diagnostic-target-scale supports only 1.0 or 2.0")
    modes = (
        ("mechanical_2s", "coverage_safe")
        if args.mode == "both"
        else (args.mode,)
    )
    scenario = LongRangeCVScenario(
        target_count=args.target_count,
        seed=args.seed,
        duration_s=args.duration,
        logic_rate_hz=args.logic_rate_hz,
        target_speed_min_mps=args.target_speed,
        target_speed_max_mps=args.target_speed,
        snapshot_interval_s=args.snapshot_interval,
        target_scale=args.diagnostic_target_scale,
        api_port=args.api_port,
        geometry_profile=args.geometry_profile,
    )
    result = run_long_range_cv_campaign(
        scenario=scenario,
        output_dir=args.output_dir,
        modes=modes,
        blocks_script=args.blocks_script,
        blocks_args=tuple(args.blocks_arg)
        if args.blocks_arg
        else ("-windowed", "-ResX=640", "-ResY=480", "-NoVSync", "-NoHMD", "-NoSound"),
        launch_blocks=not args.no_launch,
        connection_timeout_s=args.connection_timeout,
        client_timeout_s=args.client_timeout,
        prefer_nvidia_offload=not args.no_nvidia_offload,
    )
    print(f"settings={result.settings_path.resolve()}")
    for episode in result.episode_results:
        gate_status = (
            episode.metrics["coverage_gate_passed"]
            if episode.metrics.get("coverage_gate_required")
            else "not_required"
        )
        print(
            "mode={mode} center_discovery={center:.3f} interceptor_observed={interceptor:.3f} "
            "cue_completion={cue:.3f} association_accuracy={accuracy} "
            "id_switch_count={idsw} mot_gate={mot_gate} record_gate={record_gate} gate={gate}".format(
                mode=episode.mode,
                center=float(episode.metrics["center_unique_discovery_ratio"]),
                interceptor=float(episode.metrics["interceptor_observed_ratio"]),
                cue=float(episode.metrics["interceptor_cue_completion_ratio"]),
                accuracy=episode.metrics["association_accuracy"],
                idsw=episode.metrics["id_switch_count"],
                mot_gate=episode.metrics["mot_continuity"]["aggregate"]["gate_passed"],
                record_gate=episode.metrics["execution_record_gate_passed"],
                gate=gate_status,
            )
        )
    print(f"output_dir={result.output_dir.resolve()}")
    required_failures = []
    for episode in result.episode_results:
        failed = not episode.metrics.get("execution_record_gate_passed", False)
        failed = failed or bool(
            episode.metrics.get("coverage_gate_required")
            and not episode.metrics.get("coverage_gate_passed")
        )
        if failed:
            required_failures.append(episode.mode)
    if required_failures:
        print(f"required_gate_failures={','.join(required_failures)}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
