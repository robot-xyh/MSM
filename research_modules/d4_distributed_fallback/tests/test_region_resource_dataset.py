from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest
import torch

from d4_distributed_fallback.region_resource import (
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
)
from d4_distributed_fallback.region_resource_dataset import (
    REGION_LEARNING_DATASET_SCHEMA,
    REGION_LEARNING_SPLIT_ALGORITHM,
    RegionLearningDataUnavailableError,
    RegionLearningDatasetManifest,
    RegionLearningDatasetValidationError,
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningReward,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    load_region_learning_dataset,
    stage_region_learning_episode,
)
from d4_distributed_fallback.region_resource_learning import (
    ModelBundleValidationError,
    SharedRegionGraphActorCritic,
    load_region_behavior_cloning_samples,
    load_region_ppo_training_episodes,
    load_region_resource_model_bundle,
    save_region_resource_model_bundle,
)
from d4_distributed_fallback.regional_failover import RegionalAuthorityLayer


_COMMIT = "a" * 40


def _source(
    scenario_id: str,
    seed: int,
    episode_index: int,
    *,
    scale: str = "M3N3",
    dirty: bool = False,
) -> RegionLearningEpisodeSource:
    config = sha256(f"{scenario_id}:{scale}:{episode_index}".encode()).hexdigest()
    return RegionLearningEpisodeSource(
        scenario_id=scenario_id,
        scenario_version="scenario-v3",
        scenario_scale=scale,
        seed=seed,
        episode_id=f"{scenario_id}-{scale}-seed-{seed}-episode-{episode_index}",
        git_commit=_COMMIT,
        git_dirty=dirty,
        config_sha256=config,
    )


def _snapshot(source: RegionLearningEpisodeSource, frame_index: int) -> RegionResourceSnapshot:
    timestamp = frame_index * 0.25
    regions = (
        RegionResourceNode(
            region_id="west",
            target_demand=3.0,
            high_threat_backlog=1.0,
            d1_uncertainty=0.2,
            d2_uncertainty=0.1,
            d5_visibility=0.8,
            d5_consistency=0.9,
            available_resources=3,
            reserve_resources=1,
            secondary_coverage=0.9,
            secondary_readiness=0.9,
            communication_capacity=20.0,
            communication_latency_s=0.02,
            packet_loss_rate=0.01,
            current_owner_id="CENTER",
            current_owner_layer=RegionalAuthorityLayer.CENTER,
            plan_id="plan-current",
            plan_version=4,
            epoch=5,
            lease_expires_at_s=30.0,
        ),
        RegionResourceNode(
            region_id="east",
            target_demand=1.0,
            high_threat_backlog=0.0,
            d1_uncertainty=0.1,
            d2_uncertainty=0.1,
            d5_visibility=0.9,
            d5_consistency=0.9,
            available_resources=5,
            reserve_resources=1,
            secondary_coverage=0.8,
            secondary_readiness=0.8,
            communication_capacity=20.0,
            communication_latency_s=0.02,
            packet_loss_rate=0.01,
            current_owner_id="CENTER",
            current_owner_layer=RegionalAuthorityLayer.CENTER,
            plan_id="plan-current",
            plan_version=4,
            epoch=5,
            lease_expires_at_s=30.0,
        ),
    )
    return RegionResourceSnapshot(
        snapshot_id=f"{source.episode_id}-frame-{frame_index}",
        scenario_id=source.scenario_id,
        scenario_version=source.scenario_version,
        seed=source.seed,
        timestamp_s=timestamp,
        regions=regions,
        edges=(
            RegionResourceEdge(
                source_region_id="west",
                target_region_id="east",
                transferable_resources=2,
                distance_m=100.0,
                transfer_time_s=2.0,
                bandwidth_mbps=10.0,
            ),
        ),
    )


def _frames(
    source: RegionLearningEpisodeSource,
    *,
    target_available: bool = True,
    reward_available: bool = True,
    frame_count: int = 2,
) -> tuple[RegionLearningFrame, ...]:
    result: list[RegionLearningFrame] = []
    for frame_index in range(frame_count):
        snapshot = _snapshot(source, frame_index)
        recommendation = RuleRegionResourcePolicy().recommend(snapshot)
        target = (
            RegionLearningTarget.available(
                RegionLearningTargetKind.RULE, recommendation
            )
            if target_available
            else RegionLearningTarget.unavailable("formal_target_not_emitted")
        )
        reward = (
            RegionLearningReward.available(-float(frame_index + 1))
            if reward_available
            else RegionLearningReward.unavailable("episode_reward_not_finalized")
        )
        result.append(
            RegionLearningFrame(
                frame_index=frame_index,
                timestamp_s=snapshot.timestamp_s,
                snapshot=snapshot,
                target=target,
                reward=reward,
                recommendation=recommendation,
            )
        )
    return tuple(result)


def _finalize(
    root: Path,
    sources: list[RegionLearningEpisodeSource],
    *,
    target_available: bool = True,
    reward_available: bool = True,
    reverse_frames: bool = False,
    minimum_unseen_seeds: int = 2,
) -> Path:
    stage = root / "stage"
    for source in sources:
        frames = _frames(
            source,
            target_available=target_available,
            reward_available=reward_available,
        )
        stage_region_learning_episode(
            stage,
            source,
            reversed(frames) if reverse_frames else frames,
        )
    dataset = root / "dataset"
    finalize_region_learning_dataset(
        stage,
        dataset,
        created_at_utc="2026-07-20T12:00:00Z",
        split_seed=17,
        minimum_unseen_seeds=minimum_unseen_seeds,
    )
    return dataset


def test_high_cardinality_reverse_order_is_deterministic_and_seed_atomic(
    tmp_path: Path,
) -> None:
    sources = [
        _source(
            f"scenario-{scenario_index}",
            seed,
            episode_index,
            scale=f"M{scale}N{scale}",
        )
        for scenario_index, scale in enumerate((2, 3, 5, 8))
        for seed in range(8)
        for episode_index in range(3)
    ]
    forward_path = _finalize(tmp_path / "forward", sources)
    reverse_path = _finalize(
        tmp_path / "reverse",
        list(reversed(sources)),
        reverse_frames=True,
    )

    forward = load_region_learning_dataset(forward_path)
    reverse = load_region_learning_dataset(reverse_path)

    assert forward.manifest.to_dict() == reverse.manifest.to_dict()
    assert forward.manifest.schema == REGION_LEARNING_DATASET_SCHEMA
    assert forward.manifest.split.algorithm == REGION_LEARNING_SPLIT_ALGORITHM
    assert forward.manifest.availability.episode_count == 96
    assert forward.manifest.availability.frame_count == 192
    assert forward.manifest.availability.behavior_cloning_available is True
    assert forward.manifest.availability.ppo_available is True
    assert len({item.source.identity_sha256 for item in forward.episode_records}) == 96

    split_by_seed: dict[int, set[str]] = {}
    for episode in forward.episode_records:
        split_by_seed.setdefault(episode.source.seed, set()).add(episode.split.value)
    assert all(len(split_names) == 1 for split_names in split_by_seed.values())
    split_seed_sets = (
        set(forward.manifest.split.train_seeds),
        set(forward.manifest.split.validation_seeds),
        set(forward.manifest.split.test_seeds),
    )
    assert not (
        split_seed_sets[0] & split_seed_sets[1]
        or split_seed_sets[0] & split_seed_sets[2]
        or split_seed_sets[1] & split_seed_sets[2]
    )


@pytest.mark.parametrize("tamper", ["episode", "manifest"])
def test_dataset_loader_rejects_hash_tampering(tmp_path: Path, tamper: str) -> None:
    dataset = _finalize(
        tmp_path,
        [_source("scenario", seed, 0) for seed in range(4)],
    )
    if tamper == "episode":
        episode = next((dataset / "episodes").glob("*.jsonl"))
        episode.write_bytes(episode.read_bytes() + b"{}\n")
    else:
        manifest_path = dataset / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["created_at_utc"] = "tampered"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RegionLearningDatasetValidationError):
        load_region_learning_dataset(dataset)


def test_manifest_rejects_inventory_and_reproducible_split_mismatches(
    tmp_path: Path,
) -> None:
    dataset_path = _finalize(
        tmp_path,
        [_source("manifest-consistency", seed, 0) for seed in range(5)],
    )
    manifest = load_region_learning_dataset(dataset_path).manifest
    availability = manifest.availability
    inconsistent_availability = replace(
        availability,
        target_available_count=0,
        target_unavailable_count=availability.frame_count,
        behavior_cloning_available=False,
        ppo_available=False,
        unavailable_reasons=("target_unavailable",),
    )
    with pytest.raises(ValueError, match="availability does not match episode inventory"):
        RegionLearningDatasetManifest.create(
            created_at_utc=manifest.created_at_utc,
            episodes=manifest.episodes,
            split=manifest.split,
            availability=inconsistent_availability,
        )

    train = list(manifest.split.train_seeds)
    validation = list(manifest.split.validation_seeds)
    train[0], validation[0] = validation[0], train[0]
    split_payload = {
        "algorithm": manifest.split.algorithm,
        "split_seed": manifest.split.split_seed,
        "train": sorted(train),
        "validation": sorted(validation),
        "test": list(manifest.split.test_seeds),
    }
    split_sha256 = sha256(
        json.dumps(
            split_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    inconsistent_split = replace(
        manifest.split,
        train_seeds=tuple(train),
        validation_seeds=tuple(validation),
        split_sha256=split_sha256,
    )
    with pytest.raises(ValueError, match="episode split does not match its numeric seed"):
        RegionLearningDatasetManifest.create(
            created_at_utc=manifest.created_at_utc,
            episodes=manifest.episodes,
            split=inconsistent_split,
            availability=manifest.availability,
        )


def test_dirty_source_is_inventoried_but_training_loaders_fail_closed(
    tmp_path: Path,
) -> None:
    dataset = _finalize(
        tmp_path,
        [_source("dirty-scenario", seed, 0, dirty=True) for seed in range(5)],
    )
    loaded = load_region_learning_dataset(dataset)

    assert loaded.manifest.availability.dirty_episode_count == 5
    assert loaded.manifest.availability.behavior_cloning_available is False
    assert "dirty_source" in loaded.manifest.availability.unavailable_reasons
    with pytest.raises(RegionLearningDataUnavailableError, match="dirty_source"):
        load_region_behavior_cloning_samples(loaded)
    with pytest.raises(RegionLearningDataUnavailableError, match="dirty_source"):
        load_region_ppo_training_episodes(loaded)
    assert load_region_behavior_cloning_samples(
        loaded, allow_dirty_source=True
    )


def test_missing_target_is_explicit_and_bc_and_ppo_fail_closed(tmp_path: Path) -> None:
    dataset = _finalize(
        tmp_path,
        [_source("no-target", seed, 0) for seed in range(5)],
        target_available=False,
    )
    loaded = load_region_learning_dataset(dataset)

    assert loaded.manifest.availability.target_available_count == 0
    assert loaded.manifest.availability.target_unavailable_count == 10
    with pytest.raises(RegionLearningDataUnavailableError, match="target_unavailable"):
        load_region_behavior_cloning_samples(loaded)
    with pytest.raises(RegionLearningDataUnavailableError, match="target_unavailable"):
        load_region_ppo_training_episodes(loaded)


def test_missing_reward_does_not_affect_bc_but_ppo_fails_closed(tmp_path: Path) -> None:
    dataset = _finalize(
        tmp_path,
        [_source("no-reward", seed, 0) for seed in range(5)],
        reward_available=False,
    )
    loaded = load_region_learning_dataset(dataset)

    assert load_region_behavior_cloning_samples(loaded)
    with pytest.raises(RegionLearningDataUnavailableError, match="reward_unavailable"):
        load_region_ppo_training_episodes(loaded)


def test_finalize_rejects_fewer_than_three_unique_seeds(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    for seed in range(2):
        source = _source("small", seed, 0)
        stage_region_learning_episode(stage, source, _frames(source))

    with pytest.raises(
        RegionLearningDatasetValidationError,
        match="fewer_than_minimum_unique_seeds",
    ):
        finalize_region_learning_dataset(
            stage,
            tmp_path / "dataset",
            created_at_utc="2026-07-20T12:00:00Z",
            split_seed=1,
            minimum_unseen_seeds=2,
        )


def test_finalize_rejects_declared_unseen_seed_shortage(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    for seed in range(4):
        source = _source("unseen-shortage", seed, 0)
        stage_region_learning_episode(stage, source, _frames(source))

    with pytest.raises(
        RegionLearningDatasetValidationError,
        match="fewer_than_minimum_unseen_seeds",
    ):
        finalize_region_learning_dataset(
            stage,
            tmp_path / "dataset",
            created_at_utc="2026-07-20T12:00:00Z",
            split_seed=1,
            minimum_unseen_seeds=4,
        )


def test_episode_staging_rejects_incomplete_indices_and_truth_keys(tmp_path: Path) -> None:
    source = _source("invalid", 1, 0)
    frames = _frames(source)
    with pytest.raises(
        RegionLearningDatasetValidationError,
        match="contiguous from zero",
    ):
        stage_region_learning_episode(
            tmp_path / "stage",
            source,
            (replace(frames[0], frame_index=1),),
        )

    for forbidden_key in (
        "evaluator_truth",
        "assigned_global_track_id",
        "object_id",
        "offline_truth_actor_name",
    ):
        payload = frames[0].to_dict()
        payload[forbidden_key] = "forbidden"
        with pytest.raises(ValueError, match="truth or target identity"):
            RegionLearningFrame.from_dict(payload)


def test_training_target_revalidates_projection_and_authority_fences() -> None:
    source = _source("unsafe-target", 1, 0)
    snapshot = _snapshot(source, 0)
    recommendation = RuleRegionResourcePolicy().recommend(snapshot)
    stale_epoch = replace(
        recommendation.actions[0],
        expected_epoch=recommendation.actions[0].expected_epoch + 1,
    )
    stale_lease = replace(
        recommendation.actions[0],
        expected_lease_expires_at_s=(
            recommendation.actions[0].expected_lease_expires_at_s + 1.0
        ),
    )
    unsafe_reserve = replace(recommendation.actions[0], reserve_ratio=0.0)
    unknown_edge = replace(recommendation.transfers[0], edge_id="unknown-edge")
    invalid_recommendations = (
        replace(
            recommendation,
            actions=(stale_epoch, *recommendation.actions[1:]),
        ),
        replace(
            recommendation,
            actions=(stale_lease, *recommendation.actions[1:]),
        ),
        replace(
            recommendation,
            actions=(unsafe_reserve, *recommendation.actions[1:]),
        ),
        replace(recommendation, transfers=(unknown_edge,)),
    )

    for invalid in invalid_recommendations:
        with pytest.raises(
            ValueError,
            match="learning target failed deterministic safety validation",
        ):
            RegionLearningFrame(
                frame_index=0,
                timestamp_s=snapshot.timestamp_s,
                snapshot=snapshot,
                target=RegionLearningTarget.available(
                    RegionLearningTargetKind.RULE,
                    invalid,
                ),
                reward=RegionLearningReward.available(0.0),
            )


def test_dataset_round_trip_preserves_all_executable_authority_layers() -> None:
    source = _source("authority-layers", 2, 0)
    base = _snapshot(source, 0)
    owner_ids = {
        RegionalAuthorityLayer.CENTER: "CENTER",
        RegionalAuthorityLayer.SECONDARY: "SECONDARY-RECON-1",
        RegionalAuthorityLayer.DISTRIBUTED: "PEER-1",
    }

    for offset, layer in enumerate(owner_ids, start=1):
        regions = tuple(
            replace(
                node,
                current_owner_id=owner_ids[layer],
                current_owner_layer=layer,
                plan_id=f"plan-{layer.value}",
                plan_version=10 + offset,
                epoch=20 + offset,
                lease_expires_at_s=40.0 + offset,
            )
            for node in base.regions
        )
        snapshot = replace(base, regions=regions, authority_digest="")
        recommendation = RuleRegionResourcePolicy().recommend(snapshot)
        frame = RegionLearningFrame(
            frame_index=0,
            timestamp_s=snapshot.timestamp_s,
            snapshot=snapshot,
            target=RegionLearningTarget.available(
                RegionLearningTargetKind.RULE,
                recommendation,
            ),
            reward=RegionLearningReward.available(0.0),
        )

        restored = RegionLearningFrame.from_dict(frame.to_dict())

        assert {node.current_owner_layer for node in restored.snapshot.regions} == {
            layer
        }
        assert {
            (
                action.expected_owner_layer,
                action.expected_plan_version,
                action.expected_epoch,
                action.expected_lease_expires_at_s,
            )
            for action in restored.target.recommendation.actions
        } == {(layer, 10 + offset, 20 + offset, 40.0 + offset)}


def test_model_bundle_v2_binds_and_verifies_training_dataset_manifest(
    tmp_path: Path,
) -> None:
    dataset_path = _finalize(
        tmp_path / "source",
        [_source("bundle", seed, 0) for seed in range(5)],
    )
    dataset = load_region_learning_dataset(dataset_path)
    samples = load_region_behavior_cloning_samples(dataset)
    model = SharedRegionGraphActorCritic(hidden_dim=8, message_passing_steps=1)
    bundle = tmp_path / "bundle"

    manifest = save_region_resource_model_bundle(
        model,
        bundle,
        model_version="dataset-bound-v1",
        training_graphs=tuple(sample.graph for sample in samples),
        created_at_utc="2026-07-20T12:00:00Z",
        training_dataset_manifest=dataset.manifest,
    )
    loaded = load_region_resource_model_bundle(
        bundle,
        require_training_dataset_manifest=True,
    )

    assert manifest.schema == "d4-region-resource-model-bundle-v2"
    assert manifest.training_dataset_sha256 == dataset.manifest.dataset_sha256
    assert manifest.training_split_sha256 == dataset.manifest.split.split_sha256
    assert loaded.training_dataset_manifest is not None
    assert loaded.training_dataset_manifest.dataset_sha256 == dataset.manifest.dataset_sha256
    assert all(torch.isfinite(parameter).all() for parameter in loaded.model.parameters())

    training_manifest_path = bundle / "training_dataset_manifest.json"
    training_manifest_path.write_bytes(training_manifest_path.read_bytes() + b" ")
    with pytest.raises(
        ModelBundleValidationError,
        match="training_manifest_sha256_mismatch",
    ):
        load_region_resource_model_bundle(bundle)
