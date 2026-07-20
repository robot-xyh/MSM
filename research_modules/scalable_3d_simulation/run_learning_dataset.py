#!/usr/bin/env python3
"""Stream truth-isolated scalable-3D episodes into learning datasets."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.learning_export import (
    BatchLearningArtifactWriter,
)
from research_modules.scalable_3d_simulation.learning_runtime import (
    LearningRuntimeOptions,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import IntegratedStackConfig
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.scenarios import (
    AVAILABLE_SCENARIOS,
    make_curriculum_scenario,
)


GENERATION_PLAN_SCHEMA_VERSION = "scalable3d-learning-generation-plan-v1"
DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"
FORMAL_SCALES = frozenset({5, 20, 50, 100, 200})
D5_ACTIVE_VISION_TEST_FRACTION = 0.2
D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS = 20


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schedule", type=Path)
    parser.add_argument("--scales", type=int, nargs="+", default=[5, 20, 50, 100, 200])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=AVAILABLE_SCENARIOS,
        default=["nominal"],
    )
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--reserved-evaluation-seeds", type=int, nargs="*", default=[])
    parser.add_argument("--minimum-free-gb", type=float, default=5.0)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.duration <= 0.0:
        raise ValueError("--duration must be positive")
    if args.minimum_free_gb < 0.0:
        raise ValueError("--minimum-free-gb must be non-negative")
    output = args.output.resolve()
    _prepare_fresh_output(output)
    base = ScenarioConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
    cells = (
        _load_schedule(args.schedule, default_duration_s=args.duration)
        if args.schedule is not None
        else _cartesian_cells(args.scenarios, args.scales, args.seeds, args.duration)
    )
    reserved = tuple(sorted(set(int(seed) for seed in args.reserved_evaluation_seeds)))
    _validate_generation_plan(
        cells,
        reserved_evaluation_seeds=reserved,
        formal=bool(args.formal),
    )
    repository_dirty = _repository_dirty()
    if repository_dirty and not args.allow_dirty:
        raise RuntimeError(
            "learning-data generation requires a clean repository; use --allow-dirty only for development"
        )
    if args.formal and args.allow_dirty:
        raise ValueError("formal generation cannot use --allow-dirty")
    if args.formal and not _is_git_ignored(output):
        raise RuntimeError("formal output must be under a git-ignored artifact directory")
    _require_free_space(output.parent, args.minimum_free_gb)

    writer = BatchLearningArtifactWriter(output / "learning_dataset")
    plan = {
        "schema_version": GENERATION_PLAN_SCHEMA_VERSION,
        "formal": bool(args.formal),
        "git_commit": _git_output(["rev-parse", "HEAD"]),
        "repository_dirty": repository_dirty,
        "base_config": str(args.config.resolve()),
        "cell_count": len(cells),
        "generation_seed_count": len({seed for _, _, seed, _ in cells}),
        "reserved_evaluation_seeds": list(reserved),
        "d5_active_vision_split_preflight": {
            "test_fraction": D5_ACTIVE_VISION_TEST_FRACTION,
            "minimum_unseen_seed_count": D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS,
            "planned_test_seed_count": _active_vision_test_seed_count(
                len({seed for _, _, seed, _ in cells})
            ),
        },
        "cells": [
            {
                "scenario": scenario,
                "scale": scale,
                "seed": seed,
                "duration_s": duration,
            }
            for scenario, scale, seed, duration in cells
        ],
    }
    _write_json(output / "generation_plan.json", plan)
    progress_path = output / "episode_progress.jsonl"
    rows: list[dict[str, Any]] = []
    for index, (scenario, scale, seed, duration_s) in enumerate(cells):
        _require_free_space(output, args.minimum_free_gb)
        config = make_curriculum_scenario(
            scenario,
            scale=scale,
            seed=seed,
            duration_s=duration_s,
            base=base,
        )
        resolved = resolve_learning_runtime(
            config,
            LearningRuntimeOptions(),
            stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
        )
        result = run_episode(resolved.config, module_stack=resolved.stack)
        episode_row = writer.stage_episode(
            config=result.config,
            manifest=result.manifest,
            artifacts=resolved.stack.learning_artifacts(),
            offline_truth_labels=result.offline_truth_labels,
        )
        row = {
            "sequence": index,
            "scenario": scenario,
            "scale": scale,
            "seed": seed,
            "duration_s": duration_s,
            "finite_state": bool(result.summary["finite_state"]),
            "online_truth_use_count": int(result.summary["online_truth_use_count"]),
            "real_time_factor": float(result.summary["real_time_factor"]),
            "repository_dirty": bool(result.manifest.repository_dirty),
            **dict(episode_row),
        }
        if not row["finite_state"] or row["online_truth_use_count"] != 0:
            raise RuntimeError(f"episode failed safety checks: {scenario}/{scale}/{seed}")
        if args.formal and row["repository_dirty"]:
            raise RuntimeError("formal episode manifest became dirty during generation")
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
        rows.append(row)
        print(
            f"[{index + 1}/{len(cells)}] scenario={scenario} scale={scale} "
            f"seed={seed} rtf={row['real_time_factor']:.3f}"
        )

    paths = writer.finalize()
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    if args.formal:
        required = (
            summary.get("d5_dataset_finalized") is True,
            summary.get("d5_active_vision_dataset_finalized") is True,
        )
        if not all(required):
            raise RuntimeError(
                "formal dataset finalization failed: "
                f"d5_graph={summary.get('d5_dataset_finalization_reason')}, "
                "d5_active_vision="
                f"{summary.get('d5_active_vision_dataset_finalization_reason')}"
            )
    _write_progress_csv(output / "episode_progress.csv", rows)
    _write_json(
        output / "generation_summary.json",
        {
            **plan,
            "completed_episode_count": len(rows),
            "learning_export_summary": summary,
        },
    )
    print(f"learning_summary={paths['summary']}")
    return 0


def _cartesian_cells(
    scenarios: Iterable[str],
    scales: Iterable[int],
    seeds: Iterable[int],
    duration_s: float,
) -> tuple[tuple[str, int, int, float], ...]:
    return tuple(
        (str(scenario), int(scale), int(seed), float(duration_s))
        for scenario in scenarios
        for scale in scales
        for seed in seeds
    )


def _load_schedule(
    path: Path,
    *,
    default_duration_s: float,
) -> tuple[tuple[str, int, int, float], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != GENERATION_PLAN_SCHEMA_VERSION:
        raise ValueError("unsupported learning generation schedule schema")
    raw_cells = payload.get("cells")
    if not isinstance(raw_cells, list) or not raw_cells:
        raise ValueError("learning generation schedule requires non-empty cells")
    cells: list[tuple[str, int, int, float]] = []
    for raw in raw_cells:
        if not isinstance(raw, Mapping):
            raise ValueError("schedule cells must be JSON objects")
        scenario = str(raw["scenario"]).strip().lower()
        scale = int(raw["scale"])
        duration = float(raw.get("duration_s", default_duration_s))
        seeds = raw.get("seeds")
        if not isinstance(seeds, list) or not seeds:
            raise ValueError("schedule cell seeds must be a non-empty list")
        cells.extend((scenario, scale, int(seed), duration) for seed in seeds)
    return tuple(cells)


def _validate_generation_plan(
    cells: tuple[tuple[str, int, int, float], ...],
    *,
    reserved_evaluation_seeds: tuple[int, ...],
    formal: bool,
) -> None:
    if not cells:
        raise ValueError("generation plan must not be empty")
    keys: set[tuple[str, int, int]] = set()
    for scenario, scale, seed, duration in cells:
        if scenario not in AVAILABLE_SCENARIOS:
            raise ValueError(f"unknown scenario in generation plan: {scenario}")
        if scale <= 0 or seed < 0 or duration <= 0.0:
            raise ValueError("generation scale/duration must be positive and seed non-negative")
        key = (scenario, scale, seed)
        if key in keys:
            raise ValueError(f"duplicate generation cell: {key}")
        keys.add(key)
    generation_seeds = {seed for _, _, seed, _ in cells}
    overlap = generation_seeds & set(reserved_evaluation_seeds)
    if overlap:
        raise ValueError(f"generation and reserved evaluation seeds overlap: {sorted(overlap)}")
    if formal:
        if {scale for _, scale, _, _ in cells} != FORMAL_SCALES:
            raise ValueError("formal generation requires scales 5/20/50/100/200")
        if {scenario for scenario, _, _, _ in cells} != set(AVAILABLE_SCENARIOS):
            raise ValueError("formal generation requires the complete scenario catalog")
        if len(reserved_evaluation_seeds) < 20:
            raise ValueError("formal generation requires at least 20 reserved evaluation seeds")
        planned_test_seed_count = _active_vision_test_seed_count(len(generation_seeds))
        if planned_test_seed_count < D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS:
            raise ValueError(
                "formal generation requires enough unique generation seeds for at least "
                f"{D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS} D5 active-vision test seeds; "
                f"planned={planned_test_seed_count} from {len(generation_seeds)} unique seeds"
            )


def _active_vision_test_seed_count(unique_seed_count: int) -> int:
    count = int(unique_seed_count)
    if count < 3:
        return 0
    return max(
        1,
        min(count - 2, round(count * D5_ACTIVE_VISION_TEST_FRACTION)),
    )


def _prepare_fresh_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise FileExistsError(f"output directory is not empty: {path}")
        return
    path.mkdir(parents=True)


def _require_free_space(path: Path, minimum_free_gb: float) -> None:
    probe = path if path.exists() else path.parent
    free_bytes = shutil.disk_usage(probe).free
    required = float(minimum_free_gb) * 1024**3
    if free_bytes < required:
        raise RuntimeError(
            f"insufficient free space: {free_bytes / 1024**3:.2f} GiB < {minimum_free_gb:.2f} GiB"
        )


def _repository_dirty() -> bool:
    return bool(_git_output(["status", "--porcelain"]).strip())


def _is_git_ignored(path: Path) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=ROOT,
        check=False,
    )
    return completed.returncode == 0


def _git_output(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_progress_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
