from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from d5_terminal_association.active_vision_a3_v3_protocol import (
    load_frozen_a3_v3_protocol,
)
from d5_terminal_association.active_vision_a3_v3_source_readiness import (
    A3V3SourceReadinessError,
    A3_V3_PRE_GENERATION_READINESS_SCHEMA_VERSION,
    SOURCE_GENERATION_REQUEST_RELATIVE_PATH,
    validate_a3_v3_allocation_binding,
    validate_a3_v3_pre_generation_readiness,
    validate_a3_v3_registry_allocation,
    validate_a3_v3_source_generation_request,
    validate_a3_v3_source_schedule,
    _validate_episode_runtime_sample_capacity,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
PROTOCOL_PATH = (
    MODULE_ROOT / "configs/a3_v3_minority_intent_protocol_20260801.json"
)
BINDING_PATH = (
    MODULE_ROOT / "configs/a3_v3_global_seed_allocation_binding_20260801.json"
)
SCHEDULE_PATH = MODULE_ROOT / "configs/a3_v3_source_collection_schedule_20260801.json"
REQUEST_PATH = (
    MODULE_ROOT / "configs/a3_v3_source_generation_request_20260801.json"
)
REGISTRY_PATH = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rehash(payload: dict[str, object]) -> None:
    content = dict(payload)
    content.pop("content_sha256", None)
    encoded = json.dumps(
        content,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    payload["content_sha256"] = hashlib.sha256(encoded).hexdigest()


def _validate_schedule(payload: dict[str, object]) -> None:
    protocol = load_frozen_a3_v3_protocol(PROTOCOL_PATH)
    binding = _load(BINDING_PATH)
    validate_a3_v3_source_schedule(
        payload,
        protocol=protocol,
        binding=binding,
        binding_file_sha256=hashlib.sha256(BINDING_PATH.read_bytes()).hexdigest(),
        repository_root=REPOSITORY_ROOT,
    )


def _allocation(split: str) -> dict[str, object]:
    allocation_id = {
        "train": "d5-a3-v3-train",
        "validation": "d5-a3-v3-validation",
        "future_held_out": "d5-a3-v3-future-held-out",
    }[split]
    return deepcopy(
        next(
            item
            for item in _load(REGISTRY_PATH)["allocations"]
            if item["allocation_id"] == allocation_id
        )
    )


def _copy_metadata_tree(destination: Path) -> dict[str, Path]:
    relative_paths = {
        "protocol": Path(
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_intent_protocol_20260801.json"
        ),
        "protocol_schema": Path(
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_intent_protocol.schema.json"
        ),
        "source_schema": Path(
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_source_manifest.schema.json"
        ),
        "binding": Path(
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_global_seed_allocation_binding_20260801.json"
        ),
        "schedule": Path(
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_source_collection_schedule_20260801.json"
        ),
        "request": Path(SOURCE_GENERATION_REQUEST_RELATIVE_PATH),
        "registry": Path(
            "research_modules/scalable_3d_simulation/configs/"
            "scalable_learning_global_seed_registry_v1.json"
        ),
        "producer_generation": Path(
            "research_modules/scalable_3d_simulation/learning_source_generation.py"
        ),
        "producer_recipes": Path(
            "research_modules/scalable_3d_simulation/learning_source_recipes.py"
        ),
        "producer_adapters": Path(
            "research_modules/scalable_3d_simulation/learning_source_adapters.py"
        ),
        "producer_stack": Path(
            "research_modules/scalable_3d_simulation/module_stack.py"
        ),
        "producer_orchestrator": Path(
            "research_modules/scalable_3d_simulation/orchestrator.py"
        ),
        "producer_treatment": Path(
            "research_modules/scalable_3d_simulation/active_vision_collection.py"
        ),
        "producer_base_config": Path(
            "research_modules/scalable_3d_simulation/configs/"
            "nominal_200v200.json"
        ),
        "episode_staging_implementation": Path(
            "research_modules/d5_terminal_association/src/"
            "d5_terminal_association/active_vision_a3_v3_episode_evidence.py"
        ),
    }
    result: dict[str, Path] = {}
    for name, relative in relative_paths.items():
        source = REPOSITORY_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        result[name] = target
    return result


def _validate_copied_tree(root: Path, paths: dict[str, Path]) -> None:
    validate_a3_v3_pre_generation_readiness(
        repository_root=root,
        protocol_path=paths["protocol"],
        allocation_binding_path=paths["binding"],
        source_schedule_path=paths["schedule"],
        global_registry_path=paths["registry"],
        source_generation_request_path=paths["request"],
    )


def test_actual_generation_only_request_is_ready_with_stable_main_fields() -> None:
    readiness = validate_a3_v3_pre_generation_readiness()
    report = readiness.to_dict()

    assert report["schema_version"] == A3_V3_PRE_GENERATION_READINESS_SCHEMA_VERSION
    assert readiness.status == "source_generation_request_ready_generation_only"
    assert report["plan_ready"] is True
    assert readiness.pre_generation_ready is True
    assert report["producer_adapter_complete"] is True
    assert report["source_generation_request_ready"] is True
    assert report["source_generation_request_path"] == (
        SOURCE_GENERATION_REQUEST_RELATIVE_PATH
    )
    assert report["source_generation_request_sha256"] == hashlib.sha256(
        REQUEST_PATH.read_bytes()
    ).hexdigest()
    assert report["source_generation_execution_authorized"] is False
    assert report["generation_started"] is False
    assert report["training_ready"] is False
    assert report["future_held_out_payload_read_allowed"] is False
    assert report["episode_payload_read_count"] == 0
    assert report["sample_payload_read_count"] == 0
    assert report["split_summary"]["train"]["seed_count"] == 48
    assert report["split_summary"]["validation"]["seed_count"] == 24
    assert report["split_summary"]["future_held_out"]["seed_count"] == 32
    assert report["split_summary"]["train"][
        "planned_minimum_unique_sample_count"
    ] == 4608
    assert report["source_schedule"]["planned_episode_count"] == 104
    assert report["producer_capability"]["viability_audit"] == {
        "status": "all_frozen_entries_runtime_sample_capacity_passed",
        "frozen_episode_count": 104,
        "intent_window_count": 416,
        "minimum_window_capacity": 24,
        "minimum_window_quota": 24,
        "minimum_capacity_margin": 0,
        "episode_payload_read_count": 0,
        "sample_payload_read_count": 0,
    }
    assert report["producer_capability"]["adapter_status"] == (
        "complete_smoke_verified"
    )
    capability = report["producer_capability"]
    assert capability["source_generation_request_path"] == (
        SOURCE_GENERATION_REQUEST_RELATIVE_PATH
    )
    assert capability["source_generation_request_sha256"] == report[
        "source_generation_request_sha256"
    ]
    assert capability["source_generation_request_ready"] is True
    assert capability["cross_process_resume_supported"] is True
    assert capability["blockers"] == []
    assert all(
        "unsupported" not in value and "partial" not in value
        for value in report["producer_capability"]["entry_field_support"].values()
    )
    assert all(
        value.startswith("supported_by_")
        for value in report["producer_capability"]["recipe_support"].values()
    )
    assert {
        name for name, enabled in report["permissions"].items() if enabled
    } == {"source_artifact_generation"}
    assert not any(report["authority"].values())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("owner", "main", "allocation_owner_mismatch"),
        ("candidate_version", "d5-a3-v4", "candidate_version_mismatch"),
        ("lifecycle", "active", "allocation_lifecycle_mismatch"),
        ("usage_class", "train_validation_test", "allocation_usage_class_mismatch"),
        ("permitted_operations", ["dataset_generation"], "permitted_operations_mismatch"),
    ],
)
def test_allocation_owner_version_usage_and_operations_drift_fail_closed(
    field: str,
    value: object,
    message: str,
) -> None:
    allocation = _allocation("train")
    allocation[field] = value

    with pytest.raises(A3V3SourceReadinessError, match=message):
        validate_a3_v3_registry_allocation(allocation, split="train")


def test_allocation_exact_seed_set_and_source_binding_drift_fail_closed() -> None:
    allocation = _allocation("validation")
    allocation["seeds"][-1] = 24150
    with pytest.raises(A3V3SourceReadinessError, match="exact_seed_set_mismatch"):
        validate_a3_v3_registry_allocation(allocation, split="validation")

    allocation = _allocation("train")
    allocation["source_contract"]["bindings"][0]["sha256"] = "0" * 64
    with pytest.raises(A3V3SourceReadinessError, match="source_contract_mismatch"):
        validate_a3_v3_registry_allocation(allocation, split="train")


def test_binding_protocol_hash_and_prohibited_source_policy_drift_fail_closed() -> None:
    binding = _load(BINDING_PATH)
    binding["protocol_binding"]["sha256"] = "0" * 64
    _rehash(binding)
    with pytest.raises(A3V3SourceReadinessError, match="protocol_mismatch"):
        validate_a3_v3_allocation_binding(binding)

    binding = _load(BINDING_PATH)
    binding["prohibited_payload_sources"][1][
        "episode_or_sample_payload_read_allowed"
    ] = True
    _rehash(binding)
    with pytest.raises(A3V3SourceReadinessError, match="prohibited_sources_mismatch"):
        validate_a3_v3_allocation_binding(binding)


def test_schedule_has_104_unique_whole_episode_seed_entries() -> None:
    schedule = _load(SCHEDULE_PATH)
    entries = schedule["episode_entries"]

    assert len(entries) == 104
    assert [entry["entry_index"] for entry in entries] == list(range(104))
    assert [entry["seed"] for entry in entries] == list(range(24000, 24104))
    assert len({entry["episode_id"] for entry in entries}) == 104
    assert len({entry["seed"] for entry in entries}) == 104
    assert all(entry["camera_roles"] == ["interceptor", "recon"] for entry in entries)
    assert all(entry["duration_s"] == 8.0 for entry in entries)
    assert all(entry["recon_count"] >= 4 for entry in entries)
    assert all(len(entry["intent_windows"]) == 4 for entry in entries)
    assert all(
        window["end_s"] - window["start_s"] == 2.0
        for entry in entries
        for window in entry["intent_windows"]
    )
    assert all(len(entry["hard_confusion_assignments"]) == 2 for entry in entries)
    assert all(entry["minimum_unique_sample_quota"]["total"] == 96 for entry in entries)
    assert not any(
        value
        for entry in entries
        for value in entry["generation_controls"].values()
    )


def test_all_104_frozen_cells_have_conservative_runtime_sample_capacity() -> None:
    entries = _load(SCHEDULE_PATH)["episode_entries"]
    capacities = {
        entry["episode_id"]: _validate_episode_runtime_sample_capacity(entry)
        for entry in entries
    }

    assert len(capacities) == 104
    assert min(
        capacity
        for episode in capacities.values()
        for capacity in episode.values()
    ) >= 24
    assert {entry["split"] for entry in entries} == {
        "train",
        "validation",
        "future_held_out",
    }
    assert {
        tuple(window["camera_role"] for window in entry["intent_windows"])
        for entry in entries
    } == {
        ("interceptor", "recon", "interceptor", "recon"),
        ("recon", "interceptor", "recon", "interceptor"),
    }
    assert {
        assignment["family"]
        for entry in entries
        for assignment in entry["hard_confusion_assignments"]
    } == {
        "observe_vs_reacquire_projection_boundary",
        "search_vs_reacquire_cue_loss_boundary",
        "hold_vs_observe_gimbal_busy_boundary",
        "role_matched_interceptor_recon_geometry",
        "multiple_legal_targets_near_tie",
    }


def test_runtime_sample_capacity_rejects_old_single_recon_schedule() -> None:
    entry = deepcopy(_load(SCHEDULE_PATH)["episode_entries"][1])
    entry["recon_count"] = 1

    with pytest.raises(
        A3V3SourceReadinessError,
        match="runtime_sample_capacity_below_quota",
    ):
        _validate_episode_runtime_sample_capacity(entry)


def test_schedule_aggregate_coverage_matches_protocol_minimums() -> None:
    schedule = _load(SCHEDULE_PATH)
    summary = schedule["planned_coverage_summary"]
    expected_episode_counts = {"train": 48, "validation": 24, "future_held_out": 32}
    expected_total_samples = {"train": 4608, "validation": 2304, "future_held_out": 3072}
    minimum_intent_role_episodes = {"train": 16, "validation": 8, "future_held_out": 12}
    minimum_hard_episodes = {"train": 12, "validation": 6, "future_held_out": 8}

    for split, coverage in summary.items():
        assert coverage["planned_episode_count"] == expected_episode_counts[split]
        assert coverage["seed_count"] == expected_episode_counts[split]
        assert coverage["total"]["minimum_unique_samples"] == expected_total_samples[split]
        assert all(
            cell["minimum_unique_episodes"] >= minimum_intent_role_episodes[split]
            and cell["minimum_unique_seeds"] >= minimum_intent_role_episodes[split]
            for cell in coverage["per_intent_camera_role"].values()
        )
        assert all(
            family["minimum_unique_episodes"] >= minimum_hard_episodes[split]
            and family["minimum_unique_seeds"] >= minimum_hard_episodes[split]
            for family in coverage["hard_confusion_families"].values()
        )

    _validate_schedule(schedule)


def test_deleting_one_episode_entry_fails_closed_after_rehash() -> None:
    schedule = _load(SCHEDULE_PATH)
    schedule["episode_entries"].pop()
    _rehash(schedule)

    with pytest.raises(A3V3SourceReadinessError, match="episode_count_mismatch"):
        _validate_schedule(schedule)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda entry: entry.__setitem__("seed", 24001),
            "episode_seed_mismatch",
        ),
        (
            lambda entry: entry.__setitem__("episode_id", "tampered-episode"),
            "episode_episode_id_mismatch",
        ),
        (
            lambda entry: entry["intent_windows"][0].__setitem__(
                "treatment_recipe", "unsupported_recipe"
            ),
            "episode_intent_windows_mismatch",
        ),
        (
            lambda entry: entry["hard_confusion_assignments"].pop(),
            "episode_hard_confusion_assignments_mismatch",
        ),
        (
            lambda entry: entry["minimum_unique_sample_quota"].__setitem__(
                "total", 95
            ),
            "episode_minimum_unique_sample_quota_mismatch",
        ),
    ],
)
def test_episode_seed_window_recipe_and_quota_drift_fail_closed(
    mutate,
    message: str,
) -> None:
    schedule = _load(SCHEDULE_PATH)
    mutate(schedule["episode_entries"][0])
    _rehash(schedule)

    with pytest.raises(A3V3SourceReadinessError, match=message):
        _validate_schedule(schedule)


def test_declared_coverage_summary_cannot_replace_entry_recount() -> None:
    schedule = _load(SCHEDULE_PATH)
    schedule["planned_coverage_summary"]["train"]["total"][
        "minimum_unique_samples"
    ] += 1
    _rehash(schedule)

    with pytest.raises(A3V3SourceReadinessError, match="coverage_summary_mismatch"):
        _validate_schedule(schedule)


def test_independent_request_does_not_mutate_frozen_schedule_assessment() -> None:
    readiness = validate_a3_v3_pre_generation_readiness().to_dict()
    assert readiness["status"] == "source_generation_request_ready_generation_only"
    assert readiness["plan_ready"] is True
    assert readiness["pre_generation_ready"] is True
    assert readiness["producer_adapter_complete"] is True
    assert readiness["source_generation_request_ready"] is True

    schedule = _load(SCHEDULE_PATH)
    capability = schedule["producer_capability_assessment"]
    assert capability["source_generation_request_ready"] is False
    assert capability["blockers"] == [
        "d5_source_generation_request_not_authorized"
    ]
    capability["source_generation_request_ready"] = True
    capability["blockers"] = []
    _rehash(schedule)
    with pytest.raises(A3V3SourceReadinessError, match="capability_assessment_mismatch"):
        _validate_schedule(schedule)


def test_generation_request_reference_hash_drift_fails_closed(tmp_path: Path) -> None:
    paths = _copy_metadata_tree(tmp_path)
    request = _load(paths["request"])
    request["artifact_bindings"]["source_collection_schedule"]["sha256"] = (
        "0" * 64
    )
    _rehash(request)
    paths["request"].write_text(json.dumps(request), encoding="utf-8")

    with pytest.raises(A3V3SourceReadinessError, match="binding_mismatch"):
        _validate_copied_tree(tmp_path, paths)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: request["source_request"].__setitem__(
            "planned_episode_count", 103
        ),
        lambda request: request["source_request"]["split_requests"][
            "train"
        ].__setitem__("seed_count", 47),
        lambda request: request["source_request"]["split_requests"][
            "future_held_out"
        ].__setitem__("seed_range", [24072, 24102]),
    ],
)
def test_generation_request_episode_split_and_seed_drift_fail_closed(
    mutate,
) -> None:
    request = _load(REQUEST_PATH)
    mutate(request)
    _rehash(request)

    with pytest.raises(A3V3SourceReadinessError):
        validate_a3_v3_source_generation_request(request)


def test_generation_request_missing_future_one_shot_constraint_fails_closed() -> None:
    request = _load(REQUEST_PATH)
    request["future_held_out_access"].pop("second_access_allowed")
    _rehash(request)

    with pytest.raises(A3V3SourceReadinessError, match="future_access_mismatch"):
        validate_a3_v3_source_generation_request(request)


def test_generation_request_future_integrity_only_finalize_drift_fails_closed() -> None:
    request = _load(REQUEST_PATH)
    request["resume_contract"]["future_held_out_integrity_only_finalize"] = False
    _rehash(request)

    with pytest.raises(A3V3SourceReadinessError, match="resume_contract_mismatch"):
        validate_a3_v3_source_generation_request(request)


@pytest.mark.parametrize(
    "permission",
    [
        "model_artifact_generation",
        "model_training",
        "model_inference",
        "model_selection",
        "future_held_out_payload_read",
        "future_held_out_model_selection",
        "shadow",
        "assist",
        "camera_command",
        "runtime",
        "production",
        "control",
        "global_track_id_write",
    ],
)
def test_generation_request_privilege_escalation_fails_closed(
    permission: str,
) -> None:
    request = _load(REQUEST_PATH)
    request["permissions"][permission] = True
    _rehash(request)

    with pytest.raises(A3V3SourceReadinessError, match="permissions_mismatch"):
        validate_a3_v3_source_generation_request(request)


def test_generation_request_online_truth_identity_drift_fails_closed() -> None:
    request = _load(REQUEST_PATH)
    request["identity"]["truth_identity_available_to_online_policy"] = True
    _rehash(request)

    with pytest.raises(A3V3SourceReadinessError, match="identity_mismatch"):
        validate_a3_v3_source_generation_request(request)


def test_future_heldout_permission_drift_fails_closed() -> None:
    schedule = _load(SCHEDULE_PATH)
    schedule["future_held_out_access"][
        "episode_or_sample_payload_read_allowed_before_model_freeze"
    ] = True
    _rehash(schedule)

    with pytest.raises(A3V3SourceReadinessError, match="future_access_mismatch"):
        _validate_schedule(schedule)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["identity"].__setitem__(
            "global_track_id_write_allowed", True
        ),
        lambda payload: payload["authority"].__setitem__("camera_command", True),
        lambda payload: payload["generation_state"].__setitem__(
            "future_held_out_payload_read_count", 1
        ),
    ],
)
def test_identity_authority_and_future_read_state_drift_fail_closed(mutate) -> None:
    schedule = _load(SCHEDULE_PATH)
    mutate(schedule)
    _rehash(schedule)

    with pytest.raises(A3V3SourceReadinessError):
        _validate_schedule(schedule)


def test_registry_self_hash_and_file_hash_are_independent_guards(tmp_path: Path) -> None:
    paths = _copy_metadata_tree(tmp_path / "self-hash")
    registry = _load(paths["registry"])
    registry["status"] = "tampered"
    paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(A3V3SourceReadinessError, match="content_sha256_mismatch"):
        _validate_copied_tree(tmp_path / "self-hash", paths)

    paths = _copy_metadata_tree(tmp_path / "file-hash")
    registry = _load(paths["registry"])
    registry["status"] = "tampered"
    _rehash(registry)
    paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(A3V3SourceReadinessError, match="file_sha256_mismatch"):
        _validate_copied_tree(tmp_path / "file-hash", paths)


def test_actual_source_binding_file_drift_fails_closed(tmp_path: Path) -> None:
    paths = _copy_metadata_tree(tmp_path)
    paths["protocol_schema"].write_bytes(paths["protocol_schema"].read_bytes() + b"\n")

    with pytest.raises(A3V3SourceReadinessError, match="source_binding_hash_mismatch"):
        _validate_copied_tree(tmp_path, paths)


def test_producer_source_hash_drift_fails_closed(tmp_path: Path) -> None:
    paths = _copy_metadata_tree(tmp_path)
    paths["producer_treatment"].write_bytes(
        paths["producer_treatment"].read_bytes() + b"\n"
    )

    with pytest.raises(A3V3SourceReadinessError, match="producer_source_hash_mismatch"):
        _validate_copied_tree(tmp_path, paths)


def test_protocol_file_drift_fails_before_any_payload_access(tmp_path: Path) -> None:
    paths = _copy_metadata_tree(tmp_path)
    paths["protocol"].write_bytes(paths["protocol"].read_bytes() + b"\n")

    with pytest.raises(A3V3SourceReadinessError, match="protocol_sha256_mismatch"):
        _validate_copied_tree(tmp_path, paths)
