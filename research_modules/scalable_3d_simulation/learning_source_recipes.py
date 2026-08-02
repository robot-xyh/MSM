"""Strict episode recipes for the D3, D4 and D5 learning-source campaigns.

This module is main-owned orchestration.  It maps frozen module schedules to
runtime-neutral execution specifications without generating data, reading
held-out payloads, or granting learning/runtime authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .models import ScenarioConfig
from .scenarios import AVAILABLE_SCENARIOS, make_curriculum_scenario


D3_A1_V3_RECIPE_SCHEMA_VERSION = "scalable3d-d3-a1-v3-recipe-v1"
D4_A2_V8_RECIPE_SCHEMA_VERSION = "scalable3d-d4-a2-v8-recipe-v1"
D5_A3_V3_RECIPE_SCHEMA_VERSION = "scalable3d-d5-a3-v3-recipe-v1"

D3_A1_V3_SCHEDULE_SCHEMA_VERSION = (
    "d3_a1_source_independent_v3_generation_schedule_v1"
)
D4_A2_V8_REGISTRY_SCHEMA_VERSION = (
    "d4-region-resource-v8-development-seed-request-registry-v1"
)
D5_A3_V3_SCHEDULE_SCHEMA_VERSION = (
    "d5.active-vision-a3-v3-source-collection-schedule.v2"
)

DEFAULT_D3_DURATION_S = 10.0
DEFAULT_D4_DURATION_S = 3.0

_D3_RUNTIME_SCENARIO = {
    "nominal_balanced": "nominal",
    "resource_shortage": "nominal",
    "resource_surplus": "nominal",
    "dynamic_add_drop": "nominal",
    "near_tie_hard_negative": "dense_crossing",
    **{name: name for name in AVAILABLE_SCENARIOS},
}
_D3_TREATMENT = {
    "dynamic_add_drop": "roster_event_schedule_v1",
    "near_tie_hard_negative": "near_tie_cost_boundary_v1",
}


class LearningSourceRecipeError(ValueError):
    """Stable fail-closed error for one frozen source recipe."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        suffix = str(detail).strip()
        super().__init__(f"{self.code}: {suffix}" if suffix else self.code)


@dataclass(frozen=True)
class FrozenScheduleLineage:
    """Immutable identity of the schedule bytes used to build recipes."""

    path: str
    schema_version: str
    schedule_id: str
    file_sha256: str


@dataclass(frozen=True)
class RosterEventRecipe:
    """One deterministic truth-world roster event; no online identity is carried."""

    fraction_of_duration: float
    entity_kind: str
    action: str
    ordinal_start: int
    ordinal_count: int

    def __post_init__(self) -> None:
        fraction = float(self.fraction_of_duration)
        if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
            raise LearningSourceRecipeError("roster_event_fraction_invalid")
        if self.entity_kind not in {"intruder", "interceptor"}:
            raise LearningSourceRecipeError("roster_event_entity_kind_invalid")
        if self.action not in {"activate", "deactivate"}:
            raise LearningSourceRecipeError("roster_event_action_invalid")
        if int(self.ordinal_start) < 0 or int(self.ordinal_count) <= 0:
            raise LearningSourceRecipeError("roster_event_ordinal_invalid")


@dataclass(frozen=True)
class D3A1V3EpisodeRecipe:
    schema_version: str
    lineage: FrozenScheduleLineage
    entry_index: int
    episode_id: str
    cell_id: str
    scenario_family: str
    runtime_scenario: str
    seed: int
    split: str
    target_count: int
    resource_count: int
    duration_s: float
    minimum_observable_frames: int
    minimum_positive_frames: int
    minimum_negative_frames: int
    minimum_hard_negative_frames: int
    treatment_id: str | None
    roster_events: tuple[RosterEventRecipe, ...]

    def build_config(self, base: ScenarioConfig) -> ScenarioConfig:
        config = make_curriculum_scenario(
            self.runtime_scenario,
            scale=max(self.target_count, self.resource_count),
            target_count=self.target_count,
            resource_count=self.resource_count,
            seed=self.seed,
            duration_s=self.duration_s,
            base=base,
        )
        metadata = dict(config.metadata)
        metadata["learning_source_recipe"] = {
            "schema_version": self.schema_version,
            "module": "D3",
            "schedule_sha256": self.lineage.file_sha256,
            "entry_index": self.entry_index,
            "episode_id": self.episode_id,
            "cell_id": self.cell_id,
            "scenario_family": self.scenario_family,
            "split": self.split,
            "treatment_id": self.treatment_id,
            "roster_events": [
                {
                    "fraction_of_duration": item.fraction_of_duration,
                    "entity_kind": item.entity_kind,
                    "action": item.action,
                    "ordinal_start": item.ordinal_start,
                    "ordinal_count": item.ordinal_count,
                }
                for item in self.roster_events
            ],
            "permissions": _false_permissions(),
        }
        return replace(config, metadata=metadata)


@dataclass(frozen=True)
class D4A2V8EpisodeRecipe:
    schema_version: str
    lineage: FrozenScheduleLineage
    entry_index: int
    seed: int
    split: str
    topology_id: str
    region_count: int
    supply_demand_condition: str
    communication_condition: str
    requested_target_class: str
    requested_transfer_resource_count: int
    hard_negative_candidate_resource_count: int
    replicate: int
    target_count: int
    resource_count: int
    recon_count: int
    duration_s: float

    @property
    def episode_id(self) -> str:
        return f"d4-a2-v8-train-seed-{self.seed}"

    def build_config(self, base: ScenarioConfig) -> ScenarioConfig:
        scenario = (
            "communication_degraded"
            if self.communication_condition == "bounded_delay_and_loss"
            else "nominal"
        )
        config = make_curriculum_scenario(
            scenario,
            scale=max(self.target_count, self.resource_count),
            target_count=self.target_count,
            resource_count=self.resource_count,
            seed=self.seed,
            duration_s=self.duration_s,
            base=base,
        )
        metadata = dict(config.metadata)
        metadata.pop("communication_partition_schedule", None)
        if self.communication_condition == "partition_then_recovery":
            metadata["communication_partition_schedule"] = [
                {
                    "time_s": self.duration_s / 3.0,
                    "generation": 1,
                },
                {
                    "time_s": 2.0 * self.duration_s / 3.0,
                    "generation": 2,
                },
            ]
        metadata["learning_source_recipe"] = {
            "schema_version": self.schema_version,
            "module": "D4",
            "schedule_sha256": self.lineage.file_sha256,
            "entry_index": self.entry_index,
            "episode_id": self.episode_id,
            "split": self.split,
            "topology_id": self.topology_id,
            "region_count": self.region_count,
            "supply_demand_condition": self.supply_demand_condition,
            "communication_condition": self.communication_condition,
            "requested_target_class": self.requested_target_class,
            "requested_transfer_resource_count": (
                self.requested_transfer_resource_count
            ),
            "hard_negative_candidate_resource_count": (
                self.hard_negative_candidate_resource_count
            ),
            "replicate": self.replicate,
            "permissions": _false_permissions(),
        }
        return replace(
            config,
            recon_count=self.recon_count,
            region_count=self.region_count,
            region_policy_period_s=1.0,
            metadata=metadata,
        )


@dataclass(frozen=True)
class D5IntentWindowRecipe:
    window_id: str
    start_s: float
    end_s: float
    intent: str
    camera_role: str
    treatment_recipe: str
    required_controls: tuple[str, ...]
    minimum_unique_samples: int

    def __post_init__(self) -> None:
        if not self.window_id or not self.intent or not self.treatment_recipe:
            raise LearningSourceRecipeError("d5_intent_window_identity_missing")
        if self.camera_role not in {"interceptor", "recon"}:
            raise LearningSourceRecipeError("d5_intent_window_role_invalid")
        if not 0.0 <= float(self.start_s) < float(self.end_s):
            raise LearningSourceRecipeError("d5_intent_window_time_invalid")
        if int(self.minimum_unique_samples) <= 0:
            raise LearningSourceRecipeError("d5_intent_window_quota_invalid")
        if not self.required_controls or len(set(self.required_controls)) != len(
            self.required_controls
        ):
            raise LearningSourceRecipeError("d5_required_controls_invalid")


@dataclass(frozen=True)
class D5HardConfusionRecipe:
    family: str
    treatment_recipe: str
    window_ids: tuple[str, ...]
    required_controls: tuple[str, ...]
    minimum_unique_boundary_pairs: int

    def __post_init__(self) -> None:
        if not self.family or not self.treatment_recipe:
            raise LearningSourceRecipeError("d5_hard_confusion_identity_missing")
        if len(self.window_ids) < 2 or len(set(self.window_ids)) != len(
            self.window_ids
        ):
            raise LearningSourceRecipeError("d5_hard_confusion_windows_invalid")
        if int(self.minimum_unique_boundary_pairs) <= 0:
            raise LearningSourceRecipeError("d5_hard_confusion_quota_invalid")


@dataclass(frozen=True)
class D5A3V3EpisodeRecipe:
    schema_version: str
    lineage: FrozenScheduleLineage
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
    intent_windows: tuple[D5IntentWindowRecipe, ...]
    hard_confusion_assignments: tuple[D5HardConfusionRecipe, ...]
    minimum_unique_sample_quota: Mapping[str, Any]

    def build_config(self, base: ScenarioConfig) -> ScenarioConfig:
        config = make_curriculum_scenario(
            self.scenario_family,
            scale=self.scale,
            target_count=self.target_count,
            resource_count=self.resource_count,
            seed=self.seed,
            duration_s=self.duration_s,
            base=base,
        )
        metadata = dict(config.metadata)
        metadata["learning_source_recipe"] = {
            "schema_version": self.schema_version,
            "module": "D5",
            "schedule_sha256": self.lineage.file_sha256,
            "entry_index": self.entry_index,
            "episode_id": self.episode_id,
            "split": self.split,
            "allocation_id": self.allocation_id,
            "collection_profile": self.collection_profile,
            "camera_roles": list(self.camera_roles),
            "intent_windows": [
                {
                    "window_id": item.window_id,
                    "start_s": item.start_s,
                    "end_s": item.end_s,
                    "intent": item.intent,
                    "camera_role": item.camera_role,
                    "treatment_recipe": item.treatment_recipe,
                    "required_controls": list(item.required_controls),
                    "minimum_unique_samples": item.minimum_unique_samples,
                }
                for item in self.intent_windows
            ],
            "hard_confusion_assignments": [
                {
                    "family": item.family,
                    "treatment_recipe": item.treatment_recipe,
                    "window_ids": list(item.window_ids),
                    "required_controls": list(item.required_controls),
                    "minimum_unique_boundary_pairs": (
                        item.minimum_unique_boundary_pairs
                    ),
                }
                for item in self.hard_confusion_assignments
            ],
            "minimum_unique_sample_quota": _thaw(self.minimum_unique_sample_quota),
            "permissions": _false_permissions(),
        }
        return replace(config, recon_count=self.recon_count, metadata=metadata)


def load_d3_a1_v3_episode_recipes(
    path: str | Path,
    *,
    duration_s: float = DEFAULT_D3_DURATION_S,
) -> tuple[D3A1V3EpisodeRecipe, ...]:
    schedule_path, payload = _read_schedule(path)
    if payload.get("schema_version") != D3_A1_V3_SCHEDULE_SCHEMA_VERSION:
        raise LearningSourceRecipeError("d3_schedule_schema_unsupported")
    lineage = _lineage(
        schedule_path,
        payload,
        schema_field="schema_version",
        id_field="schedule_id",
    )
    episodes = _sequence(payload.get("episodes"), "d3_schedule_episodes")
    recipes: list[D3A1V3EpisodeRecipe] = []
    for index, raw_value in enumerate(episodes):
        raw = _mapping(raw_value, f"d3_episode_{index}")
        required = {
            "episode_id",
            "cell_id",
            "scenario_family",
            "seed",
            "split",
            "configured_target_count",
            "configured_resource_count",
            "minimum_observable_frames",
            "minimum_positive_frames",
            "minimum_negative_frames",
            "minimum_hard_negative_frames",
        }
        _require_exact_keys(raw, required, f"d3_episode_{index}")
        family = str(raw["scenario_family"])
        runtime_scenario = _D3_RUNTIME_SCENARIO.get(family)
        if runtime_scenario is None:
            raise LearningSourceRecipeError("d3_scenario_mapping_missing", family)
        recipe = D3A1V3EpisodeRecipe(
            schema_version=D3_A1_V3_RECIPE_SCHEMA_VERSION,
            lineage=lineage,
            entry_index=index,
            episode_id=_nonempty(raw["episode_id"], "d3_episode_id"),
            cell_id=_nonempty(raw["cell_id"], "d3_cell_id"),
            scenario_family=family,
            runtime_scenario=runtime_scenario,
            seed=_integer(raw["seed"], "d3_seed", minimum=0),
            split=_one_of(raw["split"], {"train", "validation", "test"}, "d3_split"),
            target_count=_integer(
                raw["configured_target_count"], "d3_target_count", minimum=1
            ),
            resource_count=_integer(
                raw["configured_resource_count"], "d3_resource_count", minimum=1
            ),
            duration_s=_positive_float(duration_s, "d3_duration_s"),
            minimum_observable_frames=_integer(
                raw["minimum_observable_frames"],
                "d3_minimum_observable_frames",
                minimum=1,
            ),
            minimum_positive_frames=_integer(
                raw["minimum_positive_frames"],
                "d3_minimum_positive_frames",
                minimum=1,
            ),
            minimum_negative_frames=_integer(
                raw["minimum_negative_frames"],
                "d3_minimum_negative_frames",
                minimum=1,
            ),
            minimum_hard_negative_frames=_integer(
                raw["minimum_hard_negative_frames"],
                "d3_minimum_hard_negative_frames",
                minimum=1,
            ),
            treatment_id=_D3_TREATMENT.get(family),
            roster_events=(
                _d3_dynamic_roster_events(
                    _integer(
                        raw["configured_target_count"],
                        "d3_target_count",
                        minimum=1,
                    ),
                    _integer(
                        raw["configured_resource_count"],
                        "d3_resource_count",
                        minimum=1,
                    ),
                )
                if family == "dynamic_add_drop"
                else ()
            ),
        )
        recipes.append(recipe)
    _require_unique((item.episode_id for item in recipes), "d3_episode_id_duplicate")
    _require_unique((item.seed for item in recipes), "d3_seed_duplicate")
    if len(recipes) != 300:
        raise LearningSourceRecipeError("d3_episode_count_mismatch")
    return tuple(recipes)


def load_d4_a2_v8_episode_recipes(
    path: str | Path,
    *,
    duration_s: float = DEFAULT_D4_DURATION_S,
) -> tuple[D4A2V8EpisodeRecipe, ...]:
    registry_path, payload = _read_schedule(path)
    if payload.get("schema") != D4_A2_V8_REGISTRY_SCHEMA_VERSION:
        raise LearningSourceRecipeError("d4_registry_schema_unsupported")
    lineage = _lineage(
        registry_path,
        payload,
        schema_field="schema",
        id_field="registry_id",
    )
    schedule = _sequence(payload.get("schedule"), "d4_registry_schedule")
    recipes: list[D4A2V8EpisodeRecipe] = []
    required = {
        "communication_condition",
        "hard_negative_candidate_resource_count",
        "region_count",
        "replicate",
        "requested_target_class",
        "requested_transfer_resource_count",
        "seed",
        "split",
        "supply_demand_condition",
        "topology_id",
    }
    for index, raw_value in enumerate(schedule):
        raw = _mapping(raw_value, f"d4_episode_{index}")
        _require_exact_keys(raw, required, f"d4_episode_{index}")
        region_count = _integer(raw["region_count"], "d4_region_count", minimum=1)
        recipe = D4A2V8EpisodeRecipe(
            schema_version=D4_A2_V8_RECIPE_SCHEMA_VERSION,
            lineage=lineage,
            entry_index=index,
            seed=_integer(raw["seed"], "d4_seed", minimum=0),
            split=_one_of(raw["split"], {"train"}, "d4_split"),
            topology_id=_one_of(
                raw["topology_id"],
                {
                    "directed_ring_8",
                    "directed_grid_3x3",
                    "directed_ring_12",
                    "directed_mesh_16",
                },
                "d4_topology_id",
            ),
            region_count=region_count,
            supply_demand_condition=_one_of(
                raw["supply_demand_condition"],
                {
                    "source_surplus_target_deficit",
                    "balanced_boundary",
                    "global_shortage_with_local_candidate_edge",
                },
                "d4_supply_demand_condition",
            ),
            communication_condition=_one_of(
                raw["communication_condition"],
                {"nominal", "bounded_delay_and_loss", "partition_then_recovery"},
                "d4_communication_condition",
            ),
            requested_target_class=_one_of(
                raw["requested_target_class"],
                {
                    "safe_forward_transfer",
                    "safe_reverse_transfer",
                    "hard_no_transfer_negative",
                },
                "d4_target_class",
            ),
            requested_transfer_resource_count=_integer(
                raw["requested_transfer_resource_count"],
                "d4_transfer_count",
                minimum=0,
            ),
            hard_negative_candidate_resource_count=_integer(
                raw["hard_negative_candidate_resource_count"],
                "d4_hard_negative_count",
                minimum=0,
            ),
            replicate=_integer(raw["replicate"], "d4_replicate", minimum=0),
            target_count=2 * region_count,
            resource_count=3 * region_count,
            recon_count=max(1, math.ceil(region_count / 4)),
            duration_s=_positive_float(duration_s, "d4_duration_s"),
        )
        recipes.append(recipe)
    _require_unique((item.seed for item in recipes), "d4_seed_duplicate")
    if len(recipes) != 324:
        raise LearningSourceRecipeError("d4_episode_count_mismatch")
    return tuple(recipes)


def load_d5_a3_v3_episode_recipes(
    path: str | Path,
) -> tuple[D5A3V3EpisodeRecipe, ...]:
    schedule_path, payload = _read_schedule(path)
    if payload.get("schema_version") != D5_A3_V3_SCHEDULE_SCHEMA_VERSION:
        raise LearningSourceRecipeError("d5_schedule_schema_unsupported")
    lineage = _lineage(
        schedule_path,
        payload,
        schema_field="schema_version",
        id_field="schedule_id",
    )
    entries = _sequence(payload.get("episode_entries"), "d5_episode_entries")
    recipes: list[D5A3V3EpisodeRecipe] = []
    required = {
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
    }
    for index, raw_value in enumerate(entries):
        raw = _mapping(raw_value, f"d5_episode_{index}")
        _require_exact_keys(raw, required, f"d5_episode_{index}")
        if _integer(raw["entry_index"], "d5_entry_index", minimum=0) != index:
            raise LearningSourceRecipeError("d5_entry_index_not_contiguous")
        controls = _mapping(raw["generation_controls"], "d5_generation_controls")
        if any(value is not False for value in controls.values()):
            raise LearningSourceRecipeError("d5_generation_control_not_false")
        windows = tuple(
            _parse_d5_window(item, entry_index=index)
            for item in _sequence(raw["intent_windows"], "d5_intent_windows")
        )
        if len(windows) != 4:
            raise LearningSourceRecipeError("d5_intent_window_count_mismatch")
        hard = tuple(
            _parse_d5_hard_confusion(item, entry_index=index)
            for item in _sequence(
                raw["hard_confusion_assignments"],
                "d5_hard_confusion_assignments",
            )
        )
        known_window_ids = {item.window_id for item in windows}
        if any(set(item.window_ids) - known_window_ids for item in hard):
            raise LearningSourceRecipeError("d5_hard_confusion_window_unknown")
        quota = _mapping(
            raw["minimum_unique_sample_quota"],
            "d5_minimum_unique_sample_quota",
        )
        if _integer(quota.get("total"), "d5_total_quota", minimum=1) != sum(
            item.minimum_unique_samples for item in windows
        ):
            raise LearningSourceRecipeError("d5_total_quota_mismatch")
        family = _one_of(
            raw["scenario_family"], set(AVAILABLE_SCENARIOS), "d5_scenario_family"
        )
        recipes.append(
            D5A3V3EpisodeRecipe(
                schema_version=D5_A3_V3_RECIPE_SCHEMA_VERSION,
                lineage=lineage,
                entry_index=index,
                split=_one_of(
                    raw["split"],
                    {"train", "validation", "future_held_out"},
                    "d5_split",
                ),
                allocation_id=_nonempty(raw["allocation_id"], "d5_allocation_id"),
                seed=_integer(raw["seed"], "d5_seed", minimum=0),
                episode_id=_nonempty(raw["episode_id"], "d5_episode_id"),
                scenario_family=family,
                scale=_integer(raw["scale"], "d5_scale", minimum=1),
                target_count=_integer(
                    raw["target_count"], "d5_target_count", minimum=1
                ),
                resource_count=_integer(
                    raw["resource_count"], "d5_resource_count", minimum=1
                ),
                recon_count=_integer(raw["recon_count"], "d5_recon_count", minimum=1),
                duration_s=_positive_float(raw["duration_s"], "d5_duration_s"),
                collection_profile=_one_of(
                    raw["collection_profile"],
                    {"balanced_action_role_v1"},
                    "d5_collection_profile",
                ),
                camera_roles=tuple(
                    _one_of(item, {"interceptor", "recon"}, "d5_camera_role")
                    for item in _sequence(raw["camera_roles"], "d5_camera_roles")
                ),
                intent_windows=windows,
                hard_confusion_assignments=hard,
                minimum_unique_sample_quota=_freeze(quota),
            )
        )
    _require_unique((item.episode_id for item in recipes), "d5_episode_id_duplicate")
    _require_unique((item.seed for item in recipes), "d5_seed_duplicate")
    if len(recipes) != 104:
        raise LearningSourceRecipeError("d5_episode_count_mismatch")
    return tuple(recipes)


def _parse_d5_window(
    value: Any,
    *,
    entry_index: int,
) -> D5IntentWindowRecipe:
    raw = _mapping(value, f"d5_window_entry_{entry_index}")
    _require_exact_keys(
        raw,
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
        f"d5_window_entry_{entry_index}",
    )
    return D5IntentWindowRecipe(
        window_id=_nonempty(raw["window_id"], "d5_window_id"),
        start_s=float(raw["start_s"]),
        end_s=float(raw["end_s"]),
        intent=_one_of(
            raw["intent"],
            {"observe_target", "search_sector", "hold", "reacquire"},
            "d5_intent",
        ),
        camera_role=_one_of(
            raw["camera_role"], {"interceptor", "recon"}, "d5_camera_role"
        ),
        treatment_recipe=_nonempty(
            raw["treatment_recipe"], "d5_treatment_recipe"
        ),
        required_controls=tuple(
            _nonempty(item, "d5_required_control")
            for item in _sequence(raw["required_controls"], "d5_required_controls")
        ),
        minimum_unique_samples=_integer(
            raw["minimum_unique_samples"],
            "d5_minimum_unique_samples",
            minimum=1,
        ),
    )


def _parse_d5_hard_confusion(
    value: Any,
    *,
    entry_index: int,
) -> D5HardConfusionRecipe:
    raw = _mapping(value, f"d5_hard_confusion_entry_{entry_index}")
    _require_exact_keys(
        raw,
        {
            "family",
            "treatment_recipe",
            "window_ids",
            "required_controls",
            "minimum_unique_boundary_pairs",
        },
        f"d5_hard_confusion_entry_{entry_index}",
    )
    return D5HardConfusionRecipe(
        family=_nonempty(raw["family"], "d5_hard_confusion_family"),
        treatment_recipe=_nonempty(
            raw["treatment_recipe"], "d5_hard_confusion_treatment"
        ),
        window_ids=tuple(
            _nonempty(item, "d5_hard_confusion_window")
            for item in _sequence(raw["window_ids"], "d5_hard_confusion_windows")
        ),
        required_controls=tuple(
            _nonempty(item, "d5_hard_confusion_control")
            for item in _sequence(raw["required_controls"], "d5_hard_confusion_controls")
        ),
        minimum_unique_boundary_pairs=_integer(
            raw["minimum_unique_boundary_pairs"],
            "d5_minimum_boundary_pairs",
            minimum=1,
        ),
    )


def _d3_dynamic_roster_events(
    target_count: int,
    resource_count: int,
) -> tuple[RosterEventRecipe, ...]:
    if target_count < 10 or resource_count < 8:
        raise LearningSourceRecipeError("d3_dynamic_roster_inventory_too_small")
    return (
        RosterEventRecipe(0.0, "intruder", "deactivate", target_count - 10, 10),
        RosterEventRecipe(0.25, "intruder", "activate", target_count - 10, 10),
        RosterEventRecipe(0.50, "intruder", "deactivate", 0, 10),
        RosterEventRecipe(0.625, "interceptor", "deactivate", 0, 8),
        RosterEventRecipe(0.75, "interceptor", "activate", 0, 8),
    )


def _read_schedule(path: str | Path) -> tuple[Path, Mapping[str, Any]]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise LearningSourceRecipeError("schedule_file_missing_or_unsafe", str(resolved))
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_raise_nonfinite(value)),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LearningSourceRecipeError("schedule_json_invalid", str(resolved)) from exc
    return resolved, _mapping(payload, "schedule")


def _lineage(
    path: Path,
    payload: Mapping[str, Any],
    *,
    schema_field: str,
    id_field: str,
) -> FrozenScheduleLineage:
    return FrozenScheduleLineage(
        path=str(path),
        schema_version=_nonempty(payload.get(schema_field), "schedule_schema"),
        schedule_id=_nonempty(payload.get(id_field), "schedule_id"),
        file_sha256=sha256(path.read_bytes()).hexdigest(),
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        raise LearningSourceRecipeError("mapping_required", name)
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise LearningSourceRecipeError("list_required", name)
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise LearningSourceRecipeError(
            "schedule_entry_fields_mismatch",
            f"{name}:missing={missing}:extra={extra}",
        )


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningSourceRecipeError("nonempty_string_required", name)
    return value.strip()


def _one_of(value: Any, choices: set[str], name: str) -> str:
    result = _nonempty(value, name)
    if result not in choices:
        raise LearningSourceRecipeError("unsupported_value", f"{name}={result}")
    return result


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LearningSourceRecipeError("integer_invalid", name)
    return value


def _positive_float(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise LearningSourceRecipeError("positive_float_required", name)
    return result


def _require_unique(values: Any, code: str) -> None:
    materialized = tuple(values)
    if len(set(materialized)) != len(materialized):
        raise LearningSourceRecipeError(code)


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            str(key): (
                _freeze(item)
                if isinstance(item, Mapping)
                else tuple(item)
                if isinstance(item, list)
                else item
            )
            for key, item in value.items()
        }
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _false_permissions() -> dict[str, bool]:
    return {
        "generation": False,
        "training": False,
        "validation": False,
        "test": False,
        "runtime": False,
        "assist": False,
        "assignment": False,
        "degradation": False,
        "coalition": False,
        "control": False,
        "physical": False,
        "global_track_id_create": False,
        "global_track_id_write": False,
    }


def _raise_nonfinite(value: str) -> None:
    raise LearningSourceRecipeError("nonfinite_json_constant", value)


__all__ = [
    "D3A1V3EpisodeRecipe",
    "D3_A1_V3_RECIPE_SCHEMA_VERSION",
    "D4A2V8EpisodeRecipe",
    "D4_A2_V8_RECIPE_SCHEMA_VERSION",
    "D5A3V3EpisodeRecipe",
    "D5HardConfusionRecipe",
    "D5IntentWindowRecipe",
    "D5_A3_V3_RECIPE_SCHEMA_VERSION",
    "FrozenScheduleLineage",
    "LearningSourceRecipeError",
    "RosterEventRecipe",
    "load_d3_a1_v3_episode_recipes",
    "load_d4_a2_v8_episode_recipes",
    "load_d5_a3_v3_episode_recipes",
]
