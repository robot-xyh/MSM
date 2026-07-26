#!/usr/bin/env python3
"""Capture clean reserved-seed D3 planning frames for isolated replay."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.d3_intervention_batch_input import (
    D3InterventionBatchInputOptions,
    collect_d3_intervention_batch_input,
    write_d3_intervention_batch_input,
)


DEFAULT_D3_BUNDLE = (
    ROOT
    / "research_modules"
    / "d3_assignment_planner"
    / "outputs"
    / "formal_bc_development_20260720"
    / "bundle"
)
DEFAULT_D3_MANIFEST_SHA256 = (
    "a9213d65606a9e2f921040e153488c0f4cdebb10882fa16013fce5b59f9314c0"
)
DEFAULT_D3_POLICY_VERSION = "d3_shared_edge_actor_critic_v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="nominal")
    parser.add_argument("--scale", type=int, default=5)
    parser.add_argument("--target-count", type=int)
    parser.add_argument("--resource-count", type=int)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument(
        "--batch-id",
        default="d3-isolated-intervention-nominal-5v5-v1",
    )
    parser.add_argument(
        "--evaluated-at-utc",
        default="2026-07-26T00:00:00Z",
    )
    parser.add_argument("--d3-bundle", type=Path, default=DEFAULT_D3_BUNDLE)
    parser.add_argument(
        "--d3-manifest-sha256",
        default=DEFAULT_D3_MANIFEST_SHA256,
    )
    parser.add_argument(
        "--d3-policy-version",
        default=DEFAULT_D3_POLICY_VERSION,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    options = D3InterventionBatchInputOptions(
        scenario=args.scenario,
        scale=args.scale,
        target_count=args.target_count,
        resource_count=args.resource_count,
        duration_s=args.duration,
        batch_id=args.batch_id,
        evaluated_at_utc=args.evaluated_at_utc,
    )
    capture = collect_d3_intervention_batch_input(options)
    paths = write_d3_intervention_batch_input(
        args.output,
        capture,
        bundle_dir=args.d3_bundle,
        expected_bundle_manifest_sha256=args.d3_manifest_sha256,
        expected_policy_version=args.d3_policy_version,
    )
    print(f"seed_count={len(capture.seeds)}")
    print(f"frame_count={sum(len(item.frames) for item in capture.seeds)}")
    print(f"online_truth_use_count={capture.online_truth_use_count}")
    print("learning_bundle_loaded_online=false")
    print("treatment_plan_published=false")
    print("runtime_ack_created=false")
    print("production_assignment_authority=false")
    print("production_control_authority=false")
    print(f"manifest={paths['manifest'].resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
