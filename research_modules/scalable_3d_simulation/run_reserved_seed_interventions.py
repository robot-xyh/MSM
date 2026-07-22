#!/usr/bin/env python3
"""Run isolated D3/D4 interventions on reserved scalable-3D seeds."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    ReservedSeedInterventionOptions,
    execute_reserved_seed_interventions,
    resolve_d3_development_bundle_binding,
    write_reserved_seed_intervention_execution,
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
DEFAULT_D4_BUNDLE = (
    ROOT
    / "research_modules"
    / "d4_distributed_fallback"
    / "outputs"
    / "region_resource_bc_900_20260720"
    / "bundle"
)
DEFAULT_OUTPUT = SCALABLE_ROOT / "outputs" / "reserved_seed_interventions_v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="nominal")
    parser.add_argument("--scale", type=int, default=5)
    parser.add_argument("--target-count", type=int)
    parser.add_argument("--resource-count", type=int)
    parser.add_argument("--duration", type=float, default=2.2)
    parser.add_argument("--created-at-utc", default="2026-07-21T00:00:00Z")
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    options = ReservedSeedInterventionOptions(
        scenario=args.scenario,
        scale=args.scale,
        target_count=args.target_count,
        resource_count=args.resource_count,
        duration_s=args.duration,
        created_at_utc=args.created_at_utc,
    )
    d3_bundle = resolve_d3_development_bundle_binding(
        args.d3_bundle,
        expected_manifest_sha256=args.d3_manifest_sha256,
        expected_policy_version=args.d3_policy_version,
    )
    execution = execute_reserved_seed_interventions(
        options,
        d3_bundle=d3_bundle,
        d4_bundle_dir=args.d4_bundle,
    )
    paths = write_reserved_seed_intervention_execution(args.output, execution)
    d3_treatment_applied = sum(
        item.learning_cost_applied
        for item in execution.d3_execution.arms
        if item.arm_specification.arm_kind == "treatment"
    )
    d4_treatment_applied = sum(
        item.isolated_treatment_safe_adopted
        for item in execution.d4_manifest.arm_evidence
        if item.arm.value == "treatment_candidate"
    )
    d4_rule_fallback = sum(
        item.rule_fallback_used
        for item in execution.d4_manifest.arm_evidence
        if item.arm.value == "treatment_candidate"
    )
    print(f"reserved_seed_count={len(execution.sources)}")
    print(f"d3_arm_count={len(execution.d3_execution.arms)}")
    print(f"d3_treatment_applied_count={d3_treatment_applied}")
    print(f"d4_arm_count={len(execution.d4_manifest.arm_evidence)}")
    print(f"d4_treatment_applied_count={d4_treatment_applied}")
    print(f"d4_rule_fallback_count={d4_rule_fallback}")
    print(f"online_truth_use_count={execution.source_truth_violation_count}")
    print("ppo=false")
    print("assist=false")
    print("authority=false")
    print("rule_fallback=true")
    print(f"report={paths['report_cn'].resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
