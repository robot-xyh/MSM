#!/usr/bin/env python3
"""Initialize, run, resume, and merge hash-bound experiment shards."""

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
)
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (  # noqa: E402
    FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES,
    FORMAL_R0_DEFAULT_SHARD_COUNT,
    create_experiment_matrix_execution_plan,
    create_formal_r0_execution_plan,
    load_experiment_matrix_execution_plan,
    merge_experiment_matrix_shards,
    run_experiment_matrix_shard,
)
from research_modules.scalable_3d_simulation.models import (  # noqa: E402
    ScenarioConfig,
)
from research_modules.scalable_3d_simulation.scenarios import (  # noqa: E402
    AVAILABLE_SCENARIOS,
)


DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"
DEFAULT_SEED_REGISTRY = (
    Path(__file__).with_name("configs")
    / "formal_evaluation_seed_registry_v1.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser(
        "init-r0",
        help="freeze the complete formal parent and its 900-cell R0 scope",
    )
    initialize.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    initialize.add_argument(
        "--seed-registry",
        type=Path,
        default=DEFAULT_SEED_REGISTRY,
    )
    initialize.add_argument(
        "--evaluation-seeds",
        nargs="+",
        type=int,
        default=list(range(1000, 1020)),
    )
    initialize.add_argument("--duration", type=float, default=2.0)
    initialize.add_argument(
        "--shard-count",
        type=int,
        default=FORMAL_R0_DEFAULT_SHARD_COUNT,
    )
    initialize.add_argument("--output", type=Path, required=True)
    initialize.add_argument("--created-at-utc")

    initialize_scope = subparsers.add_parser(
        "init-scope",
        help=(
            "freeze one R0 or learned scope from a complete parent inventory"
        ),
    )
    initialize_scope.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )
    initialize_scope.add_argument(
        "--seed-registry",
        type=Path,
        default=DEFAULT_SEED_REGISTRY,
    )
    initialize_scope.add_argument(
        "--evaluation-seeds",
        nargs="+",
        type=int,
        default=list(range(1000, 1020)),
    )
    initialize_scope.add_argument(
        "--scenarios",
        nargs="+",
        choices=AVAILABLE_SCENARIOS,
        default=list(AVAILABLE_SCENARIOS),
    )
    initialize_scope.add_argument(
        "--scales",
        nargs="+",
        type=int,
        default=[5, 20, 50, 100, 200],
    )
    initialize_scope.add_argument(
        "--scope-variants",
        nargs="+",
        type=str.upper,
        choices=EXPERIMENT_VARIANTS,
        required=True,
    )
    initialize_scope.add_argument("--duration", type=float, default=2.0)
    initialize_scope.add_argument(
        "--shard-count",
        type=int,
        default=FORMAL_R0_DEFAULT_SHARD_COUNT,
    )
    initialize_scope.add_argument(
        "--formal",
        action="store_true",
        help=(
            "require a clean source and the complete formal parent matrix"
        ),
    )
    initialize_scope.add_argument(
        "--allow-rule-fallback",
        action="store_true",
        help="development only; formal plans reject this option",
    )
    initialize_scope.add_argument(
        "--device",
        default="cpu",
        help="learning device frozen into the execution preflight",
    )
    initialize_scope.add_argument("--output", type=Path, required=True)
    initialize_scope.add_argument("--created-at-utc")
    _add_model_bundle_arguments(initialize_scope)

    run = subparsers.add_parser(
        "run-shard",
        help="execute one hash-bound shard",
    )
    run.add_argument("--execution-plan", type=Path, required=True)
    run.add_argument("--shard-index", type=int, required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--max-new-cells", type=int)
    run.add_argument("--device", default="cpu")
    run.add_argument(
        "--minimum-free-gib",
        type=float,
        default=FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES / 1024**3,
        help=(
            "pause before a new cell when available disk falls below this "
            "GiB reserve"
        ),
    )
    _add_model_bundle_arguments(run)

    merge = subparsers.add_parser(
        "merge-r0",
        help="verify and merge every R0 shard without claiming full completion",
    )
    merge.add_argument("--execution-plan", type=Path, required=True)
    merge.add_argument("--output", type=Path)
    merge.add_argument("--write-d6-report", action="store_true")

    merge_scope = subparsers.add_parser(
        "merge-scope",
        help="verify and merge every shard in a declared execution scope",
    )
    merge_scope.add_argument("--execution-plan", type=Path, required=True)
    merge_scope.add_argument("--output", type=Path)
    merge_scope.add_argument("--write-d6-report", action="store_true")
    return parser.parse_args()


def _add_model_bundle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--d3-model-bundle", type=Path)
    parser.add_argument("--d4-model-bundle", type=Path)
    parser.add_argument("--d5-graph-model-bundle", type=Path)
    parser.add_argument("--d5-active-vision-model-bundle", type=Path)


def _model_bundle_paths(args: argparse.Namespace) -> ModelBundlePaths:
    return ModelBundlePaths(
        d3=getattr(args, "d3_model_bundle", None),
        d4=getattr(args, "d4_model_bundle", None),
        d5_graph=getattr(args, "d5_graph_model_bundle", None),
        d5_active_vision=getattr(
            args,
            "d5_active_vision_model_bundle",
            None,
        ),
    )


def _read_base_config(path: Path) -> ScenarioConfig:
    return ScenarioConfig.from_dict(
        json.loads(path.read_text(encoding="utf-8"))
    )


def _read_seed_registry(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("seed registry must be a JSON object")
    return payload


def _validated_evaluation_seeds(
    args: argparse.Namespace,
    registry: dict[str, object],
    *,
    require_registry_match: bool,
) -> tuple[int, ...]:
    requested = tuple(
        dict.fromkeys(int(value) for value in args.evaluation_seeds)
    )
    if require_registry_match:
        declared = tuple(
            int(value) for value in registry.get("evaluation_seeds", ())
        )
        if declared != requested:
            raise ValueError(
                "requested evaluation seeds differ from frozen seed registry"
            )
    return requested


def main() -> int:
    args = parse_args()
    if args.command == "init-r0":
        base = _read_base_config(args.config)
        registry = _read_seed_registry(args.seed_registry)
        requested_evaluation = _validated_evaluation_seeds(
            args,
            registry,
            require_registry_match=True,
        )
        plan = ExperimentMatrixPlan(
            variants=EXPERIMENT_VARIANTS,
            scenarios=AVAILABLE_SCENARIOS,
            scales=(5, 20, 50, 100, 200),
            seeds=requested_evaluation,
            duration_s=args.duration,
            formal=True,
            allow_rule_fallback=False,
            training_seeds=load_training_seeds(args.seed_registry),
        )
        path = create_formal_r0_execution_plan(
            root=ROOT,
            output_root=args.output,
            base_config=base,
            parent_plan=plan,
            shard_count=args.shard_count,
            created_at_utc=args.created_at_utc,
        )
        print(f"execution_plan: {path}")
        return 0

    if args.command == "init-scope":
        base = _read_base_config(args.config)
        registry = _read_seed_registry(args.seed_registry)
        scope_variants = tuple(args.scope_variants)
        requested_evaluation = _validated_evaluation_seeds(
            args,
            registry,
            require_registry_match=bool(args.formal),
        )
        parent_variants = (
            EXPERIMENT_VARIANTS
            if args.formal
            else tuple(dict.fromkeys(("R0", *scope_variants)))
        )
        plan = ExperimentMatrixPlan(
            variants=parent_variants,
            scenarios=tuple(args.scenarios),
            scales=tuple(args.scales),
            seeds=requested_evaluation,
            duration_s=args.duration,
            formal=bool(args.formal),
            allow_rule_fallback=bool(args.allow_rule_fallback),
            training_seeds=load_training_seeds(args.seed_registry),
        )
        path = create_experiment_matrix_execution_plan(
            root=ROOT,
            output_root=args.output,
            base_config=base,
            parent_plan=plan,
            scope_variants=scope_variants,
            shard_count=args.shard_count,
            bundles=_model_bundle_paths(args),
            device=args.device,
            created_at_utc=args.created_at_utc,
        )
        print(f"execution_plan: {path}")
        return 0

    if args.command == "run-shard":
        result = run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=args.execution_plan,
            shard_index=args.shard_index,
            resume=bool(args.resume),
            max_new_cells=args.max_new_cells,
            device=args.device,
            minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
            bundles=_model_bundle_paths(args),
        )
        for name, value in result.items():
            print(f"{name}: {value}")
        return 0 if result["status"] == "complete" else 3

    if args.command == "merge-r0":
        execution = load_experiment_matrix_execution_plan(
            args.execution_plan
        )
        if tuple(execution["scope"]["variants"]) != ("R0",):
            raise ValueError("merge-r0 requires an R0-only execution scope")

    paths = merge_experiment_matrix_shards(
        root=ROOT,
        execution_plan_path=args.execution_plan,
        output_dir=args.output,
        write_d6_report=bool(args.write_d6_report),
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
