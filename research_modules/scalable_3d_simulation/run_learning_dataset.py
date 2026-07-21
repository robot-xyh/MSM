#!/usr/bin/env python3
"""Stream truth-isolated scalable-3D episodes into learning datasets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
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
TRAINING_SEED_REGISTRY_SCHEMA_VERSION = "scalable3d-training-seed-registry-v1"
DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"
FORMAL_SCALES = frozenset({5, 20, 50, 100, 200})
FORMAL_MINIMUM_SEEDS_PER_SCENARIO_SCALE = 20
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
    parser.add_argument("--reserved-evaluation-seeds", type=int, nargs="*", default=None)
    parser.add_argument("--minimum-free-gb", type=float, default=5.0)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    generation_started = time.perf_counter()
    args = parse_args(argv)
    if args.duration <= 0.0:
        raise ValueError("--duration must be positive")
    if args.minimum_free_gb < 0.0:
        raise ValueError("--minimum-free-gb must be non-negative")
    output = args.output.resolve()
    base = ScenarioConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
    if args.schedule is not None:
        cells, schedule_reserved = _load_schedule_plan(
            args.schedule,
            default_duration_s=args.duration,
        )
    else:
        cells = _cartesian_cells(args.scenarios, args.scales, args.seeds, args.duration)
        schedule_reserved = ()
    cli_reserved = (
        None
        if args.reserved_evaluation_seeds is None
        else tuple(sorted(set(int(seed) for seed in args.reserved_evaluation_seeds)))
    )
    if cli_reserved is not None and schedule_reserved and cli_reserved != schedule_reserved:
        raise ValueError(
            "CLI reserved evaluation seeds do not match the versioned schedule"
        )
    reserved = schedule_reserved if cli_reserved is None else cli_reserved
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
    _prepare_fresh_output(output)

    writer = BatchLearningArtifactWriter(
        output / "learning_dataset",
        formal=bool(args.formal),
    )
    git_commit = _git_output(["rev-parse", "HEAD"])
    schedule_sha256 = None if args.schedule is None else _sha256_file(args.schedule)
    generation_seeds = tuple(sorted({seed for _, _, seed, _ in cells}))
    plan = {
        "schema_version": GENERATION_PLAN_SCHEMA_VERSION,
        "formal": bool(args.formal),
        "git_commit": git_commit,
        "repository_dirty": repository_dirty,
        "base_config": str(args.config.resolve()),
        "schedule": None if args.schedule is None else str(args.schedule.resolve()),
        "schedule_sha256": schedule_sha256,
        "cell_count": len(cells),
        "generation_seed_count": len(generation_seeds),
        "reserved_evaluation_seeds": list(reserved),
        "d5_active_vision_split_preflight": {
            "test_fraction": D5_ACTIVE_VISION_TEST_FRACTION,
            "minimum_unseen_seed_count": D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS,
            "planned_test_seed_count": _active_vision_test_seed_count(
                len(generation_seeds)
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
    registry = _build_training_seed_registry(
        generation_seeds,
        reserved_evaluation_seeds=reserved,
        git_commit=git_commit,
        repository_dirty=repository_dirty,
        schedule_sha256=schedule_sha256,
    )
    _write_json(output / "training_seed_registry.json", registry)
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
        episode_started = time.perf_counter()
        result = run_episode(resolved.config, module_stack=resolved.stack)
        episode_run_wall_s = time.perf_counter() - episode_started
        staging_started = time.perf_counter()
        episode_row = writer.stage_episode(
            config=result.config,
            manifest=result.manifest,
            artifacts=resolved.stack.learning_artifacts(),
            offline_truth_labels=result.offline_truth_labels,
        )
        artifact_stage_wall_s = time.perf_counter() - staging_started
        row = {
            "sequence": index,
            "scenario": scenario,
            "scale": scale,
            "seed": seed,
            "duration_s": duration_s,
            "finite_state": bool(result.summary["finite_state"]),
            "online_truth_use_count": int(result.summary["online_truth_use_count"]),
            "real_time_factor": float(result.summary["real_time_factor"]),
            "episode_run_wall_s": episode_run_wall_s,
            "artifact_stage_wall_s": artifact_stage_wall_s,
            "episode_and_stage_wall_s": (
                episode_run_wall_s + artifact_stage_wall_s
            ),
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
            f"seed={seed} rtf={row['real_time_factor']:.3f} "
            f"run={episode_run_wall_s:.1f}s stage={artifact_stage_wall_s:.1f}s"
        )

    finalization_started = time.perf_counter()
    paths = writer.finalize()
    finalization_wall_s = time.perf_counter() - finalization_started
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    if args.formal:
        required = (
            summary.get("d4_dataset_finalized") is True,
            summary.get("d5_dataset_finalized") is True,
            summary.get("d5_active_vision_dataset_finalized") is True,
        )
        if not all(required):
            raise RuntimeError(
                "formal dataset finalization failed: "
                f"d4_region={summary.get('d4_dataset_finalization_reason')}, "
                f"d5_graph={summary.get('d5_dataset_finalization_reason')}, "
                "d5_active_vision="
                f"{summary.get('d5_active_vision_dataset_finalization_reason')}"
            )
    _write_progress_csv(output / "episode_progress.csv", rows)
    generation_wall_s = time.perf_counter() - generation_started
    timing_summary = _generation_timing_summary(
        rows,
        finalization_wall_s=finalization_wall_s,
        generation_wall_s=generation_wall_s,
    )
    _write_json(
        output / "generation_summary.json",
        {
            **plan,
            "completed_episode_count": len(rows),
            "training_seed_registry": "training_seed_registry.json",
            "training_seed_registry_sha256": _sha256_file(
                output / "training_seed_registry.json"
            ),
            "learning_export_summary": summary,
            "timing_summary": timing_summary,
            "learning_dataset_size_bytes": _directory_size_bytes(
                output / "learning_dataset"
            ),
            "free_space_bytes_after_finalization": shutil.disk_usage(output).free,
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
    cells, _ = _load_schedule_plan(
        path,
        default_duration_s=default_duration_s,
    )
    return cells


def _load_schedule_plan(
    path: Path,
    *,
    default_duration_s: float,
) -> tuple[tuple[tuple[str, int, int, float], ...], tuple[int, ...]]:
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
    raw_reserved = payload.get("reserved_evaluation_seeds", [])
    if not isinstance(raw_reserved, list):
        raise ValueError("schedule reserved_evaluation_seeds must be a list")
    reserved = tuple(sorted(set(int(seed) for seed in raw_reserved)))
    return tuple(cells), reserved


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
    if any(seed < 0 for seed in reserved_evaluation_seeds):
        raise ValueError("reserved evaluation seeds must be non-negative")
    overlap = generation_seeds & set(reserved_evaluation_seeds)
    if overlap:
        raise ValueError(f"generation and reserved evaluation seeds overlap: {sorted(overlap)}")
    if formal:
        expected_catalog = {
            (scenario, scale)
            for scenario in AVAILABLE_SCENARIOS
            for scale in FORMAL_SCALES
        }
        observed_catalog = {(scenario, scale) for scenario, scale, _, _ in cells}
        if observed_catalog != expected_catalog:
            missing = sorted(expected_catalog - observed_catalog)
            extra = sorted(observed_catalog - expected_catalog)
            raise ValueError(
                "formal generation requires the complete scenario/scale catalog; "
                f"missing={missing}, extra={extra}"
            )
        seed_count_by_cell = {
            key: len(
                {
                    seed
                    for scenario, scale, seed, _ in cells
                    if (scenario, scale) == key
                }
            )
            for key in expected_catalog
        }
        insufficient_cells = {
            f"{scenario}/{scale}": count
            for (scenario, scale), count in sorted(seed_count_by_cell.items())
            if count < FORMAL_MINIMUM_SEEDS_PER_SCENARIO_SCALE
        }
        if insufficient_cells:
            raise ValueError(
                "formal generation requires at least "
                f"{FORMAL_MINIMUM_SEEDS_PER_SCENARIO_SCALE} seeds per scenario/scale; "
                f"insufficient={insufficient_cells}"
            )
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


def _build_training_seed_registry(
    training_seeds: Iterable[int],
    *,
    reserved_evaluation_seeds: Iterable[int],
    git_commit: str,
    repository_dirty: bool,
    schedule_sha256: str | None,
) -> dict[str, Any]:
    training = tuple(sorted(set(int(seed) for seed in training_seeds)))
    reserved = tuple(sorted(set(int(seed) for seed in reserved_evaluation_seeds)))
    overlap = sorted(set(training) & set(reserved))
    if not training or any(seed < 0 for seed in training):
        raise ValueError("training seed registry requires non-negative training seeds")
    if any(seed < 0 for seed in reserved):
        raise ValueError("training seed registry requires non-negative reserved seeds")
    if overlap:
        raise ValueError(f"training seed registry overlap: {overlap}")
    return {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": str(git_commit),
        "repository_dirty": bool(repository_dirty),
        "schedule_sha256": schedule_sha256,
        "training_seed_count": len(training),
        "training_seeds": list(training),
        "reserved_evaluation_seed_count": len(reserved),
        "reserved_evaluation_seeds": list(reserved),
        "overlap_count": 0,
    }


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


def _generation_timing_summary(
    rows: Iterable[Mapping[str, Any]],
    *,
    finalization_wall_s: float,
    generation_wall_s: float,
) -> dict[str, float]:
    items = tuple(rows)
    episode_run_wall_s = sum(float(row["episode_run_wall_s"]) for row in items)
    artifact_stage_wall_s = sum(
        float(row["artifact_stage_wall_s"]) for row in items
    )
    accounted_wall_s = (
        episode_run_wall_s + artifact_stage_wall_s + float(finalization_wall_s)
    )
    return {
        "episode_run_wall_s": episode_run_wall_s,
        "artifact_stage_wall_s": artifact_stage_wall_s,
        "finalization_wall_s": float(finalization_wall_s),
        "generation_wall_s": float(generation_wall_s),
        "other_or_preflight_wall_s": max(
            0.0,
            float(generation_wall_s) - accounted_wall_s,
        ),
    }


def _directory_size_bytes(path: Path) -> int:
    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file()
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
