#!/usr/bin/env python3
"""Run one scalable three-dimensional point-mass baseline episode."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.learning_runtime import (
    add_learning_runtime_arguments,
    learning_runtime_options_from_args,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--drone-count",
        type=int,
        default=None,
        help="set interceptor count; also sets target count unless --target-count is given",
    )
    parser.add_argument("--target-count", type=int, default=None)
    parser.add_argument("--recon-count", type=int, default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research_modules/scalable_3d_simulation/outputs/episode"),
    )
    parser.add_argument("--plot", action="store_true")
    parser.add_argument(
        "--integrated-stack",
        action="store_true",
        help="run the truth-free D1-D7 rule baseline and write commands back to the world",
    )
    parser.add_argument("--gif", action="store_true", help="write a 3D GIF from offline truth")
    parser.add_argument("--mp4", action="store_true", help="write a 3D MP4 when ffmpeg is available")
    add_learning_runtime_arguments(parser)
    return parser.parse_args()


def load_config(path: Path) -> ScenarioConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ScenarioConfig.from_dict(payload)


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    target_count = args.target_count
    if args.drone_count is not None and target_count is None:
        target_count = args.drone_count
    resolved_resource_count = (
        config.resource_count if args.drone_count is None else args.drone_count
    )
    resolved_target_count = config.target_count if target_count is None else target_count
    scale_overridden = args.drone_count is not None or args.target_count is not None
    updates = {
        "resource_count": resolved_resource_count,
        "target_count": resolved_target_count,
        "recon_count": config.recon_count if args.recon_count is None else args.recon_count,
        "duration_s": config.duration_s if args.duration is None else args.duration,
        "seed": config.seed if args.seed is None else args.seed,
    }
    if scale_overridden:
        updates.update(
            {
                "scenario_name": (
                    f"{config.scenario_name}_cli_"
                    f"{resolved_resource_count}v{resolved_target_count}"
                ),
                "scenario_version": (
                    f"{config.scenario_version}-cli-"
                    f"{resolved_resource_count}v{resolved_target_count}"
                ),
            }
        )
    config = replace(config, **updates)
    learning_options = learning_runtime_options_from_args(args)
    module_stack = None
    if args.integrated_stack:
        resolved_runtime = resolve_learning_runtime(config, learning_options)
        config = resolved_runtime.config
        module_stack = resolved_runtime.stack
    elif learning_options.requested:
        raise ValueError("optional learning bundles require --integrated-stack")
    animation_formats = tuple(
        name for name, enabled in (("gif", args.gif), ("mp4", args.mp4)) if enabled
    )
    result = run_episode(
        config,
        output_dir=args.output,
        write_plot=args.plot,
        animation_formats=animation_formats,
        module_stack=module_stack,
    )
    print(f"episode_id={result.manifest.episode_id}")
    print(f"scale={config.resource_count}v{config.target_count}")
    print(f"finite_state={result.summary['finite_state']}")
    print(f"online_truth_use_count={result.summary['online_truth_use_count']}")
    print(f"online_observation_count={result.summary['online_observation_count']}")
    print(f"module_stack_enabled={result.summary['module_stack_enabled']}")
    print(f"real_time_factor={result.summary['real_time_factor']:.3f}")
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
