#!/usr/bin/env python3
"""Run paired R0/G1/A1/A2/A3/C1/F1 scalable-3D experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.experiment_matrix import (  # noqa: E402
    EXPERIMENT_VARIANTS,
    ExperimentMatrixPlan,
    ModelBundlePaths,
    load_training_seeds,
    run_experiment_matrix,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig  # noqa: E402
from research_modules.scalable_3d_simulation.scenarios import (  # noqa: E402
    AVAILABLE_SCENARIOS,
)


DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--variants", nargs="+", choices=EXPERIMENT_VARIANTS, default=["R0"]
    )
    parser.add_argument(
        "--scenarios", nargs="+", choices=AVAILABLE_SCENARIOS, default=["nominal"]
    )
    parser.add_argument("--scales", nargs="+", type=int, default=[5, 20, 50, 100, 200])
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 17, 27])
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--d3-bundle", type=Path)
    parser.add_argument("--d4-bundle", type=Path)
    parser.add_argument("--d5-graph-bundle", type=Path)
    parser.add_argument("--d5-active-vision-bundle", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--training-seed-registry", type=Path)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--allow-rule-fallback", action="store_true")
    parser.add_argument("--skip-d6", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = ScenarioConfig.from_dict(
        json.loads(args.config.read_text(encoding="utf-8"))
    )
    plan = ExperimentMatrixPlan(
        variants=tuple(args.variants),
        scenarios=tuple(args.scenarios),
        scales=tuple(args.scales),
        seeds=tuple(args.seeds),
        duration_s=args.duration,
        formal=bool(args.formal),
        allow_rule_fallback=bool(args.allow_rule_fallback),
        training_seeds=load_training_seeds(args.training_seed_registry),
    )
    paths = run_experiment_matrix(
        root=ROOT,
        output_dir=args.output,
        base_config=base,
        plan=plan,
        bundles=ModelBundlePaths(
            d3=args.d3_bundle,
            d4=args.d4_bundle,
            d5_graph=args.d5_graph_bundle,
            d5_active_vision=args.d5_active_vision_bundle,
        ),
        device=args.device,
        write_d6_report=not args.skip_d6,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
