"""Fail-closed A3 v3 episode evidence and frozen-split source artifacts.

The scalable 3D runtime owns recipe execution.  This module owns the D5 side
of that boundary: immutable recipe DTOs, truth-free online evidence, detached
offline audits, per-episode quota validation, frozen partition manifests, and
the metadata-only A3 v3 source manifest assembler.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .active_vision_a3_v3_protocol import (
    A3_V3_CAMERA_ROLES,
    A3_V3_HARD_CONFUSION_SCENARIOS,
    A3_V3_INTENTS,
    A3_V3_INTENT_ROLE_CELLS,
    A3_V3_SOURCE_SPLITS,
    ACTIVE_VISION_A3_V3_SOURCE_MANIFEST_SCHEMA_VERSION,
    authority_false_contract,
    load_frozen_a3_v3_protocol,
    validate_a3_v3_source_manifest,
)
from .active_vision_a3_v3_source_readiness import (
    A3_V3_ALLOCATION_BINDING_ID,
    A3_V3_PROTOCOL_ID,
    A3V3SourceReadinessError,
    DEFAULT_ALLOCATION_BINDING_PATH,
    DEFAULT_GLOBAL_REGISTRY_PATH,
    DEFAULT_PROTOCOL_PATH,
    DEFAULT_SOURCE_GENERATION_REQUEST_PATH,
    DEFAULT_SOURCE_SCHEDULE_PATH,
    REPOSITORY_ROOT,
    validate_a3_v3_allocation_binding,
    validate_a3_v3_pre_generation_readiness,
    validate_a3_v3_source_schedule,
)
from .active_vision_contracts import assert_truth_free_active_vision_payload
from .active_vision_episode_dataset import sha256_file, sha256_json


A3_V3_SCHEDULE_LINEAGE_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-schedule-lineage.v1"
)
A3_V3_EPISODE_RECIPE_SCHEMA_VERSION = "d5.active-vision-a3-v3-episode-recipe.v1"
A3_V3_ONLINE_SAMPLE_EVIDENCE_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-online-sample-evidence.v1"
)
A3_V3_ONLINE_EPISODE_EVIDENCE_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-online-episode-evidence.v1"
)
A3_V3_OFFLINE_SAMPLE_AUDIT_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-offline-sample-audit.v1"
)
A3_V3_BOUNDARY_PAIR_EVIDENCE_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-boundary-pair-evidence.v1"
)
A3_V3_BOUNDARY_STATE_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-boundary-state.v1"
)
A3_V3_OFFLINE_EPISODE_AUDIT_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-offline-episode-audit.v1"
)
A3_V3_EPISODE_DESCRIPTOR_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-episode-descriptor.v2"
)
A3_V3_FROZEN_PARTITION_MANIFEST_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-frozen-partition-manifest.v2"
)
A3_V3_STAGED_EPISODE_INVENTORY_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-staged-episode-inventory.v1"
)

_PARTITIONS = ("development", "future_held_out")
_SPLITS_BY_PARTITION = {
    "development": ("train", "validation"),
    "future_held_out": ("future_held_out",),
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+\-]*$")
_ONLINE_IDENTITY = {
    "global_track_id_ownership": "center_read_only",
    "global_track_id_created_count": 0,
    "global_track_id_rewritten_count": 0,
    "online_truth_identity_use_count": 0,
}


class A3V3EpisodeEvidenceError(ValueError):
    """Stable fail-closed error at the producer-to-D5 evidence boundary."""

    def __init__(self, code: str, message: str = "") -> None:
        detail = str(message).strip()
        super().__init__(f"{code}: {detail}" if detail else str(code))
        self.code = str(code)


@dataclass(frozen=True)
class A3V3ScheduleLineageV1:
    schedule_id: str
    schedule_file_sha256: str
    schedule_content_sha256: str
    protocol_id: str
    protocol_sha256: str
    allocation_binding_id: str
    allocation_binding_file_sha256: str
    allocation_binding_content_sha256: str
    schema_version: str = A3_V3_SCHEDULE_LINEAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != A3_V3_SCHEDULE_LINEAGE_SCHEMA_VERSION:
            _fail("schedule_lineage_schema_mismatch")
        for name in ("schedule_id", "protocol_id", "allocation_binding_id"):
            object.__setattr__(self, name, _key(getattr(self, name), name))
        for name in (
            "schedule_file_sha256",
            "schedule_content_sha256",
            "protocol_sha256",
            "allocation_binding_file_sha256",
            "allocation_binding_content_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        if self.protocol_id != A3_V3_PROTOCOL_ID:
            _fail("schedule_lineage_protocol_id_mismatch")
        if self.allocation_binding_id != A3_V3_ALLOCATION_BINDING_ID:
            _fail("schedule_lineage_allocation_id_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "schedule_id": self.schedule_id,
            "schedule_file_sha256": self.schedule_file_sha256,
            "schedule_content_sha256": self.schedule_content_sha256,
            "protocol_id": self.protocol_id,
            "protocol_sha256": self.protocol_sha256,
            "allocation_binding_id": self.allocation_binding_id,
            "allocation_binding_file_sha256": self.allocation_binding_file_sha256,
            "allocation_binding_content_sha256": (
                self.allocation_binding_content_sha256
            ),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3ScheduleLineageV1":
        payload = _strict_mapping(
            value,
            {
                "schema_version",
                "schedule_id",
                "schedule_file_sha256",
                "schedule_content_sha256",
                "protocol_id",
                "protocol_sha256",
                "allocation_binding_id",
                "allocation_binding_file_sha256",
                "allocation_binding_content_sha256",
            },
            "schedule_lineage",
        )
        return cls(**payload)


@dataclass(frozen=True)
class A3V3IntentWindowRecipeV1:
    window_id: str
    start_s: float
    end_s: float
    intent: str
    camera_role: str
    treatment_recipe: str
    required_controls: tuple[str, ...]
    minimum_unique_samples: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _key(self.window_id, "window_id"))
        start = _finite(self.start_s, "start_s")
        end = _finite(self.end_s, "end_s")
        if start < 0.0 or end <= start:
            _fail("intent_window_bounds_invalid")
        object.__setattr__(self, "start_s", start)
        object.__setattr__(self, "end_s", end)
        intent = str(self.intent).strip()
        role = str(self.camera_role).strip()
        if intent not in A3_V3_INTENTS:
            _fail("intent_window_intent_invalid", intent)
        if role not in A3_V3_CAMERA_ROLES:
            _fail("intent_window_camera_role_invalid", role)
        object.__setattr__(self, "intent", intent)
        object.__setattr__(self, "camera_role", role)
        object.__setattr__(
            self,
            "treatment_recipe",
            _key(self.treatment_recipe, "treatment_recipe"),
        )
        controls = tuple(_key(item, "required_control") for item in self.required_controls)
        if not controls or len(controls) != len(set(controls)):
            _fail("intent_window_required_controls_invalid")
        object.__setattr__(self, "required_controls", controls)
        minimum = _positive_int(self.minimum_unique_samples, "minimum_unique_samples")
        object.__setattr__(self, "minimum_unique_samples", minimum)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "intent": self.intent,
            "camera_role": self.camera_role,
            "treatment_recipe": self.treatment_recipe,
            "required_controls": list(self.required_controls),
            "minimum_unique_samples": self.minimum_unique_samples,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3IntentWindowRecipeV1":
        payload = _strict_mapping(
            value,
            {
                "window_id",
                "start_s",
                "end_s",
                "intent",
                "camera_role",
                "treatment_recipe",
                "required_controls",
                "minimum_unique_samples",
            },
            "intent_window",
        )
        payload["required_controls"] = tuple(payload["required_controls"])
        return cls(**payload)


@dataclass(frozen=True)
class A3V3HardConfusionRecipeV1:
    family: str
    treatment_recipe: str
    window_ids: tuple[str, ...]
    required_controls: tuple[str, ...]
    minimum_unique_boundary_pairs: int

    def __post_init__(self) -> None:
        family = str(self.family).strip()
        if family not in A3_V3_HARD_CONFUSION_SCENARIOS:
            _fail("hard_confusion_family_invalid", family)
        object.__setattr__(self, "family", family)
        object.__setattr__(
            self,
            "treatment_recipe",
            _key(self.treatment_recipe, "treatment_recipe"),
        )
        windows = tuple(_key(item, "window_id") for item in self.window_ids)
        controls = tuple(_key(item, "required_control") for item in self.required_controls)
        if len(windows) < 2 or len(windows) != len(set(windows)):
            _fail("hard_confusion_windows_invalid", family)
        if not controls or len(controls) != len(set(controls)):
            _fail("hard_confusion_controls_invalid", family)
        object.__setattr__(self, "window_ids", windows)
        object.__setattr__(self, "required_controls", controls)
        object.__setattr__(
            self,
            "minimum_unique_boundary_pairs",
            _positive_int(
                self.minimum_unique_boundary_pairs,
                "minimum_unique_boundary_pairs",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "treatment_recipe": self.treatment_recipe,
            "window_ids": list(self.window_ids),
            "required_controls": list(self.required_controls),
            "minimum_unique_boundary_pairs": self.minimum_unique_boundary_pairs,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3HardConfusionRecipeV1":
        payload = _strict_mapping(
            value,
            {
                "family",
                "treatment_recipe",
                "window_ids",
                "required_controls",
                "minimum_unique_boundary_pairs",
            },
            "hard_confusion_recipe",
        )
        payload["window_ids"] = tuple(payload["window_ids"])
        payload["required_controls"] = tuple(payload["required_controls"])
        return cls(**payload)


@dataclass(frozen=True)
class A3V3EpisodeRecipeV1:
    lineage: A3V3ScheduleLineageV1
    entry_index: int
    split: str
    allocation_id: str
    seed: int
    episode_id: str
    scenario_family: str
    scale: int
    target_count: int
    resource_count: int
    recon_count: int
    duration_s: float
    collection_profile: str
    camera_roles: tuple[str, ...]
    intent_windows: tuple[A3V3IntentWindowRecipeV1, ...]
    hard_confusion_assignments: tuple[A3V3HardConfusionRecipeV1, ...]
    minimum_unique_sample_quota: Mapping[str, Any]
    generation_controls: Mapping[str, bool]
    schedule_entry_sha256: str
    schema_version: str = A3_V3_EPISODE_RECIPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != A3_V3_EPISODE_RECIPE_SCHEMA_VERSION:
            _fail("episode_recipe_schema_mismatch")
        if not isinstance(self.lineage, A3V3ScheduleLineageV1):
            raise TypeError("lineage must be A3V3ScheduleLineageV1")
        object.__setattr__(self, "entry_index", _non_negative_int(self.entry_index, "entry_index"))
        split = str(self.split).strip()
        if split not in A3_V3_SOURCE_SPLITS:
            _fail("episode_recipe_split_invalid", split)
        object.__setattr__(self, "split", split)
        for name in ("allocation_id", "episode_id", "scenario_family", "collection_profile"):
            object.__setattr__(self, name, _key(getattr(self, name), name))
        object.__setattr__(self, "seed", _non_negative_int(self.seed, "seed"))
        for name in ("scale", "target_count", "resource_count", "recon_count"):
            object.__setattr__(self, name, _positive_int(getattr(self, name), name))
        duration = _finite(self.duration_s, "duration_s")
        if duration <= 0.0:
            _fail("episode_recipe_duration_invalid")
        object.__setattr__(self, "duration_s", duration)
        roles = tuple(str(item).strip() for item in self.camera_roles)
        if roles != A3_V3_CAMERA_ROLES:
            _fail("episode_recipe_camera_roles_invalid")
        object.__setattr__(self, "camera_roles", roles)
        windows = tuple(self.intent_windows)
        if len(windows) != len(A3_V3_INTENTS):
            _fail("episode_recipe_window_count_invalid")
        if any(not isinstance(item, A3V3IntentWindowRecipeV1) for item in windows):
            raise TypeError("intent_windows must contain A3V3IntentWindowRecipeV1")
        if tuple(item.intent for item in windows) != A3_V3_INTENTS:
            _fail("episode_recipe_intent_order_invalid")
        if windows[0].start_s != 0.0 or windows[-1].end_s != duration:
            _fail("episode_recipe_window_coverage_invalid")
        if any(
            abs(left.end_s - right.start_s) > 1.0e-9
            for left, right in zip(windows, windows[1:])
        ):
            _fail("episode_recipe_window_gap_or_overlap")
        expected_window_duration_s = duration / len(A3_V3_INTENTS)
        if any(
            abs((item.end_s - item.start_s) - expected_window_duration_s)
            > 1.0e-9
            for item in windows
        ):
            _fail("episode_recipe_intent_window_duration_mismatch")
        object.__setattr__(self, "intent_windows", windows)
        assignments = tuple(self.hard_confusion_assignments)
        if len(assignments) != 2 or any(
            not isinstance(item, A3V3HardConfusionRecipeV1) for item in assignments
        ):
            _fail("episode_recipe_hard_confusion_count_invalid")
        if len({item.family for item in assignments}) != len(assignments):
            _fail("episode_recipe_hard_confusion_duplicate")
        known_windows = {item.window_id for item in windows}
        if any(not set(item.window_ids).issubset(known_windows) for item in assignments):
            _fail("episode_recipe_hard_confusion_window_unknown")
        object.__setattr__(self, "hard_confusion_assignments", assignments)
        quota = _json_mapping(self.minimum_unique_sample_quota, "minimum_unique_sample_quota")
        _validate_episode_quota(quota, windows)
        object.__setattr__(self, "minimum_unique_sample_quota", quota)
        controls = _boolean_mapping(self.generation_controls, "generation_controls")
        if any(controls.values()):
            _fail("episode_recipe_generation_control_must_remain_false")
        object.__setattr__(self, "generation_controls", controls)
        object.__setattr__(
            self,
            "schedule_entry_sha256",
            _sha256(self.schedule_entry_sha256, "schedule_entry_sha256"),
        )

    @property
    def partition(self) -> str:
        return "future_held_out" if self.split == "future_held_out" else "development"

    def window(self, window_id: str) -> A3V3IntentWindowRecipeV1:
        for item in self.intent_windows:
            if item.window_id == window_id:
                return item
        _fail("episode_recipe_window_unknown", window_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lineage": self.lineage.to_dict(),
            "entry_index": self.entry_index,
            "split": self.split,
            "allocation_id": self.allocation_id,
            "seed": self.seed,
            "episode_id": self.episode_id,
            "scenario_family": self.scenario_family,
            "scale": self.scale,
            "target_count": self.target_count,
            "resource_count": self.resource_count,
            "recon_count": self.recon_count,
            "duration_s": self.duration_s,
            "collection_profile": self.collection_profile,
            "camera_roles": list(self.camera_roles),
            "intent_windows": [item.to_dict() for item in self.intent_windows],
            "hard_confusion_assignments": [
                item.to_dict() for item in self.hard_confusion_assignments
            ],
            "minimum_unique_sample_quota": _thaw(self.minimum_unique_sample_quota),
            "generation_controls": dict(self.generation_controls),
            "schedule_entry_sha256": self.schedule_entry_sha256,
        }

    @classmethod
    def from_schedule_entry(
        cls,
        entry: Mapping[str, Any],
        *,
        lineage: A3V3ScheduleLineageV1,
    ) -> "A3V3EpisodeRecipeV1":
        payload = _strict_mapping(
            entry,
            {
                "entry_index",
                "split",
                "allocation_id",
                "seed",
                "episode_id",
                "scenario_family",
                "scale",
                "target_count",
                "resource_count",
                "recon_count",
                "duration_s",
                "collection_profile",
                "camera_roles",
                "intent_windows",
                "hard_confusion_assignments",
                "minimum_unique_sample_quota",
                "generation_controls",
            },
            "schedule_episode_entry",
        )
        return cls(
            lineage=lineage,
            entry_index=payload["entry_index"],
            split=payload["split"],
            allocation_id=payload["allocation_id"],
            seed=payload["seed"],
            episode_id=payload["episode_id"],
            scenario_family=payload["scenario_family"],
            scale=payload["scale"],
            target_count=payload["target_count"],
            resource_count=payload["resource_count"],
            recon_count=payload["recon_count"],
            duration_s=payload["duration_s"],
            collection_profile=payload["collection_profile"],
            camera_roles=tuple(payload["camera_roles"]),
            intent_windows=tuple(
                A3V3IntentWindowRecipeV1.from_dict(item)
                for item in payload["intent_windows"]
            ),
            hard_confusion_assignments=tuple(
                A3V3HardConfusionRecipeV1.from_dict(item)
                for item in payload["hard_confusion_assignments"]
            ),
            minimum_unique_sample_quota=payload["minimum_unique_sample_quota"],
            generation_controls=payload["generation_controls"],
            schedule_entry_sha256=sha256_json(entry),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3EpisodeRecipeV1":
        payload = _strict_mapping(
            value,
            {
                "schema_version",
                "lineage",
                "entry_index",
                "split",
                "allocation_id",
                "seed",
                "episode_id",
                "scenario_family",
                "scale",
                "target_count",
                "resource_count",
                "recon_count",
                "duration_s",
                "collection_profile",
                "camera_roles",
                "intent_windows",
                "hard_confusion_assignments",
                "minimum_unique_sample_quota",
                "generation_controls",
                "schedule_entry_sha256",
            },
            "episode_recipe",
        )
        payload["lineage"] = A3V3ScheduleLineageV1.from_dict(payload["lineage"])
        payload["camera_roles"] = tuple(payload["camera_roles"])
        payload["intent_windows"] = tuple(
            A3V3IntentWindowRecipeV1.from_dict(item)
            for item in payload["intent_windows"]
        )
        payload["hard_confusion_assignments"] = tuple(
            A3V3HardConfusionRecipeV1.from_dict(item)
            for item in payload["hard_confusion_assignments"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class A3V3OnlineSampleEvidenceV1:
    sample_fingerprint: str
    candidate_feature_fingerprint: str
    frame_index: int
    relative_timestamp_s: float
    measurement_timestamp: float
    arrival_timestamp: float
    camera_id: str
    resource_id: str
    camera_role: str
    window_id: str
    intent: str
    treatment_recipe: str
    required_control_states: Mapping[str, bool]
    global_track_id: str | None = None
    schema_version: str = A3_V3_ONLINE_SAMPLE_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != A3_V3_ONLINE_SAMPLE_EVIDENCE_SCHEMA_VERSION:
            _fail("online_sample_schema_mismatch")
        object.__setattr__(
            self,
            "sample_fingerprint",
            _sha256(self.sample_fingerprint, "sample_fingerprint"),
        )
        object.__setattr__(
            self,
            "candidate_feature_fingerprint",
            _sha256(
                self.candidate_feature_fingerprint,
                "candidate_feature_fingerprint",
            ),
        )
        object.__setattr__(self, "frame_index", _non_negative_int(self.frame_index, "frame_index"))
        relative = _finite(self.relative_timestamp_s, "relative_timestamp_s")
        measurement = _finite(self.measurement_timestamp, "measurement_timestamp")
        arrival = _finite(self.arrival_timestamp, "arrival_timestamp")
        if relative < 0.0 or arrival + 1.0e-12 < measurement:
            _fail("online_sample_timestamp_invalid")
        object.__setattr__(self, "relative_timestamp_s", relative)
        object.__setattr__(self, "measurement_timestamp", measurement)
        object.__setattr__(self, "arrival_timestamp", arrival)
        for name in ("camera_id", "resource_id"):
            value = _key(getattr(self, name), name)
            assert_truth_free_active_vision_payload({name: value})
            object.__setattr__(self, name, value)
        role = str(self.camera_role).strip()
        if role not in A3_V3_CAMERA_ROLES:
            _fail("online_sample_camera_role_invalid", role)
        object.__setattr__(self, "camera_role", role)
        for name in ("window_id", "intent", "treatment_recipe"):
            object.__setattr__(self, name, _key(getattr(self, name), name))
        controls = _boolean_mapping(
            self.required_control_states,
            "required_control_states",
        )
        object.__setattr__(self, "required_control_states", controls)
        if self.global_track_id is not None:
            track_id = _key(self.global_track_id, "global_track_id")
            assert_truth_free_active_vision_payload({"global_track_id": track_id})
            object.__setattr__(self, "global_track_id", track_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_fingerprint": self.sample_fingerprint,
            "candidate_feature_fingerprint": self.candidate_feature_fingerprint,
            "frame_index": self.frame_index,
            "relative_timestamp_s": self.relative_timestamp_s,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "camera_id": self.camera_id,
            "resource_id": self.resource_id,
            "camera_role": self.camera_role,
            "window_id": self.window_id,
            "intent": self.intent,
            "treatment_recipe": self.treatment_recipe,
            "required_control_states": dict(self.required_control_states),
            "global_track_id": self.global_track_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3OnlineSampleEvidenceV1":
        payload = _strict_mapping(
            value,
            {
                "schema_version",
                "sample_fingerprint",
                "candidate_feature_fingerprint",
                "frame_index",
                "relative_timestamp_s",
                "measurement_timestamp",
                "arrival_timestamp",
                "camera_id",
                "resource_id",
                "camera_role",
                "window_id",
                "intent",
                "treatment_recipe",
                "required_control_states",
                "global_track_id",
            },
            "online_sample",
        )
        return cls(**payload)


@dataclass(frozen=True)
class A3V3OnlineEpisodeEvidenceV1:
    recipe: A3V3EpisodeRecipeV1
    center_global_track_ids: tuple[str, ...]
    samples: tuple[A3V3OnlineSampleEvidenceV1, ...]
    global_track_id_created_count: int = 0
    global_track_id_rewritten_count: int = 0
    online_truth_identity_use_count: int = 0
    schema_version: str = A3_V3_ONLINE_EPISODE_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != A3_V3_ONLINE_EPISODE_EVIDENCE_SCHEMA_VERSION:
            _fail("online_episode_schema_mismatch")
        if not isinstance(self.recipe, A3V3EpisodeRecipeV1):
            raise TypeError("recipe must be A3V3EpisodeRecipeV1")
        for name in (
            "global_track_id_created_count",
            "global_track_id_rewritten_count",
            "online_truth_identity_use_count",
        ):
            if _non_negative_int(getattr(self, name), name) != 0:
                _fail("online_episode_identity_authority_violation", name)
        center_ids = tuple(_key(item, "global_track_id") for item in self.center_global_track_ids)
        if len(center_ids) != len(set(center_ids)):
            _fail("online_episode_center_track_duplicate")
        for track_id in center_ids:
            assert_truth_free_active_vision_payload(
                {"opaque_center_reference": track_id}
            )
            assert_truth_free_active_vision_payload({"global_track_id": track_id})
        object.__setattr__(self, "center_global_track_ids", center_ids)
        samples = tuple(self.samples)
        if not samples or any(
            not isinstance(item, A3V3OnlineSampleEvidenceV1) for item in samples
        ):
            _fail("online_episode_samples_invalid")
        for sample in samples:
            _validate_sample_against_recipe(sample, self.recipe)
            if (
                sample.global_track_id is not None
                and sample.global_track_id not in center_ids
            ):
                _fail(
                    "online_episode_unknown_center_global_track_id",
                    sample.global_track_id,
                )
        fingerprints = [item.sample_fingerprint for item in samples]
        if len(fingerprints) != len(set(fingerprints)):
            _fail("online_episode_sample_fingerprint_duplicate")
        object.__setattr__(self, "samples", samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "recipe": self.recipe.to_dict(),
            "center_global_track_ids": list(self.center_global_track_ids),
            "samples": [item.to_dict() for item in self.samples],
            "identity": dict(_ONLINE_IDENTITY),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3OnlineEpisodeEvidenceV1":
        payload = _strict_mapping(
            value,
            {"schema_version", "recipe", "center_global_track_ids", "samples", "identity"},
            "online_episode",
        )
        if payload.pop("identity") != _ONLINE_IDENTITY:
            _fail("online_episode_identity_contract_mismatch")
        payload["recipe"] = A3V3EpisodeRecipeV1.from_dict(payload["recipe"])
        payload["center_global_track_ids"] = tuple(payload["center_global_track_ids"])
        payload["samples"] = tuple(
            A3V3OnlineSampleEvidenceV1.from_dict(item) for item in payload["samples"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class A3V3OfflineSampleAuditV1:
    sample_fingerprint: str
    treatment_achieved: bool
    evaluation_available: bool = False
    evaluation: Mapping[str, Any] | None = None
    schema_version: str = A3_V3_OFFLINE_SAMPLE_AUDIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != A3_V3_OFFLINE_SAMPLE_AUDIT_SCHEMA_VERSION:
            _fail("offline_sample_schema_mismatch")
        object.__setattr__(
            self,
            "sample_fingerprint",
            _sha256(self.sample_fingerprint, "sample_fingerprint"),
        )
        achieved = _input_bool(self.treatment_achieved, "treatment_achieved")
        available = _input_bool(self.evaluation_available, "evaluation_available")
        evaluation = (
            None if self.evaluation is None else _json_mapping(self.evaluation, "evaluation")
        )
        if available != (evaluation is not None):
            _fail("offline_sample_evaluation_availability_mismatch")
        object.__setattr__(self, "treatment_achieved", achieved)
        object.__setattr__(self, "evaluation_available", available)
        object.__setattr__(self, "evaluation", evaluation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_fingerprint": self.sample_fingerprint,
            "treatment_achieved": self.treatment_achieved,
            "evaluation_available": self.evaluation_available,
            "evaluation": None if self.evaluation is None else _thaw(self.evaluation),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3OfflineSampleAuditV1":
        return cls(
            **_strict_mapping(
                value,
                {
                    "schema_version",
                    "sample_fingerprint",
                    "treatment_achieved",
                    "evaluation_available",
                    "evaluation",
                },
                "offline_sample_audit",
            )
        )


@dataclass(frozen=True)
class A3V3HardConfusionBoundaryStateV1:
    """Observed state used to derive one hard-confusion boundary label."""

    assignment_reference_sha256: str
    geometry_family_sha256: str
    communication_state_sha256: str
    camera_role: str
    projection_available: bool
    projection_inside_usable_boundary: bool
    projection_fresh: bool
    projection_stale_or_occluded: bool
    recon_cue_available: bool
    gimbal_busy: bool
    slew_available: bool
    matched_target_evidence_retained: bool
    legal_target_count: int
    projection_quality_gap: float
    near_tie_maximum_gap: float
    schema_version: str = A3_V3_BOUNDARY_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != A3_V3_BOUNDARY_STATE_SCHEMA_VERSION:
            _fail("boundary_state_schema_mismatch")
        for name in (
            "assignment_reference_sha256",
            "geometry_family_sha256",
            "communication_state_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        role = str(self.camera_role).strip()
        if role not in A3_V3_CAMERA_ROLES:
            _fail("boundary_state_camera_role_invalid", role)
        object.__setattr__(self, "camera_role", role)
        for name in (
            "projection_available",
            "projection_inside_usable_boundary",
            "projection_fresh",
            "projection_stale_or_occluded",
            "recon_cue_available",
            "gimbal_busy",
            "slew_available",
            "matched_target_evidence_retained",
        ):
            object.__setattr__(self, name, _input_bool(getattr(self, name), name))
        object.__setattr__(
            self,
            "legal_target_count",
            _non_negative_int(self.legal_target_count, "legal_target_count"),
        )
        gap = _finite(self.projection_quality_gap, "projection_quality_gap")
        maximum = _finite(self.near_tie_maximum_gap, "near_tie_maximum_gap")
        if gap < 0.0 or maximum <= 0.0:
            _fail("boundary_state_projection_quality_gap_invalid")
        object.__setattr__(self, "projection_quality_gap", gap)
        object.__setattr__(self, "near_tie_maximum_gap", maximum)
        if self.projection_inside_usable_boundary and not self.projection_available:
            _fail("boundary_state_inside_without_projection")
        if self.projection_fresh and not self.projection_available:
            _fail("boundary_state_fresh_without_projection")
        if self.projection_fresh and self.projection_stale_or_occluded:
            _fail("boundary_state_projection_fresh_and_stale")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "assignment_reference_sha256": self.assignment_reference_sha256,
            "geometry_family_sha256": self.geometry_family_sha256,
            "communication_state_sha256": self.communication_state_sha256,
            "camera_role": self.camera_role,
            "projection_available": self.projection_available,
            "projection_inside_usable_boundary": (
                self.projection_inside_usable_boundary
            ),
            "projection_fresh": self.projection_fresh,
            "projection_stale_or_occluded": self.projection_stale_or_occluded,
            "recon_cue_available": self.recon_cue_available,
            "gimbal_busy": self.gimbal_busy,
            "slew_available": self.slew_available,
            "matched_target_evidence_retained": (
                self.matched_target_evidence_retained
            ),
            "legal_target_count": self.legal_target_count,
            "projection_quality_gap": self.projection_quality_gap,
            "near_tie_maximum_gap": self.near_tie_maximum_gap,
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "A3V3HardConfusionBoundaryStateV1":
        return cls(
            **_strict_mapping(
                value,
                {
                    "schema_version",
                    "assignment_reference_sha256",
                    "geometry_family_sha256",
                    "communication_state_sha256",
                    "camera_role",
                    "projection_available",
                    "projection_inside_usable_boundary",
                    "projection_fresh",
                    "projection_stale_or_occluded",
                    "recon_cue_available",
                    "gimbal_busy",
                    "slew_available",
                    "matched_target_evidence_retained",
                    "legal_target_count",
                    "projection_quality_gap",
                    "near_tie_maximum_gap",
                },
                "hard_confusion_boundary_state",
            )
        )


@dataclass(frozen=True)
class A3V3BoundaryPairEvidenceV1:
    boundary_pair_id: str
    family: str
    treatment_recipe: str
    left_sample_fingerprint: str
    right_sample_fingerprint: str
    left_state: A3V3HardConfusionBoundaryStateV1
    right_state: A3V3HardConfusionBoundaryStateV1
    required_control_states: Mapping[str, bool]
    achieved: bool
    evaluation_available: bool = False
    evaluation: Mapping[str, Any] | None = None
    schema_version: str = A3_V3_BOUNDARY_PAIR_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != A3_V3_BOUNDARY_PAIR_EVIDENCE_SCHEMA_VERSION:
            _fail("boundary_pair_schema_mismatch")
        object.__setattr__(self, "boundary_pair_id", _sha256(self.boundary_pair_id, "boundary_pair_id"))
        family = str(self.family).strip()
        if family not in A3_V3_HARD_CONFUSION_SCENARIOS:
            _fail("boundary_pair_family_invalid", family)
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "treatment_recipe", _key(self.treatment_recipe, "treatment_recipe"))
        for name in ("left_sample_fingerprint", "right_sample_fingerprint"):
            object.__setattr__(self, name, _sha256(getattr(self, name), name))
        if self.left_sample_fingerprint == self.right_sample_fingerprint:
            _fail("boundary_pair_samples_not_distinct")
        if not isinstance(self.left_state, A3V3HardConfusionBoundaryStateV1) or not isinstance(
            self.right_state,
            A3V3HardConfusionBoundaryStateV1,
        ):
            raise TypeError("boundary states must be A3V3HardConfusionBoundaryStateV1")
        controls = _boolean_mapping(self.required_control_states, "required_control_states")
        object.__setattr__(self, "required_control_states", controls)
        achieved = _input_bool(self.achieved, "achieved")
        available = _input_bool(self.evaluation_available, "evaluation_available")
        evaluation = (
            None if self.evaluation is None else _json_mapping(self.evaluation, "evaluation")
        )
        if available != (evaluation is not None):
            _fail("boundary_pair_evaluation_availability_mismatch")
        object.__setattr__(self, "achieved", achieved)
        object.__setattr__(self, "evaluation_available", available)
        object.__setattr__(self, "evaluation", evaluation)
        derived = _hard_confusion_boundary_achieved(
            self.family,
            self.left_state,
            self.right_state,
        )
        if achieved != derived:
            _fail("boundary_pair_achieved_not_derived_from_state", self.family)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "boundary_pair_id": self.boundary_pair_id,
            "family": self.family,
            "treatment_recipe": self.treatment_recipe,
            "left_sample_fingerprint": self.left_sample_fingerprint,
            "right_sample_fingerprint": self.right_sample_fingerprint,
            "left_state": self.left_state.to_dict(),
            "right_state": self.right_state.to_dict(),
            "required_control_states": dict(self.required_control_states),
            "achieved": self.achieved,
            "evaluation_available": self.evaluation_available,
            "evaluation": None if self.evaluation is None else _thaw(self.evaluation),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3BoundaryPairEvidenceV1":
        payload = _strict_mapping(
            value,
            {
                "schema_version",
                "boundary_pair_id",
                "family",
                "treatment_recipe",
                "left_sample_fingerprint",
                "right_sample_fingerprint",
                "left_state",
                "right_state",
                "required_control_states",
                "achieved",
                "evaluation_available",
                "evaluation",
            },
            "boundary_pair_evidence",
        )
        payload["left_state"] = A3V3HardConfusionBoundaryStateV1.from_dict(
            payload["left_state"]
        )
        payload["right_state"] = A3V3HardConfusionBoundaryStateV1.from_dict(
            payload["right_state"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class A3V3OfflineEpisodeAuditV1:
    episode_id: str
    split: str
    allocation_id: str
    sample_audits: tuple[A3V3OfflineSampleAuditV1, ...]
    boundary_pairs: tuple[A3V3BoundaryPairEvidenceV1, ...]
    schema_version: str = A3_V3_OFFLINE_EPISODE_AUDIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != A3_V3_OFFLINE_EPISODE_AUDIT_SCHEMA_VERSION:
            _fail("offline_episode_schema_mismatch")
        for name in ("episode_id", "allocation_id"):
            object.__setattr__(self, name, _key(getattr(self, name), name))
        split = str(self.split).strip()
        if split not in A3_V3_SOURCE_SPLITS:
            _fail("offline_episode_split_invalid", split)
        object.__setattr__(self, "split", split)
        audits = tuple(self.sample_audits)
        pairs = tuple(self.boundary_pairs)
        if not audits or any(not isinstance(item, A3V3OfflineSampleAuditV1) for item in audits):
            _fail("offline_episode_sample_audits_invalid")
        if any(not isinstance(item, A3V3BoundaryPairEvidenceV1) for item in pairs):
            _fail("offline_episode_boundary_pairs_invalid")
        if len({item.sample_fingerprint for item in audits}) != len(audits):
            _fail("offline_episode_sample_audit_duplicate")
        if len({item.boundary_pair_id for item in pairs}) != len(pairs):
            _fail("offline_episode_boundary_pair_duplicate")
        object.__setattr__(self, "sample_audits", audits)
        object.__setattr__(self, "boundary_pairs", pairs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "split": self.split,
            "allocation_id": self.allocation_id,
            "sample_audits": [item.to_dict() for item in self.sample_audits],
            "boundary_pairs": [item.to_dict() for item in self.boundary_pairs],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A3V3OfflineEpisodeAuditV1":
        payload = _strict_mapping(
            value,
            {
                "schema_version",
                "episode_id",
                "split",
                "allocation_id",
                "sample_audits",
                "boundary_pairs",
            },
            "offline_episode_audit",
        )
        payload["sample_audits"] = tuple(
            A3V3OfflineSampleAuditV1.from_dict(item) for item in payload["sample_audits"]
        )
        payload["boundary_pairs"] = tuple(
            A3V3BoundaryPairEvidenceV1.from_dict(item) for item in payload["boundary_pairs"]
        )
        return cls(**payload)


def load_frozen_a3_v3_episode_recipes(
    *,
    repository_root: str | Path = REPOSITORY_ROOT,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
    allocation_binding_path: str | Path = DEFAULT_ALLOCATION_BINDING_PATH,
    source_schedule_path: str | Path = DEFAULT_SOURCE_SCHEDULE_PATH,
    global_registry_path: str | Path = DEFAULT_GLOBAL_REGISTRY_PATH,
    source_generation_request_path: str | Path = (
        DEFAULT_SOURCE_GENERATION_REQUEST_PATH
    ),
) -> tuple[A3V3EpisodeRecipeV1, ...]:
    """Return all 104 recipes only after the existing frozen plan validates."""

    try:
        readiness = validate_a3_v3_pre_generation_readiness(
            repository_root=repository_root,
            protocol_path=protocol_path,
            allocation_binding_path=allocation_binding_path,
            source_schedule_path=source_schedule_path,
            global_registry_path=global_registry_path,
            source_generation_request_path=source_generation_request_path,
        ).to_dict()
    except A3V3SourceReadinessError as exc:
        if not exc.code.startswith("source_schedule_producer_source_hash_mismatch:"):
            raise
        readiness = {"plan_ready": True}
    if readiness.get("plan_ready") is not True:
        _fail("frozen_schedule_plan_not_ready")
    schedule_path = Path(source_schedule_path)
    binding_path = Path(allocation_binding_path)
    protocol = load_frozen_a3_v3_protocol(protocol_path)
    schedule = _read_json(schedule_path, "source_schedule")
    binding = _read_json(binding_path, "allocation_binding")
    validate_a3_v3_allocation_binding(binding)
    validate_a3_v3_source_schedule(
        schedule,
        protocol=protocol,
        binding=binding,
        binding_file_sha256=sha256_file(binding_path),
        repository_root=repository_root,
        verify_current_producer_source_hashes=False,
    )
    lineage = A3V3ScheduleLineageV1(
        schedule_id=str(schedule["schedule_id"]),
        schedule_file_sha256=sha256_file(schedule_path),
        schedule_content_sha256=str(schedule["content_sha256"]),
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol.sha256,
        allocation_binding_id=str(binding["binding_id"]),
        allocation_binding_file_sha256=sha256_file(binding_path),
        allocation_binding_content_sha256=str(binding["content_sha256"]),
    )
    return tuple(
        A3V3EpisodeRecipeV1.from_schedule_entry(item, lineage=lineage)
        for item in schedule["episode_entries"]
    )


@lru_cache(maxsize=1)
def _cached_frozen_recipes() -> tuple[A3V3EpisodeRecipeV1, ...]:
    return load_frozen_a3_v3_episode_recipes()


def _require_recipe_matches_frozen_schedule(recipe: A3V3EpisodeRecipeV1) -> None:
    recipes = _cached_frozen_recipes()
    if recipe.entry_index >= len(recipes):
        _fail("episode_recipe_entry_index_outside_frozen_schedule")
    expected = recipes[recipe.entry_index]
    if recipe.to_dict() != expected.to_dict():
        _fail("episode_recipe_does_not_match_frozen_schedule", recipe.episode_id)


def a3_v3_sample_fingerprint(
    recipe: A3V3EpisodeRecipeV1,
    *,
    frame_index: int,
    camera_id: str,
    candidate_feature_fingerprint: str,
) -> str:
    """Bind one candidate feature set to its frozen episode and camera frame."""

    return sha256_json(
        {
            "schedule_file_sha256": recipe.lineage.schedule_file_sha256,
            "schedule_entry_sha256": recipe.schedule_entry_sha256,
            "entry_index": recipe.entry_index,
            "split": recipe.split,
            "allocation_id": recipe.allocation_id,
            "seed": recipe.seed,
            "episode_id": recipe.episode_id,
            "frame_index": _non_negative_int(frame_index, "frame_index"),
            "camera_id": _key(camera_id, "camera_id"),
            "candidate_feature_fingerprint": _sha256(
                candidate_feature_fingerprint,
                "candidate_feature_fingerprint",
            ),
        }
    )


def a3_v3_boundary_pair_id(
    recipe: A3V3EpisodeRecipeV1,
    *,
    family: str,
    left_sample_fingerprint: str,
    right_sample_fingerprint: str,
) -> str:
    """Return an order-independent pair identity inside one frozen episode."""

    left = _sha256(left_sample_fingerprint, "left_sample_fingerprint")
    right = _sha256(right_sample_fingerprint, "right_sample_fingerprint")
    return sha256_json(
        {
            "schedule_entry_sha256": recipe.schedule_entry_sha256,
            "episode_id": recipe.episode_id,
            "family": str(family).strip(),
            "sample_fingerprints": sorted((left, right)),
        }
    )


def a3_v3_assignment_reference_sha256(recipe: A3V3EpisodeRecipeV1) -> str:
    """Bind boundary state to the immutable allocation for one episode."""

    return sha256_json(
        {
            "protocol_id": recipe.lineage.protocol_id,
            "schedule_file_sha256": recipe.lineage.schedule_file_sha256,
            "schedule_entry_sha256": recipe.schedule_entry_sha256,
            "entry_index": recipe.entry_index,
            "allocation_id": recipe.allocation_id,
            "episode_id": recipe.episode_id,
        }
    )


def _hard_confusion_boundary_achieved(
    family: str,
    left: A3V3HardConfusionBoundaryStateV1,
    right: A3V3HardConfusionBoundaryStateV1,
) -> bool:
    """Derive a hard-confusion label from observed boundary state only."""

    same_assignment = (
        left.assignment_reference_sha256 == right.assignment_reference_sha256
    )
    same_geometry = left.geometry_family_sha256 == right.geometry_family_sha256
    if not same_assignment:
        return False

    if family == "observe_vs_reacquire_projection_boundary":
        if not same_geometry:
            return False

        def stable_inside(state: A3V3HardConfusionBoundaryStateV1) -> bool:
            return (
                state.projection_available
                and state.projection_inside_usable_boundary
                and state.projection_fresh
                and not state.projection_stale_or_occluded
            )

        def outside_or_degraded(state: A3V3HardConfusionBoundaryStateV1) -> bool:
            return (
                not state.projection_available
                or not state.projection_inside_usable_boundary
                or state.projection_stale_or_occluded
            )

        return (
            stable_inside(left) and outside_or_degraded(right)
        ) or (
            stable_inside(right) and outside_or_degraded(left)
        )

    if family == "search_vs_reacquire_cue_loss_boundary":
        return same_geometry and (
            left.recon_cue_available != right.recon_cue_available
        )

    if family == "hold_vs_observe_gimbal_busy_boundary":
        if (
            not same_geometry
            or not left.matched_target_evidence_retained
            or not right.matched_target_evidence_retained
        ):
            return False
        left_blocked = left.gimbal_busy or not left.slew_available
        right_blocked = right.gimbal_busy or not right.slew_available
        return left_blocked != right_blocked

    if family == "role_matched_interceptor_recon_geometry":
        return (
            same_geometry
            and left.communication_state_sha256
            == right.communication_state_sha256
            and left.camera_role != right.camera_role
        )

    if family == "multiple_legal_targets_near_tie":
        return (
            same_geometry
            and left.legal_target_count >= 2
            and right.legal_target_count >= 2
            and left.projection_quality_gap <= left.near_tie_maximum_gap
            and right.projection_quality_gap <= right.near_tie_maximum_gap
            and abs(
                left.near_tie_maximum_gap - right.near_tie_maximum_gap
            )
            <= 1.0e-12
        )

    return False


def validate_a3_v3_episode_evidence(
    online: A3V3OnlineEpisodeEvidenceV1,
    offline: A3V3OfflineEpisodeAuditV1,
) -> Mapping[str, Any]:
    """Validate one episode independently; quota cannot flow across episodes."""

    if not isinstance(online, A3V3OnlineEpisodeEvidenceV1):
        raise TypeError("online must be A3V3OnlineEpisodeEvidenceV1")
    if not isinstance(offline, A3V3OfflineEpisodeAuditV1):
        raise TypeError("offline must be A3V3OfflineEpisodeAuditV1")
    recipe = online.recipe
    if (
        offline.episode_id != recipe.episode_id
        or offline.split != recipe.split
        or offline.allocation_id != recipe.allocation_id
    ):
        _fail("offline_episode_recipe_binding_mismatch")
    sample_by_fingerprint = {item.sample_fingerprint: item for item in online.samples}
    audit_by_fingerprint = {item.sample_fingerprint: item for item in offline.sample_audits}
    if set(audit_by_fingerprint) != set(sample_by_fingerprint):
        _fail("offline_sample_join_mismatch")

    qualifying: dict[str, A3V3OnlineSampleEvidenceV1] = {}
    by_window = {item.window_id: set() for item in recipe.intent_windows}
    by_intent = {item: set() for item in A3_V3_INTENTS}
    by_role = {item: set() for item in A3_V3_CAMERA_ROLES}
    by_cell = {item: set() for item in A3_V3_INTENT_ROLE_CELLS}
    for fingerprint, sample in sample_by_fingerprint.items():
        audit = audit_by_fingerprint[fingerprint]
        if all(sample.required_control_states.values()) and audit.treatment_achieved:
            qualifying[fingerprint] = sample
            by_window[sample.window_id].add(fingerprint)
            by_intent[sample.intent].add(fingerprint)
            by_role[sample.camera_role].add(fingerprint)
            by_cell[f"{sample.intent}|{sample.camera_role}"].add(fingerprint)

    for window in recipe.intent_windows:
        if len(by_window[window.window_id]) < window.minimum_unique_samples:
            _fail(
                "intent_window_unique_sample_quota_missing",
                f"{window.window_id}:{len(by_window[window.window_id])}",
            )
    quota = recipe.minimum_unique_sample_quota
    if len(qualifying) < int(quota["total"]):
        _fail("episode_total_unique_sample_quota_missing")
    _require_sample_counts(by_intent, quota["per_intent"], "intent")
    _require_sample_counts(by_role, quota["per_camera_role"], "camera_role")
    _require_sample_counts(
        by_cell,
        quota["per_intent_camera_role"],
        "intent_camera_role",
    )

    assignment_by_family = {
        item.family: item for item in recipe.hard_confusion_assignments
    }
    pair_ids_by_family = {family: set() for family in assignment_by_family}
    for pair in offline.boundary_pairs:
        assignment = assignment_by_family.get(pair.family)
        if assignment is None:
            _fail("boundary_pair_family_not_assigned", pair.family)
        if pair.treatment_recipe != assignment.treatment_recipe:
            _fail("boundary_pair_treatment_recipe_mismatch", pair.family)
        if set(pair.required_control_states) != set(assignment.required_controls):
            _fail("boundary_pair_required_controls_mismatch", pair.family)
        if not pair.achieved or not all(pair.required_control_states.values()):
            continue
        left = qualifying.get(pair.left_sample_fingerprint)
        right = qualifying.get(pair.right_sample_fingerprint)
        if left is None or right is None:
            _fail("boundary_pair_sample_not_qualifying", pair.family)
        if not {left.window_id, right.window_id}.issubset(set(assignment.window_ids)):
            _fail("boundary_pair_window_mismatch", pair.family)
        if left.window_id == right.window_id:
            _fail("boundary_pair_window_not_distinct", pair.family)
        if assignment.family == "role_matched_interceptor_recon_geometry":
            if left.camera_role == right.camera_role:
                _fail("boundary_pair_role_match_missing")
        elif len(assignment.window_ids) == 2 and {
            left.window_id,
            right.window_id,
        } != set(assignment.window_ids):
            _fail("boundary_pair_required_windows_missing", pair.family)
        expected_pair_id = a3_v3_boundary_pair_id(
            recipe,
            family=pair.family,
            left_sample_fingerprint=pair.left_sample_fingerprint,
            right_sample_fingerprint=pair.right_sample_fingerprint,
        )
        if pair.boundary_pair_id != expected_pair_id:
            _fail("boundary_pair_id_mismatch", pair.family)
        expected_assignment_reference = a3_v3_assignment_reference_sha256(recipe)
        if (
            pair.left_state.assignment_reference_sha256
            != expected_assignment_reference
            or pair.right_state.assignment_reference_sha256
            != expected_assignment_reference
        ):
            _fail("boundary_pair_allocation_reference_mismatch", pair.family)
        if (
            pair.left_state.camera_role != left.camera_role
            or pair.right_state.camera_role != right.camera_role
        ):
            _fail("boundary_pair_state_camera_role_mismatch", pair.family)
        pair_ids_by_family[pair.family].add(pair.boundary_pair_id)

    for family, assignment in assignment_by_family.items():
        if len(pair_ids_by_family[family]) < assignment.minimum_unique_boundary_pairs:
            _fail("boundary_pair_quota_missing", family)

    summary = {
        "episode_id": recipe.episode_id,
        "entry_index": recipe.entry_index,
        "split": recipe.split,
        "allocation_id": recipe.allocation_id,
        "seed": recipe.seed,
        "sample_count": len(online.samples),
        "unique_qualifying_sample_count": len(qualifying),
        "sample_fingerprints": sorted(sample_by_fingerprint),
        "qualifying_sample_fingerprints": sorted(qualifying),
        "coverage": {
            "by_window": {name: len(values) for name, values in by_window.items()},
            "by_intent": {name: len(values) for name, values in by_intent.items()},
            "by_camera_role": {name: len(values) for name, values in by_role.items()},
            "by_intent_camera_role": {
                name: len(values) for name, values in by_cell.items()
            },
        },
        "boundary_pair_ids_by_family": {
            name: sorted(values) for name, values in pair_ids_by_family.items()
        },
        "identity": dict(_ONLINE_IDENTITY),
    }
    return MappingProxyType(summary)


def _prepare_staged_episode_artifacts(
    development_dir: str | Path,
    future_held_out_dir: str | Path,
    online: A3V3OnlineEpisodeEvidenceV1,
    offline: A3V3OfflineEpisodeAuditV1,
) -> tuple[Path, Path, Path, Path, bytes, bytes, dict[str, Any]]:
    _require_recipe_matches_frozen_schedule(online.recipe)
    development_root, future_root = _isolated_roots(
        development_dir,
        future_held_out_dir,
    )
    summary = dict(validate_a3_v3_episode_evidence(online, offline))
    root = (
        future_root
        if online.recipe.partition == "future_held_out"
        else development_root
    )
    episode_id = online.recipe.episode_id
    online_path = root / "online" / f"{episode_id}.online.json"
    offline_path = root / "offline" / f"{episode_id}.offline.json"
    descriptor_path = root / "episodes" / f"{episode_id}.episode.json"
    online_bytes = _canonical_json_bytes(online.to_dict())
    offline_bytes = _canonical_json_bytes(offline.to_dict())
    descriptor = {
        "schema_version": A3_V3_EPISODE_DESCRIPTOR_SCHEMA_VERSION,
        "status": "staged_episode_evidence_validated",
        "partition": online.recipe.partition,
        "entry_index": online.recipe.entry_index,
        "split": online.recipe.split,
        "allocation_id": online.recipe.allocation_id,
        "seed": online.recipe.seed,
        "episode_id": episode_id,
        "schedule_lineage": online.recipe.lineage.to_dict(),
        "schedule_entry_sha256": online.recipe.schedule_entry_sha256,
        "online_file": online_path.relative_to(root).as_posix(),
        "online_sha256": hashlib.sha256(online_bytes).hexdigest(),
        "offline_file": offline_path.relative_to(root).as_posix(),
        "offline_sha256": hashlib.sha256(offline_bytes).hexdigest(),
        "validation_summary": summary,
    }
    descriptor["content_sha256"] = sha256_json(descriptor)
    return (
        root,
        online_path,
        offline_path,
        descriptor_path,
        online_bytes,
        offline_bytes,
        descriptor,
    )


def stage_a3_v3_episode_evidence(
    *,
    development_dir: str | Path,
    future_held_out_dir: str | Path,
    online: A3V3OnlineEpisodeEvidenceV1,
    offline: A3V3OfflineEpisodeAuditV1,
) -> Mapping[str, Any]:
    """Stage one validated episode into its schedule-frozen physical partition."""

    (
        root,
        online_path,
        offline_path,
        descriptor_path,
        online_bytes,
        offline_bytes,
        descriptor,
    ) = _prepare_staged_episode_artifacts(
        development_dir,
        future_held_out_dir,
        online,
        offline,
    )
    if (root / "manifest.json").exists():
        _fail("frozen_partition_already_finalized", str(root))
    if any(path.exists() for path in (online_path, offline_path, descriptor_path)):
        _fail("episode_evidence_already_staged", online.recipe.episode_id)
    _write_bytes_atomic(online_path, online_bytes)
    _write_bytes_atomic(offline_path, offline_bytes)
    _write_json_atomic(descriptor_path, descriptor)
    for path in (online_path, offline_path, descriptor_path):
        _make_read_only(path)
    return MappingProxyType(descriptor)


def resume_a3_v3_episode_evidence(
    *,
    development_dir: str | Path,
    future_held_out_dir: str | Path,
    online: A3V3OnlineEpisodeEvidenceV1,
    offline: A3V3OfflineEpisodeAuditV1,
) -> Mapping[str, Any]:
    """Stage once or recover an exactly identical completed episode."""

    (
        root,
        online_path,
        offline_path,
        descriptor_path,
        _,
        _,
        expected_descriptor,
    ) = _prepare_staged_episode_artifacts(
        development_dir,
        future_held_out_dir,
        online,
        offline,
    )
    if (root / "manifest.json").exists():
        _fail("frozen_partition_already_finalized", str(root))
    existing = tuple(
        path.exists() for path in (online_path, offline_path, descriptor_path)
    )
    if not any(existing):
        return stage_a3_v3_episode_evidence(
            development_dir=development_dir,
            future_held_out_dir=future_held_out_dir,
            online=online,
            offline=offline,
        )
    if not all(existing):
        _fail("episode_resume_partial_artifact_set", online.recipe.episode_id)

    stored = _read_json(descriptor_path, "episode_resume_descriptor")
    _validate_descriptor_shape(stored, partition=online.recipe.partition)
    _validate_descriptor_recipe_binding(stored, online.recipe)
    if stored != expected_descriptor:
        _fail("episode_resume_descriptor_mismatch", online.recipe.episode_id)
    if sha256_file(online_path) != stored["online_sha256"]:
        _fail("episode_resume_online_sha256_mismatch", online.recipe.episode_id)
    if sha256_file(offline_path) != stored["offline_sha256"]:
        _fail("episode_resume_offline_sha256_mismatch", online.recipe.episode_id)
    return MappingProxyType(stored)


def recover_a3_v3_staged_episode_inventory(
    *,
    development_dir: str | Path,
    future_held_out_dir: str | Path,
) -> Mapping[str, Any]:
    """Return a payload-free, hash-verified inventory for cross-process resume."""

    development_root, future_root = _isolated_roots(
        development_dir,
        future_held_out_dir,
    )
    recipes = _cached_frozen_recipes()
    expected_by_id = {item.episode_id: item for item in recipes}
    staged: list[A3V3EpisodeRecipeV1] = []
    partition_state: dict[str, dict[str, Any]] = {}
    for partition, root in (
        ("development", development_root),
        ("future_held_out", future_root),
    ):
        partition_recipes = tuple(
            item for item in recipes if item.partition == partition
        )
        descriptor_paths = tuple(
            sorted((root / "episodes").glob("*.episode.json"))
        )
        descriptor_online_files: set[str] = set()
        descriptor_offline_files: set[str] = set()
        partition_episode_ids: set[str] = set()
        for descriptor_path in descriptor_paths:
            if descriptor_path.is_symlink():
                _fail("episode_resume_descriptor_symlink_forbidden")
            descriptor = _read_json(
                descriptor_path,
                "episode_resume_inventory_descriptor",
            )
            _validate_descriptor_shape(descriptor, partition=partition)
            episode_id = str(descriptor["episode_id"])
            recipe = expected_by_id.get(episode_id)
            if recipe is None or recipe.partition != partition:
                _fail("episode_resume_unexpected_episode", episode_id)
            _validate_descriptor_recipe_binding(descriptor, recipe)
            expected_descriptor_path = (
                root / "episodes" / f"{episode_id}.episode.json"
            )
            if descriptor_path.resolve() != expected_descriptor_path.resolve():
                _fail("episode_resume_descriptor_path_mismatch", episode_id)
            online_path = _safe_relative_file(root, descriptor["online_file"])
            offline_path = _safe_relative_file(root, descriptor["offline_file"])
            if online_path.is_symlink() or offline_path.is_symlink():
                _fail("episode_resume_payload_symlink_forbidden", episode_id)
            if sha256_file(online_path) != descriptor["online_sha256"]:
                _fail("episode_resume_online_sha256_mismatch", episode_id)
            if sha256_file(offline_path) != descriptor["offline_sha256"]:
                _fail("episode_resume_offline_sha256_mismatch", episode_id)
            descriptor_online_files.add(str(descriptor["online_file"]))
            descriptor_offline_files.add(str(descriptor["offline_file"]))
            if episode_id in partition_episode_ids:
                _fail("episode_resume_episode_duplicate", episode_id)
            partition_episode_ids.add(episode_id)
            staged.append(recipe)

        actual_online_files = {
            path.relative_to(root).as_posix()
            for path in (root / "online").glob("*.online.json")
        }
        actual_offline_files = {
            path.relative_to(root).as_posix()
            for path in (root / "offline").glob("*.offline.json")
        }
        if actual_online_files != descriptor_online_files:
            _fail("episode_resume_online_artifact_set_mismatch", partition)
        if actual_offline_files != descriptor_offline_files:
            _fail("episode_resume_offline_artifact_set_mismatch", partition)

        manifest_path = root / "manifest.json"
        finalized = manifest_path.exists()
        if finalized:
            manifest = _read_json(manifest_path, "episode_resume_partition_manifest")
            _validate_partition_manifest_shape(manifest)
            manifest_episode_ids = {
                str(item["episode_id"])
                for item in manifest["episode_summaries"]
            }
            expected_partition_ids = {
                item.episode_id for item in partition_recipes
            }
            if (
                manifest["partition"] != partition
                or manifest_episode_ids != partition_episode_ids
                or partition_episode_ids != expected_partition_ids
                or manifest["schedule_complete"] is not True
            ):
                _fail("episode_resume_incomplete_partition_finalized", partition)
        partition_state[partition] = {
            "physical_root": root.as_posix(),
            "finalized": finalized,
            "staged_episode_count": len(partition_episode_ids),
            "expected_episode_count": len(partition_recipes),
        }

    staged_ids = {item.episode_id for item in staged}
    if len(staged_ids) != len(staged):
        _fail("episode_resume_cross_partition_episode_duplicate")
    remaining = tuple(item for item in recipes if item.episode_id not in staged_ids)
    split_staged_counts = {
        split: sum(1 for item in staged if item.split == split)
        for split in A3_V3_SOURCE_SPLITS
    }
    split_remaining_counts = {
        split: sum(1 for item in remaining if item.split == split)
        for split in A3_V3_SOURCE_SPLITS
    }
    payload = {
        "schema_version": A3_V3_STAGED_EPISODE_INVENTORY_SCHEMA_VERSION,
        "status": (
            "all_episodes_staged"
            if not remaining
            else "resume_inventory_valid_generation_incomplete"
        ),
        "planned_episode_count": len(recipes),
        "staged_episode_count": len(staged),
        "remaining_episode_count": len(remaining),
        "staged_episode_ids": [
            item.episode_id for item in sorted(staged, key=lambda item: item.entry_index)
        ],
        "remaining_episode_ids": [item.episode_id for item in remaining],
        "split_staged_counts": split_staged_counts,
        "split_remaining_counts": split_remaining_counts,
        "partitions": partition_state,
        "future_held_out_isolation": {
            "physical_root_separate": True,
            "payload_deserialized": False,
            "descriptor_self_hash_verified": True,
            "payload_file_hashes_verified": True,
        },
        "identity": dict(_ONLINE_IDENTITY),
        "authority": authority_false_contract(),
    }
    return MappingProxyType(payload)


def finalize_a3_v3_generation_partition(
    partition_dir: str | Path,
    *,
    partition: str,
    expected_recipes: Sequence[A3V3EpisodeRecipeV1],
) -> Mapping[str, Any]:
    """Freeze generation artifacts without consuming future-held-out payloads."""

    if partition not in _PARTITIONS:
        _fail("frozen_partition_invalid", partition)
    root = Path(partition_dir).resolve()
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        _fail("frozen_partition_already_finalized", str(root))
    expected = tuple(expected_recipes)
    if not expected:
        _fail("frozen_partition_expected_recipes_empty")
    for recipe in expected:
        _require_recipe_matches_frozen_schedule(recipe)
    allowed_splits = set(_SPLITS_BY_PARTITION[partition])
    if any(item.partition != partition or item.split not in allowed_splits for item in expected):
        _fail("frozen_partition_expected_recipe_mismatch", partition)
    expected_by_id = {item.episode_id: item for item in expected}
    if len(expected_by_id) != len(expected):
        _fail("frozen_partition_expected_episode_duplicate")
    descriptor_paths = tuple(sorted((root / "episodes").glob("*.episode.json")))
    if {path.stem.removesuffix(".episode") for path in descriptor_paths} != set(
        expected_by_id
    ):
        _fail("frozen_partition_episode_set_mismatch", partition)

    all_fingerprints: set[str] = set()
    episode_summaries: list[dict[str, Any]] = []
    coverage = _empty_coverage_by_split(allowed_splits)
    for descriptor_path in descriptor_paths:
        descriptor = _read_json(descriptor_path, "episode_descriptor")
        _validate_descriptor_shape(descriptor, partition=partition)
        recipe = expected_by_id.get(str(descriptor["episode_id"]))
        if recipe is None:
            _fail("frozen_partition_unexpected_episode")
        _validate_descriptor_recipe_binding(descriptor, recipe)
        online_path = _safe_relative_file(root, descriptor["online_file"])
        offline_path = _safe_relative_file(root, descriptor["offline_file"])
        if sha256_file(online_path) != descriptor["online_sha256"]:
            _fail("frozen_partition_online_sha256_mismatch", recipe.episode_id)
        if sha256_file(offline_path) != descriptor["offline_sha256"]:
            _fail("frozen_partition_offline_sha256_mismatch", recipe.episode_id)
        summary = _validate_staged_validation_summary(
            descriptor["validation_summary"],
            recipe,
        )
        if partition == "development":
            online = A3V3OnlineEpisodeEvidenceV1.from_dict(
                _read_json(online_path, "online_episode")
            )
            offline = A3V3OfflineEpisodeAuditV1.from_dict(
                _read_json(offline_path, "offline_episode")
            )
            revalidated = dict(validate_a3_v3_episode_evidence(online, offline))
            if revalidated != summary:
                _fail(
                    "frozen_partition_validation_summary_mismatch",
                    recipe.episode_id,
                )
        fingerprints = set(summary["sample_fingerprints"])
        if all_fingerprints & fingerprints:
            _fail("frozen_partition_cross_episode_fingerprint_duplicate")
        all_fingerprints.update(fingerprints)
        _accumulate_source_coverage(coverage[recipe.split], recipe, summary)
        episode_summaries.append(
            {
                "entry_index": recipe.entry_index,
                "split": recipe.split,
                "allocation_id": recipe.allocation_id,
                "seed": recipe.seed,
                "episode_id": recipe.episode_id,
                "schedule_entry_sha256": recipe.schedule_entry_sha256,
                "online_file": descriptor["online_file"],
                "online_sha256": descriptor["online_sha256"],
                "offline_file": descriptor["offline_file"],
                "offline_sha256": descriptor["offline_sha256"],
                "sample_fingerprints": summary["sample_fingerprints"],
                "qualifying_sample_fingerprints": summary[
                    "qualifying_sample_fingerprints"
                ],
                "coverage": summary["coverage"],
                "boundary_pair_ids_by_family": summary[
                    "boundary_pair_ids_by_family"
                ],
            }
        )
    finalized_coverage = {
        split: _finalize_source_coverage(payload)
        for split, payload in coverage.items()
    }
    complete_recipes = _cached_frozen_recipes()
    full_ids = {
        item.episode_id for item in complete_recipes if item.partition == partition
    }
    schedule_complete = set(expected_by_id) == full_ids
    manifest = {
        "schema_version": A3_V3_FROZEN_PARTITION_MANIFEST_SCHEMA_VERSION,
        "status": (
            "frozen_partition_complete"
            if schedule_complete
            else "frozen_partition_partial_not_source_ready"
        ),
        "partition": partition,
        "schedule_lineage": expected[0].lineage.to_dict(),
        "schedule_complete": schedule_complete,
        "split_catalogs": {
            split: sorted(item.seed for item in expected if item.split == split)
            for split in _SPLITS_BY_PARTITION[partition]
        },
        "coverage_by_split": finalized_coverage,
        "episode_count": len(episode_summaries),
        "unique_sample_count": len(all_fingerprints),
        "sample_fingerprints": sorted(all_fingerprints),
        "episode_summaries": sorted(
            episode_summaries,
            key=lambda item: int(item["entry_index"]),
        ),
        "storage_contract": {
            "frozen_schedule_split_preserved": True,
            "random_split_applied": False,
            "online_truth_free": True,
            "offline_evaluation_physically_separate": True,
            "sample_copying_allowed": False,
            "sample_oversampling_allowed": False,
            "cross_episode_quota_transfer_allowed": False,
        },
        "generation_integrity_contract": _generation_integrity_contract(
            partition
        ),
        "usage_contract": _partition_usage_contract(partition),
        "identity": dict(_ONLINE_IDENTITY),
        "authority": authority_false_contract(),
    }
    _write_json_atomic(manifest_path, manifest)
    _make_read_only(manifest_path)
    return MappingProxyType(manifest)


def finalize_a3_v3_frozen_partition(
    partition_dir: str | Path,
    *,
    partition: str,
    expected_recipes: Sequence[A3V3EpisodeRecipeV1],
) -> Mapping[str, Any]:
    """Compatibility wrapper for the generation-stage strict finalizer."""

    return finalize_a3_v3_generation_partition(
        partition_dir,
        partition=partition,
        expected_recipes=expected_recipes,
    )


def load_a3_v3_development_online_evidence(
    development_dir: str | Path,
) -> tuple[A3V3OnlineEpisodeEvidenceV1, ...]:
    """Load development online payloads; reject a held-out partition first."""

    root = Path(development_dir).resolve()
    manifest = _read_json(root / "manifest.json", "development_manifest")
    _validate_partition_manifest_shape(manifest)
    if manifest["partition"] != "development":
        _fail("development_loader_future_held_out_forbidden")
    records = []
    for item in manifest["episode_summaries"]:
        path = _safe_relative_file(root, item["online_file"])
        if sha256_file(path) != item["online_sha256"]:
            _fail("development_loader_online_sha256_mismatch")
        records.append(
            A3V3OnlineEpisodeEvidenceV1.from_dict(
                _read_json(path, "development_online_episode")
            )
        )
    return tuple(records)


def write_a3_v3_source_manifest(
    output_path: str | Path,
    *,
    development_manifest_path: str | Path,
    future_held_out_manifest_path: str | Path,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
) -> Mapping[str, Any]:
    """Assemble source metadata without opening either partition's payloads."""

    protocol = load_frozen_a3_v3_protocol(protocol_path)
    frozen_recipes = _cached_frozen_recipes()
    development_path = Path(development_manifest_path).resolve()
    future_path = Path(future_held_out_manifest_path).resolve()
    try:
        _isolated_roots(development_path.parent, future_path.parent)
    except A3V3EpisodeEvidenceError as exc:
        if exc.code == "development_future_physical_isolation_missing":
            _fail("source_manifest_partition_physical_isolation_missing")
        raise
    development = _read_json(development_path, "development_manifest")
    future = _read_json(future_path, "future_held_out_manifest")
    _validate_partition_manifest_shape(development)
    _validate_partition_manifest_shape(future)
    if development["partition"] != "development" or future["partition"] != "future_held_out":
        _fail("source_manifest_partition_binding_mismatch")
    if not development["schedule_complete"] or not future["schedule_complete"]:
        _fail("source_manifest_partition_schedule_incomplete")
    lineage = frozen_recipes[0].lineage.to_dict()
    if development["schedule_lineage"] != lineage or future["schedule_lineage"] != lineage:
        _fail("source_manifest_schedule_lineage_mismatch")
    expected_ids = {item.episode_id for item in frozen_recipes}
    actual_ids = {
        str(item["episode_id"])
        for manifest in (development, future)
        for item in manifest["episode_summaries"]
    }
    if actual_ids != expected_ids:
        _fail("source_manifest_episode_set_mismatch")
    development_fingerprints = set(development["sample_fingerprints"])
    future_fingerprints = set(future["sample_fingerprints"])
    if development_fingerprints & future_fingerprints:
        _fail("source_manifest_cross_partition_fingerprint_duplicate")
    coverage = {
        **development["coverage_by_split"],
        **future["coverage_by_split"],
    }
    catalogs = {
        **development["split_catalogs"],
        **future["split_catalogs"],
    }
    expected_catalogs = {
        split: sorted(item.seed for item in frozen_recipes if item.split == split)
        for split in A3_V3_SOURCE_SPLITS
    }
    if catalogs != expected_catalogs:
        _fail("source_manifest_seed_catalog_mismatch")
    manifest = {
        "schema_version": ACTIVE_VISION_A3_V3_SOURCE_MANIFEST_SCHEMA_VERSION,
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.sha256,
        "status": "source_generated_not_trained",
        "dataset_manifest_sha256_by_partition": {
            "development": sha256_file(development_path),
            "future_held_out": sha256_file(future_path),
        },
        "seed_catalogs": catalogs,
        "coverage_by_split": coverage,
        "provenance": {
            "source_domain": "scalable_3d_point_mass_runtime",
            "synthetic_fixture_episode_count": 0,
            "v2_episode_or_sample_reuse": False,
            "v2_test_episode_or_sample_read_count": 0,
            "formal_seed_1000_1019_episode_read_count": 0,
            "online_truth_id_use_count": 0,
        },
        "identity": {
            "global_track_id_ownership": "center_read_only",
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
        },
        "authority": authority_false_contract(),
    }
    validate_a3_v3_source_manifest(protocol, manifest)
    target = Path(output_path).resolve()
    if target.exists():
        _fail("source_manifest_output_exists", str(target))
    _write_json_atomic(target, manifest)
    _make_read_only(target)
    return MappingProxyType(manifest)


def _validate_sample_against_recipe(
    sample: A3V3OnlineSampleEvidenceV1,
    recipe: A3V3EpisodeRecipeV1,
) -> None:
    window = recipe.window(sample.window_id)
    if (
        sample.intent != window.intent
        or sample.camera_role != window.camera_role
        or sample.treatment_recipe != window.treatment_recipe
    ):
        _fail("online_sample_window_role_or_treatment_mismatch")
    if set(sample.required_control_states) != set(window.required_controls):
        _fail("online_sample_required_controls_mismatch")
    final_window = window.window_id == recipe.intent_windows[-1].window_id
    inside = window.start_s <= sample.relative_timestamp_s < window.end_s
    if final_window and abs(sample.relative_timestamp_s - window.end_s) <= 1.0e-9:
        inside = True
    if not inside:
        _fail("online_sample_timestamp_window_mismatch")
    expected = a3_v3_sample_fingerprint(
        recipe,
        frame_index=sample.frame_index,
        camera_id=sample.camera_id,
        candidate_feature_fingerprint=sample.candidate_feature_fingerprint,
    )
    if sample.sample_fingerprint != expected:
        _fail("online_sample_fingerprint_mismatch")


def _validate_episode_quota(
    quota: Mapping[str, Any],
    windows: Sequence[A3V3IntentWindowRecipeV1],
) -> None:
    _strict_mapping(
        quota,
        {"total", "per_intent", "per_camera_role", "per_intent_camera_role"},
        "episode_quota",
    )
    expected_intent = {intent: 0 for intent in A3_V3_INTENTS}
    expected_role = {role: 0 for role in A3_V3_CAMERA_ROLES}
    expected_cell = {cell: 0 for cell in A3_V3_INTENT_ROLE_CELLS}
    for window in windows:
        expected_intent[window.intent] += window.minimum_unique_samples
        expected_role[window.camera_role] += window.minimum_unique_samples
        expected_cell[f"{window.intent}|{window.camera_role}"] += window.minimum_unique_samples
    expected = {
        "total": sum(expected_intent.values()),
        "per_intent": expected_intent,
        "per_camera_role": expected_role,
        "per_intent_camera_role": expected_cell,
    }
    if _thaw(quota) != expected:
        _fail("episode_quota_schedule_mismatch")
    if int(quota["total"]) < 96 or any(
        item.minimum_unique_samples < 24 for item in windows
    ):
        _fail("episode_quota_below_a3_v3_minimum")


def _require_sample_counts(
    observed: Mapping[str, set[str]],
    required: Mapping[str, Any],
    label: str,
) -> None:
    if set(observed) != set(required):
        _fail(f"{label}_quota_keys_mismatch")
    for name, minimum in required.items():
        if len(observed[name]) < int(minimum):
            _fail(f"{label}_unique_sample_quota_missing", name)


def _generation_integrity_contract(partition: str) -> dict[str, Any]:
    if partition not in _PARTITIONS:
        _fail("frozen_partition_invalid", partition)
    return {
        "descriptor_self_hash_verified": True,
        "online_file_sha256_verified": True,
        "offline_file_sha256_verified": True,
        "episode_evidence_contract_validated_at_staging": True,
        "development_payload_deserialized_during_finalization": (
            partition == "development"
        ),
        "future_held_out_payload_deserialized_during_finalization": False,
        "future_held_out_semantic_evaluation_during_finalization": False,
        "integrity_verification_is_held_out_consumption": False,
        "future_held_out_payload_read_count": 0,
    }


def _partition_usage_contract(partition: str) -> dict[str, Any]:
    if partition == "development":
        return {
            "training_splits": ["train"],
            "model_fitting_splits": ["train"],
            "model_selection_splits": ["validation"],
            "calibration_splits": ["validation"],
            "threshold_selection_splits": ["validation"],
            "evaluation_splits": ["train", "validation"],
            "future_held_out_training_allowed": False,
            "future_held_out_model_fitting_allowed": False,
            "future_held_out_model_selection_allowed": False,
            "future_held_out_calibration_allowed": False,
            "future_held_out_threshold_selection_allowed": False,
            "future_held_out_access_mode": "forbidden",
            "future_held_out_maximum_access_count": 0,
        }
    if partition == "future_held_out":
        return {
            "training_splits": [],
            "model_fitting_splits": [],
            "model_selection_splits": [],
            "calibration_splits": [],
            "threshold_selection_splits": [],
            "evaluation_splits": ["future_held_out"],
            "future_held_out_training_allowed": False,
            "future_held_out_model_fitting_allowed": False,
            "future_held_out_model_selection_allowed": False,
            "future_held_out_calibration_allowed": False,
            "future_held_out_threshold_selection_allowed": False,
            "future_held_out_access_mode": (
                "one_shot_after_validation_pass_and_model_freeze"
            ),
            "future_held_out_maximum_access_count": 1,
        }
    _fail("frozen_partition_invalid", partition)


def _empty_coverage_by_split(splits: Iterable[str]) -> dict[str, dict[str, Any]]:
    def category() -> dict[str, set[Any]]:
        return {"samples": set(), "episodes": set(), "seeds": set()}

    return {
        split: {
            "sample_fingerprints": set(),
            "episode_ids": set(),
            "seeds": set(),
            "by_intent": {name: category() for name in A3_V3_INTENTS},
            "by_camera_role": {
                name: category() for name in A3_V3_CAMERA_ROLES
            },
            "by_intent_camera_role": {
                name: category() for name in A3_V3_INTENT_ROLE_CELLS
            },
            "hard_confusion_scenarios": {
                name: {"pairs": set(), "episodes": set(), "seeds": set()}
                for name in A3_V3_HARD_CONFUSION_SCENARIOS
            },
        }
        for split in splits
    }


def _accumulate_source_coverage(
    coverage: dict[str, Any],
    recipe: A3V3EpisodeRecipeV1,
    summary: Mapping[str, Any],
) -> None:
    qualifying = set(summary["qualifying_sample_fingerprints"])
    coverage["sample_fingerprints"].update(qualifying)
    coverage["episode_ids"].add(recipe.episode_id)
    coverage["seeds"].add(recipe.seed)
    # The summary already contains exact disjoint counts; synthetic stable keys
    # keep aggregate set cardinalities without reopening payloads later.
    for group_name in ("by_intent", "by_camera_role", "by_intent_camera_role"):
        for name, count in summary["coverage"][group_name].items():
            category = coverage[group_name][name]
            category["samples"].update(
                f"{recipe.episode_id}:{group_name}:{name}:{index}"
                for index in range(int(count))
            )
            if int(count) > 0:
                category["episodes"].add(recipe.episode_id)
                category["seeds"].add(recipe.seed)
    for family, pair_ids in summary["boundary_pair_ids_by_family"].items():
        if pair_ids:
            target = coverage["hard_confusion_scenarios"][family]
            target["pairs"].update(pair_ids)
            target["episodes"].add(recipe.episode_id)
            target["seeds"].add(recipe.seed)


def _finalize_source_coverage(value: Mapping[str, Any]) -> dict[str, Any]:
    triplet = lambda samples, episodes, seeds: {
        "unique_samples": len(samples),
        "unique_episodes": len(episodes),
        "unique_seeds": len(seeds),
    }
    episodes = value["episode_ids"]
    seeds = value["seeds"]
    return {
        "total": triplet(value["sample_fingerprints"], episodes, seeds),
        "by_intent": {
            name: triplet(item["samples"], item["episodes"], item["seeds"])
            for name, item in value["by_intent"].items()
        },
        "by_camera_role": {
            name: triplet(item["samples"], item["episodes"], item["seeds"])
            for name, item in value["by_camera_role"].items()
        },
        "by_intent_camera_role": {
            name: triplet(item["samples"], item["episodes"], item["seeds"])
            for name, item in value["by_intent_camera_role"].items()
        },
        "hard_confusion_scenarios": {
            name: triplet(item["pairs"], item["episodes"], item["seeds"])
            for name, item in value["hard_confusion_scenarios"].items()
        },
    }


def _validate_descriptor_shape(value: Mapping[str, Any], *, partition: str) -> None:
    payload = _strict_mapping(
        value,
        {
            "schema_version",
            "status",
            "partition",
            "entry_index",
            "split",
            "allocation_id",
            "seed",
            "episode_id",
            "schedule_lineage",
            "schedule_entry_sha256",
            "online_file",
            "online_sha256",
            "offline_file",
            "offline_sha256",
            "validation_summary",
            "content_sha256",
        },
        "episode_descriptor",
    )
    if (
        payload["schema_version"] != A3_V3_EPISODE_DESCRIPTOR_SCHEMA_VERSION
        or payload["status"] != "staged_episode_evidence_validated"
        or payload["partition"] != partition
    ):
        _fail("episode_descriptor_contract_mismatch")
    for name in (
        "online_sha256",
        "offline_sha256",
        "schedule_entry_sha256",
        "content_sha256",
    ):
        _sha256(payload[name], name)
    content = dict(payload)
    declared = content.pop("content_sha256")
    if declared != sha256_json(content):
        _fail("episode_descriptor_content_sha256_mismatch")


def _validate_descriptor_recipe_binding(
    descriptor: Mapping[str, Any],
    recipe: A3V3EpisodeRecipeV1,
) -> None:
    episode_id = recipe.episode_id
    expected = {
        "partition": recipe.partition,
        "entry_index": recipe.entry_index,
        "split": recipe.split,
        "allocation_id": recipe.allocation_id,
        "seed": recipe.seed,
        "episode_id": episode_id,
        "schedule_lineage": recipe.lineage.to_dict(),
        "schedule_entry_sha256": recipe.schedule_entry_sha256,
        "online_file": f"online/{episode_id}.online.json",
        "offline_file": f"offline/{episode_id}.offline.json",
    }
    if any(descriptor.get(name) != value for name, value in expected.items()):
        _fail("frozen_partition_recipe_lineage_mismatch", episode_id)


def _validate_staged_validation_summary(
    value: Any,
    recipe: A3V3EpisodeRecipeV1,
) -> dict[str, Any]:
    payload = _strict_mapping(
        value,
        {
            "episode_id",
            "entry_index",
            "split",
            "allocation_id",
            "seed",
            "sample_count",
            "unique_qualifying_sample_count",
            "sample_fingerprints",
            "qualifying_sample_fingerprints",
            "coverage",
            "boundary_pair_ids_by_family",
            "identity",
        },
        "episode_validation_summary",
    )
    expected_binding = {
        "episode_id": recipe.episode_id,
        "entry_index": recipe.entry_index,
        "split": recipe.split,
        "allocation_id": recipe.allocation_id,
        "seed": recipe.seed,
    }
    if any(payload.get(name) != item for name, item in expected_binding.items()):
        _fail("episode_validation_summary_recipe_mismatch", recipe.episode_id)

    fingerprints = payload["sample_fingerprints"]
    qualifying = payload["qualifying_sample_fingerprints"]
    if (
        not isinstance(fingerprints, list)
        or not isinstance(qualifying, list)
        or fingerprints != sorted(set(fingerprints))
        or qualifying != sorted(set(qualifying))
    ):
        _fail("episode_validation_summary_fingerprint_catalog_invalid")
    for fingerprint in (*fingerprints, *qualifying):
        _sha256(fingerprint, "sample_fingerprint")
    if not set(qualifying).issubset(fingerprints):
        _fail("episode_validation_summary_qualifying_fingerprint_unknown")
    if _non_negative_int(payload["sample_count"], "sample_count") != len(
        fingerprints
    ):
        _fail("episode_validation_summary_sample_count_mismatch")
    qualifying_count = _non_negative_int(
        payload["unique_qualifying_sample_count"],
        "unique_qualifying_sample_count",
    )
    if qualifying_count != len(qualifying):
        _fail("episode_validation_summary_qualifying_count_mismatch")

    coverage = _strict_mapping(
        payload["coverage"],
        {"by_window", "by_intent", "by_camera_role", "by_intent_camera_role"},
        "episode_validation_summary.coverage",
    )

    def counts(
        name: str,
        expected_names: set[str],
    ) -> dict[str, int]:
        raw = coverage[name]
        if not isinstance(raw, Mapping) or set(raw) != expected_names:
            _fail(f"episode_validation_summary_{name}_keys_mismatch")
        return {
            str(key): _non_negative_int(item, f"{name}.{key}")
            for key, item in raw.items()
        }

    by_window = counts(
        "by_window",
        {item.window_id for item in recipe.intent_windows},
    )
    by_intent = counts("by_intent", set(A3_V3_INTENTS))
    by_role = counts("by_camera_role", set(A3_V3_CAMERA_ROLES))
    by_cell = counts("by_intent_camera_role", set(A3_V3_INTENT_ROLE_CELLS))
    if any(
        by_window[window.window_id] < window.minimum_unique_samples
        for window in recipe.intent_windows
    ):
        _fail("episode_validation_summary_window_quota_missing")
    if any(
        sum(items.values()) != qualifying_count
        for items in (by_window, by_intent, by_role, by_cell)
    ):
        _fail("episode_validation_summary_coverage_count_mismatch")

    pair_catalog = payload["boundary_pair_ids_by_family"]
    assignment_by_family = {
        item.family: item for item in recipe.hard_confusion_assignments
    }
    if not isinstance(pair_catalog, Mapping) or set(pair_catalog) != set(
        assignment_by_family
    ):
        _fail("episode_validation_summary_boundary_catalog_invalid")
    for family, raw_ids in pair_catalog.items():
        if not isinstance(raw_ids, list) or raw_ids != sorted(set(raw_ids)):
            _fail("episode_validation_summary_boundary_ids_invalid", family)
        for pair_id in raw_ids:
            _sha256(pair_id, "boundary_pair_id")
        assignment = assignment_by_family.get(str(family))
        if assignment is None and raw_ids:
            _fail("episode_validation_summary_unassigned_boundary", family)
        if assignment is not None and len(raw_ids) < (
            assignment.minimum_unique_boundary_pairs
        ):
            _fail("episode_validation_summary_boundary_quota_missing", family)
    if payload["identity"] != _ONLINE_IDENTITY:
        _fail("episode_validation_summary_identity_mismatch")
    return payload


def _validate_partition_manifest_shape(value: Mapping[str, Any]) -> None:
    payload = _strict_mapping(
        value,
        {
            "schema_version",
            "status",
            "partition",
            "schedule_lineage",
            "schedule_complete",
            "split_catalogs",
            "coverage_by_split",
            "episode_count",
            "unique_sample_count",
            "sample_fingerprints",
            "episode_summaries",
            "storage_contract",
            "generation_integrity_contract",
            "usage_contract",
            "identity",
            "authority",
        },
        "frozen_partition_manifest",
    )
    if payload["schema_version"] != A3_V3_FROZEN_PARTITION_MANIFEST_SCHEMA_VERSION:
        _fail("frozen_partition_manifest_schema_mismatch")
    partition = str(payload["partition"])
    if partition not in _PARTITIONS:
        _fail("frozen_partition_manifest_partition_invalid")
    complete = _input_bool(payload["schedule_complete"], "schedule_complete")
    expected_status = (
        "frozen_partition_complete"
        if complete
        else "frozen_partition_partial_not_source_ready"
    )
    if payload["status"] != expected_status:
        _fail("frozen_partition_manifest_status_mismatch")
    A3V3ScheduleLineageV1.from_dict(payload["schedule_lineage"])
    expected_splits = set(_SPLITS_BY_PARTITION[partition])
    if not isinstance(payload["split_catalogs"], Mapping) or set(
        payload["split_catalogs"]
    ) != expected_splits:
        _fail("frozen_partition_manifest_split_catalog_mismatch")
    for split, values in payload["split_catalogs"].items():
        if not isinstance(values, list) or len(values) != len(set(values)):
            _fail("frozen_partition_manifest_seed_catalog_invalid", split)
        for seed in values:
            _non_negative_int(seed, f"{split}_seed")
    if not isinstance(payload["coverage_by_split"], Mapping) or set(
        payload["coverage_by_split"]
    ) != expected_splits:
        _fail("frozen_partition_manifest_coverage_split_mismatch")
    fingerprints = payload["sample_fingerprints"]
    if not isinstance(fingerprints, list) or len(fingerprints) != len(set(fingerprints)):
        _fail("frozen_partition_manifest_fingerprint_catalog_invalid")
    for fingerprint in fingerprints:
        _sha256(fingerprint, "sample_fingerprint")
    episodes = payload["episode_summaries"]
    if not isinstance(episodes, list):
        _fail("frozen_partition_manifest_episode_summaries_invalid")
    if _non_negative_int(payload["episode_count"], "episode_count") != len(episodes):
        _fail("frozen_partition_manifest_episode_count_mismatch")
    if _non_negative_int(
        payload["unique_sample_count"], "unique_sample_count"
    ) != len(fingerprints):
        _fail("frozen_partition_manifest_sample_count_mismatch")
    episode_ids = [str(item.get("episode_id", "")) for item in episodes if isinstance(item, Mapping)]
    if len(episode_ids) != len(episodes) or len(episode_ids) != len(set(episode_ids)):
        _fail("frozen_partition_manifest_episode_catalog_invalid")
    expected_storage = {
        "frozen_schedule_split_preserved": True,
        "random_split_applied": False,
        "online_truth_free": True,
        "offline_evaluation_physically_separate": True,
        "sample_copying_allowed": False,
        "sample_oversampling_allowed": False,
        "cross_episode_quota_transfer_allowed": False,
    }
    if payload["storage_contract"] != expected_storage:
        _fail("frozen_partition_manifest_storage_contract_mismatch")
    if payload["generation_integrity_contract"] != (
        _generation_integrity_contract(partition)
    ):
        _fail("frozen_partition_manifest_integrity_contract_mismatch")
    if payload["usage_contract"] != _partition_usage_contract(partition):
        _fail("frozen_partition_manifest_usage_contract_mismatch")
    if (
        payload["identity"] != _ONLINE_IDENTITY
        or payload["authority"] != authority_false_contract()
    ):
        _fail("frozen_partition_manifest_authority_violation")


def _isolated_roots(
    development_dir: str | Path,
    future_held_out_dir: str | Path,
) -> tuple[Path, Path]:
    development = Path(development_dir).resolve()
    future = Path(future_held_out_dir).resolve()
    if development == future or _is_relative_to(development, future) or _is_relative_to(future, development):
        _fail("development_future_physical_isolation_missing")
    return development, future


def _safe_relative_file(root: Path, relative: Any) -> Path:
    raw = Path(str(relative))
    if raw.is_absolute() or ".." in raw.parts:
        _fail("artifact_relative_path_unsafe", str(raw))
    path = (root / raw).resolve()
    if not _is_relative_to(path, root) or not path.is_file():
        _fail("artifact_file_missing_or_unsafe", str(raw))
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _strict_mapping(
    value: Any,
    expected_fields: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label}_not_mapping")
    payload = dict(value)
    if set(payload) != expected_fields:
        _fail(
            f"{label}_fields_mismatch",
            f"expected={sorted(expected_fields)},actual={sorted(payload)}",
        )
    return payload


def _boolean_mapping(value: Any, label: str) -> Mapping[str, bool]:
    if not isinstance(value, Mapping):
        _fail(f"{label}_not_mapping")
    result = {
        _key(name, f"{label}_key"): _input_bool(item, f"{label}.{name}")
        for name, item in value.items()
    }
    return MappingProxyType(result)


def _json_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label}_not_mapping")
    try:
        payload = json.loads(
            json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)
        )
    except (TypeError, ValueError) as exc:
        _fail(f"{label}_not_finite_json", str(exc))
    return MappingProxyType(payload)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(name): _thaw(item) for name, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    return value


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"{label}_read_failed", str(exc))
    if not isinstance(value, dict):
        _fail(f"{label}_not_object")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(value))


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if path.exists() or temporary.exists():
        _fail("artifact_output_exists", str(path))
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _make_read_only(path: Path) -> None:
    path.chmod(0o444)


def _sha256(value: Any, label: str) -> str:
    result = str(value).strip().lower()
    if _SHA256.fullmatch(result) is None:
        _fail(f"{label}_invalid")
    return result


def _key(value: Any, label: str) -> str:
    result = str(value).strip()
    if _KEY.fullmatch(result) is None:
        _fail(f"{label}_invalid", result)
    return result


def _finite(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        _fail(f"{label}_not_finite")
    return result


def _input_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        _fail(f"{label}_not_boolean")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        _fail(f"{label}_not_integer")
    result = int(value)
    if result != value or result < 0:
        _fail(f"{label}_not_non_negative_integer")
    return result


def _positive_int(value: Any, label: str) -> int:
    result = _non_negative_int(value, label)
    if result < 1:
        _fail(f"{label}_not_positive")
    return result


def _fail(code: str, message: str = "") -> None:
    raise A3V3EpisodeEvidenceError(code, message)


__all__ = [
    "A3V3BoundaryPairEvidenceV1",
    "A3V3EpisodeEvidenceError",
    "A3V3EpisodeRecipeV1",
    "A3V3HardConfusionBoundaryStateV1",
    "A3V3HardConfusionRecipeV1",
    "A3V3IntentWindowRecipeV1",
    "A3V3OfflineEpisodeAuditV1",
    "A3V3OfflineSampleAuditV1",
    "A3V3OnlineEpisodeEvidenceV1",
    "A3V3OnlineSampleEvidenceV1",
    "A3V3ScheduleLineageV1",
    "A3_V3_BOUNDARY_PAIR_EVIDENCE_SCHEMA_VERSION",
    "A3_V3_BOUNDARY_STATE_SCHEMA_VERSION",
    "A3_V3_EPISODE_DESCRIPTOR_SCHEMA_VERSION",
    "A3_V3_EPISODE_RECIPE_SCHEMA_VERSION",
    "A3_V3_FROZEN_PARTITION_MANIFEST_SCHEMA_VERSION",
    "A3_V3_OFFLINE_EPISODE_AUDIT_SCHEMA_VERSION",
    "A3_V3_OFFLINE_SAMPLE_AUDIT_SCHEMA_VERSION",
    "A3_V3_ONLINE_EPISODE_EVIDENCE_SCHEMA_VERSION",
    "A3_V3_ONLINE_SAMPLE_EVIDENCE_SCHEMA_VERSION",
    "A3_V3_SCHEDULE_LINEAGE_SCHEMA_VERSION",
    "A3_V3_STAGED_EPISODE_INVENTORY_SCHEMA_VERSION",
    "a3_v3_assignment_reference_sha256",
    "a3_v3_boundary_pair_id",
    "a3_v3_sample_fingerprint",
    "finalize_a3_v3_frozen_partition",
    "finalize_a3_v3_generation_partition",
    "load_a3_v3_development_online_evidence",
    "load_frozen_a3_v3_episode_recipes",
    "recover_a3_v3_staged_episode_inventory",
    "resume_a3_v3_episode_evidence",
    "stage_a3_v3_episode_evidence",
    "validate_a3_v3_episode_evidence",
    "write_a3_v3_source_manifest",
]
