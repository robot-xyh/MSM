from __future__ import annotations

import json

import pytest

from research_modules.scalable_3d_simulation.run_learning_dataset import (
    D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS,
    GENERATION_PLAN_SCHEMA_VERSION,
    _active_vision_test_seed_count,
    _load_schedule,
    _prepare_fresh_output,
    _validate_generation_plan,
)
from research_modules.scalable_3d_simulation.scenarios import AVAILABLE_SCENARIOS


def test_schedule_expands_cells_and_rejects_duplicates(tmp_path) -> None:
    path = tmp_path / "schedule.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": GENERATION_PLAN_SCHEMA_VERSION,
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
