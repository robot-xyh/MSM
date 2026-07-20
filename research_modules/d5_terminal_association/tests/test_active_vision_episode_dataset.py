from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

from d5_terminal_association.active_vision_contracts import (
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionDecisionV1,
    ActiveVisionFovMode,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionRuntimeMode,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    DeterministicLookAtScanPolicy,
)
from d5_terminal_association.active_vision_episode_dataset import (
    ActiveVisionCameraFeedbackV1,
    ActiveVisionDatasetValidationError,
    ActiveVisionEpisodeRecordV1,
    ActiveVisionOfflineLabelV1,
    ActiveVisionRuntimeAckV1,
    ActiveVisionSourceIdentityV1,
    active_vision_sample_from_decision,
    audit_active_vision_episode_dataset,
    finalize_active_vision_episode_dataset,
    load_active_vision_episode_dataset,
    load_active_vision_episode_record,
    stage_active_vision_episode_record,
    stage_active_vision_offline_labels,
    unavailable_active_vision_offline_labels,
)
from d5_terminal_association.active_vision_learning import ActiveVisionTransition


GENERATION_CONFIG = {
    "recording_mode": "whole_episode",
    "policy_source": "deterministic_rule_demonstration",
}


def _snapshot(*, seed: int, camera_count: int, track_count: int) -> ActiveVisionSnapshotV1:
    now = 1000.0 + seed
    tracks = tuple(
        ActiveVisionTrackReference(
            global_track_id=f"GT-{seed:03d}-{index:03d}",
            track_version=seed + 1,
            measurement_timestamp=now - 0.05,
        )
        for index in range(track_count)
    )
    cameras = tuple(
        ActiveVisionCameraState(
            camera_id=f"CAM-{index:03d}",
            resource_id=f"RES-{index:03d}",
            state_timestamp=now,
            yaw_deg=float(index),
            pitch_deg=-2.0,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            yaw_limits_deg=(-90.0, 90.0),
            pitch_limits_deg=(-45.0, 30.0),
            max_yaw_rate_deg_s=60.0,
            max_pitch_rate_deg_s=45.0,
            max_slew_deg_s=70.0,
            current_fov_mode=ActiveVisionFovMode.WIDE,
        )
        for index in range(camera_count)
    )
    assignments = tuple(
        ActiveVisionAssignmentReference(
            resource_id=camera.resource_id,
            camera_id=camera.camera_id,
            global_track_id=tracks[index % track_count].global_track_id,
        )
        for index, camera in enumerate(cameras)
    )
    projections = tuple(
        ActiveVisionProjectionEvidence(
            camera_id=assignment.camera_id,
            global_track_id=assignment.global_track_id,
            measurement_timestamp=now - 0.05,
            arrival_timestamp=now - 0.02,
            yaw_error_deg=3.0,
            pitch_error_deg=-1.0,
            projection_covariance_deg2=(1.0, 0.0, 0.0, 1.0),
            visibility_probability=0.9,
            occlusion_fraction=0.05,
            association_confidence=0.95,
            in_fov=True,
        )
        for assignment in assignments
    )
    return ActiveVisionSnapshotV1(
        snapshot_timestamp=now,
        plan=ActiveVisionPlanReference(
            plan_version=seed + 1,
            coalition_version=seed + 2,
            assignments=assignments,
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=seed + 3,
            plan_version=seed + 1,
            coalition_version=seed + 2,
            update_timestamp=now - 0.01,
            healthy=True,
        ),
        tracks=tracks,
        cameras=cameras,
        projections=projections,
    )


def _record(
    seed: int,
    *,
    camera_count: int | None = None,
    track_count: int | None = None,
    scenario_version: str = "unified-3d-v1",
    episode_suffix: str | None = None,
) -> ActiveVisionEpisodeRecordV1:
    suffix = "" if episode_suffix is None else f"-{episode_suffix}"
    snapshot = _snapshot(
        seed=seed,
        camera_count=camera_count or (seed % 4) + 1,
        track_count=track_count or (seed % 6) + 1,
    )
    policy = DeterministicLookAtScanPolicy()
    samples = []
    for index, camera in enumerate(snapshot.cameras):
        rule = policy.select_action(
            snapshot,
            camera_id=camera.camera_id,
            current_timestamp=snapshot.snapshot_timestamp,
            expected_plan_version=snapshot.plan.plan_version,
            expected_coalition_version=snapshot.plan.coalition_version,
            expected_communication_version=snapshot.communication.communication_version,
        )
        decision = ActiveVisionDecisionV1(
            requested_mode=ActiveVisionRuntimeMode.SHADOW,
            effective_mode=ActiveVisionRuntimeMode.SHADOW,
            rule_action=rule,
            requested_action=rule,
            effective_action=rule,
            fallback_reason=None,
            inference_latency_ms=0.0,
            model_fingerprint=None,
            plan_version=snapshot.plan.plan_version,
            coalition_version=snapshot.plan.coalition_version,
            communication_version=snapshot.communication.communication_version,
        )
        command_version = seed * 100 + index
        sample_key = f"sample-{seed:03d}{suffix}-{index:03d}"
        feedback = ActiveVisionCameraFeedbackV1(
            camera_state=replace(camera, state_timestamp=snapshot.snapshot_timestamp + 0.02),
            last_accepted_command_version=command_version,
        )
        ack = ActiveVisionRuntimeAckV1(
            sample_key=sample_key,
            camera_id=camera.camera_id,
            command_version=command_version,
            ack_timestamp=snapshot.snapshot_timestamp + 0.01,
            accepted=True,
            status_code="applied",
            plan_version=snapshot.plan.plan_version,
            coalition_version=snapshot.plan.coalition_version,
            communication_version=snapshot.communication.communication_version,
        )
        samples.append(
            active_vision_sample_from_decision(
                sample_key=sample_key,
                observation_key=f"observation-{seed:03d}{suffix}-{index:03d}",
                sequence_index=index,
                camera_id=camera.camera_id,
                snapshot=snapshot,
                decision=decision,
                camera_feedback=feedback,
                runtime_ack=ack if index % 2 == 0 else None,
            )
        )
    return ActiveVisionEpisodeRecordV1(
        scenario_version=scenario_version,
        seed=seed,
        episode_id=f"episode-{seed:03d}{suffix}",
        source_identity=ActiveVisionSourceIdentityV1(
            git_commit="a" * 40,
            git_dirty=False,
            config_sha256="b" * 64,
        ),
        samples=tuple(samples),
        synthetic_fixture=True,
    )


def _available_labels(record: ActiveVisionEpisodeRecordV1) -> tuple[ActiveVisionOfflineLabelV1, ...]:
    return tuple(
        ActiveVisionOfflineLabelV1(
            sample_key=sample.sample_key,
            observation_key=sample.observation_key,
            reward_available=True,
            reward=0.5,
            reward_provenance="offline_episode_outcome_v1",
            outcome_available=True,
            outcome={
                "truth_entity_id": f"entity-{index:03d}",
                "visibility_improved": True,
            },
        )
        for index, sample in enumerate(record.samples)
    )


def _stage_records(
    root: Path,
    count: int,
    *,
    rewards_available: bool = True,
) -> tuple[ActiveVisionEpisodeRecordV1, ...]:
    records = tuple(_record(seed) for seed in range(count))
    for record in records:
        stage_active_vision_episode_record(
            root,
            record,
            generation_config=GENERATION_CONFIG,
        )
        labels = (
            _available_labels(record)
            if rewards_available
            else unavailable_active_vision_offline_labels(record)
        )
        stage_active_vision_offline_labels(root, record.episode_uid, labels)
    return records


def test_detached_episode_dataset_round_trip_dynamic_counts_and_training_views(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dataset"
    records = _stage_records(root, 8)
    manifest = finalize_active_vision_episode_dataset(
        root,
        split_seed=17,
        minimum_unseen_seed_count=1,
    )
    dataset = load_active_vision_episode_dataset(root)

    assert manifest["schema_version"] == "d5.active-vision-episode-dataset.v2"
    assert manifest["split_policy"]["shared_seed_values_atomic_across_scenarios"] is True
    assert {item.split for item in dataset.episodes} == {"train", "validation", "test"}
    groups = {}
    for item in dataset.episodes:
        assert groups.setdefault(item.record.group_key, item.split) == item.split
    assert {len(item.record.samples[0].snapshot.cameras) for item in dataset.episodes} == {
        len(record.samples[0].snapshot.cameras) for record in records
    }
    assert any(
        sample.runtime_ack is None
        for item in dataset.episodes
        for sample in item.record.samples
    )
    assert any(
        sample.runtime_ack is not None
        for item in dataset.episodes
        for sample in item.record.samples
    )
    assert manifest["storage_contract"] == {
        "online_truth_free": True,
        "offline_labels_physically_separate": True,
        "detached": True,
        "immutable": True,
        "missing_numeric_labels_use_null": True,
    }
    assert manifest["source_identity_summary"]["git_commits"] == ["a" * 40]
    first_descriptor = manifest["episodes"][0]
    online_text = (root / first_descriptor["online_file"]).read_text(encoding="utf-8")
    offline_text = (root / first_descriptor["offline_file"]).read_text(encoding="utf-8")
    assert "truth_entity_id" not in online_text
    assert "truth_entity_id" in offline_text
    assert Path(first_descriptor["online_file"]).parent.name == "online"
    assert Path(first_descriptor["offline_file"]).parent.name == "offline"
    assert not stat.S_IMODE((root / "manifest.json").stat().st_mode) & 0o222

    bc = dataset.behavior_cloning_episodes("train")
    ppo = dataset.ppo_episodes("train")
    assert all(
        transition.selected_action == sample.rule_demonstration_action
        and transition.reward is None
        for episode, loaded in zip(bc, dataset.split("train"), strict=True)
        for transition, sample in zip(episode.transitions, loaded.record.samples, strict=True)
    )
    assert all(
        transition.selected_action == sample.effective_action and transition.reward == 0.5
        for episode, loaded in zip(ppo, dataset.split("train"), strict=True)
        for transition, sample in zip(episode.transitions, loaded.record.samples, strict=True)
    )
    audit = audit_active_vision_episode_dataset(root)
    assert audit["status"] == "valid_detached_immutable_dataset"
    assert audit["sample_count"] == sum(len(record.samples) for record in records)


def test_unavailable_reward_is_null_and_ppo_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    _stage_records(root, 5, rewards_available=False)
    finalize_active_vision_episode_dataset(root, minimum_unseen_seed_count=1)
    dataset = load_active_vision_episode_dataset(root)

    assert dataset.manifest["availability"]["reward"]["status"] == "unavailable"
    assert all(
        transition.reward is None
        for episode in dataset.behavior_cloning_episodes("train")
        for transition in episode.transitions
    )
    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        dataset.ppo_episodes("train")
    assert exc_info.value.code == "ppo_reward_unavailable"
    offline_path = next((root / "offline").glob("*.offline.json"))
    payload = json.loads(offline_path.read_text(encoding="utf-8"))
    assert payload["labels"][0]["reward"]["available"] is False
    assert payload["labels"][0]["reward"]["value"] is None


def test_split_is_seed_atomic_across_scenarios_and_deterministic(tmp_path: Path) -> None:
    scenarios = ("unified-3d-2v2-v1", "unified-3d-5v5-v1")
    records = [
        _record(
            seed,
            scenario_version=scenario,
            episode_suffix=f"{scenario[-6:-3]}-a",
        )
        for seed in range(8)
        for scenario in scenarios
    ]
    records.append(
        _record(
            3,
            scenario_version=scenarios[0],
            episode_suffix="2v2-b",
        )
    )

    manifests = []
    for root, ordered_records in (
        (tmp_path / "ordered", records),
        (tmp_path / "reversed", list(reversed(records))),
    ):
        for record in ordered_records:
            stage_active_vision_episode_record(
                root,
                record,
                generation_config=GENERATION_CONFIG,
            )
            stage_active_vision_offline_labels(
                root,
                record.episode_uid,
                _available_labels(record),
            )
        manifests.append(
            finalize_active_vision_episode_dataset(
                root,
                split_seed=71,
                minimum_unseen_seed_count=1,
            )
        )
        load_active_vision_episode_dataset(root)

    assignments = [
        {
            (item["scenario_version"], item["seed"], item["episode_id"]): item["split"]
            for item in manifest["episodes"]
        }
        for manifest in manifests
    ]
    assert assignments[0] == assignments[1]
    assert manifests[0]["split_sha256"] == manifests[1]["split_sha256"]
    assert manifests[0]["training_set_sha256"] == manifests[1]["training_set_sha256"]

    split_by_seed: dict[int, set[str]] = {}
    split_by_group: dict[tuple[str, int], set[str]] = {}
    for item in manifests[0]["episodes"]:
        split_by_seed.setdefault(item["seed"], set()).add(item["split"])
        group = (item["scenario_version"], item["seed"])
        split_by_group.setdefault(group, set()).add(item["split"])
    assert all(len(splits) == 1 for splits in split_by_seed.values())
    assert all(len(splits) == 1 for splits in split_by_group.values())

    seeds_by_split = {
        split: {
            item["seed"]
            for item in manifests[0]["episodes"]
            if item["split"] == split
        }
        for split in ("train", "validation", "test")
    }
    assert all(seeds_by_split.values())
    assert seeds_by_split["test"].isdisjoint(seeds_by_split["train"])
    assert seeds_by_split["test"].isdisjoint(seeds_by_split["validation"])
    assert seeds_by_split["train"].isdisjoint(seeds_by_split["validation"])


def test_split_fails_closed_for_too_few_unique_or_declared_unseen_seeds(
    tmp_path: Path,
) -> None:
    too_few = tmp_path / "too-few"
    _stage_records(too_few, 2)
    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        finalize_active_vision_episode_dataset(too_few, minimum_unseen_seed_count=1)
    assert exc_info.value.code == "insufficient_split_groups"

    reused = tmp_path / "reused"
    reused_records = [
        _record(seed, scenario_version=scenario, episode_suffix=f"{seed}-{index}")
        for seed in (10, 11)
        for index, scenario in enumerate(("scale-small-v1", "scale-large-v1"))
    ]
    for record in reused_records:
        stage_active_vision_episode_record(
            reused,
            record,
            generation_config=GENERATION_CONFIG,
        )
        stage_active_vision_offline_labels(
            reused,
            record.episode_uid,
            _available_labels(record),
        )
    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        finalize_active_vision_episode_dataset(reused, minimum_unseen_seed_count=1)
    assert exc_info.value.code == "insufficient_split_groups"

    unseen = tmp_path / "unseen"
    _stage_records(unseen, 5)
    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        finalize_active_vision_episode_dataset(unseen, minimum_unseen_seed_count=2)
    assert exc_info.value.code == "insufficient_unseen_test_seeds"


def test_offline_join_and_reward_contract_reject_placeholders(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    record = _record(1)
    stage_active_vision_episode_record(root, record, generation_config=GENERATION_CONFIG)
    wrong = tuple(
        replace(label, observation_key="observation-wrong")
        for label in _available_labels(record)
    )
    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        stage_active_vision_offline_labels(root, record.episode_uid, wrong)
    assert exc_info.value.code == "offline_label_join_mismatch"

    sample = record.samples[0]
    with pytest.raises(ValueError, match="never zero padding"):
        ActiveVisionOfflineLabelV1(
            sample_key=sample.sample_key,
            observation_key=sample.observation_key,
            reward_available=False,
            reward=0.0,
        )
    with pytest.raises(ValueError, match="requires a bounded value"):
        ActiveVisionOfflineLabelV1(
            sample_key=sample.sample_key,
            observation_key=sample.observation_key,
            reward_available=True,
            reward=0.5,
            reward_provenance="offline",
        )
    with pytest.raises(ValueError, match="requires factual outcome"):
        ActiveVisionOfflineLabelV1(
            sample_key=sample.sample_key,
            observation_key=sample.observation_key,
            causal_label_available=True,
            causal_label={"benefit": True},
        )
    with pytest.raises(ValueError, match=r"\[-1, 1\]"):
        ActiveVisionTransition(
            snapshot=sample.snapshot,
            camera_id=sample.camera_id,
            selected_action=sample.effective_action,
            reward=1.01,
        )


def test_online_loader_rejects_truth_unknown_center_and_local_rewrite(tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("truth", "unknown", "rewrite")]
    for root in roots:
        record = _record(3, camera_count=1, track_count=2)
        descriptor = stage_active_vision_episode_record(
            root, record, generation_config=GENERATION_CONFIG
        )
        online_path = root / descriptor["online_file"]
        online_path.chmod(0o644)
        payload = json.loads(online_path.read_text(encoding="utf-8"))
        if root.name == "truth":
            payload["samples"][0]["truth_entity_id"] = "entity-001"
            expected = "online_truth_identity_forbidden"
        elif root.name == "unknown":
            payload["samples"][0]["effective_action"]["target_global_track_id"] = "GT-UNKNOWN"
            expected = "unknown_center_reference"
        else:
            other_center_id = payload["samples"][0]["snapshot"]["tracks"][1]["global_track_id"]
            payload["samples"][0]["effective_action"]["target_global_track_id"] = other_center_id
            expected = "global_track_id_local_rewrite"
        online_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
            load_active_vision_episode_record(online_path)
        assert exc_info.value.code == expected


def test_dataset_hash_tamper_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    _stage_records(root, 5)
    manifest = finalize_active_vision_episode_dataset(root, minimum_unseen_seed_count=1)
    online_path = root / manifest["episodes"][0]["online_file"]
    online_path.chmod(0o644)
    online_path.write_bytes(online_path.read_bytes() + b" ")

    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        load_active_vision_episode_dataset(root)
    assert exc_info.value.code == "artifact_sha_mismatch"
