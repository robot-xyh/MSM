from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.learning_label_backfill import (
    LearningLabelBackfillConfig,
    LearningLabelBackfillError,
    audit_learning_label_readiness,
    audit_learning_label_sidecar_bundle,
    write_learning_label_sidecars,
)


_COMMIT = "1" * 40
_CONFIG_SHA = "2" * 64
_RESERVED_SEEDS = list(range(1000, 1020))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(value) + b"\n")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_canonical(row) + b"\n" for row in rows))


def _write_gzip_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write(_canonical(row) + b"\n")


def _region_snapshot(backlog: float) -> dict[str, object]:
    return {
        "regions": [
            {
                "target_demand": 2.0,
                "high_threat_backlog": backlog,
                "d1_uncertainty": 0.2,
                "d2_uncertainty": 0.1,
                "d5_visibility": 0.7,
                "d5_consistency": 0.8,
                "reserve_resources": 1.0,
                "committed_resources": 2.0,
                "communication_latency_s": 0.05,
                "packet_loss_rate": 0.01,
                "assignment_conflict_count": 0.0,
                "degradation_failed": False,
            }
        ]
    }


def _d4_frame(index: int, timestamp: float, backlog: float) -> dict[str, object]:
    return {
        "schema": "d4-region-learning-frame-v1",
        "frame_index": index,
        "timestamp_s": timestamp,
        "snapshot": _region_snapshot(backlog),
        "target": {"availability": "available", "recommendation": {}},
        "recommendation": {
            "actions": [
                {
                    "resource_quota_delta": 0,
                    "hold": False,
                    "request_replan": False,
                }
            ],
            "transfers": [],
        },
    }


def _projection(timestamp: float, angular_error: float, visibility: float) -> dict[str, object]:
    return {
        "camera_id": "CAM-1",
        "global_track_id": "GT-1",
        "yaw_error_deg": angular_error,
        "pitch_error_deg": 0.0,
        "visibility_probability": visibility,
        "association_confidence": visibility,
        "occlusion_fraction": 1.0 - visibility,
        "in_fov": True,
        "measurement_timestamp": timestamp,
        "arrival_timestamp": timestamp + 0.01,
    }


def _snapshot(timestamp: float, angular_error: float, visibility: float) -> dict[str, object]:
    return {
        "schema_version": "d5.active-vision-snapshot.v1",
        "snapshot_timestamp": timestamp,
        "plan": {"plan_version": 1, "coalition_version": 1},
        "communication": {"communication_version": 1},
        "cameras": [{"camera_id": "CAM-1"}],
        "tracks": [{"global_track_id": "GT-1"}],
        "projections": [_projection(timestamp, angular_error, visibility)],
    }


def _feedback(timestamp: float, accepted_version: int | None) -> dict[str, object]:
    return {
        "schema_version": "d5.active-vision-camera-feedback.v1",
        "camera_state": {"camera_id": "CAM-1", "state_timestamp": timestamp},
        "last_accepted_command_version": accepted_version,
    }


def _action(timestamp: float) -> dict[str, object]:
    return {
        "schema_version": "d5.active-vision-action.v1",
        "camera_id": "CAM-1",
        "intent": "observe_target",
        "target_global_track_id": "GT-1",
        "issued_timestamp": timestamp,
    }


def _object_row(kind: str, record_type: str, value: dict[str, object]) -> tuple[str, dict[str, object]]:
    key = f"{kind}-sha256-{_sha_bytes(_canonical(value) + b'\n')}"
    return key, {"record_type": record_type, "object_key": key, "value": value}


def _unavailable_offline_label(sample_key: str, observation_key: str) -> dict[str, object]:
    return {
        "schema_version": "d5.active-vision-offline-label.v1",
        "sample_key": sample_key,
        "observation_key": observation_key,
        "reward": {
            "available": False,
            "value": None,
            "minimum": -1.0,
            "maximum": 1.0,
            "provenance": None,
        },
        "outcome": {"available": False, "value": None},
        "counterfactual": {
            "available": False,
            "reward": None,
            "minimum": -1.0,
            "maximum": 1.0,
            "provenance": None,
        },
        "causal_label": {"available": False, "value": None},
    }


def _build_dataset(
    tmp_path: Path,
    *,
    ack_state: str | None = "accepted",
    seed: int = 1,
    export_schema: str = "scalable3d-learning-export-v2",
    d4_identity_mismatch: bool = False,
    d4_split_mismatch: bool = False,
    d5_cross_split_mismatch: bool = False,
    invalid_offline_null: bool = False,
) -> Path:
    generation_root = tmp_path / "generation"
    root = generation_root / "learning_dataset"
    root.mkdir(parents=True)
    episode_id = f"fixture-s{seed}"
    scenario_version = "fixture-v1"

    registry = {
        "schema_version": "scalable3d-training-seed-registry-v1",
        "training_seeds": [1],
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "overlap_count": 0,
    }
    _write_json(generation_root / "training_seed_registry.json", registry)
    plan = {
        "schema_version": "scalable3d-learning-generation-plan-v1",
        "formal": True,
        "repository_dirty": False,
        "git_commit": _COMMIT,
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
    }
    _write_json(generation_root / "generation_plan.json", plan)
    batch_summary = {"schema_version": export_schema, "episode_count": 1}
    _write_json(root / "batch_learning_export_summary.json", batch_summary)
    generation_summary = {
        "schema_version": "scalable3d-learning-generation-plan-v1",
        "formal": True,
        "repository_dirty": False,
        "git_commit": _COMMIT,
        "completed_episode_count": 1,
        "learning_export_summary": batch_summary,
        "training_seed_registry_sha256": _sha_file(
            generation_root / "training_seed_registry.json"
        ),
    }
    _write_json(generation_root / "generation_summary.json", generation_summary)
    checkpoint = {
        "schema_version": "scalable3d-learning-generation-checkpoint-v2",
        "state": "finalized",
        "plan_sha256": _sha_file(generation_root / "generation_plan.json"),
        "generation_summary_sha256": _sha_file(
            generation_root / "generation_summary.json"
        ),
        "completed_episode_count": 1,
        "git_commit": _COMMIT,
        "repository_dirty": False,
    }
    _write_json(generation_root / "generation_checkpoint.json", checkpoint)
    _write_jsonl(
        root / "episodes.jsonl",
        [
            {
                "episode_id": episode_id,
                "scenario_version": scenario_version,
                "seed": seed,
                "config_sha256": _CONFIG_SHA,
            }
        ],
    )

    d4_root = root / "d4_region"
    d4_relative = "episodes/fixture.jsonl"
    d4_path = d4_root / d4_relative
    frames = [_d4_frame(0, 0.0, 2.0), _d4_frame(1, 0.5, 1.0)]
    source = {
        "schema": "d4-region-learning-source-v1",
        "episode_id": episode_id,
        "scenario_version": scenario_version,
        "seed": seed,
        "config_sha256": "3" * 64 if d4_identity_mismatch else _CONFIG_SHA,
        "git_commit": _COMMIT,
        "git_dirty": False,
    }
    frame_rows = [{"record_type": "frame", "frame": frame} for frame in frames]
    frame_bytes = b"".join(_canonical(row) + b"\n" for row in frame_rows)
    d4_rows = [
        {
            "record_type": "episode_header",
            "schema": "d4-region-learning-episode-v1",
            "source": source,
        },
        *frame_rows,
        {
            "record_type": "episode_footer",
            "schema": "d4-region-learning-episode-v1",
            "complete": True,
            "frame_count": len(frames),
            "frames_sha256": _sha_bytes(frame_bytes),
        },
    ]
    _write_jsonl(d4_path, d4_rows)
    declared_split = "validation" if d4_split_mismatch else "train"
    d4_unsigned = {
        "schema": "d4-region-learning-dataset-v1",
        "episodes": [
            {
                "relative_path": d4_relative,
                "episode_sha256": _sha_file(d4_path),
                "frame_count": len(frames),
                "split": declared_split,
                "source": source,
            }
        ],
        "split": {
            "train_seeds": [seed],
            "validation_seeds": [],
            "test_seeds": [],
        },
        "availability": {"frame_count": len(frames)},
    }
    d4_hash = _sha_bytes(_canonical(d4_unsigned))
    _write_json(
        d4_root / "manifest.json",
        {
            **d4_unsigned,
            "dataset_id": f"d4-region-learning-dataset-{d4_hash}",
            "dataset_sha256": d4_hash,
        },
    )

    d5_root = root / "d5_active_vision"
    uid = "fixture-episode"
    snapshots = [_snapshot(0.0, 20.0, 0.4), _snapshot(0.2, 5.0, 0.9)]
    feedback_values = [_feedback(0.0, None), _feedback(0.2, 7 if ack_state == "accepted" else None)]
    snapshot_rows = [_object_row("snapshot", "snapshot", item) for item in snapshots]
    feedback_rows = [
        _object_row("camera-feedback", "camera_feedback", item)
        for item in feedback_values
    ]
    sample_rows: list[dict[str, object]] = []
    action = _action(0.0)
    for index in range(2):
        sample_key = f"sample-{index}"
        ack: dict[str, object] | None = None
        if index == 0 and ack_state is not None:
            ack = {
                "schema_version": "d5.active-vision-runtime-ack.v1",
                "sample_key": sample_key,
                "camera_id": "CAM-1",
                "command_version": 7,
                "ack_timestamp": 0.1,
                "accepted": ack_state == "accepted",
                "status_code": "applied" if ack_state == "accepted" else "rejected",
                "plan_version": 1,
                "coalition_version": 1,
                "communication_version": 1,
            }
        sample_rows.append(
            {
                "record_type": "sample",
                "schema_version": "d5.active-vision-sample.v2",
                "sample_key": sample_key,
                "observation_key": f"observation-{index}",
                "sequence_index": index,
                "camera_id": "CAM-1",
                "snapshot_key": snapshot_rows[index][0],
                "rule_demonstration_action": action,
                "requested_action": action,
                "effective_action": action,
                "requested_mode": "assist",
                "effective_mode": "assist",
                "fallback_reason": None,
                "plan_version": 1,
                "coalition_version": 1,
                "communication_version": 1,
                "camera_feedback_key": feedback_rows[index][0],
                "runtime_ack": ack,
            }
        )
    sample_index = [
        {
            "sequence_index": row["sequence_index"],
            "sample_key": row["sample_key"],
            "observation_key": row["observation_key"],
            "snapshot_key": row["snapshot_key"],
            "camera_feedback_key": row["camera_feedback_key"],
        }
        for row in sample_rows
    ]
    online_rows: list[dict[str, object]] = [
        {
            "record_type": "header",
            "schema_version": "d5.active-vision-episode-record.v2",
            "episode_uid": uid,
            "episode_id": episode_id,
            "scenario_version": scenario_version,
            "seed": seed,
            "source_identity": {
                "schema_version": "d5.active-vision-source-identity.v1",
                "config_sha256": _CONFIG_SHA,
                "git_commit": _COMMIT,
                "git_dirty": False,
            },
        }
    ]
    for index in range(2):
        online_rows.extend([feedback_rows[index][1], snapshot_rows[index][1], sample_rows[index]])
    online_rows.append(
        {
            "record_type": "footer",
            "schema_version": "d5.active-vision-episode-record.v2",
            "sample_count": 2,
            "unique_snapshot_count": 2,
            "unique_camera_feedback_count": 2,
            "sample_index_sha256": _sha_bytes(_canonical(sample_index) + b"\n"),
        }
    )
    online_relative = f"online/{uid}.online.jsonl.gz"
    online_path = d5_root / online_relative
    _write_gzip_jsonl(online_path, online_rows)

    offline_labels = [
        _unavailable_offline_label(f"sample-{index}", f"observation-{index}")
        for index in range(2)
    ]
    if invalid_offline_null:
        offline_labels[0]["reward"]["value"] = 0.0  # type: ignore[index]
    offline_relative = f"offline/{uid}.offline.json"
    offline_path = d5_root / offline_relative
    _write_json(
        offline_path,
        {
            "schema_version": "d5.active-vision-offline-labels.v1",
            "episode_uid": uid,
            "episode_id": episode_id,
            "scenario_version": scenario_version,
            "seed": seed,
            "reward_bounds": {"minimum": -1.0, "maximum": 1.0},
            "labels": offline_labels,
        },
    )
    availability = {
        name: {"sample_count": 2, "available_sample_count": 0, "status": "unavailable"}
        for name in ("outcome", "reward", "counterfactual", "causal_label")
    }
    descriptor = {
        "schema_version": "d5.active-vision-episode-descriptor.v2",
        "episode_uid": uid,
        "episode_id": episode_id,
        "scenario_version": scenario_version,
        "seed": seed,
        "source_identity": {
            "schema_version": "d5.active-vision-source-identity.v1",
            "config_sha256": _CONFIG_SHA,
            "git_commit": _COMMIT,
            "git_dirty": False,
        },
        "synthetic_fixture": True,
        "dataset_config_sha256": "4" * 64,
        "online_file": online_relative,
        "online_sha256": _sha_file(online_path),
        "online_storage_layout": "deduplicated-reference-stream-jsonl-gzip-v1",
        "unique_snapshot_count": 2,
        "unique_camera_feedback_count": 2,
        "offline_file": offline_relative,
        "offline_sha256": _sha_file(offline_path),
        "sample_count": 2,
        "availability": availability,
        "split": "validation" if d5_cross_split_mismatch else "train",
    }
    descriptor_path = d5_root / "episodes" / f"{uid}.episode.json"
    _write_json(descriptor_path, descriptor)
    _write_json(
        d5_root / "manifest.json",
        {
            "schema_version": "d5.active-vision-episode-dataset.v3",
            "storage_contract": {
                "online_truth_free": True,
                "offline_labels_physically_separate": True,
            },
            "episodes": [descriptor],
            "availability": availability,
        },
    )
    checksum_paths = sorted(
        path for path in d5_root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    (d5_root / "SHA256SUMS").write_text(
        "".join(
            f"{_sha_file(path)}  {path.relative_to(d5_root).as_posix()}\n"
            for path in checksum_paths
        ),
        encoding="ascii",
    )
    return root


def _load_sidecar_rows(bundle: Path, module: str) -> list[dict[str, object]]:
    path = next((bundle / module).glob("*.jsonl.gz"))
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def test_acknowledged_action_has_bounded_reward_but_no_causal_label(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path)
    bundle = tmp_path / "sidecars"

    manifest = write_learning_label_sidecars(source, bundle)
    rows = _load_sidecar_rows(bundle, "d5_active_vision")
    readiness = json.loads((bundle / "readiness.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "d6.learning-label-sidecar-bundle.v1"
    assert rows[0]["outcome"]["available"] is True
    assert 0.0 < rows[0]["reward"]["value"] <= 1.0
    assert rows[0]["reward"]["provenance"]["reward_semantics"] == (
        "bounded_observed_transition_after_versioned_ack"
    )
    assert rows[0]["counterfactual"]["available"] is False
    assert rows[0]["causal_label"]["available"] is False
    assert readiness["d5_active_vision"]["reward"]["available_count"] == 1


def test_missing_ack_keeps_observed_outcome_but_blocks_reward(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path, ack_state=None)

    readiness = audit_learning_label_readiness(source)

    assert readiness["d5_active_vision"]["observed_outcome"]["available_count"] == 1
    assert readiness["d5_active_vision"]["reward"]["available_count"] == 0
    assert readiness["d5_active_vision"]["reward"]["reasons"] == {
        "observed_outcome_unavailable": 1,
        "runtime_ack_missing": 1,
    }
    assert readiness["overall"]["d5_active_vision_behavior_cloning_available"] is True
    assert readiness["overall"]["d5_active_vision_ppo_available"] is False


def test_rejected_ack_is_an_explicit_negative_execution_result(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path, ack_state="rejected")
    bundle = tmp_path / "sidecars"

    write_learning_label_sidecars(source, bundle)
    first = _load_sidecar_rows(bundle, "d5_active_vision")[0]

    assert first["outcome"]["available"] is True
    assert first["reward"]["available"] is True
    assert first["reward"]["value"] == -1.0
    assert first["reward"]["provenance"]["reward_semantics"] == "rejected_command_penalty"


def test_last_d4_and_d5_records_have_no_fabricated_successor(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path)
    bundle = tmp_path / "sidecars"

    write_learning_label_sidecars(source, bundle)
    d4_rows = _load_sidecar_rows(bundle, "d4_region")
    d5_rows = _load_sidecar_rows(bundle, "d5_active_vision")

    assert d4_rows[0]["outcome"]["available"] is True
    assert d4_rows[0]["reward"]["reason"] == "d4_recommendation_application_evidence_missing"
    assert d4_rows[-1]["outcome"]["reason"] == "successor_frame_missing"
    assert d5_rows[-1]["outcome"]["reason"] == "successor_camera_sample_missing"
    assert d5_rows[-1]["reward"]["reason"] == "observed_outcome_unavailable"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"export_schema": "unknown"}, "source_contract_mismatch"),
        ({"d4_identity_mismatch": True}, "d4_episode_identity_mismatch"),
        ({"d4_split_mismatch": True}, "d4_split_mismatch"),
        ({"seed": 1000}, "reserved_seed_leakage"),
        ({"invalid_offline_null": True}, "d5_source_unavailable_layer_not_null"),
    ],
)
def test_contract_violations_fail_closed(
    tmp_path: Path,
    kwargs: dict[str, object],
    reason: str,
) -> None:
    source = _build_dataset(tmp_path, **kwargs)

    with pytest.raises(LearningLabelBackfillError) as captured:
        audit_learning_label_readiness(source)

    assert captured.value.code == reason


def test_source_tamper_is_detected(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path)
    online = next((source / "d5_active_vision" / "online").glob("*.jsonl.gz"))
    online.write_bytes(online.read_bytes() + b"tamper")

    with pytest.raises(LearningLabelBackfillError) as captured:
        audit_learning_label_readiness(source)

    assert captured.value.code == "d5_artifact_hash_mismatch"


def test_cross_module_split_mismatch_blocks_joint_training_only(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path, d5_cross_split_mismatch=True)

    readiness = audit_learning_label_readiness(source)
    alignment = readiness["truth_isolation"]["cross_module_split_alignment"]

    assert alignment["status"] == "inconsistent"
    assert alignment["mismatched_episode_count"] == 1
    assert alignment["mismatched_seed_count"] == 1
    assert alignment["training_scope"] == "module_local_training_only"
    assert readiness["overall"]["d4_behavior_cloning_available"] is True
    assert readiness["overall"]["d5_active_vision_behavior_cloning_available"] is True
    assert readiness["overall"]["cross_module_joint_training_available"] is False


def test_sidecar_bundle_is_detached_atomic_and_deterministic(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path)
    source_hashes = {
        path.relative_to(source): _sha_file(path)
        for path in source.rglob("*")
        if path.is_file()
    }
    first = tmp_path / "sidecars-a"
    second = tmp_path / "sidecars-b"

    first_manifest = write_learning_label_sidecars(source, first)
    repeated_manifest = write_learning_label_sidecars(source, first)
    second_manifest = write_learning_label_sidecars(source, second)

    assert first_manifest == repeated_manifest == second_manifest
    assert audit_learning_label_sidecar_bundle(first) == first_manifest
    first_bytes = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_bytes = {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_bytes == second_bytes
    assert source_hashes == {
        path.relative_to(source): _sha_file(path)
        for path in source.rglob("*")
        if path.is_file()
    }


def test_sidecars_cannot_be_written_inside_source(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path)

    with pytest.raises(LearningLabelBackfillError) as captured:
        write_learning_label_sidecars(source, source / "labels")

    assert captured.value.code == "output_inside_source"


def test_sidecar_manifest_detects_rewritten_readiness_even_with_updated_checksum(
    tmp_path: Path,
) -> None:
    source = _build_dataset(tmp_path)
    bundle = tmp_path / "sidecars"
    write_learning_label_sidecars(source, bundle)
    readiness_path = bundle / "readiness.json"
    readiness_path.write_bytes(readiness_path.read_bytes() + b" ")
    checksum_path = bundle / "SHA256SUMS"
    rewritten = []
    for line in checksum_path.read_text(encoding="ascii").splitlines():
        digest, relative = line.split("  ", 1)
        if relative == "readiness.json":
            digest = _sha_file(readiness_path)
        rewritten.append(f"{digest}  {relative}\n")
    checksum_path.write_text("".join(rewritten), encoding="ascii")

    with pytest.raises(LearningLabelBackfillError) as captured:
        audit_learning_label_sidecar_bundle(bundle)

    assert captured.value.code == "bundle_readiness_hash_mismatch"


def test_existing_bundle_rejects_a_different_labeling_policy(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path)
    bundle = tmp_path / "sidecars"
    write_learning_label_sidecars(source, bundle)

    with pytest.raises(LearningLabelBackfillError) as captured:
        write_learning_label_sidecars(
            source,
            bundle,
            config=LearningLabelBackfillConfig(d5_transition_window_s=0.25),
        )

    assert captured.value.code == "existing_bundle_policy_mismatch"


def test_sidecar_generation_requires_full_source_hash_verification(tmp_path: Path) -> None:
    source = _build_dataset(tmp_path)

    with pytest.raises(LearningLabelBackfillError) as captured:
        write_learning_label_sidecars(
            source,
            tmp_path / "sidecars",
            config=LearningLabelBackfillConfig(verify_all_source_hashes=False),
        )

    assert captured.value.code == "source_hash_verification_required"


def test_reserved_evaluation_seed_contract_cannot_be_overridden() -> None:
    with pytest.raises(ValueError, match="frozen to 1000-1019"):
        LearningLabelBackfillConfig(reserved_evaluation_seeds=(1000,))
