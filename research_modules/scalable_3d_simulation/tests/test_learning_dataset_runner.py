from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.run_learning_dataset import (
    D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS,
    FORMAL_MINIMUM_SEEDS_PER_SCENARIO_SCALE,
    GENERATION_PLAN_SCHEMA_VERSION,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
    _active_vision_test_seed_count,
    _build_training_seed_registry,
    _load_schedule,
    _load_schedule_plan,
    _prepare_fresh_output,
    _validate_generation_plan,
)
from research_modules.scalable_3d_simulation.scenarios import AVAILABLE_SCENARIOS


SCALABLE_ROOT = Path(__file__).resolve().parents[1]


def test_schedule_expands_cells_and_rejects_duplicates(tmp_path) -> None:
    path = tmp_path / "schedule.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": GENERATION_PLAN_SCHEMA_VERSION,
                "reserved_evaluation_seeds": [102, 101, 102],
                "cells": [
                    {
                        "scenario": "nominal",
                        "scale": 5,
                        "seeds": [1, 2],
                        "duration_s": 1.5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cells = _load_schedule(path, default_duration_s=2.0)
    assert cells == (("nominal", 5, 1, 1.5), ("nominal", 5, 2, 1.5))
    loaded_cells, reserved = _load_schedule_plan(path, default_duration_s=2.0)
    assert loaded_cells == cells
    assert reserved == (101, 102)
    with pytest.raises(ValueError, match="duplicate generation cell"):
        _validate_generation_plan(
            (cells[0], cells[0]),
            reserved_evaluation_seeds=(101,),
            formal=False,
        )


def test_generation_and_evaluation_seed_overlap_fails_closed() -> None:
    with pytest.raises(ValueError, match="overlap"):
        _validate_generation_plan(
            (("nominal", 5, 17, 1.0),),
            reserved_evaluation_seeds=(17,),
            formal=False,
        )

    with pytest.raises(ValueError, match="non-negative"):
        _validate_generation_plan(
            (("nominal", 5, 17, 1.0),),
            reserved_evaluation_seeds=(-1,),
            formal=False,
        )


def test_formal_plan_requires_full_catalog_scales_and_twenty_reserved_seeds() -> None:
    cells = tuple(
        (scenario, scale, seed, 1.0)
        for scenario in AVAILABLE_SCENARIOS
        for scale in (5, 20, 50, 100, 200)
        for seed in range(100)
    )
    _validate_generation_plan(
        cells,
        reserved_evaluation_seeds=tuple(range(100, 120)),
        formal=True,
    )
    with pytest.raises(ValueError, match="at least 20"):
        _validate_generation_plan(
            cells,
            reserved_evaluation_seeds=tuple(range(100, 119)),
            formal=True,
        )


def test_formal_plan_rejects_missing_cartesian_cell_and_small_cell_denominator() -> None:
    complete = tuple(
        (scenario, scale, seed, 1.0)
        for scenario in AVAILABLE_SCENARIOS
        for scale in (5, 20, 50, 100, 200)
        for seed in range(FORMAL_MINIMUM_SEEDS_PER_SCENARIO_SCALE)
    )
    missing_cell = tuple(
        item
        for item in complete
        if not (item[0] == "nominal" and item[1] == 5)
    )
    with pytest.raises(ValueError, match="complete scenario/scale catalog"):
        _validate_generation_plan(
            missing_cell,
            reserved_evaluation_seeds=tuple(range(100, 120)),
            formal=True,
        )

    small_cell = complete[:-1]
    with pytest.raises(ValueError, match="seeds per scenario/scale"):
        _validate_generation_plan(
            small_cell,
            reserved_evaluation_seeds=tuple(range(100, 120)),
            formal=True,
        )


def test_formal_plan_fails_before_running_when_d5_unseen_seed_budget_is_too_small() -> None:
    cells = tuple(
        (scenario, scale, seed, 1.0)
        for scenario in AVAILABLE_SCENARIOS
        for scale in (5, 20, 50, 100, 200)
        for seed in range(20)
    )
    assert _active_vision_test_seed_count(20) < D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS
    with pytest.raises(ValueError, match="D5 active-vision test seeds"):
        _validate_generation_plan(
            cells,
            reserved_evaluation_seeds=tuple(range(100, 120)),
            formal=True,
        )


def test_prepare_fresh_output_accepts_existing_empty_directory(tmp_path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    _prepare_fresh_output(existing)
    assert existing.is_dir()

    created = tmp_path / "created"
    _prepare_fresh_output(created)
    assert created.is_dir()

    (existing / "record.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="not empty"):
        _prepare_fresh_output(existing)


def test_committed_balanced_schedule_meets_formal_preflight() -> None:
    cells, reserved = _load_schedule_plan(
        SCALABLE_ROOT / "configs" / "learning_generation_balanced_v1.json",
        default_duration_s=2.0,
    )
    assert len(cells) == 900
    assert len({seed for _, _, seed, _ in cells}) == 100
    assert reserved == tuple(range(1000, 1020))
    counts = {
        (scenario, scale): sum(
            row_scenario == scenario and row_scale == scale
            for row_scenario, row_scale, _, _ in cells
        )
        for scenario in AVAILABLE_SCENARIOS
        for scale in (5, 20, 50, 100, 200)
    }
    assert set(counts.values()) == {FORMAL_MINIMUM_SEEDS_PER_SCENARIO_SCALE}
    _validate_generation_plan(
        cells,
        reserved_evaluation_seeds=reserved,
        formal=True,
    )


def test_training_seed_registry_is_separate_versioned_and_disjoint() -> None:
    registry = _build_training_seed_registry(
        (2, 1, 2),
        reserved_evaluation_seeds=(101, 100),
        git_commit="a" * 40,
        repository_dirty=False,
        schedule_sha256="b" * 64,
    )
    assert registry["schema_version"] == TRAINING_SEED_REGISTRY_SCHEMA_VERSION
    assert registry["training_seeds"] == [1, 2]
    assert registry["reserved_evaluation_seeds"] == [100, 101]
    assert registry["overlap_count"] == 0

    with pytest.raises(ValueError, match="overlap"):
        _build_training_seed_registry(
            (1, 2),
            reserved_evaluation_seeds=(2, 3),
            git_commit="a" * 40,
            repository_dirty=False,
            schedule_sha256=None,
        )
