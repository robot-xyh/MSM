#!/usr/bin/env python3
"""Run isolated multi-cycle D3 control/treatment point-mass episodes."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.isolated_paired_rollout import (
    IsolatedPairedRolloutOptions,
    execute_isolated_paired_rollouts,
    write_isolated_paired_rollout_execution,
)
from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    resolve_d3_development_bundle_binding,
)


SCALABLE_ROOT = Path(__file__).resolve().parent
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
DEFAULT_OUTPUT = SCALABLE_ROOT / "outputs" / "isolated_paired_rollout_v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="nominal")
    parser.add_argument("--scale", type=int, default=5)
    parser.add_argument("--target-count", type=int)
    parser.add_argument("--resource-count", type=int)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1000])
    parser.add_argument("--created-at-utc", default="2026-07-22T00:00:00Z")
    parser.add_argument("--d3-bundle", type=Path, default=DEFAULT_D3_BUNDLE)
    parser.add_argument(
        "--d3-manifest-sha256",
        default=DEFAULT_D3_MANIFEST_SHA256,
    )
    parser.add_argument(
        "--d3-policy-version",
        default=DEFAULT_D3_POLICY_VERSION,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    options = IsolatedPairedRolloutOptions(
        scenario=args.scenario,
        scale=args.scale,
        target_count=args.target_count,
        resource_count=args.resource_count,
        duration_s=args.duration,
        seeds=tuple(args.seeds),
        created_at_utc=args.created_at_utc,
    )
    binding = resolve_d3_development_bundle_binding(
        args.d3_bundle,
        expected_manifest_sha256=args.d3_manifest_sha256,
        expected_policy_version=args.d3_policy_version,
    )
    execution = execute_isolated_paired_rollouts(options, d3_bundle=binding)
    paths = write_isolated_paired_rollout_execution(args.output, execution)
    print(f"pairs={len(execution.pairs)}")
    print(f"d3_bundle_loaded={execution.d3_bundle_loaded}")
    print(
        "treatment_learning_applied_seeds="
        f"{sum(pair.treatment.learning_applied_cycle_count > 0 for pair in execution.pairs)}"
    )
    print(
        "final_binding_changed_seeds="
        f"{sum(pair.final_binding_changed for pair in execution.pairs)}"
    )
    print(f"manifest={paths['manifest'].resolve()}")
    print(f"report={paths['report_cn'].resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
