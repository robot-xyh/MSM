#!/usr/bin/env python3
"""Run the ideal center-A/interceptor-B two-stage registration demonstration."""

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

from d5_terminal_association.ideal_registration_demo import (  # noqa: E402
    IdealRegistrationConfig,
    evaluate_ideal_registration,
    run_ideal_registration,
    run_seed_batch,
)
from d5_terminal_association.ideal_registration_reporting import (  # noqa: E402
    write_ideal_registration_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument("--batch-seed-start", type=int, default=20260810)
    parser.add_argument("--batch-seed-count", type=int, default=10)
    parser.add_argument("--duration-s", type=float, default=15.0)
    parser.add_argument("--physics-dt-s", type=float, default=0.1)
    parser.add_argument("--image-period-s", type=float, default=0.2)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            MODULE_ROOT
            / "outputs"
            / "ideal_20_target_two_stage_registration_20260810"
        ),
    )
    parser.add_argument(
        "--skip-media",
        action="store_true",
        help="write CSV/JSON/report without PNG and GIF (test/debug only)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_seed_count <= 0:
        raise ValueError("batch-seed-count must be positive")
    config = IdealRegistrationConfig(
        target_count=args.target_count,
        seed=args.seed,
        duration_s=args.duration_s,
        physics_dt_s=args.physics_dt_s,
        image_period_s=args.image_period_s,
    )
    online_run, offline_truth = run_ideal_registration(config)
    standard_metric = evaluate_ideal_registration(online_run, offline_truth)
    batch_seeds = tuple(
        range(args.batch_seed_start, args.batch_seed_start + args.batch_seed_count)
    )
    template_payload = asdict(config)
    template_payload["seed"] = args.batch_seed_start
    template = IdealRegistrationConfig(**template_payload)
    batch_metrics = list(run_seed_batch(batch_seeds, base_config=template))
    if args.seed not in batch_seeds:
        batch_metrics.insert(0, standard_metric)
    written = write_ideal_registration_artifacts(
        online_run,
        offline_truth,
        tuple(batch_metrics),
        args.output_dir,
        generate_media=not args.skip_media,
    )
    passed = sum(metric.acceptance_passed() for metric in batch_metrics)
    print(f"standard_seed={args.seed}")
    print(f"standard_end_to_end_accuracy={standard_metric.end_to_end_accuracy:.6f}")
    print(f"batch_passed={passed}/{len(batch_metrics)}")
    print(f"output_dir={args.output_dir.resolve()}")
    print(f"artifact_count={len(written)}")
    return 0 if passed == len(batch_metrics) else 2


if __name__ == "__main__":
    raise SystemExit(main())
