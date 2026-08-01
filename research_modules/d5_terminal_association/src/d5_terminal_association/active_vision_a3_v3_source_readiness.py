"""Fail-closed source-allocation readiness for the frozen D5 A3 v3 protocol.

This module reads only protocol, allocation and collection-plan metadata. It
never opens an episode or sample payload, creates a dataset, trains a model, or
grants camera, runtime, control, identity or other operational authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .active_vision_a3_v3_protocol import (
    A3_V3_CAMERA_ROLES,
    A3_V3_HARD_CONFUSION_SCENARIOS,
    A3_V3_INTENTS,
    A3_V3_SOURCE_SPLITS,
    FrozenA3V3Protocol,
    load_frozen_a3_v3_protocol,
)


A3_V3_ALLOCATION_BINDING_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-global-seed-allocation-binding.v1"
)
A3_V3_SOURCE_SCHEDULE_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-source-collection-schedule.v2"
)
A3_V3_PRE_GENERATION_READINESS_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-pre-generation-readiness.v2"
)

A3_V3_ALLOCATION_BINDING_ID = "d5-a3-v3-global-seed-binding-20260801-v1"
A3_V3_SOURCE_SCHEDULE_ID = "d5-a3-v3-source-collection-schedule-20260801-v2"
A3_V3_PROTOCOL_ID = "a3_v3_hierarchical_intent_legal_candidate_ranking_20260801"
A3_V3_PROTOCOL_SHA256 = (
    "5a01b9f5f0636a3d22338ac1c3212a242d51944a974263ca7a165909ab3dcb64"
)

GLOBAL_REGISTRY_SCHEMA_VERSION = "scalable3d-global-seed-registry-v1"
GLOBAL_REGISTRY_POLICY_VERSION = "scalable3d-seed-allocation-policy-v1"
GLOBAL_REGISTRY_ID = "scalable3d-learning-source-allocation-20260801-v1"
GLOBAL_REGISTRY_CONTENT_SHA256 = (
    "89d99bf064a8c0e226eead5b675f05daf70ac2d4c6f6139322502da54ab0aea7"
)
GLOBAL_REGISTRY_FILE_SHA256 = (
    "1c9778e1cbfcd5679956ac2c1fc71a1e780207c4579abdc9b129d162a252c4b6"
)

MODULE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
DEFAULT_PROTOCOL_PATH = (
    MODULE_ROOT / "configs/a3_v3_minority_intent_protocol_20260801.json"
)
DEFAULT_ALLOCATION_BINDING_PATH = (
    MODULE_ROOT / "configs/a3_v3_global_seed_allocation_binding_20260801.json"
)
DEFAULT_SOURCE_SCHEDULE_PATH = (
    MODULE_ROOT / "configs/a3_v3_source_collection_schedule_20260801.json"
)
DEFAULT_GLOBAL_REGISTRY_PATH = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)

_AUTHORITY_FIELDS = (
    "shadow",
    "assist",
    "promotion",
    "ppo",
    "assignment",
    "degradation",
    "runtime",
    "production",
    "control",
    "camera_command",
    "global_track_id_create",
    "global_track_id_write",
)
_FALSE_AUTHORITY = {name: False for name in _AUTHORITY_FIELDS}

_PROTOCOL_BINDINGS = (
    {
        "role": "minority_intent_protocol",
        "path": (
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_intent_protocol_20260801.json"
        ),
        "sha256": A3_V3_PROTOCOL_SHA256,
    },
    {
        "role": "protocol_schema",
        "path": (
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_intent_protocol.schema.json"
        ),
        "sha256": (
            "531763bee3a28e12b36bcd6aecacab8236fb20a4b0cb9e8e0cec8f339a145e79"
        ),
    },
    {
        "role": "source_manifest_schema",
        "path": (
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_minority_source_manifest.schema.json"
        ),
        "sha256": (
            "c858206bfefde1db0717658c55eb16a723b387c4c257b5c8c1bec18406537040"
        ),
    },
)

_SPLIT_EXPECTATIONS: Mapping[str, Mapping[str, Any]] = {
    "train": {
        "allocation_id": "d5-a3-v3-train",
        "usage_class": "train_only",
        "split_policy": "whole_episode_train_v1",
        "permitted_operations": ["dataset_generation", "training"],
        "seed_range": [24000, 24047],
        "seed_count": 48,
    },
    "validation": {
        "allocation_id": "d5-a3-v3-validation",
        "usage_class": "validation_only",
        "split_policy": "whole_episode_validation_v1",
        "permitted_operations": ["dataset_generation", "validation"],
        "seed_range": [24048, 24071],
        "seed_count": 24,
    },
    "future_held_out": {
        "allocation_id": "d5-a3-v3-future-held-out",
        "usage_class": "test_only",
        "split_policy": "whole_episode_one_shot_future_held_out_v1",
        "permitted_operations": ["dataset_generation", "test"],
        "seed_range": [24072, 24103],
        "seed_count": 32,
    },
}

_BINDING_GENERATION_STATE = {
    "episode_generation_started": False,
    "sample_generation_started": False,
    "source_manifest_generated": False,
    "training_started": False,
    "model_frozen": False,
    "validation_gate_passed": False,
    "future_held_out_payload_read_count": 0,
    "formal_seed_payload_read_count": 0,
    "v2_seed_payload_read_count": 0,
}

_SOURCE_COLLECTION_CONTRACT = {
    "source_domain": "scalable_3d_point_mass_runtime",
    "whole_episode_seed_atomic": True,
    "one_episode_per_seed": True,
    "cross_split_episode_reuse_allowed": False,
    "sample_copying_allowed": False,
    "sample_oversampling_allowed": False,
    "synthetic_fixture_allowed": False,
    "online_truth_free_required": True,
    "truth_identity_available_to_online_policy": False,
    "per_episode_entry_required": True,
    "planned_counts_are_not_observed_coverage": True,
    "unique_sample_identity": (
        "seed_episode_frame_camera_candidate_feature_fingerprint"
    ),
}

_EPISODE_GENERATION_CONTROLS = {
    "truth_identity_available_to_online_policy": False,
    "truth_online_injection_allowed": False,
    "direct_label_control_allowed": False,
    "sample_copying_allowed": False,
    "sample_oversampling_allowed": False,
}

_SCENARIO_FAMILIES = (
    "nominal",
    "dense_crossing",
    "formation_split",
    "evasive_multilevel",
    "delayed_noisy",
    "communication_degraded",
    "center_failure",
    "secondary_failure",
    "high_threat_m_to_n",
)
_SCALES = (5, 20, 50, 100, 200)
_COLLECTION_PROFILE = "balanced_action_role_v1"
_EPISODE_DURATION_S = 6.0
_MINIMUM_SAMPLES_PER_INTENT_WINDOW = 24

_INTENT_RECIPE_BY_INTENT = {
    "observe_target": "observe_target_stable_projection_v1",
    "search_sector": "search_sector_truth_free_cue_loss_or_no_projection_v1",
    "hold": "hold_bounded_gimbal_busy_v1",
    "reacquire": "reacquire_stale_or_occluded_projection_v1",
}
_HARD_RECIPE_BY_FAMILY = {
    "observe_vs_reacquire_projection_boundary": "projection_boundary_sweep_v1",
    "search_vs_reacquire_cue_loss_boundary": "recon_cue_loss_boundary_v1",
    "hold_vs_observe_gimbal_busy_boundary": "gimbal_busy_boundary_v1",
    "role_matched_interceptor_recon_geometry": "role_matched_geometry_v1",
    "multiple_legal_targets_near_tie": "multiple_legal_targets_near_tie_v1",
}
_RECIPE_REQUIRED_CONTROLS = {
    "observe_target_stable_projection_v1": [
        "assigned_projection_fresh",
        "projection_inside_usable_boundary",
    ],
    "search_sector_truth_free_cue_loss_or_no_projection_v1": [
        "assignment_retained",
        "truth_free_recon_cue_loss_or_projection_absence",
    ],
    "hold_bounded_gimbal_busy_v1": [
        "matched_target_evidence_retained",
        "bounded_gimbal_busy_or_slew_unavailable",
    ],
    "reacquire_stale_or_occluded_projection_v1": [
        "assignment_retained",
        "projection_stale_occluded_or_outside_boundary",
    ],
    "projection_boundary_sweep_v1": [
        "paired_inside_outside_projection_boundary",
        "same_assignment_and_geometry_family",
    ],
    "recon_cue_loss_boundary_v1": [
        "paired_fresh_and_suppressed_truth_free_recon_cue",
        "assignment_retained",
    ],
    "gimbal_busy_boundary_v1": [
        "paired_pre_busy_and_busy_window",
        "matched_target_evidence_retained",
    ],
    "role_matched_geometry_v1": [
        "matched_interceptor_recon_geometry",
        "role_specific_camera_state_without_role_leakage",
    ],
    "multiple_legal_targets_near_tie_v1": [
        "multiple_legal_target_references",
        "bounded_projection_quality_gap",
    ],
}
_RECIPE_CATEGORY_TARGET = {
    **{
        recipe: ("intent", intent)
        for intent, recipe in _INTENT_RECIPE_BY_INTENT.items()
    },
    **{
        recipe: ("hard_confusion", family)
        for family, recipe in _HARD_RECIPE_BY_FAMILY.items()
    },
}
_RECIPE_PRODUCER_SUPPORT = {
    "observe_target_stable_projection_v1": (
        "natural_outcome_not_window_controllable"
    ),
    "search_sector_truth_free_cue_loss_or_no_projection_v1": (
        "partial_periodic_recon_cue_loss_only"
    ),
    "hold_bounded_gimbal_busy_v1": "partial_command_induced_settle_only",
    "reacquire_stale_or_occluded_projection_v1": (
        "natural_outcome_not_window_controllable"
    ),
    "projection_boundary_sweep_v1": "unsupported",
    "recon_cue_loss_boundary_v1": "partial_periodic_not_window_controllable",
    "gimbal_busy_boundary_v1": "partial_command_induced_not_window_controllable",
    "role_matched_geometry_v1": "unsupported",
    "multiple_legal_targets_near_tie_v1": "unsupported",
}

_PRODUCER_SOURCE_BINDINGS = (
    {
        "role": "generation_entrypoint",
        "path": "research_modules/scalable_3d_simulation/run_learning_dataset.py",
        "sha256": (
            "71dc52572e7a0ec12ad0b4496dacf27b0145bc0acfe3cff26812114b55394aab"
        ),
    },
    {
        "role": "active_vision_collection_treatment",
        "path": "research_modules/scalable_3d_simulation/active_vision_collection.py",
        "sha256": (
            "ea298c8d1c210adebe683d6050e54e3603fa1cd3ee6c6e47dbf3b836ab1067dc"
        ),
    },
    {
        "role": "v2_reference_schedule",
        "path": (
            "research_modules/scalable_3d_simulation/configs/"
            "d5_a3_source_independent_point_mass_v2.json"
        ),
        "sha256": (
            "fcc288262b64a971cfc94ad152081a01e31388032a4c1eacbd58a1e70e7279a7"
        ),
    },
)
_PRODUCER_ENTRY_FIELD_SUPPORT = {
    "split": "unsupported_by_generation_schedule_schema",
    "allocation_id": "cli_argument_not_per_episode",
    "seed": "supported_as_cells_seeds",
    "episode_id": "runtime_derived_not_schedule_controlled",
    "scenario_family": "supported_as_cells_scenario",
    "scale": "supported_as_cells_scale",
    "target_count": "scenario_scale_derived_not_per_episode_mapped",
    "resource_count": "scenario_scale_derived_not_per_episode_mapped",
    "recon_count": "scenario_scale_derived_not_per_episode_mapped",
    "duration_s": "supported_as_cells_duration_s",
    "collection_profile": "supported_once_per_generation_run_only",
    "camera_roles": "runtime_implicit_not_schedule_validated",
    "intent_windows": "unsupported",
    "hard_confusion_assignments": "unsupported",
    "minimum_unique_sample_quota": "post_generation_audit_only",
}
_PRODUCER_BLOCKERS = (
    "run_learning_dataset_schedule_schema_does_not_accept_d5_episode_entries",
    "per_episode_split_episode_id_target_resource_recon_not_mapped",
    "per_episode_intent_and_hard_confusion_windows_not_executable",
    "projection_occlusion_role_geometry_near_tie_treatments_missing",
    "planned_minimum_sample_quotas_are_post_generation_audit_only",
)

_PRODUCER_CAPABILITY_ASSESSMENT = {
    "assessment_version": "d5-a3-v3-producer-capability-20260801-v1",
    "assessed_on": "2026-08-01",
    "adapter_status": "missing",
    "producer_adapter_complete": False,
    "source_generation_request_ready": False,
    "existing_schedule_cell_fields": ["scenario", "scale", "seeds", "duration_s"],
    "existing_run_level_fields": [
        "global_seed_registry",
        "seed_allocation_id",
        "d5_active_vision_collection_profile",
    ],
    "source_bindings": [dict(item) for item in _PRODUCER_SOURCE_BINDINGS],
    "entry_field_support": dict(_PRODUCER_ENTRY_FIELD_SUPPORT),
    "recipe_support": dict(_RECIPE_PRODUCER_SUPPORT),
    "blockers": list(_PRODUCER_BLOCKERS),
}

_FUTURE_ACCESS_CONTRACT = {
    "metadata_planning_allowed_before_model_freeze": True,
    "episode_or_sample_payload_read_allowed_before_model_freeze": False,
    "episode_or_sample_payload_read_allowed_before_validation_gate": False,
    "training_use_allowed": False,
    "model_selection_use_allowed": False,
    "calibration_use_allowed": False,
    "threshold_adjustment_use_allowed": False,
    "access_policy": "one_shot_after_validation_pass_and_model_freeze",
    "maximum_access_count": 1,
    "second_access_allowed": False,
    "feedback_after_access_allowed": False,
}


class A3V3SourceReadinessError(ValueError):
    """Stable fail-closed error at the D5 A3 v3 source boundary."""

    def __init__(self, code: str, message: str = "") -> None:
        detail = str(message).strip()
        super().__init__(f"{code}: {detail}" if detail else str(code))
        self.code = str(code)


@dataclass(frozen=True)
class A3V3PreGenerationReadiness:
    """Metadata-only readiness result; no payload or authority is carried."""

    payload: Mapping[str, Any]

    @property
    def status(self) -> str:
        return str(self.payload["status"])

    @property
    def pre_generation_ready(self) -> bool:
        return bool(self.payload["pre_generation_ready"])

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def validate_a3_v3_pre_generation_readiness(
    *,
    repository_root: str | Path = REPOSITORY_ROOT,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
    allocation_binding_path: str | Path = DEFAULT_ALLOCATION_BINDING_PATH,
    source_schedule_path: str | Path = DEFAULT_SOURCE_SCHEDULE_PATH,
    global_registry_path: str | Path = DEFAULT_GLOBAL_REGISTRY_PATH,
) -> A3V3PreGenerationReadiness:
    """Validate the frozen source plan without opening any generated payload."""

    root = Path(repository_root).resolve()
    if not root.is_dir():
        _fail("repository_root_invalid", str(root))

    protocol = load_frozen_a3_v3_protocol(_safe_file(Path(protocol_path), root))
    if protocol.protocol_id != A3_V3_PROTOCOL_ID:
        _fail("protocol_id_mismatch")
    if protocol.sha256 != A3_V3_PROTOCOL_SHA256:
        _fail("protocol_sha256_mismatch")

    binding_path = _safe_file(Path(allocation_binding_path), root)
    binding = _read_json(binding_path, "allocation_binding")
    validate_a3_v3_allocation_binding(binding)

    registry_path = _safe_file(Path(global_registry_path), root)
    registry = _read_json(registry_path, "global_seed_registry")
    allocation_summary = _validate_global_registry(
        registry,
        registry_path=registry_path,
        repository_root=root,
        binding=binding,
    )

    schedule_path = _safe_file(Path(source_schedule_path), root)
    schedule = _read_json(schedule_path, "source_schedule")
    schedule_summary = validate_a3_v3_source_schedule(
        schedule,
        protocol=protocol,
        binding=binding,
        binding_file_sha256=_sha256_file(binding_path),
        repository_root=root,
    )

    payload = {
        "schema_version": A3_V3_PRE_GENERATION_READINESS_SCHEMA_VERSION,
        "status": "plan_ready_but_producer_adapter_missing",
        "plan_ready": True,
        "pre_generation_ready": False,
        "producer_adapter_complete": False,
        "source_generation_request_ready": False,
        "training_ready": False,
        "protocol": {
            "protocol_id": protocol.protocol_id,
            "protocol_sha256": protocol.sha256,
            "status": protocol.status,
        },
        "global_seed_registry": {
            "registry_id": GLOBAL_REGISTRY_ID,
            "content_sha256": GLOBAL_REGISTRY_CONTENT_SHA256,
            "file_sha256": GLOBAL_REGISTRY_FILE_SHA256,
            "source_binding_count": allocation_summary["source_binding_count"],
        },
        "allocation_binding": {
            "binding_id": A3_V3_ALLOCATION_BINDING_ID,
            "content_sha256": binding["content_sha256"],
            "file_sha256": _sha256_file(binding_path),
        },
        "source_schedule": {
            "schedule_id": A3_V3_SOURCE_SCHEDULE_ID,
            "content_sha256": schedule["content_sha256"],
            "file_sha256": _sha256_file(schedule_path),
            "planned_episode_count": schedule_summary["planned_episode_count"],
        },
        "split_summary": schedule_summary["split_summary"],
        "producer_capability": schedule_summary["producer_capability"],
        "seed_overlap_count": 0,
        "protected_seed_overlap_count": 0,
        "episode_payload_read_count": 0,
        "sample_payload_read_count": 0,
        "formal_seed_payload_read_count": 0,
        "v2_seed_payload_read_count": 0,
        "future_held_out_payload_read_count": 0,
        "future_held_out_payload_read_allowed": False,
        "source_manifest_generated": False,
        "weights_generated": False,
        "authority": dict(_FALSE_AUTHORITY),
        "downstream_blockers": [
            *_PRODUCER_BLOCKERS,
            "source_episode_payloads_not_generated",
            "source_manifest_not_generated",
            "development_cache_not_generated",
            "model_not_trained_or_frozen",
            "validation_gate_not_run",
            "future_held_out_payload_access_not_authorized",
        ],
    }
    return A3V3PreGenerationReadiness(payload=payload)


def validate_a3_v3_allocation_binding(payload: Mapping[str, Any]) -> None:
    """Validate immutable global-registry expectations owned by D5."""

    _expect_fields(
        payload,
        {
            "schema_version",
            "binding_id",
            "status",
            "frozen_on",
            "protocol_binding",
            "global_seed_registry_binding",
            "split_allocations",
            "prohibited_payload_sources",
            "generation_state",
            "authority",
            "content_sha256",
        },
        "allocation_binding",
    )
    _validate_self_hash(payload, "allocation_binding")
    expected_scalar = {
        "schema_version": A3_V3_ALLOCATION_BINDING_SCHEMA_VERSION,
        "binding_id": A3_V3_ALLOCATION_BINDING_ID,
        "status": "allocation_reserved_source_not_generated",
        "frozen_on": "2026-08-01",
    }
    for name, value in expected_scalar.items():
        if payload.get(name) != value:
            _fail(f"allocation_binding_{name}_mismatch")

    protocol_binding = _mapping(payload.get("protocol_binding"), "protocol_binding")
    if protocol_binding != {
        "path": _PROTOCOL_BINDINGS[0]["path"],
        "protocol_id": A3_V3_PROTOCOL_ID,
        "sha256": A3_V3_PROTOCOL_SHA256,
    }:
        _fail("allocation_binding_protocol_mismatch")

    registry_binding = _mapping(
        payload.get("global_seed_registry_binding"),
        "global_seed_registry_binding",
    )
    if registry_binding != {
        "path": (
            "research_modules/scalable_3d_simulation/configs/"
            "scalable_learning_global_seed_registry_v1.json"
        ),
        "schema_version": GLOBAL_REGISTRY_SCHEMA_VERSION,
        "policy_version": GLOBAL_REGISTRY_POLICY_VERSION,
        "registry_id": GLOBAL_REGISTRY_ID,
        "status": "allocations_reserved_generation_not_started",
        "content_sha256": GLOBAL_REGISTRY_CONTENT_SHA256,
        "file_sha256": GLOBAL_REGISTRY_FILE_SHA256,
    }:
        _fail("allocation_binding_registry_mismatch")

    split_payload = _mapping(payload.get("split_allocations"), "split_allocations")
    _expect_fields(split_payload, set(A3_V3_SOURCE_SPLITS), "split_allocations")
    for split in A3_V3_SOURCE_SPLITS:
        if _mapping(split_payload[split], f"split_allocations.{split}") != (
            _expected_binding_split(split)
        ):
            _fail(f"allocation_binding_split_mismatch:{split}")

    expected_prohibited = [
        {
            "source_id": "formal-evaluation-v1",
            "seed_range": [1000, 1019],
            "episode_or_sample_payload_read_allowed": False,
            "reuse_allowed": False,
        },
        {
            "source_id": "d5-a3-v2-corpus",
            "seed_range": [22100, 22199],
            "episode_or_sample_payload_read_allowed": False,
            "reuse_allowed": False,
        },
    ]
    if payload.get("prohibited_payload_sources") != expected_prohibited:
        _fail("allocation_binding_prohibited_sources_mismatch")
    if payload.get("generation_state") != _BINDING_GENERATION_STATE:
        _fail("allocation_binding_generation_state_mismatch")
    _validate_false_authority(payload.get("authority"), "allocation_binding")


def validate_a3_v3_source_schedule(
    payload: Mapping[str, Any],
    *,
    protocol: FrozenA3V3Protocol,
    binding: Mapping[str, Any],
    binding_file_sha256: str,
    repository_root: str | Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Validate the 104-entry source plan without reading episode payloads."""

    _expect_fields(
        payload,
        {
            "schema_version",
            "schedule_id",
            "status",
            "frozen_on",
            "protocol_binding",
            "global_allocation_binding",
            "source_collection_contract",
            "producer_capability_assessment",
            "episode_entries",
            "planned_coverage_summary",
            "future_held_out_access",
            "identity",
            "generation_state",
            "authority",
            "content_sha256",
        },
        "source_schedule",
    )
    _validate_self_hash(payload, "source_schedule")
    expected_scalar = {
        "schema_version": A3_V3_SOURCE_SCHEDULE_SCHEMA_VERSION,
        "schedule_id": A3_V3_SOURCE_SCHEDULE_ID,
        "status": "collection_plan_frozen_producer_adapter_missing",
        "frozen_on": "2026-08-01",
    }
    for name, value in expected_scalar.items():
        if payload.get(name) != value:
            _fail(f"source_schedule_{name}_mismatch")
    if payload.get("protocol_binding") != {
        "protocol_id": A3_V3_PROTOCOL_ID,
        "sha256": A3_V3_PROTOCOL_SHA256,
    }:
        _fail("source_schedule_protocol_mismatch")
    if protocol.protocol_id != A3_V3_PROTOCOL_ID or protocol.sha256 != A3_V3_PROTOCOL_SHA256:
        _fail("source_schedule_loaded_protocol_mismatch")

    binding_reference = _mapping(
        payload.get("global_allocation_binding"),
        "global_allocation_binding",
    )
    if binding_reference != {
        "path": (
            "research_modules/d5_terminal_association/configs/"
            "a3_v3_global_seed_allocation_binding_20260801.json"
        ),
        "binding_id": A3_V3_ALLOCATION_BINDING_ID,
        "content_sha256": binding["content_sha256"],
        "file_sha256": binding_file_sha256,
    }:
        _fail("source_schedule_allocation_binding_mismatch")
    if payload.get("source_collection_contract") != _SOURCE_COLLECTION_CONTRACT:
        _fail("source_schedule_collection_contract_mismatch")
    if payload.get("future_held_out_access") != _FUTURE_ACCESS_CONTRACT:
        _fail("source_schedule_future_access_mismatch")
    if payload.get("identity") != {
        "global_track_id_ownership": "center_read_only",
        "global_track_id_create_allowed": False,
        "global_track_id_write_allowed": False,
        "truth_identity_available_to_online_policy": False,
    }:
        _fail("source_schedule_identity_mismatch")
    if payload.get("generation_state") != _BINDING_GENERATION_STATE:
        _fail("source_schedule_generation_state_mismatch")
    _validate_false_authority(payload.get("authority"), "source_schedule")

    root = Path(repository_root).resolve()
    if not root.is_dir():
        _fail("repository_root_invalid", str(root))
    producer_capability = _validate_producer_capability_assessment(
        payload.get("producer_capability_assessment"),
        repository_root=root,
    )

    entries = _object_sequence(payload.get("episode_entries"), "episode_entries")
    expected_assignments = _expected_split_seed_assignments()
    if len(entries) != len(expected_assignments):
        _fail("source_schedule_episode_count_mismatch")

    seen_episode_ids: set[str] = set()
    seen_seeds: set[int] = set()
    entries_by_split: dict[str, list[Mapping[str, Any]]] = {
        split: [] for split in A3_V3_SOURCE_SPLITS
    }
    for entry_index, (entry, expected_assignment) in enumerate(
        zip(entries, expected_assignments, strict=True)
    ):
        expected_split, expected_seed = expected_assignment
        validated = _validate_episode_entry(
            entry,
            entry_index=entry_index,
            expected_split=expected_split,
            expected_seed=expected_seed,
        )
        episode_id = str(validated["episode_id"])
        seed = int(validated["seed"])
        if episode_id in seen_episode_ids:
            _fail(f"source_schedule_episode_id_duplicate:{episode_id}")
        if seed in seen_seeds:
            _fail(f"source_schedule_seed_duplicate:{seed}")
        seen_episode_ids.add(episode_id)
        seen_seeds.add(seed)
        entries_by_split[expected_split].append(validated)

    split_seed_sets = {
        split: {int(entry["seed"]) for entry in split_entries}
        for split, split_entries in entries_by_split.items()
    }
    for split, expected in _SPLIT_EXPECTATIONS.items():
        expected_seeds = set(_seed_range(expected["seed_range"], split))
        if split_seed_sets[split] != expected_seeds:
            _fail(f"source_schedule_exact_seed_set_mismatch:{split}")
    for index, left in enumerate(A3_V3_SOURCE_SPLITS):
        for right in A3_V3_SOURCE_SPLITS[index + 1 :]:
            if split_seed_sets[left] & split_seed_sets[right]:
                _fail(f"source_schedule_split_overlap:{left}:{right}")
    prohibited = set(range(1000, 1020)) | set(range(22100, 22200))
    if seen_seeds & prohibited:
        _fail("source_schedule_prohibited_seed_overlap")

    planned_coverage = _summarize_planned_coverage(entries_by_split)
    if payload.get("planned_coverage_summary") != planned_coverage:
        _fail("source_schedule_planned_coverage_summary_mismatch")
    _validate_planned_coverage_against_protocol(
        planned_coverage,
        source_request=_mapping(protocol.payload["source_request"], "source_request"),
    )

    split_summary = {
        split: {
            "allocation_id": _SPLIT_EXPECTATIONS[split]["allocation_id"],
            "seed_count": coverage["seed_count"],
            "planned_episode_count": coverage["planned_episode_count"],
            "planned_minimum_unique_sample_count": coverage["total"][
                "minimum_unique_samples"
            ],
            "intent_count": len(A3_V3_INTENTS),
            "camera_role_count": len(A3_V3_CAMERA_ROLES),
            "intent_role_cell_count": len(A3_V3_INTENTS)
            * len(A3_V3_CAMERA_ROLES),
            "hard_confusion_family_count": len(A3_V3_HARD_CONFUSION_SCENARIOS),
            "quota_plan_passed": True,
        }
        for split, coverage in planned_coverage.items()
    }

    return {
        "schedule_id": A3_V3_SOURCE_SCHEDULE_ID,
        "planned_episode_count": len(entries),
        "split_summary": split_summary,
        "producer_capability": producer_capability,
        "seed_overlap_count": 0,
        "prohibited_seed_overlap_count": 0,
        "episode_payload_read_count": 0,
        "sample_payload_read_count": 0,
        "future_held_out_payload_read_allowed": False,
        "authority": dict(_FALSE_AUTHORITY),
    }


def validate_a3_v3_registry_allocation(
    payload: Mapping[str, Any],
    *,
    split: str,
) -> None:
    """Validate one decoded D5 allocation against the immutable split anchor."""

    if split not in _SPLIT_EXPECTATIONS:
        _fail(f"global_registry_split_unknown:{split}")
    _validate_registry_allocation(
        payload,
        split=split,
        expected=_SPLIT_EXPECTATIONS[split],
    )


def _validate_global_registry(
    payload: Mapping[str, Any],
    *,
    registry_path: Path,
    repository_root: Path,
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    _expect_fields(
        payload,
        {
            "schema_version",
            "policy_version",
            "registry_id",
            "status",
            "protected_seed_sets",
            "allocations",
            "unallocated_requests",
            "generation_state",
            "content_sha256",
        },
        "global_seed_registry",
    )
    _validate_self_hash(payload, "global_seed_registry")
    if _sha256_file(registry_path) != GLOBAL_REGISTRY_FILE_SHA256:
        _fail("global_registry_file_sha256_mismatch")
    expected_registry = {
        "schema_version": GLOBAL_REGISTRY_SCHEMA_VERSION,
        "policy_version": GLOBAL_REGISTRY_POLICY_VERSION,
        "registry_id": GLOBAL_REGISTRY_ID,
        "status": "allocations_reserved_generation_not_started",
        "content_sha256": GLOBAL_REGISTRY_CONTENT_SHA256,
    }
    for name, value in expected_registry.items():
        if payload.get(name) != value:
            _fail(f"global_registry_{name}_mismatch")
    if payload.get("generation_state") != {
        "episode_generation_started": False,
        "sample_generation_started": False,
        "training_started": False,
        "formal_seed_payload_read": False,
        "module_readiness_required": True,
    }:
        _fail("global_registry_generation_state_mismatch")

    protected_sets = _object_sequence(
        payload.get("protected_seed_sets"),
        "protected_seed_sets",
    )
    protected_by_id: dict[str, set[int]] = {}
    protected_owner: dict[int, str] = {}
    for raw in protected_sets:
        set_id = _nonempty_text(raw.get("set_id"), "protected_seed_set.set_id")
        if set_id in protected_by_id:
            _fail(f"global_registry_protected_set_duplicate:{set_id}")
        seeds = set(_strict_seed_sequence(raw.get("seeds"), f"protected:{set_id}"))
        if raw.get("dataset_generation_allowed") is not False:
            _fail(f"global_registry_protected_generation_allowed:{set_id}")
        protected_by_id[set_id] = seeds
        for seed in seeds:
            if seed in protected_owner:
                _fail(f"global_registry_protected_seed_overlap:{seed}")
            protected_owner[seed] = set_id
    if protected_by_id.get("formal-evaluation-v1") != set(range(1000, 1020)):
        _fail("global_registry_formal_protection_mismatch")
    if protected_by_id.get("d5-a3-v2-corpus") != set(range(22100, 22200)):
        _fail("global_registry_v2_protection_mismatch")
    formal_record = next(
        item for item in protected_sets if item.get("set_id") == "formal-evaluation-v1"
    )
    if formal_record.get("payload_read_allowed") is not False:
        _fail("global_registry_formal_payload_read_policy_mismatch")

    allocations = _object_sequence(payload.get("allocations"), "allocations")
    allocations_by_id: dict[str, Mapping[str, Any]] = {}
    allocated_seed_owner: dict[int, str] = {}
    for raw in allocations:
        allocation_id = _nonempty_text(raw.get("allocation_id"), "allocation_id")
        if allocation_id in allocations_by_id:
            _fail(f"global_registry_allocation_duplicate:{allocation_id}")
        seeds = _strict_seed_sequence(raw.get("seeds"), f"allocation:{allocation_id}")
        if raw.get("seed_count") != len(seeds):
            _fail(f"global_registry_allocation_seed_count_mismatch:{allocation_id}")
        for seed in seeds:
            if seed in protected_owner:
                _fail(f"global_registry_allocation_uses_protected_seed:{allocation_id}")
            if seed in allocated_seed_owner:
                _fail(f"global_registry_allocation_seed_overlap:{seed}")
            allocated_seed_owner[seed] = allocation_id
        allocations_by_id[allocation_id] = raw

    source_binding_count = 0
    split_binding = _mapping(binding["split_allocations"], "split_allocations")
    for split in A3_V3_SOURCE_SPLITS:
        expected = _SPLIT_EXPECTATIONS[split]
        allocation_id = str(expected["allocation_id"])
        actual = allocations_by_id.get(allocation_id)
        if actual is None:
            _fail(f"global_registry_allocation_missing:{allocation_id}")
        _validate_registry_allocation(actual, split=split, expected=expected)
        binding_split = _mapping(split_binding[split], f"binding_split:{split}")
        expected_seeds = set(_seed_range(binding_split["seed_range"], split))
        actual_seeds = set(_strict_seed_sequence(actual["seeds"], allocation_id))
        if actual_seeds != expected_seeds:
            _fail(f"global_registry_exact_seed_set_mismatch:{split}")
        source_contract = _mapping(actual.get("source_contract"), "source_contract")
        bindings = _object_sequence(source_contract.get("bindings"), "source_bindings")
        for source_binding in bindings:
            logical_path = _nonempty_text(source_binding.get("path"), "source_binding.path")
            expected_sha = _nonempty_text(source_binding.get("sha256"), "source_binding.sha256")
            source_path = _safe_repo_relative_file(repository_root, logical_path)
            if _sha256_file(source_path) != expected_sha:
                _fail(f"global_registry_source_binding_hash_mismatch:{logical_path}")
            source_binding_count += 1

    return {
        "source_binding_count": source_binding_count,
        "allocation_count": len(A3_V3_SOURCE_SPLITS),
    }


def _validate_registry_allocation(
    actual: Mapping[str, Any],
    *,
    split: str,
    expected: Mapping[str, Any],
) -> None:
    _expect_fields(
        actual,
        {
            "allocation_id",
            "owner",
            "candidate_version",
            "lifecycle",
            "usage_class",
            "split_policy",
            "permitted_operations",
            "seed_count",
            "seeds",
            "source_contract",
        },
        f"registry_allocation:{split}",
    )
    scalar_expectations = {
        "allocation_id": expected["allocation_id"],
        "owner": "D5",
        "candidate_version": "d5-a3-v3",
        "lifecycle": "reserved",
        "usage_class": expected["usage_class"],
        "split_policy": expected["split_policy"],
        "permitted_operations": expected["permitted_operations"],
        "seed_count": expected["seed_count"],
    }
    for name, value in scalar_expectations.items():
        if actual.get(name) != value:
            _fail(f"global_registry_allocation_{name}_mismatch:{split}")
    actual_seeds = _strict_seed_sequence(actual.get("seeds"), f"allocation:{split}")
    expected_seeds = _seed_range(expected["seed_range"], f"allocation:{split}")
    if actual_seeds != expected_seeds:
        _fail(f"global_registry_exact_seed_set_mismatch:{split}")
    source_contract = _mapping(actual.get("source_contract"), "source_contract")
    if source_contract != _expected_source_contract(split):
        _fail(f"global_registry_source_contract_mismatch:{split}")


def _validate_producer_capability_assessment(
    value: Any,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    assessment = _mapping(value, "producer_capability_assessment")
    if assessment != _PRODUCER_CAPABILITY_ASSESSMENT:
        _fail("source_schedule_producer_capability_assessment_mismatch")
    for binding in _PRODUCER_SOURCE_BINDINGS:
        source_path = _safe_repo_relative_file(repository_root, binding["path"])
        if _sha256_file(source_path) != binding["sha256"]:
            _fail(f"source_schedule_producer_source_hash_mismatch:{binding['role']}")
    return {
        "adapter_status": "missing",
        "producer_adapter_complete": False,
        "source_generation_request_ready": False,
        "source_binding_count": len(_PRODUCER_SOURCE_BINDINGS),
        "entry_field_support": dict(_PRODUCER_ENTRY_FIELD_SUPPORT),
        "recipe_support": dict(_RECIPE_PRODUCER_SUPPORT),
        "blockers": list(_PRODUCER_BLOCKERS),
    }


def _expected_split_seed_assignments() -> tuple[tuple[str, int], ...]:
    return tuple(
        (split, seed)
        for split in A3_V3_SOURCE_SPLITS
        for seed in _seed_range(_SPLIT_EXPECTATIONS[split]["seed_range"], split)
    )


def _validate_episode_entry(
    value: Mapping[str, Any],
    *,
    entry_index: int,
    expected_split: str,
    expected_seed: int,
) -> Mapping[str, Any]:
    entry = _mapping(value, f"episode_entry:{entry_index}")
    expected = _expected_episode_entry(
        entry_index=entry_index,
        split=expected_split,
        seed=expected_seed,
    )
    _expect_fields(entry, set(expected), f"episode_entry:{entry_index}")
    for field, expected_value in expected.items():
        if entry.get(field) != expected_value:
            _fail(f"source_schedule_episode_{field}_mismatch:{entry_index}")
    return entry


def _expected_episode_entry(
    *,
    entry_index: int,
    split: str,
    seed: int,
) -> dict[str, Any]:
    scale = _SCALES[entry_index % len(_SCALES)]
    intent_windows = _expected_intent_windows(entry_index)
    return {
        "entry_index": entry_index,
        "split": split,
        "allocation_id": _SPLIT_EXPECTATIONS[split]["allocation_id"],
        "seed": seed,
        "episode_id": f"d5-a3-v3-{split.replace('_', '-')}-seed-{seed}",
        "scenario_family": _SCENARIO_FAMILIES[
            entry_index % len(_SCENARIO_FAMILIES)
        ],
        "scale": scale,
        "target_count": scale,
        "resource_count": scale,
        "recon_count": max(1, math.ceil(scale / 25)),
        "duration_s": _EPISODE_DURATION_S,
        "collection_profile": _COLLECTION_PROFILE,
        "camera_roles": list(A3_V3_CAMERA_ROLES),
        "intent_windows": intent_windows,
        "hard_confusion_assignments": _expected_hard_confusion_assignments(
            entry_index
        ),
        "minimum_unique_sample_quota": _expected_episode_sample_quota(
            intent_windows
        ),
        "generation_controls": dict(_EPISODE_GENERATION_CONTROLS),
    }


def _expected_intent_windows(entry_index: int) -> list[dict[str, Any]]:
    role_patterns = (
        {
            "observe_target": "interceptor",
            "search_sector": "recon",
            "hold": "interceptor",
            "reacquire": "recon",
        },
        {
            "observe_target": "recon",
            "search_sector": "interceptor",
            "hold": "recon",
            "reacquire": "interceptor",
        },
    )
    roles = role_patterns[entry_index % len(role_patterns)]
    window_duration = _EPISODE_DURATION_S / len(A3_V3_INTENTS)
    windows: list[dict[str, Any]] = []
    for window_index, intent in enumerate(A3_V3_INTENTS):
        recipe = _INTENT_RECIPE_BY_INTENT[intent]
        windows.append(
            {
                "window_id": f"intent-window-{window_index}",
                "start_s": window_index * window_duration,
                "end_s": (window_index + 1) * window_duration,
                "intent": intent,
                "camera_role": roles[intent],
                "treatment_recipe": recipe,
                "required_controls": list(_RECIPE_REQUIRED_CONTROLS[recipe]),
                "minimum_unique_samples": _MINIMUM_SAMPLES_PER_INTENT_WINDOW,
            }
        )
    return windows


def _expected_hard_confusion_assignments(
    entry_index: int,
) -> list[dict[str, Any]]:
    window_ids_by_family = {
        "observe_vs_reacquire_projection_boundary": [
            "intent-window-0",
            "intent-window-3",
        ],
        "search_vs_reacquire_cue_loss_boundary": [
            "intent-window-1",
            "intent-window-3",
        ],
        "hold_vs_observe_gimbal_busy_boundary": [
            "intent-window-2",
            "intent-window-0",
        ],
        "role_matched_interceptor_recon_geometry": [
            "intent-window-0",
            "intent-window-1",
            "intent-window-2",
            "intent-window-3",
        ],
        "multiple_legal_targets_near_tie": [
            "intent-window-0",
            "intent-window-3",
        ],
    }
    family_count = len(A3_V3_HARD_CONFUSION_SCENARIOS)
    family_indices = (entry_index % family_count, (entry_index + 2) % family_count)
    assignments: list[dict[str, Any]] = []
    for family_index in family_indices:
        family = A3_V3_HARD_CONFUSION_SCENARIOS[family_index]
        recipe = _HARD_RECIPE_BY_FAMILY[family]
        assignments.append(
            {
                "family": family,
                "treatment_recipe": recipe,
                "window_ids": window_ids_by_family[family],
                "required_controls": list(_RECIPE_REQUIRED_CONTROLS[recipe]),
                "minimum_unique_boundary_pairs": 1,
            }
        )
    return assignments


def _expected_episode_sample_quota(
    intent_windows: list[dict[str, Any]],
) -> dict[str, Any]:
    per_intent = {intent: 0 for intent in A3_V3_INTENTS}
    per_role = {role: 0 for role in A3_V3_CAMERA_ROLES}
    per_intent_role = {
        f"{intent}|{role}": 0
        for intent in A3_V3_INTENTS
        for role in A3_V3_CAMERA_ROLES
    }
    for window in intent_windows:
        intent = str(window["intent"])
        role = str(window["camera_role"])
        sample_count = int(window["minimum_unique_samples"])
        per_intent[intent] += sample_count
        per_role[role] += sample_count
        per_intent_role[f"{intent}|{role}"] += sample_count
    return {
        "total": sum(per_intent.values()),
        "per_intent": per_intent,
        "per_camera_role": per_role,
        "per_intent_camera_role": per_intent_role,
    }


def _summarize_planned_coverage(
    entries_by_split: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    return {
        split: _summarize_split_coverage(split, entries_by_split[split])
        for split in A3_V3_SOURCE_SPLITS
    }


def _summarize_split_coverage(
    split: str,
    entries: list[Mapping[str, Any]],
) -> dict[str, Any]:
    def triplet(quota_path: tuple[str, ...]) -> dict[str, int]:
        samples = 0
        episode_ids: set[str] = set()
        seeds: set[int] = set()
        for entry in entries:
            quota: Any = entry["minimum_unique_sample_quota"]
            for name in quota_path:
                quota = quota[name]
            count = int(quota)
            samples += count
            if count > 0:
                episode_ids.add(str(entry["episode_id"]))
                seeds.add(int(entry["seed"]))
        return {
            "minimum_unique_samples": samples,
            "minimum_unique_episodes": len(episode_ids),
            "minimum_unique_seeds": len(seeds),
        }

    hard_confusion: dict[str, dict[str, int]] = {}
    for family in A3_V3_HARD_CONFUSION_SCENARIOS:
        family_entries = [
            entry
            for entry in entries
            if family
            in {
                str(assignment["family"])
                for assignment in entry["hard_confusion_assignments"]
            }
        ]
        hard_confusion[family] = {
            "minimum_unique_episodes": len(
                {str(entry["episode_id"]) for entry in family_entries}
            ),
            "minimum_unique_seeds": len(
                {int(entry["seed"]) for entry in family_entries}
            ),
        }

    return {
        "allocation_id": _SPLIT_EXPECTATIONS[split]["allocation_id"],
        "planned_episode_count": len(entries),
        "seed_count": len({int(entry["seed"]) for entry in entries}),
        "total": triplet(("total",)),
        "per_intent": {
            intent: triplet(("per_intent", intent)) for intent in A3_V3_INTENTS
        },
        "per_camera_role": {
            role: triplet(("per_camera_role", role))
            for role in A3_V3_CAMERA_ROLES
        },
        "per_intent_camera_role": {
            f"{intent}|{role}": triplet(
                ("per_intent_camera_role", f"{intent}|{role}")
            )
            for intent in A3_V3_INTENTS
            for role in A3_V3_CAMERA_ROLES
        },
        "hard_confusion_families": hard_confusion,
        "scenario_family_episode_counts": {
            scenario: sum(
                1 for entry in entries if entry["scenario_family"] == scenario
            )
            for scenario in _SCENARIO_FAMILIES
        },
        "scale_episode_counts": {
            str(scale): sum(1 for entry in entries if entry["scale"] == scale)
            for scale in _SCALES
        },
    }


def _validate_planned_coverage_against_protocol(
    planned: Mapping[str, Any],
    *,
    source_request: Mapping[str, Any],
) -> None:
    minimums = _mapping(
        source_request.get("coverage_minimums_by_split"),
        "coverage_minimums_by_split",
    )
    confusion_requirements = {
        str(item["id"]): item
        for item in _object_sequence(
            source_request.get("hard_confusion_scenarios"),
            "hard_confusion_scenarios",
        )
    }
    for split in A3_V3_SOURCE_SPLITS:
        coverage = _mapping(planned[split], f"planned_coverage:{split}")
        quotas = _mapping(minimums[split], f"coverage_minimums:{split}")
        _require_triplet_mapping(
            "total", coverage["total"], quotas["total"], split
        )
        for intent in A3_V3_INTENTS:
            _require_triplet_mapping(
                f"intent:{intent}",
                coverage["per_intent"][intent],
                quotas["per_intent"],
                split,
            )
        for role in A3_V3_CAMERA_ROLES:
            _require_triplet_mapping(
                f"camera_role:{role}",
                coverage["per_camera_role"][role],
                quotas["per_camera_role"],
                split,
            )
        for intent in A3_V3_INTENTS:
            for role in A3_V3_CAMERA_ROLES:
                label = f"{intent}|{role}"
                _require_triplet_mapping(
                    f"intent_role:{label}",
                    coverage["per_intent_camera_role"][label],
                    quotas["per_intent_camera_role"],
                    split,
                )
        for family in A3_V3_HARD_CONFUSION_SCENARIOS:
            actual = coverage["hard_confusion_families"][family]
            requirement = confusion_requirements[family]
            if int(actual["minimum_unique_episodes"]) < int(
                requirement["minimum_unique_episodes_by_split"][split]
            ):
                _fail(
                    f"source_schedule_hard_confusion_episode_quota:{split}:{family}"
                )
            if int(actual["minimum_unique_seeds"]) < int(
                requirement["minimum_unique_seeds_by_split"][split]
            ):
                _fail(
                    f"source_schedule_hard_confusion_seed_quota:{split}:{family}"
                )


def _require_triplet_mapping(
    label: str,
    actual: Any,
    quota: Any,
    split: str,
) -> None:
    actual_mapping = _mapping(actual, f"actual_coverage:{split}:{label}")
    quota_mapping = _mapping(quota, f"coverage_quota:{split}:{label}")
    _require_count_triplet(
        label,
        int(actual_mapping["minimum_unique_samples"]),
        int(actual_mapping["minimum_unique_episodes"]),
        int(actual_mapping["minimum_unique_seeds"]),
        quota_mapping,
        split,
    )


def _require_count_triplet(
    label: str,
    samples: int,
    episodes: int,
    seeds: int,
    quota: Mapping[str, Any],
    split: str,
) -> None:
    actual = {
        "minimum_unique_samples": samples,
        "minimum_unique_episodes": episodes,
        "minimum_unique_seeds": seeds,
    }
    for name, value in actual.items():
        if value < int(quota[name]):
            _fail(f"source_schedule_quota_below_minimum:{split}:{label}:{name}")


def _expected_binding_split(split: str) -> dict[str, Any]:
    expected = _SPLIT_EXPECTATIONS[split]
    return {
        "allocation_id": expected["allocation_id"],
        "owner": "D5",
        "candidate_version": "d5-a3-v3",
        "lifecycle": "reserved",
        "usage_class": expected["usage_class"],
        "split_policy": expected["split_policy"],
        "permitted_operations": expected["permitted_operations"],
        "seed_range": expected["seed_range"],
        "seed_count": expected["seed_count"],
        "source_contract": _expected_source_contract(split),
    }


def _expected_source_contract(split: str) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "protocol_id": A3_V3_PROTOCOL_ID,
        "split": split,
    }
    if split == "future_held_out":
        contract["maximum_evaluation_access_count"] = 1
    contract["bindings"] = [dict(item) for item in _PROTOCOL_BINDINGS]
    return contract


def _validate_false_authority(value: Any, label: str) -> None:
    authority = _mapping(value, f"{label}.authority")
    if authority != _FALSE_AUTHORITY:
        _fail(f"{label}_authority_must_remain_false")


def _validate_self_hash(payload: Mapping[str, Any], label: str) -> None:
    declared = payload.get("content_sha256")
    if not isinstance(declared, str) or len(declared) != 64:
        _fail(f"{label}_content_sha256_invalid")
    content = dict(payload)
    content.pop("content_sha256", None)
    if declared != _canonical_sha256(content):
        _fail(f"{label}_content_sha256_mismatch")


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise A3V3SourceReadinessError(f"{label}_read_failed", str(path)) from exc
    return _mapping(payload, label)


def _safe_file(path: Path, root: Path) -> Path:
    if path.is_symlink():
        _fail("metadata_symlink_forbidden", str(path))
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise A3V3SourceReadinessError("metadata_file_unsafe", str(path)) from exc
    if not resolved.is_file():
        _fail("metadata_file_not_regular", str(path))
    return resolved


def _safe_repo_relative_file(root: Path, logical_path: str) -> Path:
    relative = Path(logical_path)
    if relative.is_absolute() or ".." in relative.parts:
        _fail("source_binding_path_unsafe", logical_path)
    return _safe_file(root / relative, root)


def _seed_range(value: Any, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != 2:
        _fail(f"{label}_seed_range_invalid")
    start = _nonnegative_int(value[0], f"{label}.seed_start")
    end = _nonnegative_int(value[1], f"{label}.seed_end")
    if end < start:
        _fail(f"{label}_seed_range_inverted")
    return tuple(range(start, end + 1))


def _strict_seed_sequence(value: Any, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        _fail(f"{label}_seed_sequence_invalid")
    seeds = tuple(_nonnegative_int(item, label) for item in value)
    if seeds != tuple(sorted(set(seeds))):
        _fail(f"{label}_seed_sequence_not_canonical")
    return seeds


def _object_sequence(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        _fail(f"{label}_object_sequence_invalid")
    return tuple(value)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label}_not_object")
    return value


def _expect_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(f"{label}_fields_mismatch", f"missing={missing}, extra={extra}")


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label}_invalid")
    return value.strip()


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(f"{label}_invalid")
    return int(value)


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{label}_invalid")
    return int(value)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(code: str, message: str = "") -> None:
    raise A3V3SourceReadinessError(code, message)


__all__ = [
    "A3V3PreGenerationReadiness",
    "A3V3SourceReadinessError",
    "A3_V3_ALLOCATION_BINDING_SCHEMA_VERSION",
    "A3_V3_PRE_GENERATION_READINESS_SCHEMA_VERSION",
    "A3_V3_SOURCE_SCHEDULE_SCHEMA_VERSION",
    "DEFAULT_ALLOCATION_BINDING_PATH",
    "DEFAULT_GLOBAL_REGISTRY_PATH",
    "DEFAULT_PROTOCOL_PATH",
    "DEFAULT_SOURCE_SCHEDULE_PATH",
    "validate_a3_v3_allocation_binding",
    "validate_a3_v3_pre_generation_readiness",
    "validate_a3_v3_registry_allocation",
    "validate_a3_v3_source_schedule",
]
