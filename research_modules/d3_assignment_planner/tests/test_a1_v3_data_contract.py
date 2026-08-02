from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d3_assignment_planner.a1_v3_data_contract import (
    A1_V3_DATASET_MANIFEST_SCHEMA_V1,
    A1_V3_OFFLINE_LABEL_SCHEMA_V1,
    A1_V3_NEAR_TIE_BOUNDARY_ID_V1,
    A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP,
    A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP,
    A1_V3_NEAR_TIE_REASON_MET,
    A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR,
    A1_V3_ONLINE_FRAME_SCHEMA_V1,
    A1_V3_PERMISSION_FIELDS,
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
GENERATOR_CONFIG_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generator_config_v1.json"
)
MAIN_REGISTRY_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_main_allocation_registry_v1.json"
)
SCHEDULE_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generation_schedule_v1.json"
)
GLOBAL_REGISTRY_PATH = (
    MODULE_ROOT.parent
    / "scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
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
    edges = [[0, 0], [0, 1]]
    edge_costs = [
        {"edge": [0, 0], "rule_cost": 1.0},
        {"edge": [0, 1], "rule_cost": 1.001},
    ]
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
            "anonymous_resource_count": 2,
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
            "items": [
                {"edge": [0, 0], "residual": 0.0, "rank": 1},
                {"edge": [0, 1], "residual": 0.5, "rank": 2},
            ],
        },
        "action_mask": {
            "shape": [1, 2],
            "true_count": 2,
            "content_sha256": action_mask_content_sha256(
                (1, 2), ((0, 0), (0, 1))
            ),
        },
        "rule_cost_near_tie": {
            "boundary_id": A1_V3_NEAR_TIE_BOUNDARY_ID_V1,
            "maximum_absolute_gap": A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP,
            "maximum_relative_gap": A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP,
            "relative_denominator_floor": (
                A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR
            ),
            "qualification_logic": "absolute_and_relative",
            "candidate_edge_costs": edge_costs,
            "candidate_edge_costs_sha256": canonical_json_sha256(edge_costs),
            "evaluated_target_count": 1,
            "qualifying_target_count": 1,
            "target_margins": [
                {
                    "target_index": 0,
                    "best_edge": [0, 0],
                    "second_edge": [0, 1],
                    "best_rule_cost": 1.0,
                    "second_rule_cost": 1.001,
                    "absolute_gap": 0.0009999999999998899,
                    "relative_gap": 0.0009999999999998899,
                    "qualifies": True,
                }
            ],
            "reason_code": A1_V3_NEAR_TIE_REASON_MET,
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


def _validate_frozen_readiness(
    *,
    generator_config_path: Path = GENERATOR_CONFIG_PATH,
    global_registry_path: Path = GLOBAL_REGISTRY_PATH,
    registry_path: Path = MAIN_REGISTRY_PATH,
    schedule_path: Path = SCHEDULE_PATH,
):
    return validate_a1_v3_pre_generation_readiness(
        generator_config_path=generator_config_path,
        global_registry_path=global_registry_path,
        registry_path=registry_path,
        schedule_path=schedule_path,
    )


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
        "offline_identity_audit": {
            "availability": "unavailable",
            "complete_identity_audit_claimed": False,
            "complete_identity_label_frame_count": 0,
            "partial_identity_label_frame_count": 0,
            "empty_identity_label_frame_count": 2700,
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


def test_api_can_report_request_only_while_default_cli_uses_frozen_plan(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = validate_a1_v3_pre_generation_readiness()
    assert report.status == "request_only"
    assert report.ready is False
    assert report.reason_codes == ("main_seed_registry_missing",)
    assert contract_main(["readiness"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ready"
    assert output["plan_only"] is True
    assert output["data_generated"] is False
    assert output["permissions"] == _permissions()


def test_readiness_accepts_exact_global_allocation_and_fixed_schedule() -> None:
    report = _validate_frozen_readiness()
    assert report.status == "ready"
    assert report.ready is True
    assert (report.cell_count, report.episode_count, report.unique_seed_count) == (
        15,
        300,
        300,
    )
    assert report.minimum_observable_frame_count == 2700
    assert report.minimum_hard_negative_frame_count == 450
    assert report.global_registry_id == (
        "scalable3d-learning-source-allocation-20260801-v1"
    )
    assert report.allocation_id == "d3-a1-v3-all-splits"
    assert report.generator_config_id == "d3-a1-v3-generator-config-20260801-v1"
    schedule = _json(SCHEDULE_PATH)
    per_cell: dict[str, dict[str, int]] = {}
    for episode in schedule["episodes"]:
        counts = per_cell.setdefault(
            episode["cell_id"], {"train": 0, "validation": 0, "test": 0}
        )
        counts[episode["split"]] += 1
    assert len(per_cell) == 15
    assert set(tuple(counts.values()) for counts in per_cell.values()) == {(12, 4, 4)}


def test_readiness_rejects_global_registry_file_or_hash_drift(tmp_path: Path) -> None:
    global_registry = deepcopy(_json(GLOBAL_REGISTRY_PATH))
    global_registry["generation_state"]["formal_seed_payload_read"] = True
    path = tmp_path / "global_registry.json"
    _write_json(path, global_registry)
    report = _validate_frozen_readiness(global_registry_path=path)
    assert report.status == "fail_closed"
    assert report.reason_codes == ("global_registry_file_sha256_mismatch",)


def test_readiness_rejects_generator_config_hash_or_source_drift(
    tmp_path: Path,
) -> None:
    config = deepcopy(_json(GENERATOR_CONFIG_PATH))
    config["source"]["repository_dirty"] = True
    path = tmp_path / "generator_config.json"
    _write_json(path, config)
    report = _validate_frozen_readiness(generator_config_path=path)
    assert report.status == "fail_closed"
    assert report.reason_codes == ("registry_generator_source_mismatch",)


def test_readiness_rejects_seed_drift_from_exact_global_allocation(
    tmp_path: Path,
) -> None:
    registry = deepcopy(_json(MAIN_REGISTRY_PATH))
    registry["allocation"]["assigned_seed_values"][0] = 22999
    registry["split"]["seed_values"]["train"][0] = 22999
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, registry)
    report = _validate_frozen_readiness(registry_path=registry_path)
    assert report.status == "fail_closed"
    assert report.reason_codes == (
        "registry_assigned_seed_global_allocation_mismatch",
    )


def test_readiness_rejects_incomplete_global_forbidden_union(tmp_path: Path) -> None:
    registry = deepcopy(_json(MAIN_REGISTRY_PATH))
    forbidden = registry["allocation"]["forbidden_seed_values"]
    forbidden.remove(24000)
    registry["allocation"]["forbidden_seed_count"] = len(forbidden)
    registry["allocation"]["forbidden_seed_values_sha256"] = canonical_json_sha256(
        forbidden
    )
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, registry)
    report = _validate_frozen_readiness(registry_path=registry_path)
    assert report.status == "fail_closed"
    assert report.reason_codes == ("registry_global_forbidden_union_mismatch",)


def test_readiness_rejects_whole_seed_split_drift(tmp_path: Path) -> None:
    registry = deepcopy(_json(MAIN_REGISTRY_PATH))
    train = registry["split"]["seed_values"]["train"]
    validation = registry["split"]["seed_values"]["validation"]
    train[-1], validation[0] = validation[0], train[-1]
    train.sort()
    validation.sort()
    registry_path = tmp_path / "registry.json"
    _write_json(registry_path, registry)
    report = _validate_frozen_readiness(registry_path=registry_path)
    assert report.status == "fail_closed"
    assert report.reason_codes == ("registry_fixed_split_seed_assignment_mismatch",)


def test_readiness_rejects_cell_assignment_drift(tmp_path: Path) -> None:
    schedule = deepcopy(_json(SCHEDULE_PATH))
    left = schedule["episodes"][0]
    right = schedule["episodes"][20]
    cell_fields = (
        "cell_id",
        "scenario_family",
        "configured_target_count",
        "configured_resource_count",
    )
    for field in cell_fields:
        left[field], right[field] = right[field], left[field]
    schedule_path = tmp_path / "schedule.json"
    _write_json(schedule_path, schedule)
    report = _validate_frozen_readiness(schedule_path=schedule_path)
    assert report.status == "fail_closed"
    assert report.reason_codes == ("schedule_fixed_cell_seed_assignment_mismatch",)


@pytest.mark.parametrize(
    "artifact",
    ("generator_config", "registry", "schedule"),
)
@pytest.mark.parametrize("permission_name", A1_V3_PERMISSION_FIELDS)
def test_readiness_rejects_any_permission_drift(
    tmp_path: Path,
    artifact: str,
    permission_name: str,
) -> None:
    source_paths = {
        "generator_config": GENERATOR_CONFIG_PATH,
        "registry": MAIN_REGISTRY_PATH,
        "schedule": SCHEDULE_PATH,
    }
    payload = deepcopy(_json(source_paths[artifact]))
    payload["permissions"][permission_name] = True
    drifted_path = tmp_path / f"{artifact}.json"
    _write_json(drifted_path, payload)
    kwargs = {f"{artifact}_path": drifted_path}
    if artifact == "generator_config":
        kwargs = {"generator_config_path": drifted_path}
    report = _validate_frozen_readiness(**kwargs)
    assert report.status == "fail_closed"
    assert report.reason_codes == ("permission_true_forbidden",)


def test_read_only_loaders_validate_full_gate_and_strip_audit_identity(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "dataset"
    _write_dataset(
        dataset_path,
        config_path=GENERATOR_CONFIG_PATH,
        registry_path=MAIN_REGISTRY_PATH,
        schedule_path=SCHEDULE_PATH,
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
        registry_path=MAIN_REGISTRY_PATH,
        schedule_path=SCHEDULE_PATH,
        generator_config_path=GENERATOR_CONFIG_PATH,
        global_registry_path=GLOBAL_REGISTRY_PATH,
    )
    training = load_a1_v3_training_dataset(
        dataset_path,
        registry_path=MAIN_REGISTRY_PATH,
        schedule_path=SCHEDULE_PATH,
        generator_config_path=GENERATOR_CONFIG_PATH,
        global_registry_path=GLOBAL_REGISTRY_PATH,
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
    dataset_path = tmp_path / "dataset"
    _write_dataset(
        dataset_path,
        config_path=GENERATOR_CONFIG_PATH,
        registry_path=MAIN_REGISTRY_PATH,
        schedule_path=SCHEDULE_PATH,
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
            registry_path=MAIN_REGISTRY_PATH,
            schedule_path=SCHEDULE_PATH,
            generator_config_path=GENERATOR_CONFIG_PATH,
            global_registry_path=GLOBAL_REGISTRY_PATH,
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
