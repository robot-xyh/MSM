from __future__ import annotations

from collections import Counter
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import stat

import pytest

import d5_terminal_association.active_vision_episode_dataset as episode_dataset_module
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
    enumerate_safe_action_candidates,
)
from d5_terminal_association.active_vision_episode_dataset import (
    ActiveVisionCameraFeedbackV1,
    ActiveVisionDatasetValidationError,
    ActiveVisionEpisodeRecordV1,
    ActiveVisionOfflineLabelV1,
    ActiveVisionRuntimeAckV1,
    ActiveVisionSourceIdentityV1,
    active_vision_sample_from_decision,
    audit_active_vision_episode_record,
    audit_active_vision_episode_dataset,
    finalize_active_vision_episode_dataset,
    load_active_vision_episode_dataset,
    load_active_vision_episode_dataset_lazy,
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
            yaw_deg=float(index % 91),
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


def _read_online_rows(path: Path) -> list[dict[str, object]]:
    with gzip.open(path, mode="rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _write_online_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("wb") as raw_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=6,
            fileobj=raw_handle,
            mtime=0,
        ) as stream:
            for row in rows:
                stream.write(
                    (
                        json.dumps(
                            row,
                            ensure_ascii=True,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                )


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

    assert manifest["schema_version"] == "d5.active-vision-episode-dataset.v3"
    assert manifest["split_policy"]["shared_seed_values_atomic_across_scenarios"] is True
    assert manifest["storage_contract"]["online_storage_layout"].endswith("jsonl-gzip-v1")
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
        "online_storage_layout": "deduplicated-reference-stream-jsonl-gzip-v1",
        "shared_objects_referenced_by_sha256_key": True,
        "offline_join_uses_stream_audit": True,
        "detached": True,
        "immutable": True,
        "missing_numeric_labels_use_null": True,
    }
    assert manifest["source_identity_summary"]["git_commits"] == ["a" * 40]
    first_descriptor = manifest["episodes"][0]
    with gzip.open(root / first_descriptor["online_file"], mode="rt", encoding="utf-8") as stream:
        online_text = stream.read()
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


def test_relative_dataset_root_supports_staging_finalize_and_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    root = Path("relative-dataset")
    records = _stage_records(root, 5)
    finalize_active_vision_episode_dataset(root, minimum_unseen_seed_count=1)

    dataset = load_active_vision_episode_dataset(root)

    assert len(dataset.episodes) == len(records)


def test_validate_cli_serializes_nested_immutable_audit_mappings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "cli-validate-dataset"
    records = _stage_records(root, 5)
    finalize_active_vision_episode_dataset(root, minimum_unseen_seed_count=1)

    exit_code = episode_dataset_module.main(
        ("validate", "--dataset-dir", str(root))
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "valid_detached_immutable_dataset"
    assert payload["episode_count"] == len(records)
    assert payload["availability"]["reward"]["status"] == "available"
    assert payload["source_domain_summary"]["episode_count"] == len(records)


def test_recorded_modes_cannot_bypass_rule_fallback() -> None:
    sample = _record(80, camera_count=1, track_count=2).samples[0]
    alternative = next(
        action
        for action in enumerate_safe_action_candidates(
            sample.snapshot,
            camera_id=sample.camera_id,
            current_timestamp=sample.rule_demonstration_action.issued_timestamp,
        )
        if action.action_key != sample.rule_demonstration_action.action_key
    )

    with pytest.raises(ValueError, match="preserve the deterministic rule action"):
        replace(
            sample,
            requested_mode=ActiveVisionRuntimeMode.ASSIST,
            effective_mode=ActiveVisionRuntimeMode.DISABLED,
            requested_action=alternative,
            effective_action=alternative,
            fallback_reason="model_timeout",
        )

    assisted = replace(
        sample,
        requested_mode=ActiveVisionRuntimeMode.ASSIST,
        effective_mode=ActiveVisionRuntimeMode.ASSIST,
        requested_action=alternative,
        effective_action=alternative,
        fallback_reason=None,
    )
    assert assisted.effective_action == alternative


def test_high_cardinality_stream_deduplicates_snapshot_and_scales_near_linearly(
    tmp_path: Path,
) -> None:
    measurements: dict[int, tuple[int, int, int]] = {}
    for camera_count in (16, 64):
        root = tmp_path / f"cardinality-{camera_count}"
        record = _record(
            81,
            camera_count=camera_count,
            track_count=camera_count * 2,
            episode_suffix=str(camera_count),
        )
        legacy_bytes = len(
            episode_dataset_module._canonical_json_bytes(
                episode_dataset_module._legacy_embedded_episode_record_payload_for_size_test(
                    record
                )
            )
        )
        descriptor = stage_active_vision_episode_record(
            root,
            record,
            generation_config=GENERATION_CONFIG,
        )
        online_path = root / descriptor["online_file"]
        with gzip.open(online_path, mode="rb") as stream:
            deduplicated_bytes = len(stream.read())
        audit = audit_active_vision_episode_record(online_path)
        assert audit["sample_count"] == camera_count
        assert audit["unique_snapshot_count"] == 1
        assert descriptor["unique_snapshot_count"] == 1
        measurements[camera_count] = (
            legacy_bytes,
            deduplicated_bytes,
            online_path.stat().st_size,
        )

    legacy_small, deduplicated_small, compressed_small = measurements[16]
    legacy_large, deduplicated_large, compressed_large = measurements[64]
    assert legacy_large / legacy_small > 10.0
    assert deduplicated_large / deduplicated_small < 6.0
    assert compressed_large / compressed_small < 6.0
    assert deduplicated_large < legacy_large * 0.15
    assert compressed_large < legacy_large * 0.05


def test_200_camera_writer_is_deterministic_byte_equivalent_and_bounded_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: Counter[str] = Counter()
    tracked_names = (
        "_assert_online_truth_free",
        "_canonical_json_bytes",
        "_feedback_to_payload",
        "_snapshot_to_payload",
        "_stream_object_key",
        "assert_truth_free_active_vision_payload",
        "sha256_file",
    )
    for name in tracked_names:
        original = getattr(episode_dataset_module, name)

        def tracked(*args: object, _name: str = name, _original=original, **kwargs: object):
            calls[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(episode_dataset_module, name, tracked)

    record = _record(777, camera_count=200, track_count=400)
    outputs: list[bytes] = []
    decompressed: list[bytes] = []
    for suffix in ("a", "b"):
        root = tmp_path / suffix
        descriptor = stage_active_vision_episode_record(
            root,
            record,
            generation_config=GENERATION_CONFIG,
        )
        encoded = (root / descriptor["online_file"]).read_bytes()
        outputs.append(encoded)
        decompressed.append(gzip.decompress(encoded))

    assert outputs[0] == outputs[1]
    assert decompressed[0] == decompressed[1]
    assert len(outputs[0]) <= 50_000
    assert len(decompressed[0]) == 732_969
    assert hashlib.sha256(decompressed[0]).hexdigest() == (
        "b9b6650a7bbb2407a4c08dc25681bf79eb29c4f32c12463804811d0ac257ddea"
    )

    # Two complete writes share one snapshot each and keep every camera feedback.
    assert calls["_snapshot_to_payload"] == 2
    assert calls["_feedback_to_payload"] == 400
    assert calls["_stream_object_key"] == 0
    assert calls["sha256_file"] == 4
    assert calls["_canonical_json_bytes"] <= 820
    assert calls["_assert_online_truth_free"] <= 820
    # The old per-sample full-snapshot path made more than 80,000 calls for one
    # build.  The bounded count proves that center identities are checked once
    # per frozen snapshot while every sample-owned field remains audited.
    assert calls["assert_truth_free_active_vision_payload"] < 4_000


def test_writer_reaudits_snapshot_payload_and_rejects_injected_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record(778, camera_count=8, track_count=16)
    original = episode_dataset_module._snapshot_to_payload

    def inject_truth(snapshot: ActiveVisionSnapshotV1) -> dict[str, object]:
        payload = original(snapshot)
        payload["truth_entity_id"] = "entity-001"
        return payload

    monkeypatch.setattr(episode_dataset_module, "_snapshot_to_payload", inject_truth)
    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        stage_active_vision_episode_record(
            tmp_path,
            record,
            generation_config=GENERATION_CONFIG,
        )
    assert exc_info.value.code == "online_truth_identity_forbidden"
    assert not tuple((tmp_path / "online").glob("*.online.jsonl.gz"))


def test_offline_staging_stream_audits_without_loading_complete_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "dataset"
    record = _record(82, camera_count=200, track_count=400)
    descriptor = stage_active_vision_episode_record(
        root,
        record,
        generation_config=GENERATION_CONFIG,
    )

    def reject_full_reload(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline staging must not load the complete online record")

    monkeypatch.setattr(
        episode_dataset_module,
        "load_active_vision_episode_record",
        reject_full_reload,
    )
    staged = stage_active_vision_offline_labels(
        root,
        record.episode_uid,
        _available_labels(record),
    )

    assert staged["online_sha256"] == descriptor["online_sha256"]
    assert staged["offline_file"] is not None
    assert descriptor["sample_count"] == 200
    assert descriptor["unique_snapshot_count"] == 1
    assert (root / descriptor["online_file"]).stat().st_size < 1_000_000

    tampered_root = tmp_path / "tampered"
    tampered_record = _record(83, camera_count=8, track_count=16)
    tampered_descriptor = stage_active_vision_episode_record(
        tampered_root,
        tampered_record,
        generation_config=GENERATION_CONFIG,
    )
    tampered_path = tampered_root / tampered_descriptor["online_file"]
    tampered_path.chmod(0o644)
    tampered_path.write_bytes(tampered_path.read_bytes() + b"tamper")
    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        stage_active_vision_offline_labels(
            tampered_root,
            tampered_record.episode_uid,
            _available_labels(tampered_record),
        )
    assert exc_info.value.code == "online_sha_mismatch"


def test_multi_episode_finalize_and_audit_never_materialize_complete_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "many-episodes"
    for seed in range(6):
        for scenario_index, scenario in enumerate(("scale-50-v1", "scale-200-v1")):
            record = _record(
                seed,
                camera_count=48,
                track_count=96,
                scenario_version=scenario,
                episode_suffix=f"scenario-{scenario_index}",
            )
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

    stream_materialization_modes: list[bool] = []
    original_stream_reader = episode_dataset_module._read_episode_record_stream

    def tracked_stream_reader(
        path: Path,
        *,
        materialize: bool,
    ) -> object:
        stream_materialization_modes.append(materialize)
        return original_stream_reader(path, materialize=materialize)

    def reject_complete_materialization(*args: object, **kwargs: object) -> None:
        raise AssertionError("finalize/audit must not materialize a complete episode record")

    monkeypatch.setattr(
        episode_dataset_module,
        "_read_episode_record_stream",
        tracked_stream_reader,
    )
    monkeypatch.setattr(
        episode_dataset_module,
        "load_active_vision_episode_record",
        reject_complete_materialization,
    )
    monkeypatch.setattr(
        episode_dataset_module,
        "_load_staged_episode",
        reject_complete_materialization,
    )
    monkeypatch.setattr(
        episode_dataset_module,
        "load_active_vision_episode_dataset",
        reject_complete_materialization,
    )

    manifest = finalize_active_vision_episode_dataset(
        root,
        split_seed=29,
        minimum_unseen_seed_count=1,
    )
    audit = audit_active_vision_episode_dataset(root)

    assert len(manifest["episodes"]) == 12
    assert audit["episode_count"] == 12
    assert audit["sample_count"] == 576
    assert audit["episode_loading"] == "streaming_one_episode_at_a_time"
    assert stream_materialization_modes
    assert not any(stream_materialization_modes)


def test_finalize_reuses_stream_and_digest_evidence_but_public_audit_is_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "counted-finalization"
    episode_count = 6
    _stage_records(root, episode_count)

    phase = {"name": "finalize"}
    counts: Counter[tuple[str, str]] = Counter()
    hash_paths: Counter[tuple[str, str]] = Counter()
    original_stream_reader = episode_dataset_module._read_episode_record_stream
    original_offline_reader = episode_dataset_module._load_offline_labels_for_join
    original_sha256_file = episode_dataset_module.sha256_file
    original_public_audit = episode_dataset_module.audit_active_vision_episode_dataset

    def tracked_stream_reader(path: Path, *, materialize: bool) -> object:
        counts[(phase["name"], "stream_read")] += 1
        counts[(phase["name"], f"stream_materialize_{materialize}")] += 1
        return original_stream_reader(path, materialize=materialize)

    def tracked_offline_reader(*args: object, **kwargs: object) -> object:
        counts[(phase["name"], "offline_join_parse")] += 1
        return original_offline_reader(*args, **kwargs)

    def tracked_sha256_file(path: str | Path) -> str:
        artifact = Path(path).resolve().relative_to(root.resolve()).as_posix()
        counts[(phase["name"], "sha256_file")] += 1
        hash_paths[(phase["name"], artifact)] += 1
        return original_sha256_file(path)

    def tracked_public_audit(*args: object, **kwargs: object) -> object:
        counts[(phase["name"], "public_dataset_audit")] += 1
        return original_public_audit(*args, **kwargs)

    monkeypatch.setattr(
        episode_dataset_module,
        "_read_episode_record_stream",
        tracked_stream_reader,
    )
    monkeypatch.setattr(
        episode_dataset_module,
        "_load_offline_labels_for_join",
        tracked_offline_reader,
    )
    monkeypatch.setattr(episode_dataset_module, "sha256_file", tracked_sha256_file)
    monkeypatch.setattr(
        episode_dataset_module,
        "audit_active_vision_episode_dataset",
        tracked_public_audit,
    )

    finalize_active_vision_episode_dataset(root, minimum_unseen_seed_count=1)

    artifact_count = sum(
        1
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    assert counts[("finalize", "stream_read")] == episode_count
    assert counts[("finalize", "stream_materialize_False")] == episode_count
    assert counts[("finalize", "offline_join_parse")] == episode_count
    assert counts[("finalize", "sha256_file")] == artifact_count
    assert counts[("finalize", "public_dataset_audit")] == 0
    assert all(
        count == 1
        for (counted_phase, _), count in hash_paths.items()
        if counted_phase == "finalize"
    )

    phase["name"] = "public_audit"
    audit = episode_dataset_module.audit_active_vision_episode_dataset(root)

    assert audit["episode_count"] == episode_count
    assert counts[("public_audit", "public_dataset_audit")] == 1
    assert counts[("public_audit", "stream_read")] == episode_count
    assert counts[("public_audit", "stream_materialize_False")] == episode_count
    assert counts[("public_audit", "offline_join_parse")] == episode_count
    assert counts[("public_audit", "sha256_file")] == artifact_count
    assert all(
        count == 1
        for (counted_phase, _), count in hash_paths.items()
        if counted_phase == "public_audit"
    )


def test_lazy_training_iterators_materialize_only_the_current_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "lazy-dataset"
    _stage_records(root, 8)
    finalize_active_vision_episode_dataset(
        root,
        split_seed=41,
        minimum_unseen_seed_count=1,
    )

    full_episode_calls: list[str] = []
    online_episode_calls: list[str] = []
    offline_label_calls: list[str] = []
    original_full_loader = episode_dataset_module._load_staged_episode
    original_online_loader = episode_dataset_module._load_online_staged_episode
    original_offline_loader = episode_dataset_module._load_offline_labels

    def tracked_full_loader(
        dataset_root: Path,
        descriptor: dict[str, object],
    ) -> object:
        full_episode_calls.append(str(descriptor["episode_uid"]))
        return original_full_loader(dataset_root, descriptor)

    def tracked_online_loader(
        dataset_root: Path,
        descriptor: dict[str, object],
    ) -> object:
        online_episode_calls.append(str(descriptor["episode_uid"]))
        return original_online_loader(dataset_root, descriptor)

    def tracked_offline_loader(path: Path, record: ActiveVisionEpisodeRecordV1) -> object:
        offline_label_calls.append(record.episode_uid)
        return original_offline_loader(path, record)

    monkeypatch.setattr(episode_dataset_module, "_load_staged_episode", tracked_full_loader)
    monkeypatch.setattr(
        episode_dataset_module,
        "_load_online_staged_episode",
        tracked_online_loader,
    )
    monkeypatch.setattr(
        episode_dataset_module,
        "_load_offline_labels",
        tracked_offline_loader,
    )

    dataset = load_active_vision_episode_dataset_lazy(root)
    train_count = len(dataset.split_descriptors("train"))
    assert train_count > 1
    assert full_episode_calls == []
    assert online_episode_calls == []
    assert offline_label_calls == []

    bc_iterator = dataset.iter_behavior_cloning_episodes("train")
    first_bc = next(bc_iterator)
    assert len(first_bc.transitions) > 0
    assert len(online_episode_calls) == 1
    assert full_episode_calls == []
    assert offline_label_calls == []
    remaining_bc = list(bc_iterator)
    assert len(remaining_bc) + 1 == train_count
    assert len(online_episode_calls) == train_count
    assert full_episode_calls == []
    assert offline_label_calls == []

    ppo_iterator = dataset.iter_ppo_episodes("train")
    first_ppo = next(ppo_iterator)
    assert all(item.reward == 0.5 for item in first_ppo.transitions)
    assert len(full_episode_calls) == 1
    assert len(offline_label_calls) == 1
    remaining_ppo = list(ppo_iterator)
    assert len(remaining_ppo) + 1 == train_count
    assert len(full_episode_calls) == train_count
    assert len(offline_label_calls) == train_count


def test_legacy_embedded_online_record_schema_fails_closed(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.online.json"
    legacy_path.write_text(
        json.dumps({"schema_version": "d5.active-vision-episode-record.v1"}),
        encoding="utf-8",
    )

    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        load_active_vision_episode_record(legacy_path)
    assert exc_info.value.code == "online_record_schema_unsupported"


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
        rows = _read_online_rows(online_path)
        sample = next(row for row in rows if row["record_type"] == "sample")
        snapshot = next(row for row in rows if row["record_type"] == "snapshot")
        if root.name == "truth":
            sample["truth_entity_id"] = "entity-001"
            expected = "online_truth_identity_forbidden"
        elif root.name == "unknown":
            sample["effective_action"]["target_global_track_id"] = "GT-UNKNOWN"
            expected = "unknown_center_reference"
        else:
            other_center_id = snapshot["value"]["tracks"][1]["global_track_id"]
            sample["effective_action"]["target_global_track_id"] = other_center_id
            expected = "global_track_id_local_rewrite"
        _write_online_rows(online_path, rows)
        for reader in (audit_active_vision_episode_record, load_active_vision_episode_record):
            with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
                reader(online_path)
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


def test_digest_evidence_fails_closed_if_artifact_changes_during_one_audit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"first-version")
    evidence = {}
    episode_dataset_module._file_digest_once(path, evidence)

    path.write_bytes(b"changed-version-with-different-size")

    with pytest.raises(ActiveVisionDatasetValidationError) as exc_info:
        episode_dataset_module._file_digest_once(path, evidence)
    assert exc_info.value.code == "artifact_changed_during_audit"
