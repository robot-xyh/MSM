#!/usr/bin/env python3
"""Run the independent dual-optical multi-target AirSim experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PACKAGE_PARENT = Path(__file__).resolve().parents[1]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from dual_optical_40target.core import CameraSpec, ScenarioConfig  # noqa: E402
from dual_optical_40target.reporting import (  # noqa: E402
    generate_experiment_report,
    load_experiment_result,
)
from dual_optical_40target.runtime import (  # noqa: E402
    DualOpticalAirSimRunner,
    reprocess_enhanced_outputs,
    write_json,
)


DEFAULT_OUTPUT = Path(
    "research_modules/independent_experiments/dual_optical_40target/outputs/"
    "airsim_seed_20260811_epipolar_mht_run01"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--duration-s", type=float, default=12.0)
    parser.add_argument("--sample-rate-hz", type=float, default=100.0)
    parser.add_argument("--target-speed-mps", type=float, default=50.0)
    parser.add_argument(
        "--scan-mode",
        choices=("triangle", "continuous_360"),
        default="triangle",
    )
    parser.add_argument("--scan-period-s", type=float, default=1.0)
    parser.add_argument(
        "--target-motion-profile",
        choices=("legacy_crossing", "split_0_minus30"),
        default="legacy_crossing",
    )
    parser.add_argument("--gimbal-pose-error", action="store_true")
    parser.add_argument("--gimbal-fixed-bias-mrad", type=float, default=0.4)
    parser.add_argument("--gimbal-jitter-rms-mrad", type=float, default=0.3)
    parser.add_argument("--clock-speed", type=float, default=0.1)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--blocks-script",
        type=Path,
        default=Path("Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh"),
    )
    parser.add_argument("--api-port", type=int, default=41451)
    parser.add_argument("--connection-timeout-s", type=float, default=90.0)
    parser.add_argument("--client-timeout-s", type=float, default=10.0)
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument(
        "--save-keyframes",
        action="store_true",
        help="save AirSim camera PNG keyframes; disabled by default",
    )
    parser.add_argument("--no-keyframes", action="store_true")
    parser.add_argument("--no-nvidia-offload", action="store_true")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="rebuild figures and report from records already in --output-dir",
    )
    parser.add_argument(
        "--reprocess-enhanced",
        action="store_true",
        help="recompute enhanced association and upgrade saved metrics to v3",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.report_only:
        result = load_experiment_result(args.output_dir)
        if args.reprocess_enhanced:
            result = reprocess_enhanced_outputs(result)
    else:
        config = ScenarioConfig(
            target_count=args.target_count,
            seed=args.seed,
            duration_s=args.duration_s,
            sample_rate_hz=args.sample_rate_hz,
            target_speed_mps=args.target_speed_mps,
            scan_mode=args.scan_mode,
            scan_period_s=args.scan_period_s,
            target_motion_profile=args.target_motion_profile,
            gimbal_pose_error_enabled=args.gimbal_pose_error,
            gimbal_fixed_bias_mrad=args.gimbal_fixed_bias_mrad,
            gimbal_jitter_rms_mrad=args.gimbal_jitter_rms_mrad,
            api_port=args.api_port,
            clock_speed=args.clock_speed,
        )
        runner = DualOpticalAirSimRunner(
            config=config,
            camera_spec=CameraSpec(),
            output_dir=args.output_dir,
            blocks_script=args.blocks_script,
            launch_blocks=not args.no_launch,
            connection_timeout_s=args.connection_timeout_s,
            client_timeout_s=args.client_timeout_s,
            save_keyframes=args.save_keyframes and not args.no_keyframes,
            prefer_nvidia_offload=not args.no_nvidia_offload,
        )
        result = runner.run()
    report_paths = generate_experiment_report(result)
    manifest_path = result.output_dir / "record_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["report_artifacts"] = {
        name: str(path.relative_to(result.output_dir))
        for name, path in report_paths.items()
    }
    write_json(manifest_path, manifest)
    metrics = result.metrics
    print(f"output_dir={result.output_dir.resolve()}")
    print(f"report={report_paths['report'].resolve()}")
    print(
        "matches={matches} correct={correct} precision={precision} recall={recall} "
        "truth_leakage={leakage} overall={overall}".format(
            matches=metrics["match_count"],
            correct=metrics["correct_match_count"],
            precision=metrics["association_precision"],
            recall=metrics["association_full_target_recall"],
            leakage=metrics["online_truth_leakage_count"],
            overall=metrics["acceptance"]["overall_passed"],
        )
    )
    enhanced = metrics.get("enhanced_association") or {}
    if enhanced:
        print(
            "enhanced_selected={selected} enhanced_confirmed={confirmed} "
            "enhanced_correct={correct} enhanced_false={false} "
            "enhanced_recall={recall} fit_reduction={reduction}".format(
                selected=enhanced.get("selected_match_count"),
                confirmed=enhanced.get("confirmed_match_count"),
                correct=enhanced.get("correct_match_count"),
                false=enhanced.get("false_match_count"),
                recall=enhanced.get("association_full_target_recall"),
                reduction=enhanced.get("fit_reduction_ratio"),
            )
        )
    return 0 if metrics["acceptance"]["overall_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
