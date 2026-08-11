#!/usr/bin/env python3
"""Run the ideal irregular-crossing narrow-FOV scan and registration scenario."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
for path in (MODULE_ROOT / "src", REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from d5_terminal_association.ideal_irregular_crossing_demo import (  # noqa: E402
    IrregularCrossingConfig,
    evaluate_irregular_crossing,
    run_irregular_crossing_experiment,
    run_irregular_seed_batch,
)
from d5_terminal_association.ideal_irregular_crossing_reporting import (  # noqa: E402
    write_irregular_crossing_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument("--batch-seed-start", type=int, default=20260810)
    parser.add_argument("--batch-seed-count", type=int, default=10)
    parser.add_argument("--duration-s", type=float, default=15.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            MODULE_ROOT
            / "outputs"
            / "ideal_20_target_irregular_crossing_20260810"
        ),
    )
    parser.add_argument("--skip-media", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_seed_count <= 0:
        raise ValueError("batch-seed-count must be positive")
    config = IrregularCrossingConfig(
        target_count=args.target_count,
        seed=args.seed,
        duration_s=args.duration_s,
    )
    online_run, offline_truth = run_irregular_crossing_experiment(config)
    standard_metrics = evaluate_irregular_crossing(online_run, offline_truth)
    template_payload = asdict(config)
    template_payload["seed"] = args.batch_seed_start
    batch_metrics = run_irregular_seed_batch(
        range(args.batch_seed_start, args.batch_seed_start + args.batch_seed_count),
        base_config=IrregularCrossingConfig(**template_payload),
    )
    written = write_irregular_crossing_artifacts(
        online_run,
        offline_truth,
        standard_metrics,
        batch_metrics,
        args.output_dir,
        generate_media=not args.skip_media,
    )
    mechanical = next(
        metric for metric in standard_metrics if metric.mode == "mechanical_2s"
    )
    coverage_safe = next(
        metric for metric in standard_metrics if metric.mode == "coverage_safe"
    )
    batch_passed = sum(
        metric.coverage_safe_acceptance_passed() for metric in batch_metrics
    )
    print(f"standard_seed={args.seed}")
    print(
        "geometry="
        f"radial_span:{online_run.geometry.initial_radial_span_m:.3f},"
        f"altitude_span:{online_run.geometry.initial_altitude_span_m:.3f},"
        f"minimum_separation:{online_run.geometry.minimum_pairwise_3d_separation_m:.3f},"
        f"crossing_A:{len(online_run.geometry.projected_crossing_pairs_a)},"
        f"crossing_B:{len(online_run.geometry.projected_crossing_pairs_b)}"
    )
    print(
        "mechanical_2s="
        f"center:{mechanical.center_discovery_ratio:.3f},"
        f"B:{mechanical.camera_b_cued_observation_ratio:.3f},"
        f"chain:{mechanical.complete_chain_ratio:.3f}"
    )
    print(
        "coverage_safe="
        f"center:{coverage_safe.center_discovery_ratio:.3f},"
        f"B:{coverage_safe.camera_b_cued_observation_ratio:.3f},"
        f"chain:{coverage_safe.complete_chain_ratio:.3f},"
        f"duration:{coverage_safe.scan_actual_duration_s:.3f}"
    )
    print(f"coverage_safe_batch_passed={batch_passed}/{len(batch_metrics)}")
    print(f"output_dir={args.output_dir.resolve()}")
    print(f"artifact_count={len(written)}")
    return 0 if batch_passed == len(batch_metrics) else 2


if __name__ == "__main__":
    raise SystemExit(main())
