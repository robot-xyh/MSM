from __future__ import annotations

import json
from pathlib import Path

import pytest

import research_modules.scalable_3d_simulation.run_learning_dataset as learning_runner
from research_modules.scalable_3d_simulation.run_learning_dataset import (
    D5_ACTIVE_VISION_MINIMUM_UNSEEN_SEEDS,
    FORMAL_MINIMUM_SEEDS_PER_SCENARIO_SCALE,
    GENERATION_CHECKPOINT_SCHEMA_VERSION,
    GENERATION_PLAN_SCHEMA_VERSION,
    LEGACY_GENERATION_CHECKPOINT_SCHEMA_VERSION,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
    _active_vision_test_seed_count,
    _build_training_seed_registry,
    _directory_size_bytes,
    _generation_timing_summary,
    _load_schedule,
    _load_schedule_plan,
    _prepare_fresh_output,
    _validate_generation_plan,
    main as run_learning_dataset_main,
)
from research_modules.scalable_3d_simulation.scenarios import AVAILABLE_SCENARIOS


SCALABLE_ROOT = Path(__file__).resolve().parents[1]


def test_recon_track_cues_require_an_explicit_generation_flag() -> None:
    default_args = learning_runner.parse_args(["--output", "/tmp/unused"])
    enabled_args = learning_runner.parse_args(
        ["--output", "/tmp/unused", "--d5-recon-track-cues"]
    )

    assert default_args.d5_recon_track_cues is False
    assert enabled_args.d5_recon_track_cues is True


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
    unsupported = json.loads(path.read_text(encoding="utf-8"))
    unsupported["execution_order"] = "unknown"
    path.write_text(json.dumps(unsupported), encoding="utf-8")
    with pytest.raises(ValueError, match="execution order"):
        _load_schedule_plan(path, default_duration_s=2.0)
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


def test_generation_timing_summary_and_directory_size(tmp_path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "first.bin").write_bytes(b"abc")
    (nested / "second.bin").write_bytes(b"de")

    summary = _generation_timing_summary(
        (
            {"episode_run_wall_s": 0.75, "artifact_stage_wall_s": 1.25},
            {"episode_run_wall_s": 1.25, "artifact_stage_wall_s": 1.75},
        ),
        finalization_wall_s=4.0,
        generation_wall_s=10.0,
    )

    assert _directory_size_bytes(tmp_path) == 5
    assert summary == {
        "episode_run_wall_s": 2.0,
        "artifact_stage_wall_s": 3.0,
        "finalization_wall_s": 4.0,
        "generation_wall_s": 10.0,
        "other_or_preflight_wall_s": 1.0,
    }


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
    expected_catalog = {
        (scenario, scale)
        for scenario in AVAILABLE_SCENARIOS
        for scale in (5, 20, 50, 100, 200)
    }
    for start in range(0, len(cells), len(expected_catalog)):
        block = cells[start : start + len(expected_catalog)]
        assert {(scenario, scale) for scenario, scale, _, _ in block} == (
            expected_catalog
        )
    _validate_generation_plan(
        cells,
        reserved_evaluation_seeds=reserved,
        formal=True,
    )


def test_d5_a3_source_independent_schedule_is_disjoint_and_cell_complete() -> None:
    cells, reserved = _load_schedule_plan(
        SCALABLE_ROOT
        / "configs"
        / "d5_a3_source_independent_point_mass_v1.json",
        default_duration_s=3.0,
    )

    assert len(cells) == 100
    generation_seeds = {seed for _, _, seed, _ in cells}
    assert generation_seeds == set(range(21000, 21100))
    assert generation_seeds.isdisjoint(range(1000, 1020))
    assert reserved == tuple(range(1000, 1020))
    expected_catalog = {
        (scenario, scale)
        for scenario in AVAILABLE_SCENARIOS
        for scale in (5, 20, 50, 100, 200)
    }
    counts = {
        key: sum((scenario, scale) == key for scenario, scale, _, _ in cells)
        for key in expected_catalog
    }
    assert set(counts) == expected_catalog
    assert set(counts.values()) == {2, 3}
    assert sum(count == 3 for count in counts.values()) == 10
    assert all(duration_s == 3.0 for _, _, _, duration_s in cells)
    for start in (0, len(expected_catalog)):
        block = cells[start : start + len(expected_catalog)]
        assert {(scenario, scale) for scenario, scale, _, _ in block} == (
            expected_catalog
        )
    _validate_generation_plan(
        cells,
        reserved_evaluation_seeds=reserved,
        formal=False,
    )


def test_committed_capacity_probe_schedule_covers_each_scenario_once() -> None:
    cells, reserved = _load_schedule_plan(
        SCALABLE_ROOT / "configs" / "capacity_probe_200v200_v1.json",
        default_duration_s=2.0,
    )

    assert len(cells) == len(AVAILABLE_SCENARIOS) == 9
    assert {scenario for scenario, _, _, _ in cells} == set(AVAILABLE_SCENARIOS)
    assert {scale for _, scale, _, _ in cells} == {200}
    assert len({seed for _, _, seed, _ in cells}) == 9
    assert reserved == tuple(range(1000, 1020))
    _validate_generation_plan(
        cells,
        reserved_evaluation_seeds=reserved,
        formal=False,
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


def test_learning_generation_pauses_and_resumes_at_episode_boundary(
    tmp_path: Path,
) -> None:
    output = tmp_path / "resumable_generation"
    common = [
        "--output",
        str(output),
        "--scenarios",
        "nominal",
        "--scales",
        "2",
        "--seeds",
        "71",
        "72",
        "73",
        "--duration",
        "0.25",
        "--minimum-free-gb",
        "0",
        "--allow-dirty",
    ]

    assert run_learning_dataset_main([*common, "--max-episodes-per-run", "1"]) == 0

    paused = json.loads(
        (output / "generation_checkpoint.json").read_text(encoding="utf-8")
    )
    assert paused["schema_version"] == GENERATION_CHECKPOINT_SCHEMA_VERSION
    assert paused["state"] == "paused"
    assert paused["completed_episode_count"] == 1
    assert paused["remaining_episode_count"] == 2
    assert paused["invocation_count"] == 1
    assert not (output / "generation_summary.json").exists()

    plan_path = output / "generation_plan.json"
    original_plan = plan_path.read_bytes()
    tampered_plan = json.loads(original_plan)
    tampered_plan["cells"][0]["seed"] = 999
    plan_path.write_text(json.dumps(tampered_plan), encoding="utf-8")
    with pytest.raises(RuntimeError, match="stored plan"):
        run_learning_dataset_main([*common, "--resume"])
    plan_path.write_bytes(original_plan)

    episode_index = output / "learning_dataset" / "_staging" / "episodes.jsonl"
    original_index = episode_index.read_bytes()
    episode_index.write_bytes(original_index + original_index)
    with pytest.raises(RuntimeError, match="duplicate episode IDs"):
        run_learning_dataset_main([*common, "--resume"])
    episode_index.write_bytes(original_index)

    assert (
        run_learning_dataset_main(
            [*common, "--resume", "--max-episodes-per-run", "2"]
        )
        == 0
    )

    summary = json.loads(
        (output / "generation_summary.json").read_text(encoding="utf-8")
    )
    finalized = json.loads(
        (output / "generation_checkpoint.json").read_text(encoding="utf-8")
    )
    progress = [
        json.loads(line)
        for line in (output / "episode_progress.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert summary["completed_episode_count"] == 3
    assert summary["invocation_count"] == 2
    assert finalized["state"] == "finalized"
    assert finalized["completed_episode_count"] == 3
    assert finalized["remaining_episode_count"] == 0
    assert [row["sequence"] for row in progress] == [0, 1, 2]
    assert (output / "learning_dataset" / "episodes.jsonl").is_file()


def test_generation_checkpoint_advances_after_each_complete_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "crash_recovery"
    common = [
        "--output",
        str(output),
        "--scenarios",
        "nominal",
        "--scales",
        "2",
        "--seeds",
        "81",
        "82",
        "83",
        "--duration",
        "0.25",
        "--minimum-free-gb",
        "0",
        "--allow-dirty",
    ]
    original_run_episode = learning_runner.run_episode
    call_count = 0

    def fail_on_second_episode(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("injected episode failure")
        return original_run_episode(*args, **kwargs)

    monkeypatch.setattr(learning_runner, "run_episode", fail_on_second_episode)
    with pytest.raises(RuntimeError, match="injected episode failure"):
        learning_runner.main(common)

    checkpoint = json.loads(
        (output / "generation_checkpoint.json").read_text(encoding="utf-8")
    )
    assert checkpoint["state"] == "paused"
    assert checkpoint["completed_episode_count"] == 1
    assert checkpoint["next_sequence"] == 1
    assert checkpoint["last_completed_episode_id"]

    monkeypatch.setattr(learning_runner, "run_episode", original_run_episode)
    assert learning_runner.main([*common, "--resume"]) == 0
    finalized = json.loads(
        (output / "generation_checkpoint.json").read_text(encoding="utf-8")
    )
    assert finalized["state"] == "finalized"
    assert finalized["completed_episode_count"] == 3
    assert finalized["checkpoint_recovery_count"] == 0


def test_resume_reconciles_validated_progress_ahead_of_legacy_checkpoint(
    tmp_path: Path,
) -> None:
    output = tmp_path / "legacy_checkpoint_lag"
    common = [
        "--output",
        str(output),
        "--scenarios",
        "nominal",
        "--scales",
        "2",
        "--seeds",
        "91",
        "92",
        "93",
        "--duration",
        "0.25",
        "--minimum-free-gb",
        "0",
        "--allow-dirty",
    ]

    assert learning_runner.main([*common, "--max-episodes-per-run", "1"]) == 0
    first_checkpoint = json.loads(
        (output / "generation_checkpoint.json").read_text(encoding="utf-8")
    )
    assert (
        learning_runner.main(
            [*common, "--resume", "--max-episodes-per-run", "1"]
        )
        == 0
    )

    first_checkpoint["schema_version"] = LEGACY_GENERATION_CHECKPOINT_SCHEMA_VERSION
    (output / "generation_checkpoint.json").write_text(
        json.dumps(first_checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert learning_runner.main([*common, "--resume"]) == 0

    finalized = json.loads(
        (output / "generation_checkpoint.json").read_text(encoding="utf-8")
    )
    assert finalized["schema_version"] == GENERATION_CHECKPOINT_SCHEMA_VERSION
    assert finalized["completed_episode_count"] == 3
    assert finalized["checkpoint_recovery_count"] == 1
    assert finalized["recovered_progress_row_count"] == 1
    assert finalized["invocation_count"] == 3
