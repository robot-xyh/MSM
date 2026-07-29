from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
    RuleRegionResourcePolicy,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_dataset import (
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningReward,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    stage_region_learning_episode,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v4_shadow_candidate import (
    RegionResourceV4BuildConfig,
    _load_external_dataset_for_v4,
    build_region_resource_v4_development_fixture,
)
from research_modules.scalable_3d_simulation import d4_v4_external_dataset
from research_modules.scalable_3d_simulation.d4_v4_external_dataset import (
    D4V4ExternalDatasetExportConfig,
    D4V4ExternalDatasetExportError,
    export_d4_v4_external_runtime_dataset,
)


_COMMIT = "a" * 40


def _source_dataset(tmp_path: Path, *, seed_count: int = 12) -> Path:
    staging = tmp_path / "source-staging"
    dataset = tmp_path / "source-dataset"
    policy = RuleRegionResourcePolicy()
    for seed in range(seed_count):
        source = RegionLearningEpisodeSource(
            scenario_id="external-runtime-fixture",
            scenario_version="v1",
            scenario_scale="R8",
            seed=seed,
            episode_id=f"external-runtime-fixture-{seed}",
            git_commit=_COMMIT,
            git_dirty=False,
            config_sha256=sha256(f"source:{seed}".encode()).hexdigest(),
        )
        frames = []
        for frame_index in range(2):
            timestamp_s = 0.5 * frame_index
            snapshot = replace(
                build_region_resource_v4_development_fixture(
                    seed=seed,
                    timestamp_s=timestamp_s,
                ),
                snapshot_id=f"external-{seed}-{frame_index}",
                scenario_id=source.scenario_id,
                scenario_version=source.scenario_version,
            )
            recommendation = policy.recommend(snapshot)
            frames.append(
                RegionLearningFrame(
                    frame_index=frame_index,
                    timestamp_s=timestamp_s,
                    snapshot=snapshot,
                    target=RegionLearningTarget.available(
                        RegionLearningTargetKind.RULE,
                        recommendation,
                    ),
                    reward=RegionLearningReward.unavailable(
                        "runtime_outcome_not_used"
                    ),
                    recommendation=recommendation,
                )
            )
        stage_region_learning_episode(staging, source, frames)
    finalize_region_learning_dataset(
        staging,
        dataset,
        created_at_utc="2026-07-29T00:00:00Z",
        split_seed=1,
        minimum_unique_seeds=6,
        minimum_unseen_seeds=2,
    )
    return dataset


def _config() -> D4V4ExternalDatasetExportConfig:
    return D4V4ExternalDatasetExportConfig(
        split_seed=9,
        minimum_unique_seeds=6,
        minimum_unseen_seeds=2,
        minimum_train_seeds=1,
        minimum_validation_seeds=1,
        minimum_test_seeds=1,
    )


def test_external_export_passes_v4_governance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_dataset(tmp_path)
    monkeypatch.setattr(
        d4_v4_external_dataset,
        "_clean_repository_identity",
        lambda _root: {
            "git_commit": _COMMIT,
            "source_worktree_dirty": False,
            "exporter_sha256": "b" * 64,
        },
    )
    output = tmp_path / "external-output"
    summary = export_d4_v4_external_runtime_dataset(
        source,
        output,
        repository_root=tmp_path,
        config=_config(),
    )

    loaded, evidence, governance = _load_external_dataset_for_v4(
        output / "dataset",
        source_evidence_path=output / "external_dataset_evidence.json",
        config=RegionResourceV4BuildConfig(
            minimum_train_seeds=1,
            minimum_validation_seeds=1,
            minimum_test_seeds=1,
            epochs=1,
            confidence_epochs=1,
        ),
    )
    assert loaded.manifest.dataset_sha256 == summary["dataset_sha256"]
    assert evidence.source_worktree_dirty is False
    assert governance["test_payload_read_count"] == 0
    assert governance["split_action_inventory"]["train"] == {
        "frame_count": 16,
        "positive_executable_difference_count": 1,
        "negative_no_executable_difference_count": 15,
        "transfer_target_count": 1,
        "unsafe_difference_count": 0,
    }
    assert governance["split_action_inventory"]["validation"] == {
        "frame_count": 4,
        "positive_executable_difference_count": 1,
        "negative_no_executable_difference_count": 3,
        "transfer_target_count": 1,
        "unsafe_difference_count": 0,
    }
    derivation = json.loads(
        (output / "source_derivation_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert derivation["generation"]["generated_by_v4_builder"] is False
    assert derivation["generation"]["truth_identifier_use_count"] == 0
    assert summary["production_permission_available"] is False


def test_external_export_fails_without_safe_validation_positive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_dataset(tmp_path, seed_count=6)
    monkeypatch.setattr(
        d4_v4_external_dataset,
        "_clean_repository_identity",
        lambda _root: {
            "git_commit": _COMMIT,
            "source_worktree_dirty": False,
            "exporter_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(
        d4_v4_external_dataset,
        "_safe_transfer_alternative",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(
        D4V4ExternalDatasetExportError,
        match="d4_v4_safe_positive_unavailable",
    ):
        export_d4_v4_external_runtime_dataset(
            source,
            tmp_path / "external-output",
            repository_root=tmp_path,
            config=_config(),
        )
