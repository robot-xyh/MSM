from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import pytest

import research_modules.scalable_3d_simulation.learning_source_generation as source_generation
from research_modules.d5_terminal_association.src.d5_terminal_association.active_vision_a3_v3_episode_evidence import (
    load_frozen_a3_v3_episode_recipes,
    recover_a3_v3_staged_episode_inventory,
    stage_a3_v3_episode_evidence,
)
from research_modules.scalable_3d_simulation.learning_source_adapters import (
    build_d5_a3_runtime_episode,
)
from research_modules.scalable_3d_simulation.learning_source_generation import (
    run_authorized_learning_source_generation,
)
from research_modules.scalable_3d_simulation.learning_source_generation_authorization import (
    LearningSourceGenerationAuthorization,
    generation_only_permissions,
)
from research_modules.scalable_3d_simulation.learning_source_recipes import (
    load_d5_a3_v3_episode_recipes,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEDULE_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d5_terminal_association/configs/"
    "a3_v3_source_collection_schedule_20260801.json"
)
BASE_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/nominal_200v200.json"
)
REQUEST_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d5_terminal_association/configs/"
    "a3_v3_source_generation_request_20260801.json"
)


def test_all_104_frozen_recipes_build_truth_isolated_runtime_configs() -> None:
    runtime_recipes = load_d5_a3_v3_episode_recipes(SCHEDULE_PATH)
    evidence_recipes = load_frozen_a3_v3_episode_recipes(
        source_schedule_path=SCHEDULE_PATH
    )
    base_config = ScenarioConfig.from_dict(
        json.loads(BASE_CONFIG_PATH.read_text(encoding="utf-8"))
    )

    assert len(runtime_recipes) == len(evidence_recipes) == 104
    for entry_index, (runtime_recipe, evidence_recipe) in enumerate(
        zip(runtime_recipes, evidence_recipes, strict=True)
    ):
        assert (
            runtime_recipe.entry_index,
            runtime_recipe.seed,
            runtime_recipe.episode_id,
            runtime_recipe.split,
            runtime_recipe.allocation_id,
        ) == (
            evidence_recipe.entry_index,
            evidence_recipe.seed,
            evidence_recipe.episode_id,
            evidence_recipe.split,
            evidence_recipe.allocation_id,
        )
        config = runtime_recipe.build_config(base_config)
        metadata = config.metadata["learning_source_recipe"]
        serialized = json.dumps(metadata, sort_keys=True).lower()

        assert metadata["module"] == "D5"
        assert metadata["entry_index"] == entry_index
        assert metadata["episode_id"] == runtime_recipe.episode_id
        assert config.seed == runtime_recipe.seed
        assert config.target_count == runtime_recipe.target_count
        assert config.resource_count == runtime_recipe.resource_count
        assert config.recon_count == runtime_recipe.recon_count
        assert config.duration_s == runtime_recipe.duration_s
        assert len(metadata["intent_windows"]) == 4
        assert len(metadata["hard_confusion_assignments"]) == 2
        assert all(value is False for value in metadata["permissions"].values())
        assert not any(
            forbidden in serialized
            for forbidden in (
                "truth_id",
                "actor_id",
                "object_id",
                "truth_global_track_id",
            )
        )


def test_first_frozen_recipe_meets_quota_with_real_scalable_producer(
    tmp_path: Path,
) -> None:
    runtime_recipe = load_d5_a3_v3_episode_recipes(SCHEDULE_PATH)[0]
    evidence_recipe = load_frozen_a3_v3_episode_recipes(
        source_schedule_path=SCHEDULE_PATH
    )[0]
    base_config = ScenarioConfig.from_dict(
        json.loads(BASE_CONFIG_PATH.read_text(encoding="utf-8"))
    )
    config = runtime_recipe.build_config(base_config)
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(
            capture_learning_artifacts=True,
            d5_recon_track_cues_enabled=True,
            d5_active_vision_collection_profile="balanced_action_role_v1",
        )
    )

    result = run_episode(config, module_stack=stack)
    frames = stack.learning_artifacts().d5_active_vision_frames
    online, offline = build_d5_a3_runtime_episode(
        recipe=evidence_recipe,
        active_vision_frames=frames,
    )
    descriptor = stage_a3_v3_episode_evidence(
        development_dir=tmp_path / "development",
        future_held_out_dir=tmp_path / "future-held-out",
        online=online,
        offline=offline,
    )
    counts = Counter(sample.window_id for sample in online.samples)

    assert config.duration_s == 8.0
    assert config.visual_period_s == 0.1
    assert config.recon_count == 4
    assert frames
    assert frames[0].timestamp_s <= 1.4
    assert frames[-1].timestamp_s >= config.duration_s - 0.5
    assert all(
        counts[window.window_id] >= window.minimum_unique_samples
        for window in evidence_recipe.intent_windows
    )
    assert len({sample.sample_fingerprint for sample in online.samples}) == len(
        online.samples
    )
    assert len(offline.boundary_pairs) == len(
        evidence_recipe.hard_confusion_assignments
    )
    assert descriptor["episode_id"] == evidence_recipe.episode_id
    assert descriptor["status"] == "staged_episode_evidence_validated"
    assert result.summary["online_truth_use_count"] == 0


def test_main_generation_api_resumes_two_bounded_train_episodes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_sha256 = hashlib.sha256(REQUEST_PATH.read_bytes()).hexdigest()
    authorization = LearningSourceGenerationAuthorization(
        authorization_id="d5-source-generation-resume-smoke",
        authorization_file_sha256="a" * 64,
        source_git_commit="b" * 40,
        preflight_sha256="c" * 64,
        registry_file_sha256="d" * 64,
        module_request_sha256={
            "D3": "3" * 64,
            "D4": "4" * 64,
            "D5": request_sha256,
        },
        planned_episode_count={"D3": 300, "D4": 324, "D5": 104},
        permissions=generation_only_permissions(),
        approver_id="d5-test",
        approval_reason="bounded generation-only resume smoke",
        approved_at_utc="2026-08-02T00:00:00Z",
    )
    monkeypatch.setattr(
        source_generation,
        "load_learning_source_generation_authorization",
        lambda *args, **kwargs: authorization,
    )
    output = tmp_path / "d5-source"
    common = {
        "module": "D5",
        "output_dir": output,
        "authorization_path": tmp_path / "test-authorization.json",
        "authorization_sha256": "a" * 64,
        "repository_root": REPOSITORY_ROOT,
        "max_episodes_per_run": 1,
        "minimum_free_gb": 0.0,
    }

    first = run_authorized_learning_source_generation(**common)
    second = run_authorized_learning_source_generation(**common, resume=True)
    inventory = recover_a3_v3_staged_episode_inventory(
        development_dir=output / "development",
        future_held_out_dir=output / "future_held_out",
    )
    progress = [
        json.loads(line)
        for line in (output / "episode_progress.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert first["state"] == "paused"
    assert first["completed_episode_count"] == 1
    assert first["newly_completed_episode_count"] == 1
    assert first["invocation_count"] == 1
    assert second["state"] == "paused"
    assert second["completed_episode_count"] == 2
    assert second["newly_completed_episode_count"] == 1
    assert second["invocation_count"] == 2
    assert inventory["staged_episode_count"] == 2
    assert inventory["split_staged_counts"] == {
        "train": 2,
        "validation": 0,
        "future_held_out": 0,
    }
    assert inventory["future_held_out_isolation"]["payload_deserialized"] is False
    assert not tuple((output / "future_held_out" / "online").glob("*.json"))
    assert not tuple((output / "future_held_out" / "offline").glob("*.json"))
    assert [row["seed"] for row in progress] == [24000, 24001]
    assert all(row["online_truth_use_count"] == 0 for row in progress)
    assert all(row["global_track_id_created_count"] == 0 for row in progress)
    assert all(row["global_track_id_rewritten_count"] == 0 for row in progress)
    assert all(row["training_started"] is False for row in progress)
    assert all(row["runtime_authority_granted"] is False for row in progress)
    assert all(row["control_authority_granted"] is False for row in progress)
    assert authorization.permissions == generation_only_permissions()
