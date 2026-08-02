"""Strict A1 v3 source-generation request-readiness artifact loader."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .a1_v3_data_contract import (
    A1_V3_DATA_CONTRACT_SCHEMA_V1,
    A1_V3_GENERATION_SCHEDULE_SCHEMA_V1,
    A1_V3_GLOBAL_SEED_REGISTRY_SCHEMA_V1,
    A1_V3_MAIN_SEED_REGISTRY_SCHEMA_V1,
    A1_V3_OFFLINE_LABEL_SCHEMA_V1,
    A1_V3_ONLINE_FRAME_SCHEMA_V1,
    A1_V3_REQUEST_SCHEMA_V1,
    A1_V3_SOURCE_GENERATION_REQUEST_ID,
    A1_V3_SOURCE_GENERATION_REQUEST_LOGICAL_PATH,
    A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS,
    A1_V3_SOURCE_GENERATION_REQUEST_SCHEMA_V1,
    A1_V3_SPLIT_POLICY_V1,
    A1_V3_SPLIT_SEED_COUNTS,
    A1_V3_TRAINING_FEATURE_SCHEMA_V1,
    A1_V3_TRAINING_TARGET_SCHEMA_V1,
    A1V3ContractDescriptor,
    A1V3DataContractError,
    A1V3FrozenRequest,
    A1V3GenerationSchedule,
    A1V3GlobalAllocation,
    A1V3SeedRegistry,
    canonical_json_sha256,
)
from .a1_v3_sidecar_classification import (
    A1_V3_DERIVABLE_ACTION_CHANGE_TYPES,
    A1_V3_DERIVABLE_HARD_NEGATIVE_TYPES,
    A1_V3_REJECTED_UNDERIVED_TAXONOMY,
    A1_V3_SIDECAR_CLASSIFICATION_POLICY_ID,
    A1_V3_SIDECAR_CLASSIFICATION_POLICY_SCHEMA_V1,
    A1_V3_SIDECAR_CLASSIFICATION_SCHEMA_V1,
    A1_V3_SIDECAR_CLASSIFIER_LOGICAL_PATH,
    DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH,
    load_a1_v3_sidecar_classification_policy,
)


_REQUEST_PATH = (
    "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_development_data_request_v1.json"
)
_SCHEDULE_PATH = (
    "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_generation_schedule_v1.json"
)
_ALLOCATION_PATH = (
    "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_main_allocation_registry_v1.json"
)
_GLOBAL_REGISTRY_PATH = (
    "research_modules/scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)
_DATA_CONTRACT_PATH = (
    "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_data_contract_v1.json"
)
_SIDECAR_POLICY_PATH = (
    "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_sidecar_classification_policy_v1.json"
)
_NEAR_TIE_BOUNDARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs/a1_source_independent_v3_near_tie_boundary_v1.json"
)
_RUNTIME_QUOTA_PROBE = {
    "probe_date": "2026-08-02",
    "duration_s": 10.0,
    "audited_cell_count": 15,
    "audited_recipe_count": 15,
    "required_per_episode": {
        "positive_frame_count": 3,
        "negative_frame_count": 3,
        "hard_negative_frame_count": 2,
    },
    "passing_runtime_to_writer_recipe_ids": [
        "a1-v3-cell-00-train-00",
        "a1-v3-cell-01-train-00",
        "a1-v3-cell-02-train-00",
        "a1-v3-cell-03-train-00",
        "a1-v3-cell-04-train-00",
        "a1-v3-cell-05-train-00",
        "a1-v3-cell-06-train-00",
        "a1-v3-cell-07-train-00",
        "a1-v3-cell-08-train-00",
        "a1-v3-cell-09-train-00",
        "a1-v3-cell-10-train-00",
        "a1-v3-cell-11-train-00",
        "a1-v3-cell-12-train-00",
        "a1-v3-cell-13-train-00",
        "a1-v3-cell-14-train-00",
    ],
    "blocking_cell_ids": [],
    "runtime_results": [
        {
            "cell_id": "nominal-balanced-5t5r",
            "episode_id": "a1-v3-cell-00-train-00",
            "seed": 23000,
            "frame_count": 10,
            "positive_frame_count": 3,
            "negative_frame_count": 7,
            "hard_negative_frame_count": 3,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "dense-crossing-20t20r",
            "episode_id": "a1-v3-cell-01-train-00",
            "seed": 23012,
            "frame_count": 10,
            "positive_frame_count": 3,
            "negative_frame_count": 7,
            "hard_negative_frame_count": 6,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "dense-crossing-50t50r",
            "episode_id": "a1-v3-cell-02-train-00",
            "seed": 23024,
            "frame_count": 10,
            "positive_frame_count": 7,
            "negative_frame_count": 3,
            "hard_negative_frame_count": 3,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "formation-split-50t50r",
            "episode_id": "a1-v3-cell-03-train-00",
            "seed": 23036,
            "frame_count": 10,
            "positive_frame_count": 4,
            "negative_frame_count": 6,
            "hard_negative_frame_count": 6,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "evasive-multilevel-100t100r",
            "episode_id": "a1-v3-cell-04-train-00",
            "seed": 23048,
            "frame_count": 10,
            "positive_frame_count": 6,
            "negative_frame_count": 4,
            "hard_negative_frame_count": 4,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "delayed-noisy-200t200r",
            "episode_id": "a1-v3-cell-05-train-00",
            "seed": 23060,
            "frame_count": 9,
            "positive_frame_count": 3,
            "negative_frame_count": 6,
            "hard_negative_frame_count": 6,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "communication-degraded-5t5r",
            "episode_id": "a1-v3-cell-06-train-00",
            "seed": 23072,
            "frame_count": 10,
            "positive_frame_count": 3,
            "negative_frame_count": 7,
            "hard_negative_frame_count": 5,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "center-failure-20t20r",
            "episode_id": "a1-v3-cell-07-train-00",
            "seed": 23084,
            "frame_count": 10,
            "positive_frame_count": 3,
            "negative_frame_count": 7,
            "hard_negative_frame_count": 5,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "secondary-failure-50t50r",
            "episode_id": "a1-v3-cell-08-train-00",
            "seed": 23096,
            "frame_count": 10,
            "positive_frame_count": 3,
            "negative_frame_count": 7,
            "hard_negative_frame_count": 7,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "high-threat-m-to-n-100t100r",
            "episode_id": "a1-v3-cell-09-train-00",
            "seed": 23108,
            "frame_count": 10,
            "positive_frame_count": 5,
            "negative_frame_count": 5,
            "hard_negative_frame_count": 5,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "high-threat-m-to-n-200t200r",
            "episode_id": "a1-v3-cell-10-train-00",
            "seed": 23120,
            "frame_count": 10,
            "positive_frame_count": 5,
            "negative_frame_count": 5,
            "hard_negative_frame_count": 5,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "resource-surplus-20t30r",
            "episode_id": "a1-v3-cell-11-train-00",
            "seed": 23132,
            "frame_count": 10,
            "positive_frame_count": 3,
            "negative_frame_count": 7,
            "hard_negative_frame_count": 6,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "resource-shortage-30t20r",
            "episode_id": "a1-v3-cell-12-train-00",
            "seed": 23144,
            "frame_count": 10,
            "positive_frame_count": 3,
            "negative_frame_count": 7,
            "hard_negative_frame_count": 3,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "dynamic-add-drop-100t80r",
            "episode_id": "a1-v3-cell-13-train-00",
            "seed": 23156,
            "frame_count": 10,
            "positive_frame_count": 7,
            "negative_frame_count": 3,
            "hard_negative_frame_count": 3,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
        {
            "cell_id": "near-tie-hard-negative-50t50r",
            "episode_id": "a1-v3-cell-14-train-00",
            "seed": 23168,
            "frame_count": 10,
            "positive_frame_count": 3,
            "negative_frame_count": 7,
            "hard_negative_frame_count": 7,
            "quota_met": True,
            "writer_staged": True,
            "reason_codes": [],
        },
    ],
    "main_anonymous_external_event_contract_observed": True,
    "caller_classification_override_used": False,
    "classifier_error_count": 0,
    "writer_staged_cell_count": 15,
    "all_frozen_cells_quota_ready": True,
    "online_truth_use_count": 0,
    "blocker_codes": [],
}


@dataclass(frozen=True)
class A1V3SourceGenerationRequestArtifact:
    request_id: str
    file_sha256: str
    sidecar_classification_policy_id: str
    sidecar_classification_policy_sha256: str
    sidecar_classifier_sha256: str
    ready: bool
    reason_codes: tuple[str, ...]


def load_a1_v3_source_generation_request_artifact(
    path: str | Path,
    *,
    request: A1V3FrozenRequest,
    descriptor: A1V3ContractDescriptor,
    global_allocation: A1V3GlobalAllocation,
    registry: A1V3SeedRegistry,
    schedule: A1V3GenerationSchedule,
    sidecar_classification_policy_path: str | Path = (
        DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH
    ),
) -> A1V3SourceGenerationRequestArtifact:
    """Validate request readiness without authorizing or starting generation."""

    file_path = Path(path)
    payload, file_sha = _read_json(file_path, "source_generation_request")
    artifact = _strict_mapping(
        payload,
        {
            "schema_version",
            "request_id",
            "status",
            "scope",
            "bindings",
            "seed_contract",
            "schema_contract",
            "producer_capability",
            "permissions",
            "content_sha256",
        },
        "source_generation_request_fields_mismatch",
    )
    if artifact["schema_version"] != A1_V3_SOURCE_GENERATION_REQUEST_SCHEMA_V1:
        _fail("source_generation_request_schema_mismatch")
    if artifact["request_id"] != A1_V3_SOURCE_GENERATION_REQUEST_ID:
        _fail("source_generation_request_id_mismatch")
    if artifact["status"] != "request_ready_frozen_runtime_quota_probe_passed":
        _fail("source_generation_request_status_mismatch")
    declared_content_sha = _sha256_value(
        artifact["content_sha256"], "source_generation_request.content_sha256"
    )
    content_payload = dict(artifact)
    content_payload.pop("content_sha256")
    if canonical_json_sha256(content_payload) != declared_content_sha:
        _fail("source_generation_request_content_sha256_mismatch")
    if artifact["scope"] != {
        "request_readiness_only": True,
        "source_generation_authorized": False,
        "episode_generation_started": False,
        "data_generated": False,
        "validation_payload_read": False,
        "formal_seed_payload_read": False,
        "model_trained": False,
        "shadow_started": False,
        "assignment_changed": False,
        "runtime_started": False,
        "physical_started": False,
        "control_started": False,
    }:
        _fail("source_generation_request_scope_mismatch")

    near_tie_sha = _file_sha256(
        _NEAR_TIE_BOUNDARY_PATH, "sidecar_near_tie_boundary"
    )
    policy = load_a1_v3_sidecar_classification_policy(
        sidecar_classification_policy_path,
        request=request,
        near_tie_boundary_file_sha256=near_tie_sha,
    )
    classifier_path = Path(__file__).with_name(
        Path(A1_V3_SIDECAR_CLASSIFIER_LOGICAL_PATH).name
    )
    classifier_sha = _file_sha256(classifier_path, "sidecar_classifier_source")

    expected_bindings = {
        "frozen_request": {
            "path": _REQUEST_PATH,
            "schema_version": A1_V3_REQUEST_SCHEMA_V1,
            "identity": request.request_id,
            "file_sha256": request.file_sha256,
        },
        "generation_schedule": {
            "path": _SCHEDULE_PATH,
            "schema_version": A1_V3_GENERATION_SCHEDULE_SCHEMA_V1,
            "identity": schedule.schedule_id,
            "file_sha256": schedule.file_sha256,
        },
        "main_allocation_registry": {
            "path": _ALLOCATION_PATH,
            "schema_version": A1_V3_MAIN_SEED_REGISTRY_SCHEMA_V1,
            "identity": registry.registry_id,
            "file_sha256": registry.file_sha256,
        },
        "global_seed_registry": {
            "path": _GLOBAL_REGISTRY_PATH,
            "schema_version": A1_V3_GLOBAL_SEED_REGISTRY_SCHEMA_V1,
            "identity": global_allocation.registry_id,
            "content_sha256": global_allocation.content_sha256,
            "file_sha256": global_allocation.file_sha256,
            "allocation_id": global_allocation.allocation_id,
        },
        "data_contract": {
            "path": _DATA_CONTRACT_PATH,
            "schema_version": A1_V3_DATA_CONTRACT_SCHEMA_V1,
            "identity": descriptor.contract_id,
            "file_sha256": descriptor.file_sha256,
        },
        "sidecar_classification_policy": {
            "path": _SIDECAR_POLICY_PATH,
            "schema_version": A1_V3_SIDECAR_CLASSIFICATION_POLICY_SCHEMA_V1,
            "identity": policy.policy_id,
            "file_sha256": policy.file_sha256,
        },
        "sidecar_classifier": {
            "path": A1_V3_SIDECAR_CLASSIFIER_LOGICAL_PATH,
            "schema_version": A1_V3_SIDECAR_CLASSIFICATION_SCHEMA_V1,
            "file_sha256": classifier_sha,
        },
    }
    if artifact["bindings"] != expected_bindings:
        _fail("source_generation_request_binding_mismatch")

    assigned_seeds = tuple(registry.assigned_seeds)
    split_seed_hashes = {
        split: canonical_json_sha256(list(registry.split_seed_values[split]))
        for split in ("train", "validation", "test")
    }
    schedule_seed_binding = [
        {
            "schedule_index": index,
            "episode_id": episode.episode_id,
            "cell_id": episode.cell_id,
            "seed": episode.seed,
            "split": episode.split,
        }
        for index, episode in enumerate(schedule.episodes)
    ]
    formal_seeds = list(range(1000, 1020))
    expected_seed_contract = {
        "allocation_id": global_allocation.allocation_id,
        "assigned_seed_count": 300,
        "assigned_seed_minimum": 23000,
        "assigned_seed_maximum": 23299,
        "assigned_seed_values_sha256": canonical_json_sha256(list(assigned_seeds)),
        "split_policy_version": A1_V3_SPLIT_POLICY_V1,
        "split_seed_counts": dict(A1_V3_SPLIT_SEED_COUNTS),
        "split_seed_values_sha256": split_seed_hashes,
        "schedule_episode_seed_binding_sha256": canonical_json_sha256(
            schedule_seed_binding
        ),
        "global_allocation_permitted_operations": ["dataset_generation"],
        "operation_is_seed_reservation_not_authorization": True,
        "formal_seed_values_sha256": canonical_json_sha256(formal_seeds),
        "formal_seed_overlap_count": len(set(formal_seeds) & set(assigned_seeds)),
        "formal_seed_payload_read_allowed": False,
    }
    if artifact["seed_contract"] != expected_seed_contract:
        _fail("source_generation_request_seed_contract_mismatch")

    expected_schema_contract = {
        "request_schema_version": A1_V3_REQUEST_SCHEMA_V1,
        "generation_schedule_schema_version": A1_V3_GENERATION_SCHEDULE_SCHEMA_V1,
        "main_allocation_schema_version": A1_V3_MAIN_SEED_REGISTRY_SCHEMA_V1,
        "global_registry_schema_version": A1_V3_GLOBAL_SEED_REGISTRY_SCHEMA_V1,
        "data_contract_schema_version": A1_V3_DATA_CONTRACT_SCHEMA_V1,
        "online_frame_schema_version": A1_V3_ONLINE_FRAME_SCHEMA_V1,
        "offline_label_schema_version": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
        "training_feature_schema_version": A1_V3_TRAINING_FEATURE_SCHEMA_V1,
        "training_target_schema_version": A1_V3_TRAINING_TARGET_SCHEMA_V1,
        "sidecar_classification_policy_schema_version": (
            A1_V3_SIDECAR_CLASSIFICATION_POLICY_SCHEMA_V1
        ),
        "sidecar_classification_schema_version": (
            A1_V3_SIDECAR_CLASSIFICATION_SCHEMA_V1
        ),
        "split_policy_version": A1_V3_SPLIT_POLICY_V1,
    }
    if artifact["schema_contract"] != expected_schema_contract:
        _fail("source_generation_request_schema_contract_mismatch")

    expected_capability = {
        "deterministic_sidecar_classifier_available": True,
        "continuous_anonymous_frame_classification_required": True,
        "caller_sidecar_classification_override_allowed": False,
        "writer_quota_gate_fail_closed": True,
        "deterministically_emitted_action_change_types": list(
            A1_V3_DERIVABLE_ACTION_CHANGE_TYPES
        ),
        "deterministically_emitted_hard_negative_types": list(
            A1_V3_DERIVABLE_HARD_NEGATIVE_TYPES
        ),
        "rejected_underived_taxonomy": list(
            A1_V3_REJECTED_UNDERIVED_TAXONOMY
        ),
        "unsupported_taxonomy_is_rejected": True,
        "frozen_runtime_quota_probe": _RUNTIME_QUOTA_PROBE,
    }
    if artifact["producer_capability"] != expected_capability:
        _fail("source_generation_request_producer_capability_mismatch")

    expected_permissions = {
        name: name == "source_generation_request"
        for name in A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS
    }
    permissions = _strict_mapping(
        artifact["permissions"],
        set(A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS),
        "source_generation_request_permission_fields_mismatch",
    )
    if any(not isinstance(value, bool) for value in permissions.values()):
        _fail("source_generation_request_permission_value_not_boolean")
    if permissions != expected_permissions:
        _fail("source_generation_request_permission_mismatch")

    return A1V3SourceGenerationRequestArtifact(
        request_id=A1_V3_SOURCE_GENERATION_REQUEST_ID,
        file_sha256=file_sha,
        sidecar_classification_policy_id=A1_V3_SIDECAR_CLASSIFICATION_POLICY_ID,
        sidecar_classification_policy_sha256=policy.file_sha256,
        sidecar_classifier_sha256=classifier_sha,
        ready=True,
        reason_codes=(),
    )


def _read_json(path: Path, name: str) -> tuple[Mapping[str, Any], str]:
    if path.is_symlink():
        _fail(f"{name}_symlink_forbidden")
    try:
        content = path.read_bytes()
    except OSError as exc:
        _fail(f"{name}_read_failed", str(exc))
    try:
        payload = json.loads(content.decode("ascii"), object_pairs_hook=_unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"{name}_json_invalid", str(exc))
    if not isinstance(payload, Mapping):
        _fail(f"{name}_object_required")
    return payload, sha256(content).hexdigest()


def _file_sha256(path: Path, name: str) -> str:
    if path.is_symlink():
        _fail(f"{name}_symlink_forbidden")
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        _fail(f"{name}_read_failed", str(exc))


def _strict_mapping(
    value: Any,
    expected_fields: set[str],
    code: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        _fail(code)
    return value


def _sha256_value(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or not set(value).issubset(set("0123456789abcdef"))
    ):
        _fail("source_generation_request_sha256_invalid", name)
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("source_generation_request_duplicate_json_key", key)
        result[key] = value
    return result


def _fail(code: str, message: str = "") -> None:
    raise A1V3DataContractError(code, message)
