#!/usr/bin/env python3
"""Run reserved D3 interventions through isolated D7 point-mass worlds."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.isolated_physical_rollout import (
    CheckpointPhysicalRolloutOptions,
    execute_checkpoint_paired_physical_rollouts,
    write_checkpoint_paired_physical_rollouts,
)
from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    INTERVENTION_KINDS,
    ReservedSeedInterventionOptions,
    execute_reserved_seed_interventions,
    resolve_d3_development_bundle_binding,
)
from research_modules.scalable_3d_simulation.run_reserved_seed_interventions import (
    DEFAULT_D3_BUNDLE,
    DEFAULT_D3_MANIFEST_SHA256,
    DEFAULT_D3_POLICY_VERSION,
    DEFAULT_D4_BUNDLE,
)


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent
    / "outputs"
    / "checkpoint_paired_physical_v1"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="nominal")
    parser.add_argument(
        "--intervention-kind",
        choices=("auto", *INTERVENTION_KINDS),
        default="auto",
    )
    parser.add_argument("--scale", type=int, default=5)
    parser.add_argument("--target-count", type=int)
    parser.add_argument("--resource-count", type=int)
    parser.add_argument("--source-duration", type=float, default=2.2)
    parser.add_argument("--maximum-physical-duration", type=float)
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
    parser.add_argument("--d4-bundle", type=Path, default=DEFAULT_D4_BUNDLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-d6", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = resolve_d3_development_bundle_binding(
        args.d3_bundle,
        expected_manifest_sha256=args.d3_manifest_sha256,
        expected_policy_version=args.d3_policy_version,
    )
    intervention = execute_reserved_seed_interventions(
        ReservedSeedInterventionOptions(
            scenario=args.scenario,
            scale=args.scale,
            target_count=args.target_count,
            resource_count=args.resource_count,
            duration_s=args.source_duration,
            intervention_kind=args.intervention_kind,
            created_at_utc=args.created_at_utc,
        ),
        d3_bundle=bundle,
        d4_bundle_dir=args.d4_bundle,
    )
    execution = execute_checkpoint_paired_physical_rollouts(
        intervention,
        options=CheckpointPhysicalRolloutOptions(
            maximum_duration_s=args.maximum_physical_duration,
            evaluate_with_d6=not args.skip_d6,
            created_at_utc=args.created_at_utc,
        ),
    )
    paths = write_checkpoint_paired_physical_rollouts(args.output, execution)
    changed = sum(
        tuple(
            (row["resource_id"], row["global_track_id"])
            for row in pair.control.plan_payload["assignments"]
        )
        != tuple(
            (row["resource_id"], row["global_track_id"])
            for row in pair.treatment.plan_payload["assignments"]
        )
        for pair in execution.pairs
    )
    print(f"pair_count={len(execution.pairs)}")
    print(f"binding_changed_seed_count={changed}")
    print(
        "control_applied_command_count="
        f"{sum(item.control.applied_command_count for item in execution.pairs)}"
    )
    print(
        "treatment_applied_command_count="
        f"{sum(item.treatment.applied_command_count for item in execution.pairs)}"
    )
    print("production_runtime_ack=false")
    print("counterfactual_available=false")
    print("causal_available=false")
    print(f"manifest={paths['manifest'].resolve()}")
    print(f"report={paths['report_cn'].resolve()}")
    if not args.skip_d6:
        print(f"d6_report={paths['d6_report_cn'].resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
