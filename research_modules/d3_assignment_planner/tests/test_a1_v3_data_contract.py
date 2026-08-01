from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d3_assignment_planner.a1_v3_data_contract import (
    A1_V3_DATASET_MANIFEST_SCHEMA_V1,
    A1_V3_GENERATION_SCHEDULE_SCHEMA_V1,
    A1_V3_MAIN_SEED_REGISTRY_SCHEMA_V1,
    A1_V3_OFFLINE_LABEL_SCHEMA_V1,
    A1_V3_ONLINE_FRAME_SCHEMA_V1,
    A1_V3_SPLIT_POLICY_V1,
    A1_V3_TRAINING_FEATURE_SCHEMA_V1,
    A1_V3_TRAINING_TARGET_SCHEMA_V1,
    A1V3DataContractError,
    A1V3OfflineLabel,
    A1V3OnlineFrame,
    action_mask_content_sha256,
    canonical_json_line,
    canonical_json_sha256,
    load_a1_v3_audit_dataset,
    load_a1_v3_training_dataset,
    validate_a1_v3_pre_generation_readiness,
    main as contract_main,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_development_data_request_v1.json"
)
EXCLUSION_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_seed_exclusion_registry_v1.json"
)
CONTRACT_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_data_contract_v1.json"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )


def _permissions() -> dict[str, bool]:
    return dict(_json(CONTRACT_PATH)["permissions"])


def _online_payload(
    *,
    cell: dict | None = None,
    seed: int = 30000,
    split: str = "train",
    episode_id: str = "v3-unit-episode-000",
    frame_index: int = 0,
) -> dict:
    if cell is None:
        cell = _json(REQUEST_PATH)["collection_cells"][0]
    edges = [[0, 0]]
    demand = [1]
    return {
        "schema_version": A1_V3_ONLINE_FRAME_SCHEMA_V1,
        "record_kind": "online_identity_free_diagnostic_frame",
        "source": {
            "split": split,
            "scenario_family": cell["scenario_family"],
            "cell_id": cell["cell_id"],
            "seed": seed,
            "episode_id": episode_id,
            "frame_index": frame_index,
            "measurement_timestamp_s": frame_index * 0.1,
            "arrival_timestamp_s": frame_index * 0.1 + 0.01,
            "configured_target_count": cell["configured_target_count"],
            "configured_resource_count": cell["configured_resource_count"],
        },
        "observed_scale": {
            "anonymous_target_count": 1,
            "anonymous_resource_count": 1,
        },
        "candidate_edge_indices": edges,
        "candidate_edge_indices_sha256": canonical_json_sha256(edges),
        "teacher_mask_observability": {
            "teacher_edge_count": 1,
            "teacher_edges_in_candidate_mask_count": 1,
            "all_teacher_edges_in_candidate_mask": True,
        },
        "model_residual_ranking": {
            "rank_direction": "ascending_cost_residual_then_edge",
            "items": [{"edge": [0, 0], "residual": 0.0, "rank": 1}],
        },
        "action_mask": {
            "shape": [1, 1],
            "true_count": 1,
            "content_sha256": action_mask_content_sha256((1, 1), ((0, 0),)),
        },
        "anonymous_target_demand_slots": demand,
        "target_demand_slots_sha256": canonical_json_sha256(demand),
        "selected_edges": {
            "teacher": [[0, 0]],
            "candidate_pre_projection": [[0, 0]],
            "effective_post_projection": [[0, 0]],
        },
        "projection": {
            "pre_projection_reason_codes": ["candidate_available"],
            "post_projection_reason_codes": ["candidate_accepted"],
        },
        "online_truth_use_count": 0,
        "center_identity_ownership": {
            "owner": "center",
            "learning_create_allowed": False,
            "learning_rewrite_allowed": False,
        },
        "permissions": _permissions(),
    }


def _offline_payload(
    online: dict,
    *,
    frame_class: str = "positive",
    hard_negative: bool = False,
    hard_negative_type: str | None = None,
) -> dict:
    source = online["source"]
    action_types = _json(REQUEST_PATH)["action_change_types"]
    return {
        "schema_version": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
        "record_kind": "offline_d6_audit_label",
        "source_ref": {
            "split": source["split"],
            "cell_id": source["cell_id"],
            "seed": source["seed"],
            "episode_id": source["episode_id"],
            "frame_index": source["frame_index"],
            "online_payload_sha256": canonical_json_sha256(online),
        },
        "classification": {
            "frame_class": frame_class,
            "hard_negative": hard_negative,
            "action_change_type": (
                action_types[1] if frame_class == "positive" else action_types[0]
            ),
            "hard_negative_type": hard_negative_type,
        },
        "offline_identity_labels": {
            "truth_target_labels": [],
            "actor_labels": [],
            "object_labels": [],
            "center_global_track_labels": [],
        },
        "identity_provenance": {
            "global_track_id_owner": "center",
            "learning_path_created_global_track_id_count": 0,
            "learning_path_rewritten_global_track_id_count": 0,
        },
        "permissions": _permissions(),
    }


def _registry_payload(config_sha: str) -> dict:
    forbidden = sorted(
        set(range(0, 100))
        | set(range(1000, 1020))
        | set(range(20000, 20100))
    )
    assigned = list(range(30000, 30300))
    return {
        "schema_version": A1_V3_MAIN_SEED_REGISTRY_SCHEMA_V1,
        "registry_id": "main-a1-v3-unit-registry-v1",
        "status": "assigned_generation_authorized",
        "request_binding": {
            "request_id": _json(REQUEST_PATH)["request_id"],
            "request_file_sha256": _sha(REQUEST_PATH),
            "exclusion_registry_file_sha256": _sha(EXCLUSION_PATH),
        },
        "source": {
            "owner": "main",
            "git_commit": "a" * 40,
            "repository_dirty": True,
            "canonical_d3_registry_snapshot_path": "main/d3_seed_registry.json",
            "canonical_d3_registry_snapshot_sha256": "b" * 64,
            "generator_config_path": "a1_v3_generator_config.json",
            "generator_config_sha256": config_sha,
        },
        "allocation": {
            "unique_seed_count": 300,
            "assigned_seed_values": assigned,
            "forbidden_seed_values": forbidden,
            "forbidden_seed_count": len(forbidden),
            "forbidden_seed_values_sha256": canonical_json_sha256(forbidden),
            "canonical_registry_union_complete": True,
            "generation_authorized": True,
        },
        "split": {
            "policy_version": A1_V3_SPLIT_POLICY_V1,
            "unit": "whole_seed_one_episode_atomic",
            "ratios_percent": {"train": 60, "validation": 20, "test": 20},
            "seed_counts": {"train": 180, "validation": 60, "test": 60},
            "seed_values": {
                "train": assigned[:180],
                "validation": assigned[180:240],
                "test": assigned[240:],
            },
            "cross_split_seed_overlap_allowed": False,
        },
        "permissions": _permissions(),
    }


def _schedule_payload(registry_path: Path) -> dict:
    request = _json(REQUEST_PATH)
    contract = _json(CONTRACT_PATH)
    registry = _json(registry_path)
    split_by_seed = {
        seed: split
        for split, values in registry["split"]["seed_values"].items()
        for seed in values
    }
    episodes = []
    seed_offset = 0
    for cell_index, cell in enumerate(request["collection_cells"]):
        for episode_offset in range(20):
            seed = registry["allocation"]["assigned_seed_values"][seed_offset]
            episodes.append(
                {
                    "episode_id": (
                        f"a1-v3-cell-{cell_index:02d}-episode-{episode_offset:02d}"
                    ),
                    "cell_id": cell["cell_id"],
                    "scenario_family": cell["scenario_family"],
                    "seed": seed,
                    "split": split_by_seed[seed],
                    "configured_target_count": cell["configured_target_count"],
                    "configured_resource_count": cell["configured_resource_count"],
                    "minimum_observable_frames": 9,
                    "minimum_positive_frames": 3,
                    "minimum_negative_frames": 3,
                    "minimum_hard_negative_frames": 2 if episode_offset < 10 else 1,
                }
            )
            seed_offset += 1
    return {
        "schema_version": A1_V3_GENERATION_SCHEDULE_SCHEMA_V1,
        "schedule_id": "main-a1-v3-unit-schedule-v1",
        "status": "planned_not_generated",
        "bindings": {
            "request_id": request["request_id"],
            "request_file_sha256": _sha(REQUEST_PATH),
            "registry_id": registry["registry_id"],
            "registry_file_sha256": _sha(registry_path),
            "contract_id": contract["contract_id"],
            "contract_file_sha256": _sha(CONTRACT_PATH),
        },
        "source": {
            "git_commit": registry["source"]["git_commit"],
            "repository_dirty": registry["source"]["repository_dirty"],
            "generator_config_path": registry["source"]["generator_config_path"],
            "generator_config_sha256": registry["source"][
                "generator_config_sha256"
            ],
        },
        "record_contract": {
            "online_frame_schema_version": A1_V3_ONLINE_FRAME_SCHEMA_V1,
            "offline_label_schema_version": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
            "training_feature_schema_version": A1_V3_TRAINING_FEATURE_SCHEMA_V1,
            "training_target_schema_version": A1_V3_TRAINING_TARGET_SCHEMA_V1,
            "split_policy_version": A1_V3_SPLIT_POLICY_V1,
            "diagnostic_observability_requirements": request[
                "diagnostic_observability_requirements"
            ],
            "online_identity_representation": "anonymous_ordinal_indices_only",
            "online_truth_use_count": 0,
            "all_permissions_false": True,
            "full_online_frame_exposed_by_training_loader": False,
        },
        "episodes": episodes,
        "declared_totals": {
            "cell_count": 15,
            "episode_count": 300,
            "unique_seed_count": 300,
            "minimum_observable_frame_count": 2700,
            "minimum_positive_frame_count": 900,
            "minimum_negative_frame_count": 900,
            "minimum_hard_negative_frame_count": 450,
        },
        "permissions": _permissions(),
    }


def _contract_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    config_path = tmp_path / "a1_v3_generator_config.json"
    _write_json(config_path, {"schema_version": "unit_generator_config_v1"})
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, _registry_payload(_sha(config_path)))
    schedule_path = tmp_path / "schedule.json"
    _write_json(schedule_path, _schedule_payload(registry_path))
    return config_path, registry_path, schedule_path


def _write_dataset(
    root: Path,
    *,
    config_path: Path,
    registry_path: Path,
    schedule_path: Path,
) -> None:
    root.mkdir()
    request = _json(REQUEST_PATH)
    registry = _json(registry_path)
    schedule = _json(schedule_path)
    hard_type = request["hard_negative_types"][0]
    online_rows: list[dict] = []
    offline_rows: list[dict] = []
    cell_counts: dict[str, dict[str, int]] = {}
    for episode_index, episode in enumerate(schedule["episodes"]):
        cell = next(
            item
            for item in request["collection_cells"]
            if item["cell_id"] == episode["cell_id"]
        )
        episode_hard_count = 2 if episode_index % 20 < 10 else 1
        for frame_index in range(9):
            online = _online_payload(
                cell=cell,
                seed=episode["seed"],
                split=episode["split"],
                episode_id=episode["episode_id"],
                frame_index=frame_index,
            )
            is_positive = frame_index < 3
            is_hard = 3 <= frame_index < 3 + episode_hard_count
            offline = _offline_payload(
                online,
                frame_class="positive" if is_positive else "negative",
                hard_negative=is_hard,
                hard_negative_type=hard_type if is_hard else None,
            )
            online_rows.append(online)
            offline_rows.append(offline)
        counts = cell_counts.setdefault(
            episode["cell_id"],
            {
                "episode_count": 0,
                "frame_count": 0,
                "positive_frame_count": 0,
                "negative_frame_count": 0,
                "hard_negative_frame_count": 0,
            },
        )
        counts["episode_count"] += 1
        counts["frame_count"] += 9
        counts["positive_frame_count"] += 3
        counts["negative_frame_count"] += 6
        counts["hard_negative_frame_count"] += episode_hard_count
    ordering = sorted(
        range(len(online_rows)),
        key=lambda index: (
            online_rows[index]["source"]["cell_id"],
            online_rows[index]["source"]["seed"],
            online_rows[index]["source"]["episode_id"],
            online_rows[index]["source"]["frame_index"],
        ),
    )
    online_rows = [online_rows[index] for index in ordering]
    offline_rows = [offline_rows[index] for index in ordering]
    online_bytes = b"".join(canonical_json_line(item) for item in online_rows)
    offline_bytes = b"".join(canonical_json_line(item) for item in offline_rows)
    (root / "online_frames.jsonl").write_bytes(online_bytes)
    (root / "offline_labels.jsonl").write_bytes(offline_bytes)
    contract = _json(CONTRACT_PATH)
    manifest = {
        "schema_version": A1_V3_DATASET_MANIFEST_SCHEMA_V1,
        "dataset_id": "a1-v3-unit-generated-dataset-v1",
        "status": "generated_untrained_not_admitted",
        "contract_bindings": {
            "request_id": request["request_id"],
            "request_file_sha256": _sha(REQUEST_PATH),
            "contract_id": contract["contract_id"],
            "contract_file_sha256": _sha(CONTRACT_PATH),
            "registry_id": registry["registry_id"],
            "registry_file_sha256": _sha(registry_path),
            "schedule_id": schedule["schedule_id"],
            "schedule_file_sha256": _sha(schedule_path),
            "online_frame_schema_version": A1_V3_ONLINE_FRAME_SCHEMA_V1,
            "offline_label_schema_version": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
            "training_feature_schema_version": A1_V3_TRAINING_FEATURE_SCHEMA_V1,
            "training_target_schema_version": A1_V3_TRAINING_TARGET_SCHEMA_V1,
            "split_policy_version": A1_V3_SPLIT_POLICY_V1,
        },
        "source": {
            "git_commit": registry["source"]["git_commit"],
            "repository_dirty": registry["source"]["repository_dirty"],
            "generator_config_path": registry["source"]["generator_config_path"],
            "generator_config_sha256": _sha(config_path),
        },
        "artifacts": {
            "online_frames_path": "online_frames.jsonl",
            "online_frames_sha256": sha256(online_bytes).hexdigest(),
            "offline_labels_path": "offline_labels.jsonl",
            "offline_labels_sha256": sha256(offline_bytes).hexdigest(),
        },
        "counts": {
            "cell_count": 15,
            "episode_count": 300,
            "unique_seed_count": 300,
            "frame_count": 2700,
            "positive_frame_count": 900,
            "negative_frame_count": 1800,
            "hard_negative_frame_count": 450,
            "online_truth_use_count": 0,
            "learning_created_global_track_id_count": 0,
            "learning_rewritten_global_track_id_count": 0,
            "duplicate_episode_count": 0,
            "duplicate_frame_count": 0,
        },
        "split": registry["split"],
        "cell_counts": [
            {"cell_id": cell["cell_id"], **cell_counts[cell["cell_id"]]}
            for cell in request["collection_cells"]
        ],
        "state": {
            "data_generated": True,
            "model_trained": False,
            "bundle_written": False,
            "v2_bundle_or_threshold_changed": False,
            "formal_holdout_read": False,
        },
        "permissions": _permissions(),
    }
    _write_json(root / "dataset_manifest.json", manifest)


def test_online_frame_strict_round_trip_covers_requested_observability() -> None:
    payload = _online_payload()
    frame = A1V3OnlineFrame.from_dict(payload)
    assert frame.to_dict() == payload
    assert frame.all_teacher_edges_in_candidate_mask is True
    assert frame.residual_ranking[0].rank == 1
    assert frame.target_demand_slots == (1,)
    assert frame.source.arrival_timestamp_s > frame.source.measurement_timestamp_s


@pytest.mark.parametrize(
    "failure_kind",
    (
        "missing_field",
        "identity_leak",
        "dual_timestamp",
        "mask_mismatch",
        "rank_mismatch",
        "demand_mismatch",
        "permission_true",
    ),
)
def test_online_frame_rejects_incomplete_or_unsafe_payloads(
    failure_kind: str,
) -> None:
    payload = deepcopy(_online_payload())
    if failure_kind == "missing_field":
        del payload["projection"]
    elif failure_kind == "identity_leak":
        payload["source"]["actor_id"] = "actor_target_0"
    elif failure_kind == "dual_timestamp":
        payload["source"]["arrival_timestamp_s"] = -1.0
    elif failure_kind == "mask_mismatch":
        payload["action_mask"]["true_count"] = 0
    elif failure_kind == "rank_mismatch":
        payload["model_residual_ranking"]["items"][0]["rank"] = 2
    elif failure_kind == "demand_mismatch":
        payload["anonymous_target_demand_slots"] = [2]
        payload["target_demand_slots_sha256"] = canonical_json_sha256([2])
    elif failure_kind == "permission_true":
        payload["permissions"]["assignment"] = True
    with pytest.raises(A1V3DataContractError):
        A1V3OnlineFrame.from_dict(payload)


def test_offline_label_is_separate_and_global_identity_remains_center_owned() -> None:
    request = _json(REQUEST_PATH)
    online = _online_payload()
    payload = _offline_payload(online)
    label = A1V3OfflineLabel.from_dict(
        payload,
        action_change_types=frozenset(request["action_change_types"]),
        hard_negative_types=frozenset(request["hard_negative_types"]),
    )
    assert label.online_payload_sha256 == canonical_json_sha256(online)
    leaked = deepcopy(payload)
    leaked["identity_provenance"][
        "learning_path_rewritten_global_track_id_count"
    ] = 1
    with pytest.raises(A1V3DataContractError, match="identity_provenance"):
        A1V3OfflineLabel.from_dict(
            leaked,
            action_change_types=frozenset(request["action_change_types"]),
            hard_negative_types=frozenset(request["hard_negative_types"]),
        )


def test_readiness_without_main_registry_is_request_only_and_cli_exits_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = validate_a1_v3_pre_generation_readiness()
    assert report.status == "request_only"
    assert report.ready is False
    assert report.reason_codes == ("main_seed_registry_missing",)
    assert contract_main(["readiness"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "request_only"
    assert output["data_generated"] is False


def test_readiness_accepts_exact_15_cell_300_episode_schedule(tmp_path: Path) -> None:
    _, registry_path, schedule_path = _contract_inputs(tmp_path)
    report = validate_a1_v3_pre_generation_readiness(
        registry_path=registry_path,
        schedule_path=schedule_path,
    )
    assert report.status == "ready"
    assert report.ready is True
    assert (report.cell_count, report.episode_count, report.unique_seed_count) == (
        15,
        300,
        300,
    )
    assert report.minimum_observable_frame_count == 2700
    assert report.minimum_hard_negative_frame_count == 450


def test_readiness_rejects_seed_overlap(tmp_path: Path) -> None:
    config_path, registry_path, _ = _contract_inputs(tmp_path)
    registry = _registry_payload(_sha(config_path))
    registry["allocation"]["assigned_seed_values"][0] = 0
    registry["split"]["seed_values"]["train"][0] = 0
    _write_json(registry_path, registry)
    schedule_path = tmp_path / "overlap_schedule.json"
    _write_json(schedule_path, _schedule_payload(registry_path))
    report = validate_a1_v3_pre_generation_readiness(
        registry_path=registry_path,
        schedule_path=schedule_path,
    )
    assert report.status == "fail_closed"
    assert report.reason_codes == ("registry_seed_overlap",)


def test_schedule_rejects_schema_or_duplicate_episode(tmp_path: Path) -> None:
    _, registry_path, schedule_path = _contract_inputs(tmp_path)
    schedule = _json(schedule_path)
    del schedule["record_contract"]["all_permissions_false"]
    _write_json(schedule_path, schedule)
    report = validate_a1_v3_pre_generation_readiness(
        registry_path=registry_path,
        schedule_path=schedule_path,
    )
    assert report.status == "fail_closed"
    assert report.reason_codes == ("schedule_record_contract_fields_mismatch",)


def test_read_only_loaders_validate_full_gate_and_strip_audit_identity(
    tmp_path: Path,
) -> None:
    config_path, registry_path, schedule_path = _contract_inputs(tmp_path)
    dataset_path = tmp_path / "dataset"
    _write_dataset(
        dataset_path,
        config_path=config_path,
        registry_path=registry_path,
        schedule_path=schedule_path,
    )
    before = {
        path.name: path.read_bytes()
        for path in (
            dataset_path / "dataset_manifest.json",
            dataset_path / "online_frames.jsonl",
            dataset_path / "offline_labels.jsonl",
        )
    }
    audit = load_a1_v3_audit_dataset(
        dataset_path,
        registry_path=registry_path,
        schedule_path=schedule_path,
        generator_config_path=config_path,
    )
    training = load_a1_v3_training_dataset(
        dataset_path,
        registry_path=registry_path,
        schedule_path=schedule_path,
        generator_config_path=config_path,
    )
    assert len(audit.online_frames) == len(audit.offline_labels) == 2700
    assert len(training.samples) == 2700
    assert training.manifest.episode_count == 300
    sample = training.samples[0]
    feature_payload = sample.features.to_model_input_dict()
    feature_keys = _recursive_keys(feature_payload)
    forbidden_fragments = (
        "teacher",
        "selected",
        "effective",
        "classification",
        "truth",
        "actor",
        "object",
        "global_track",
        "global_id",
    )
    assert feature_payload["schema_version"] == A1_V3_TRAINING_FEATURE_SCHEMA_V1
    assert not any(
        fragment in key.lower()
        for key in feature_keys
        for fragment in forbidden_fragments
    )
    assert not hasattr(sample, "online_frame")
    assert not hasattr(sample, "label")
    assert sample.target.to_dict()["schema_version"] == A1_V3_TRAINING_TARGET_SCHEMA_V1
    assert sample.target.teacher_edges == ((0, 0),)
    assert sample.target.frame_class in {"positive", "negative"}
    assert audit.online_frames[0].effective_selected_edges == ((0, 0),)
    assert not hasattr(sample.target, "effective_selected_edges")
    assert not hasattr(sample.target, "truth_target_labels")
    assert not hasattr(sample.target, "center_global_track_labels")
    with pytest.raises(FrozenInstanceError):
        sample.target.frame_class = "negative"  # type: ignore[misc]
    after = {path.name: path.read_bytes() for path in dataset_path.iterdir()}
    assert before == after


def test_training_loader_rejects_rehashed_file_with_broken_frame_binding(
    tmp_path: Path,
) -> None:
    config_path, registry_path, schedule_path = _contract_inputs(tmp_path)
    dataset_path = tmp_path / "dataset"
    _write_dataset(
        dataset_path,
        config_path=config_path,
        registry_path=registry_path,
        schedule_path=schedule_path,
    )
    offline_path = dataset_path / "offline_labels.jsonl"
    labels = [
        json.loads(line)
        for line in offline_path.read_text(encoding="ascii").splitlines()
    ]
    labels[0]["source_ref"]["online_payload_sha256"] = "f" * 64
    offline_bytes = b"".join(canonical_json_line(item) for item in labels)
    offline_path.write_bytes(offline_bytes)
    manifest_path = dataset_path / "dataset_manifest.json"
    manifest = _json(manifest_path)
    manifest["artifacts"]["offline_labels_sha256"] = sha256(
        offline_bytes
    ).hexdigest()
    _write_json(manifest_path, manifest)

    with pytest.raises(
        A1V3DataContractError,
        match="offline_online_payload_sha256_mismatch",
    ):
        load_a1_v3_training_dataset(
            dataset_path,
            registry_path=registry_path,
            schedule_path=schedule_path,
            generator_config_path=config_path,
        )


def _recursive_keys(value: object) -> tuple[str, ...]:
    keys: list[str] = []
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            keys.extend(str(key) for key in item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return tuple(keys)
