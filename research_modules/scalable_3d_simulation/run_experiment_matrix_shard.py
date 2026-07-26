#!/usr/bin/env python3
"""Initialize, run, resume, and merge formal R0 experiment shards."""

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
    load_training_seeds,
)
from research_modules.scalable_3d_simulation.experiment_matrix_sharding import (  # noqa: E402
    FORMAL_R0_DEFAULT_MINIMUM_FREE_BYTES,
    FORMAL_R0_DEFAULT_SHARD_COUNT,
    create_formal_r0_execution_plan,
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

    merge = subparsers.add_parser(
        "merge-r0",
        help="verify and merge every R0 shard without claiming full completion",
    )
    merge.add_argument("--execution-plan", type=Path, required=True)
    merge.add_argument("--output", type=Path)
    merge.add_argument("--write-d6-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "init-r0":
        base = ScenarioConfig.from_dict(
            json.loads(args.config.read_text(encoding="utf-8"))
        )
        registry = json.loads(
            args.seed_registry.read_text(encoding="utf-8")
        )
        declared_evaluation = tuple(
            int(value) for value in registry.get("evaluation_seeds", ())
        )
        requested_evaluation = tuple(
            dict.fromkeys(int(value) for value in args.evaluation_seeds)
        )
        if declared_evaluation != requested_evaluation:
            raise ValueError(
                "requested evaluation seeds differ from frozen seed registry"
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

    if args.command == "run-shard":
        result = run_experiment_matrix_shard(
            root=ROOT,
            execution_plan_path=args.execution_plan,
            shard_index=args.shard_index,
            resume=bool(args.resume),
            max_new_cells=args.max_new_cells,
            device=args.device,
            minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
        )
        for name, value in result.items():
            print(f"{name}: {value}")
        return 0 if result["status"] == "complete" else 3

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
