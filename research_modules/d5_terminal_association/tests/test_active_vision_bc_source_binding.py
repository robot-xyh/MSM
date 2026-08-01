from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from d5_terminal_association.active_vision_bc_training import (
    ACTIVE_VISION_BC_FROZEN_CONFIG_SCHEMA_VERSION,
    ACTIVE_VISION_BC_SOURCE_BINDING_SCHEMA_VERSION,
    ActiveVisionBcConfig,
    load_frozen_behavior_cloning_config,
    point_mass_development_source_binding,
    validate_frozen_behavior_cloning_binding,
)


def _write_json(path: Path, payload: object) -> str:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return sha256(path.read_bytes()).hexdigest()


def _source_fixture(tmp_path: Path) -> tuple[SimpleNamespace, dict[str, Path]]:
    commit = "d" * 40
    schedule_sha256 = "e" * 64
    training_seeds = [22100, 22101, 22102]
    reserved_seeds = [1000, 1001]
    cells = [
        {"duration_s": 3.0, "scale": 5, "scenario": "nominal", "seed": seed}
        for seed in training_seeds
    ]
    plan = {
        "schema_version": "scalable3d-learning-generation-plan-v1",
        "git_commit": commit,
        "repository_dirty": False,
        "formal": False,
        "schedule_sha256": schedule_sha256,
        "cell_count": 3,
        "generation_seed_count": 3,
        "reserved_evaluation_seeds": reserved_seeds,
        "cells": cells,
    }
    registry = {
        "schema_version": "scalable3d-training-seed-registry-v1",
        "git_commit": commit,
        "repository_dirty": False,
        "schedule_sha256": schedule_sha256,
        "training_seed_count": 3,
        "training_seeds": training_seeds,
        "reserved_evaluation_seed_count": 2,
        "reserved_evaluation_seeds": reserved_seeds,
        "overlap_count": 0,
    }
    paths = {
        "plan": tmp_path / "generation_plan.json",
        "summary": tmp_path / "generation_summary.json",
        "registry": tmp_path / "training_seed_registry.json",
    }
    plan_sha256 = _write_json(paths["plan"], plan)
    registry_sha256 = _write_json(paths["registry"], registry)
    summary = {
        **plan,
        "completed_episode_count": 3,
        "training_seed_registry": paths["registry"].name,
        "training_seed_registry_sha256": registry_sha256,
        "checkpoint_recovery_count": 0,
        "timing_summary": {"generation_wall_s": 12.5},
    }
    summary_sha256 = _write_json(paths["summary"], summary)
    descriptors = tuple(
        {
            "seed": seed,
            "split": split,
            "sample_count": 10,
            "source_identity": {
                "git_commit": commit,
                "git_dirty": False,
            },
        }
        for seed, split in zip(training_seeds, ("train", "validation", "test"))
    )
    dataset = SimpleNamespace(
        manifest={
            "split_sha256": "a" * 64,
            "training_set_sha256": "b" * 64,
        },
        manifest_sha256="c" * 64,
        episode_descriptors=descriptors,
    )
    paths["plan_sha256"] = Path(plan_sha256)
    paths["summary_sha256"] = Path(summary_sha256)
    paths["registry_sha256"] = Path(registry_sha256)
    return dataset, paths


def test_point_mass_source_binding_separates_internal_and_external_hashes(
    tmp_path: Path,
) -> None:
    dataset, paths = _source_fixture(tmp_path)

    binding = point_mass_development_source_binding(
        dataset,
        generation_plan_path=paths["plan"],
        generation_summary_path=paths["summary"],
        training_seed_registry_path=paths["registry"],
    )

    assert binding["schema_version"] == ACTIVE_VISION_BC_SOURCE_BINDING_SCHEMA_VERSION
    assert binding["status"] == "valid_point_mass_development_source_binding"
    assert binding["binding_scope"][
        "generation_plan_embeds_training_registry_sha256"
    ] is False
    assert binding["generation_summary"]["training_seed_registry_sha256"] == str(
        paths["registry_sha256"]
    )
    assert binding["dataset"]["manifest_sha256"] == "c" * 64
    assert binding["dataset"]["episode_count_by_split"] == {
        "train": 1,
        "validation": 1,
        "test": 1,
    }
    assert binding["reserved_evaluation"]["dataset_overlap"] == []
    assert binding["reserved_evaluation"]["formal_r0_read_or_run"] is False


def test_point_mass_source_binding_rejects_summary_registry_hash_change(
    tmp_path: Path,
) -> None:
    dataset, paths = _source_fixture(tmp_path)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    summary["training_seed_registry_sha256"] = "0" * 64
    _write_json(paths["summary"], summary)

    with pytest.raises(ValueError, match="summary registry hash mismatch"):
        point_mass_development_source_binding(
            dataset,
            generation_plan_path=paths["plan"],
            generation_summary_path=paths["summary"],
            training_seed_registry_path=paths["registry"],
        )


def test_frozen_config_binds_one_configuration_and_all_authorities_false(
    tmp_path: Path,
) -> None:
    dataset, paths = _source_fixture(tmp_path)
    source_binding = point_mass_development_source_binding(
        dataset,
        generation_plan_path=paths["plan"],
        generation_summary_path=paths["summary"],
        training_seed_registry_path=paths["registry"],
    )
    config = ActiveVisionBcConfig(seed=17, epochs=5, hidden_dim=64, device="cpu")
    payload = {
        "schema_version": ACTIVE_VISION_BC_FROZEN_CONFIG_SCHEMA_VERSION,
        "work_package": "test",
        "frozen_before_training": True,
        "source_hashes": {
            "dataset_manifest_sha256": source_binding["dataset"]["manifest_sha256"],
            "generation_plan_sha256": source_binding["generation_plan"]["sha256"],
            "generation_summary_sha256": source_binding["generation_summary"][
                "sha256"
            ],
            "training_seed_registry_sha256": source_binding[
                "training_seed_registry"
            ]["sha256"],
        },
        "selection_contract": {
            "configuration_count": 1,
            "hyperparameter_search": False,
            "validation_used_for_best_epoch": True,
            "test_used_for_training_or_selection": False,
            "repeat_on_gate_failure": False,
        },
        "authority": {
            "assist": False,
            "promotion": False,
            "ppo": False,
            "assignment": False,
            "degradation": False,
            "runtime": False,
            "production": False,
            "control": False,
            "camera_command": False,
            "global_track_id_write": False,
        },
        "config": config.__dict__,
    }
    config_path = tmp_path / "frozen_config.json"
    _write_json(config_path, payload)

    loaded, evidence = load_frozen_behavior_cloning_config(config_path)
    validate_frozen_behavior_cloning_binding(
        evidence,
        config=loaded,
        source_binding=source_binding,
    )

    assert loaded == config
    assert evidence["selection_contract"]["configuration_count"] == 1
    assert not any(evidence["authority"].values())
