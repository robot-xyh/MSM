#!/usr/bin/env python3
"""Run scale-and-seed curriculum baselines for the scalable 3D environment."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.reporting import write_batch_outputs


DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scales", type=int, nargs="+", default=[5, 20, 50, 100, 200])
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 17, 27])
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research_modules/scalable_3d_simulation/outputs/curriculum"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = ScenarioConfig.from_dict(
        json.loads(args.config.read_text(encoding="utf-8"))
    )
    results = []
    for scale in args.scales:
        for seed in args.seeds:
            config = replace(
                base,
                scenario_name=f"nominal_{scale}v{scale}",
                scenario_version=f"{scale}v{scale}-nominal-v1",
                target_count=scale,
                resource_count=scale,
                recon_count=max(1, int(math.ceil(scale / 25.0))),
                seed=seed,
                duration_s=args.duration,
            )
            episode_dir = args.output / f"{scale}v{scale}" / f"seed_{seed}"
            result = run_episode(config, output_dir=episode_dir)
            results.append(result)
            print(
                f"scale={scale} seed={seed} finite={result.summary['finite_state']} "
                f"rtf={result.summary['real_time_factor']:.3f}"
            )
    paths = write_batch_outputs(results, args.output)
    print(f"episodes={len(results)}")
    print(f"summary={paths['episode_summary_csv'].resolve()}")
    print(f"report={paths['report'].resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
