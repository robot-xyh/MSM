from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
    RuleRegionResourcePolicy,
    split_scenario_seed_groups,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_dataset import (
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningReward,
    RegionLearningSplit,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    load_region_learning_dataset,
    load_region_learning_dataset_splits,
    stage_region_learning_episode,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_learning import (
    snapshot_to_region_graph,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v4_shadow_candidate import (
    RegionResourceV4BuildConfig,
    _load_external_dataset_for_v4,
    _v4_confidence_observable_key,
    build_region_resource_v4_development_fixture,
)
from research_modules.scalable_3d_simulation import d4_v4_external_dataset
from research_modules.scalable_3d_simulation.d4_v4_external_dataset import (
    D4V4ExternalDatasetExportConfig,
    D4V4ExternalDatasetExportError,
    export_d4_v4_external_runtime_dataset,
)


_COMMIT = "a" * 40


def _source_dataset(
    tmp_path: Path,
    *,
    seed_count: int = 12,
    scenario_id: str = "external-runtime-fixture",
    observable_seed_aliases: dict[int, int] | None = None,
) -> Path:
    staging = tmp_path / "source-staging"
    dataset = tmp_path / "source-dataset"
    policy = RuleRegionResourcePolicy()
    for seed in range(seed_count):
        source = RegionLearningEpisodeSource(
            scenario_id=scenario_id,
            scenario_version="v1",
            scenario_scale="R8",
            seed=seed,
            episode_id=f"{scenario_id}-{seed}",
            git_commit=_COMMIT,
            git_dirty=False,
            config_sha256=sha256(f"source:{seed}".encode()).hexdigest(),
        )
        frames = []
        for frame_index in range(2):
            timestamp_s = 0.5 * frame_index
            observable_seed = (observable_seed_aliases or {}).get(
                seed,
                seed,
            )
            base_snapshot = build_region_resource_v4_development_fixture(
                seed=seed,
                timestamp_s=timestamp_s,
            )
            snapshot = replace(
                base_snapshot,
                snapshot_id=f"external-{seed}-{frame_index}",
                scenario_id=source.scenario_id,
                scenario_version=source.scenario_version,
                regions=tuple(
                    replace(
                        region,
                        d1_uncertainty=(
                            region.d1_uncertainty
                            + 0.01 * observable_seed
                            + 0.001 * frame_index
                        ),
                    )
                    if region_index == 0
                    else region
                    for region_index, region in enumerate(
                        base_snapshot.regions
                    )
                ),
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
        train_positive_frame_count=2,
        validation_positive_frame_count=1,
        source_kind="external_region_learning_dataset",
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
    assert evidence.source_kind == "external_region_learning_dataset"
    assert governance["test_payload_read_count"] == 0
    assert governance["split_action_inventory"]["train"] == {
        "frame_count": 16,
        "positive_executable_difference_count": 2,
        "negative_no_executable_difference_count": 14,
        "transfer_target_count": 2,
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
    label_audit = derivation["generation"]["observable_label_audit"]
    assert label_audit["mixed_positive_negative_observable_key_count"] == 0
    assert label_audit["selected_positive_record_count_by_split"] == {
        "test": 0,
        "train": 2,
        "validation": 1,
    }
    assert (
        label_audit["observable_key_uses_source_seed_episode_or_target"]
        is False
    )
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


def test_external_export_combines_distinct_source_datasets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _source_dataset(
        tmp_path / "first",
        scenario_id="external-runtime-first",
    )
    second = _source_dataset(
        tmp_path / "second",
        scenario_id="external-runtime-second",
    )
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
        (first, second),
        output,
        repository_root=tmp_path,
        config=_config(),
    )
    derivation = json.loads(
        (output / "source_derivation_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert derivation["source"]["dataset_count"] == 2
    assert derivation["source"]["episode_count"] == 24
    assert derivation["output"]["episode_count"] == 24
    label_audit = derivation["generation"]["observable_label_audit"]
    assert label_audit["mixed_positive_negative_observable_key_count"] == 0
    assert label_audit["selected_positive_record_count_by_split"] == {
        "test": 0,
        "train": 2,
        "validation": 2,
    }
    assert summary["positive_record_count_by_split"] == {
        "test": 0,
        "train": 2,
        "validation": 2,
    }


def test_external_export_propagates_one_label_across_train_validation_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prototype = _source_dataset(tmp_path / "prototype")
    prototype_loaded = load_region_learning_dataset(prototype)
    config = replace(
        _config(),
        train_positive_frame_count=1,
        validation_positive_frame_count=1,
    )
    split = split_scenario_seed_groups(
        [episode.source for episode in prototype_loaded.episode_records],
        train_fraction=config.train_fraction,
        validation_fraction=config.validation_fraction,
        split_seed=config.split_seed,
        minimum_unique_seeds=config.minimum_unique_seeds,
        minimum_unseen_seeds=config.minimum_unseen_seeds,
    )
    train_seed = int(split.train_seeds[0])
    validation_seed = int(split.validation_seeds[0])
    source = _source_dataset(
        tmp_path / "aliased",
        observable_seed_aliases={validation_seed: train_seed},
    )
    monkeypatch.setattr(
        d4_v4_external_dataset,
        "_clean_repository_identity",
        lambda _root: {
            "git_commit": _COMMIT,
            "source_worktree_dirty": False,
            "exporter_sha256": "b" * 64,
        },
    )
    original_safe_transfer = (
        d4_v4_external_dataset._safe_transfer_alternative
    )

    def _only_aliased_pair(snapshot, **kwargs):
        if int(snapshot.seed) not in {train_seed, validation_seed}:
            return None
        return original_safe_transfer(snapshot, **kwargs)

    monkeypatch.setattr(
        d4_v4_external_dataset,
        "_safe_transfer_alternative",
        _only_aliased_pair,
    )
    output = tmp_path / "external-output"
    export_d4_v4_external_runtime_dataset(
        source,
        output,
        repository_root=tmp_path,
        config=config,
    )

    derivation = json.loads(
        (output / "source_derivation_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    positive_records = derivation["positive_records"]
    assert {record["split"] for record in positive_records} == {
        "train",
        "validation",
    }
    positive_frame_keys = {
        (
            record["source_identity_sha256"],
            int(record["frame_index"]),
        )
        for record in positive_records
    }
    loaded = load_region_learning_dataset_splits(
        output / "dataset",
        splits=(
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ),
    )
    positive_observable_keys = {
        _v4_confidence_observable_key(
            snapshot_to_region_graph(frame.snapshot, device="cpu")
        )
        for episode in loaded.episode_records
        for frame in episode.frames
        if (
            episode.source.identity_sha256,
            int(frame.frame_index),
        )
        in positive_frame_keys
    }
    assert len(positive_observable_keys) == 1
    label_audit = derivation["generation"]["observable_label_audit"]
    assert label_audit["selected_positive_observable_key_count"] == 1
    assert label_audit["mixed_positive_negative_observable_key_count"] == 0
