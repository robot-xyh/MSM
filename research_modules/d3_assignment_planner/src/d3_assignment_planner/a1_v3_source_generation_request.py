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
_RUNTIME_QUOTA_PROBE_INVENTORY_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs/a1_source_independent_v3_runtime_quota_probe_inventory_v1.json"
)
_NEAR_TIE_BOUNDARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs/a1_source_independent_v3_near_tie_boundary_v1.json"
)


def _load_runtime_quota_probe_inventory() -> tuple[Mapping[str, Any], str]:
    """Load the frozen full-schedule inventory without granting authority."""

    path = _RUNTIME_QUOTA_PROBE_INVENTORY_PATH
    if path.is_symlink():
        raise RuntimeError("runtime_quota_probe_inventory_symlink_forbidden")
    try:
        content = path.read_bytes()
        payload = json.loads(content.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("runtime_quota_probe_inventory_invalid") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("runtime_quota_probe_inventory_object_required")
    expected_fields = {
        "schema_version",
        "evidence_content_sha256",
        "passing_runtime_to_writer_recipe_ids",
        "runtime_results",
        "caller_classification_override_used",
        "classifier_error_count",
        "blocker_codes",
    }
    if set(payload) != expected_fields:
        raise RuntimeError("runtime_quota_probe_inventory_fields_mismatch")
    passing = payload["passing_runtime_to_writer_recipe_ids"]
    results = payload["runtime_results"]
    if (
        payload["schema_version"]
        != "d3_a1_v3_runtime_quota_probe_inventory_v1"
        or payload["evidence_content_sha256"]
        != "5a580e19c0ff97c3ef7446ec4e759eb79f50ef1b91e23f8525d1f0473ff8958f"
        or not isinstance(passing, list)
        or not isinstance(results, list)
        or len(passing) != 300
        or len(results) != 300
        or payload["caller_classification_override_used"] is not False
        or payload["classifier_error_count"] != 0
        or payload["blocker_codes"] != []
    ):
        raise RuntimeError("runtime_quota_probe_inventory_contract_mismatch")
    return payload, sha256(content).hexdigest()

# This dirty full probe proves request-level quota viability only.  Its source
# and artifact bindings are frozen here so it cannot be promoted to formal
# generation, training, runtime, or control evidence by changing a status flag.
_RUNTIME_QUOTA_PROBE = {
    "probe_date": "2026-08-02",
    "probe_kind": "cross_seed_quota_viability_exploratory",
    "status": "exploratory_dirty_pass",
    "generated_at_utc": "2026-08-02T22:14:18.558049+00:00",
    "source_git_commit": "909e7bee3cad6edef0c03991848960f88f616601",
    "audited_cell_count": 15,
    "audited_recipe_count": 300,
    "episode_count": 300,
    "pass_count": 300,
    "failure_count": 0,
    "probe_error_count": 0,
    "repository_dirty": True,
    "exploratory_only": True,
    "formal_source_generation": False,
    "dataset_finalized": False,
    "readiness_eligible": False,
    "training_started": False,
    "runtime_authority_granted": False,
    "control_authority_granted": False,
    "required_per_episode": {
        "observable_frame_count": 9,
        "positive_frame_count": 3,
        "negative_frame_count": 3,
        "hard_negative_frame_count": 2,
    },
    "minimum_observed_per_episode": {
        "observable_frame_count": 9,
        "positive_frame_count": 3,
        "negative_frame_count": 3,
        "hard_negative_frame_count": 3,
    },
    "observed_frame_totals": {
        "observable_frame_count": 3086,
        "positive_frame_count": 1313,
        "negative_frame_count": 1773,
        "hard_negative_frame_count": 1771,
    },
    "all_frozen_cells_quota_ready": True,
    "online_truth_use_count": 0,
    "global_track_id_created_count": 0,
    "global_track_id_rewritten_count": 0,
    "duplicate_frame_count": 0,
    "forbidden_formal_seed_read_count": 0,
    "r0_shard_10_19_read_count": 0,
    "evidence_artifacts": {
        "summary": {
            "basename": (
                "msm_d3_300_exact_reference_20260802_final_timing_v5.json"
            ),
            "sha256": (
                "53c2e8a417a926b018d0b491149c2c7f2bf7fd4f17f5fe8035e4b4450508e415"
            ),
        },
        "episodes_jsonl": {
            "basename": (
                "msm_d3_300_exact_reference_20260802_final_timing_v5.json."
                "episodes.jsonl"
            ),
            "sha256": (
                "78da424c51a1b91d7ffcf288af9eeb4c887a8353cae8b125efcb7dbce7a66ad3"
            ),
        },
        "checkpoint": {
            "basename": (
                "msm_d3_300_exact_reference_20260802_final_timing_v5.json."
                "checkpoint.json"
            ),
            "sha256": (
                "ad2641e2b1258dbbd8869b46d9954fbe596434f624793dc5dbc6ae8d020975ee"
            ),
        },
        "content_sha256": (
            "5a580e19c0ff97c3ef7446ec4e759eb79f50ef1b91e23f8525d1f0473ff8958f"
        ),
    },
    "source_only_contract": {
        "candidate_reference_access_allowed": False,
        "counterfactual_mode": "coverage_degrading",
        "effective_safe_reference_exact_match_required": True,
        "global_track_id_write_allowed": False,
        "online_truth_read_allowed": False,
        "post_projection_reference_policy": "exact_safe_reference",
        "safe_reference_enters_after_candidate_freeze": True,
    },
    "source_bindings": {
        "assignment_safety_projection": {
            "path": (
                "research_modules/d3_assignment_planner/src/"
                "d3_assignment_planner/a1_assignment_aware_development.py"
            ),
            "sha256": (
                "19c2577b921e03563a37c49e3e983c257891fe7276314342bec779177a0a252c"
            ),
        },
        "base_config": {
            "path": (
                "research_modules/scalable_3d_simulation/configs/"
                "nominal_200v200.json"
            ),
            "sha256": (
                "2279fa380ce2d79d98690b148653b0409a2471bb35d8aab77f9ed5d0f7b97072"
            ),
        },
        "data_contract": {
            "path": (
                "research_modules/d3_assignment_planner/src/"
                "d3_assignment_planner/a1_v3_data_contract.py"
            ),
            "sha256": (
                "6d2b0e35f66ae5895bf9a9aa56d039840fd7520dc7d24179aec3d3f70f271065"
            ),
        },
        "dataset_writer": {
            "path": (
                "research_modules/d3_assignment_planner/src/"
                "d3_assignment_planner/a1_v3_dataset_writer.py"
            ),
            "sha256": (
                "9a99603640df3dfb5382fbd2447261cce332e245a65c3fc3049026498444301a"
            ),
        },
        "episode_treatments": {
            "path": (
                "research_modules/scalable_3d_simulation/episode_treatments.py"
            ),
            "sha256": (
                "135a526ad9591c2fa3a0041d50335db1fcb75e1129e97df60c5739df66b4cf9c"
            ),
        },
        "frozen_request": {
            "path": (
                "research_modules/d3_assignment_planner/configs/"
                "a1_source_independent_v3_development_data_request_v1.json"
            ),
            "sha256": (
                "5215a09774cae8edbb15ab5cd6254b8aad149a364188b9458a28c8968cd65d07"
            ),
        },
        "generation_schedule": {
            "path": (
                "research_modules/d3_assignment_planner/configs/"
                "a1_source_independent_v3_generation_schedule_v1.json"
            ),
            "sha256": (
                "a9b494de5eb2f349bc6370a1252ea5f5481211dc16da17b002a90972f3b0bdfa"
            ),
        },
        "learning_source_adapter": {
            "path": (
                "research_modules/scalable_3d_simulation/"
                "learning_source_adapters.py"
            ),
            "sha256": (
                "7fb1b660ab3dae035d055ed83bb465c4420f465da8e127dbb8f0054af15534da"
            ),
        },
        "learning_source_recipes": {
            "path": (
                "research_modules/scalable_3d_simulation/"
                "learning_source_recipes.py"
            ),
            "sha256": (
                "34ced4f02c089b492b2ba58a94220fa319acd98ae65efa276c98fa7e4c8302d9"
            ),
        },
        "orchestrator": {
            "path": "research_modules/scalable_3d_simulation/orchestrator.py",
            "sha256": (
                "bdc5adebe7cbb0f5cb65716ee08fc1f636ed5fd45c65883a3bb8409080e0335f"
            ),
        },
        "probe_runner": {
            "path": (
                "research_modules/d3_assignment_planner/simulations/"
                "run_a1_v3_cross_seed_quota_probe.py"
            ),
            "sha256": (
                "137a3f08774a8ed5a87ea59b072707f709af9c2b4b4c2b2546316dd598a0ddc0"
            ),
        },
        "probe_source": {
            "path": (
                "research_modules/d3_assignment_planner/src/"
                "d3_assignment_planner/a1_v3_quota_probe.py"
            ),
            "sha256": (
                "bc660ed9700134582eccde73387204b435fb06697e99c5623d1ad2d8d1371e5f"
            ),
        },
        "sidecar_classification_policy": {
            "path": (
                "research_modules/d3_assignment_planner/configs/"
                "a1_source_independent_v3_sidecar_classification_policy_v1.json"
            ),
            "sha256": (
                "71ba4f09f75c7c6108a5f79cbd8e5698617341df748f93fe33a1a97e0b83c3e1"
            ),
        },
        "sidecar_classifier": {
            "path": (
                "research_modules/d3_assignment_planner/src/"
                "d3_assignment_planner/a1_v3_sidecar_classification.py"
            ),
            "sha256": (
                "9b9981dbd54141aaabe6b569d245c2b1486bcc9a337bf783d82dd64770826df4"
            ),
        },
        "source_generation_request_validation": {
            "path": (
                "research_modules/d3_assignment_planner/src/"
                "d3_assignment_planner/a1_v3_source_generation_request.py"
            ),
            "sha256": (
                "f3e03b1f7911a07ad80c0b47c57eaaff879e7deaf0f9abbc7721685e0b63bf10"
            ),
        },
        "source_only_projection": {
            "path": (
                "research_modules/d3_assignment_planner/src/"
                "d3_assignment_planner/a1_v3_source_only_projection.py"
            ),
            "selected_counterfactual_mode": "coverage_degrading",
            "selected_post_projection_reference_policy": (
                "exact_safe_reference"
            ),
            "sha256": (
                "d71a887d080849b7a8aea5c96f2f5c27b6ac0b678d0f1fd6d8cf7e525f5f390f"
            ),
        },
    },
    "blocker_codes": [],
}

_RUNTIME_QUOTA_INVENTORY, _RUNTIME_QUOTA_INVENTORY_SHA256 = (
    _load_runtime_quota_probe_inventory()
)
_RUNTIME_QUOTA_PROBE = {
    **_RUNTIME_QUOTA_PROBE,
    "passing_runtime_to_writer_recipe_ids": list(
        _RUNTIME_QUOTA_INVENTORY["passing_runtime_to_writer_recipe_ids"]
    ),
    "runtime_results": list(_RUNTIME_QUOTA_INVENTORY["runtime_results"]),
    "caller_classification_override_used": _RUNTIME_QUOTA_INVENTORY[
        "caller_classification_override_used"
    ],
    "classifier_error_count": _RUNTIME_QUOTA_INVENTORY[
        "classifier_error_count"
    ],
    "blocker_codes": list(_RUNTIME_QUOTA_INVENTORY["blocker_codes"]),
    "inventory_binding": {
        "path": (
            "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_runtime_quota_probe_inventory_v1.json"
        ),
        "schema_version": "d3_a1_v3_runtime_quota_probe_inventory_v1",
        "file_sha256": _RUNTIME_QUOTA_INVENTORY_SHA256,
        "evidence_content_sha256": _RUNTIME_QUOTA_INVENTORY[
            "evidence_content_sha256"
        ],
    },
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
    status = artifact["status"]
    if status not in {
        "request_ready_frozen_runtime_quota_probe_passed",
        "request_blocked_cross_seed_quota_viability_not_proven",
    }:
        _fail("source_generation_request_status_mismatch")
    request_ready = status == "request_ready_frozen_runtime_quota_probe_passed"
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
        name: request_ready and name == "source_generation_request"
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
        ready=request_ready,
        reason_codes=(
            ()
            if request_ready
            else ("cross_seed_quota_viability_not_proven",)
        ),
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
