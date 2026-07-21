#!/usr/bin/env python3
"""Run scale-and-seed curriculum baselines for the scalable 3D environment."""

from __future__ import annotations

import argparse
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
from research_modules.scalable_3d_simulation.learning_export import (
    BatchLearningArtifactWriter,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.reporting import write_batch_outputs
from research_modules.scalable_3d_simulation.module_stack import IntegratedStackConfig
from research_modules.scalable_3d_simulation.scenarios import (
    AVAILABLE_SCENARIOS,
    make_curriculum_scenario,
)


DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scales", type=int, nargs="+", default=[5, 20, 50, 100, 200])
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 17, 27])
    parser.add_argument("--scenarios", nargs="+", default=["nominal"], choices=AVAILABLE_SCENARIOS)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument(
        "--integrated-stack",
        action="store_true",
        help="run each episode through the truth-free D1-D7 rule baseline",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research_modules/scalable_3d_simulation/outputs/curriculum"),
    )
    parser.add_argument(
        "--export-learning-data",
        action="store_true",
        help="write split-safe multi-seed D3/D4/D5 training artifacts",
    )
    parser.add_argument(
        "--d5-recon-track-cues",
        action="store_true",
        help=(
            "give recon cameras truth-free observation cues from the current "
            "versioned assignment plan; disabled by default"
        ),
    )
    add_learning_runtime_arguments(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = ScenarioConfig.from_dict(
        json.loads(args.config.read_text(encoding="utf-8"))
    )
    learning_options = learning_runtime_options_from_args(args)
    if learning_options.requested and not args.integrated_stack:
        raise ValueError("optional learning bundles require --integrated-stack")
    if args.export_learning_data and not args.integrated_stack:
        raise ValueError("--export-learning-data requires --integrated-stack")
    results = []
    learning_writer = (
        BatchLearningArtifactWriter(args.output / "learning_dataset")
        if args.export_learning_data
        else None
    )
    for scenario in args.scenarios:
        for scale in args.scales:
            for seed in args.seeds:
                config = make_curriculum_scenario(
                    scenario,
                    scale=scale,
                    seed=seed,
                    duration_s=args.duration,
                    base=base,
                )
                module_stack = None
                if args.integrated_stack:
                    resolved_runtime = resolve_learning_runtime(
                        config,
                        learning_options,
                        stack_config=IntegratedStackConfig(
                            capture_learning_artifacts=args.export_learning_data,
                            d5_recon_track_cues_enabled=(
                                args.d5_recon_track_cues
                            ),
                        ),
                    )
                    config = resolved_runtime.config
                    module_stack = resolved_runtime.stack
                episode_dir = args.output / scenario / f"{scale}v{scale}" / f"seed_{seed}"
                result = run_episode(
                    config,
                    output_dir=episode_dir,
                    module_stack=module_stack,
                )
                if learning_writer is not None:
                    artifact_provider = getattr(module_stack, "learning_artifacts", None)
                    if not callable(artifact_provider):
                        raise RuntimeError("integrated stack did not expose learning artifacts")
                    learning_writer.stage_episode(
                        config=result.config,
                        manifest=result.manifest,
                        artifacts=artifact_provider(),
                        offline_truth_labels=result.offline_truth_labels,
                        online_messages=result.online_messages,
                    )
                results.append(result)
                print(
                    f"scenario={scenario} scale={scale} seed={seed} "
                    f"finite={result.summary['finite_state']} "
                    f"rtf={result.summary['real_time_factor']:.3f}"
                )
    paths = write_batch_outputs(results, args.output)
    learning_paths = {} if learning_writer is None else learning_writer.finalize()
    print(f"episodes={len(results)}")
    print(f"summary={paths['episode_summary_csv'].resolve()}")
    print(f"report={paths['report'].resolve()}")
    if learning_paths:
        print(f"learning_summary={learning_paths['summary'].resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
