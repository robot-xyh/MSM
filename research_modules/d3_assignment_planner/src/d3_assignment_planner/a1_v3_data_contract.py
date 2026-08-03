"""Fail-closed A1 v3 development-source data contracts.

The contracts in this module authorize no planner, training, runtime, or
physical action.  They let main describe a future generation batch and let D3
or D6 validate the resulting anonymous diagnostics without touching the
frozen v2 bundle or formal holdout.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any


A1_V3_DATA_CONTRACT_SCHEMA_V1 = "d3_a1_source_independent_v3_data_contract_v1"
A1_V3_ONLINE_FRAME_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_online_frame_v1"
)
A1_V3_OFFLINE_LABEL_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_offline_label_v1"
)
A1_V3_TRAINING_FEATURE_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_training_features_v1"
)
A1_V3_TRAINING_TARGET_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_training_target_v1"
)
A1_V3_MAIN_SEED_REGISTRY_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_main_seed_registry_v1"
)
A1_V3_GENERATION_SCHEDULE_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_generation_schedule_v1"
)
A1_V3_DATASET_MANIFEST_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_dataset_manifest_v1"
)
A1_V3_SPLIT_POLICY_V1 = (
    "d3_a1_source_independent_v3_whole_seed_60_20_20_v1"
)
A1_V3_READINESS_REPORT_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_readiness_report_v1"
)
A1_V3_REQUEST_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_development_data_request_v1"
)
A1_V3_SOURCE_GENERATION_REQUEST_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_source_generation_request_readiness_v1"
)
A1_V3_SOURCE_GENERATION_REQUEST_ID = (
    "d3-a1-v3-source-generation-request-20260801-v1"
)
A1_V3_SOURCE_GENERATION_REQUEST_LOGICAL_PATH = (
    "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_source_generation_request_readiness_v1.json"
)
A1_V3_EXCLUSION_REGISTRY_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_seed_exclusion_registry_v1"
)
A1_V3_GENERATOR_CONFIG_SCHEMA_V1 = (
    "d3_a1_source_independent_v3_generator_config_v1"
)
A1_V3_GLOBAL_SEED_REGISTRY_SCHEMA_V1 = "scalable3d-global-seed-registry-v1"
A1_V3_GLOBAL_SEED_POLICY_V1 = "scalable3d-seed-allocation-policy-v1"
A1_V3_GLOBAL_REGISTRY_ID = (
    "scalable3d-learning-source-allocation-20260801-v1"
)
A1_V3_GLOBAL_REGISTRY_CONTENT_SHA256 = (
    "982f34673cdf944c8d8799d2939361ab002130c0cddf8238a83c6e46e299530c"
)
A1_V3_GLOBAL_REGISTRY_FILE_SHA256 = (
    "98caa683ceae61b89580afc44545875c4345fa1b92bfc05cdc91e232c9f7f988"
)
A1_V3_GLOBAL_ALLOCATION_ID = "d3-a1-v3-all-splits"
A1_V3_GLOBAL_ALLOCATION_CANDIDATE = "d3-a1-v3"
A1_V3_GLOBAL_ALLOCATION_SPLIT_POLICY = "whole_seed_60_20_20_v1"
A1_V3_GENERATOR_CONFIG_ID = "d3-a1-v3-generator-config-20260801-v1"
A1_V3_MAIN_REGISTRY_ID = "d3-a1-v3-main-allocation-registry-20260801-v1"
A1_V3_GENERATION_SCHEDULE_ID = "d3-a1-v3-generation-schedule-20260801-v1"
A1_V3_MAIN_REGISTRY_STATUS = "allocation_bound_plan_only"
A1_V3_GENERATOR_CONFIG_STATUS = "frozen_plan_only_not_generated"
A1_V3_NEAR_TIE_BOUNDARY_ID_V1 = "d3-a1-v3-rule-cost-near-tie-boundary-v1"
A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP = 0.10
A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP = 0.002
A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR = 1.0
A1_V3_NEAR_TIE_REASON_MET = "near_tie_rule_cost_boundary_met_v1"
A1_V3_NEAR_TIE_REASON_NOT_MET = "near_tie_rule_cost_boundary_not_met_v1"
A1_V3_ACTION_CHANGE_TYPES = (
    "keep_exact_r0",
    "assignment_coverage_contraction",
    "assignment_coverage_recovery",
    "single_target_rebind_with_resource_release",
    "two_target_pair_swap",
    "multi_target_cycle",
    "target_appearance_assignment",
    "target_loss_release",
    "resource_failure_reassignment",
    "resource_recovery_reassignment",
    "m_to_n_demand_increase",
    "m_to_n_demand_decrease",
    "primary_reserve_role_change",
)

A1_V3_MANIFEST_FILENAME = "dataset_manifest.json"
A1_V3_ONLINE_FRAMES_FILENAME = "online_frames.jsonl"
A1_V3_OFFLINE_LABELS_FILENAME = "offline_labels.jsonl"
A1_V3_SPLITS = ("train", "validation", "test")
A1_V3_SPLIT_PERCENT = {"train": 60, "validation": 20, "test": 20}
A1_V3_SPLIT_SEED_COUNTS = {"train": 180, "validation": 60, "test": 60}
A1_V3_CELL_SPLIT_SEED_COUNTS = {"train": 12, "validation": 4, "test": 4}
A1_V3_PERMISSION_FIELDS = (
    "generation",
    "training",
    "optimizer",
    "checkpoint_selection",
    "normalization_refit",
    "threshold_adjustment",
    "runtime",
    "assist",
    "authority",
    "assignment",
    "plan",
    "control",
    "physical",
    "formal_admission",
    "production_admission",
)
A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS = (
    "source_generation_request",
    "source_generation",
    "episode_generation",
    "dataset_artifact_write",
    "validation_payload_read",
    "formal_seed_payload_read",
    "training",
    "optimizer",
    "checkpoint_selection",
    "normalization_refit",
    "threshold_adjustment",
    "shadow",
    "assist",
    "authority",
    "assignment",
    "plan",
    "runtime",
    "physical",
    "control",
    "formal_admission",
    "production_admission",
)
A1_V3_EXCLUSION_PERMISSION_FIELDS = tuple(
    name
    for name in A1_V3_PERMISSION_FIELDS
    if name not in {"normalization_refit", "authority"}
)
A1_V3_OBSERVABILITY_REQUIREMENTS = (
    "anonymous_candidate_edge_indices_or_content_sha256",
    "teacher_edges_in_candidate_mask_count_and_boolean",
    "per_edge_model_residual_rank_before_hungarian",
    "anonymous_action_mask_shape_count_and_content_sha256",
    "anonymous_target_demand_slot_vector_or_content_sha256",
    "teacher_candidate_and_effective_selected_edges",
    "pre_projection_and_post_projection_reason_codes",
    "observed_anonymous_target_and_resource_counts",
    "source_split_scenario_scale_seed_episode_frame_and_dual_timestamps",
    "all_permissions_false_and_online_truth_use_zero",
)

MODULE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
DEFAULT_A1_V3_REQUEST_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_development_data_request_v1.json"
)
DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_seed_exclusion_registry_v1.json"
)
DEFAULT_A1_V3_DATA_CONTRACT_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_data_contract_v1.json"
)
DEFAULT_A1_V3_GENERATOR_CONFIG_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generator_config_v1.json"
)
DEFAULT_A1_V3_MAIN_SEED_REGISTRY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_main_allocation_registry_v1.json"
)
DEFAULT_A1_V3_GENERATION_SCHEDULE_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generation_schedule_v1.json"
)
DEFAULT_A1_V3_GLOBAL_SEED_REGISTRY_PATH = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)
DEFAULT_A1_V3_SOURCE_GENERATION_REQUEST_PATH = (
    MODULE_ROOT
    / "configs/"
    "a1_source_independent_v3_source_generation_request_readiness_v1.json"
)
DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_sidecar_classification_policy_v1.json"
)

_REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_LOWER_HEX = frozenset("0123456789abcdef")
_ONLINE_FORBIDDEN_KEY_MARKERS = (
    "truth",
    "actor",
    "object_id",
    "object_name",
    "global_track",
    "globaltrack",
    "track_id",
    "target_id",
    "resource_id",
    "vehicle_id",
)
_ONLINE_FORBIDDEN_VALUE_PREFIXES = (
    "actor_",
    "object_",
    "truth_",
    "gt3d-",
    "global-track-",
)


class A1V3DataContractError(ValueError):
    """A fail-closed contract error with a stable low-level audit code."""

    def __init__(self, code: str, message: str = "") -> None:
        detail = str(message).strip()
        super().__init__(f"{code}: {detail}" if detail else str(code))
        self.code = str(code)


@dataclass(frozen=True)
class A1V3FrameSource:
    split: str
    scenario_family: str
    cell_id: str
    seed: int
    episode_id: str
    frame_index: int
    measurement_timestamp_s: float
    arrival_timestamp_s: float
    configured_target_count: int
    configured_resource_count: int

    @property
    def frame_key(self) -> tuple[int, str, int]:
        return (self.seed, self.episode_id, self.frame_index)

    @property
    def episode_key(self) -> tuple[int, str]:
        return (self.seed, self.episode_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "split": self.split,
            "scenario_family": self.scenario_family,
            "cell_id": self.cell_id,
            "seed": self.seed,
            "episode_id": self.episode_id,
            "frame_index": self.frame_index,
            "measurement_timestamp_s": self.measurement_timestamp_s,
            "arrival_timestamp_s": self.arrival_timestamp_s,
            "configured_target_count": self.configured_target_count,
            "configured_resource_count": self.configured_resource_count,
        }


@dataclass(frozen=True)
class A1V3EdgeResidualRank:
    edge: tuple[int, int]
    residual: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge": [self.edge[0], self.edge[1]],
            "residual": self.residual,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class A1V3NearTieTargetMargin:
    target_index: int
    best_edge: tuple[int, int]
    second_edge: tuple[int, int]
    best_rule_cost: float
    second_rule_cost: float
    absolute_gap: float
    relative_gap: float
    qualifies: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_index": self.target_index,
            "best_edge": list(self.best_edge),
            "second_edge": list(self.second_edge),
            "best_rule_cost": self.best_rule_cost,
            "second_rule_cost": self.second_rule_cost,
            "absolute_gap": self.absolute_gap,
            "relative_gap": self.relative_gap,
            "qualifies": self.qualifies,
        }


@dataclass(frozen=True)
class A1V3OnlineFrame:
    """Identity-free online diagnostic frame used by the learning path."""

    source: A1V3FrameSource
    observed_target_count: int
    observed_resource_count: int
    candidate_edges: tuple[tuple[int, int], ...]
    candidate_edges_sha256: str
    teacher_edges: tuple[tuple[int, int], ...]
    candidate_selected_edges: tuple[tuple[int, int], ...]
    effective_selected_edges: tuple[tuple[int, int], ...]
    teacher_edge_count: int
    teacher_edges_in_candidate_mask_count: int
    all_teacher_edges_in_candidate_mask: bool
    residual_ranking: tuple[A1V3EdgeResidualRank, ...]
    action_mask_shape: tuple[int, int]
    action_mask_true_count: int
    action_mask_sha256: str
    candidate_edge_rule_costs: tuple[float, ...]
    candidate_edge_rule_costs_sha256: str
    near_tie_target_margins: tuple[A1V3NearTieTargetMargin, ...]
    near_tie_qualifying_target_count: int
    near_tie_reason_code: str
    target_demand_slots: tuple[int, ...]
    target_demand_slots_sha256: str
    pre_projection_reason_codes: tuple[str, ...]
    post_projection_reason_codes: tuple[str, ...]

    @property
    def frame_key(self) -> tuple[int, str, int]:
        return self.source.frame_key

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": A1_V3_ONLINE_FRAME_SCHEMA_V1,
            "record_kind": "online_identity_free_diagnostic_frame",
            "source": self.source.to_dict(),
            "observed_scale": {
                "anonymous_target_count": self.observed_target_count,
                "anonymous_resource_count": self.observed_resource_count,
            },
            "candidate_edge_indices": [list(edge) for edge in self.candidate_edges],
            "candidate_edge_indices_sha256": self.candidate_edges_sha256,
            "teacher_mask_observability": {
                "teacher_edge_count": self.teacher_edge_count,
                "teacher_edges_in_candidate_mask_count": (
                    self.teacher_edges_in_candidate_mask_count
                ),
                "all_teacher_edges_in_candidate_mask": (
                    self.all_teacher_edges_in_candidate_mask
                ),
            },
            "model_residual_ranking": {
                "rank_direction": "ascending_cost_residual_then_edge",
                "items": [item.to_dict() for item in self.residual_ranking],
            },
            "action_mask": {
                "shape": list(self.action_mask_shape),
                "true_count": self.action_mask_true_count,
                "content_sha256": self.action_mask_sha256,
            },
            "rule_cost_near_tie": {
                "boundary_id": A1_V3_NEAR_TIE_BOUNDARY_ID_V1,
                "maximum_absolute_gap": A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP,
                "maximum_relative_gap": A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP,
                "relative_denominator_floor": (
                    A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR
                ),
                "qualification_logic": "absolute_and_relative",
                "candidate_edge_costs": [
                    {
                        "edge": list(edge),
                        "rule_cost": cost,
                    }
                    for edge, cost in zip(
                        self.candidate_edges,
                        self.candidate_edge_rule_costs,
                        strict=True,
                    )
                ],
                "candidate_edge_costs_sha256": (
                    self.candidate_edge_rule_costs_sha256
                ),
                "evaluated_target_count": len(self.near_tie_target_margins),
                "qualifying_target_count": self.near_tie_qualifying_target_count,
                "target_margins": [
                    item.to_dict() for item in self.near_tie_target_margins
                ],
                "reason_code": self.near_tie_reason_code,
            },
            "anonymous_target_demand_slots": list(self.target_demand_slots),
            "target_demand_slots_sha256": self.target_demand_slots_sha256,
            "selected_edges": {
                "teacher": [list(edge) for edge in self.teacher_edges],
                "candidate_pre_projection": [
                    list(edge) for edge in self.candidate_selected_edges
                ],
                "effective_post_projection": [
                    list(edge) for edge in self.effective_selected_edges
                ],
            },
            "projection": {
                "pre_projection_reason_codes": list(
                    self.pre_projection_reason_codes
                ),
                "post_projection_reason_codes": list(
                    self.post_projection_reason_codes
                ),
            },
            "online_truth_use_count": 0,
            "center_identity_ownership": {
                "owner": "center",
                "learning_create_allowed": False,
                "learning_rewrite_allowed": False,
            },
            "permissions": _false_permissions(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A1V3OnlineFrame":
        payload = _mapping(value, "online_frame")
        _reject_online_identity(payload)
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "record_kind",
                "source",
                "observed_scale",
                "candidate_edge_indices",
                "candidate_edge_indices_sha256",
                "teacher_mask_observability",
                "model_residual_ranking",
                "action_mask",
                "rule_cost_near_tie",
                "anonymous_target_demand_slots",
                "target_demand_slots_sha256",
                "selected_edges",
                "projection",
                "online_truth_use_count",
                "center_identity_ownership",
                "permissions",
            },
            "online_frame_fields_mismatch",
        )
        if payload["schema_version"] != A1_V3_ONLINE_FRAME_SCHEMA_V1:
            _fail("online_frame_schema_mismatch")
        if payload["record_kind"] != "online_identity_free_diagnostic_frame":
            _fail("online_frame_kind_mismatch")

        source_raw = _mapping(payload["source"], "online_frame.source")
        _require_exact_keys(
            source_raw,
            {
                "split",
                "scenario_family",
                "cell_id",
                "seed",
                "episode_id",
                "frame_index",
                "measurement_timestamp_s",
                "arrival_timestamp_s",
                "configured_target_count",
                "configured_resource_count",
            },
            "online_source_fields_mismatch",
        )
        split = _choice(source_raw["split"], A1_V3_SPLITS, "source.split")
        scenario_family = _nonempty_string(
            source_raw["scenario_family"], "source.scenario_family"
        )
        cell_id = _nonempty_string(source_raw["cell_id"], "source.cell_id")
        seed = _nonnegative_integer(source_raw["seed"], "source.seed")
        episode_id = _nonempty_string(source_raw["episode_id"], "source.episode_id")
        frame_index = _nonnegative_integer(
            source_raw["frame_index"], "source.frame_index"
        )
        measurement_timestamp = _finite_number(
            source_raw["measurement_timestamp_s"], "source.measurement_timestamp_s"
        )
        arrival_timestamp = _finite_number(
            source_raw["arrival_timestamp_s"], "source.arrival_timestamp_s"
        )
        if arrival_timestamp < measurement_timestamp:
            _fail(
                "dual_timestamp_order_invalid",
                "arrival_timestamp_s precedes measurement_timestamp_s",
            )
        configured_target_count = _positive_integer(
            source_raw["configured_target_count"], "source.configured_target_count"
        )
        configured_resource_count = _positive_integer(
            source_raw["configured_resource_count"],
            "source.configured_resource_count",
        )
        source = A1V3FrameSource(
            split=split,
            scenario_family=scenario_family,
            cell_id=cell_id,
            seed=seed,
            episode_id=episode_id,
            frame_index=frame_index,
            measurement_timestamp_s=measurement_timestamp,
            arrival_timestamp_s=arrival_timestamp,
            configured_target_count=configured_target_count,
            configured_resource_count=configured_resource_count,
        )

        scale = _mapping(payload["observed_scale"], "online_frame.observed_scale")
        _require_exact_keys(
            scale,
            {"anonymous_target_count", "anonymous_resource_count"},
            "observed_scale_fields_mismatch",
        )
        target_count = _nonnegative_integer(
            scale["anonymous_target_count"], "anonymous_target_count"
        )
        resource_count = _nonnegative_integer(
            scale["anonymous_resource_count"], "anonymous_resource_count"
        )

        candidate_edges = _edge_sequence(
            payload["candidate_edge_indices"],
            "candidate_edge_indices",
            target_count=target_count,
            resource_count=resource_count,
        )
        candidate_sha = _sha256_value(
            payload["candidate_edge_indices_sha256"],
            "candidate_edge_indices_sha256",
        )
        if canonical_json_sha256([list(edge) for edge in candidate_edges]) != candidate_sha:
            _fail("candidate_edge_sha256_mismatch")

        selected = _mapping(payload["selected_edges"], "online_frame.selected_edges")
        _require_exact_keys(
            selected,
            {"teacher", "candidate_pre_projection", "effective_post_projection"},
            "selected_edge_fields_mismatch",
        )
        teacher_edges = _edge_sequence(
            selected["teacher"],
            "selected_edges.teacher",
            target_count=target_count,
            resource_count=resource_count,
        )
        candidate_selected = _edge_sequence(
            selected["candidate_pre_projection"],
            "selected_edges.candidate_pre_projection",
            target_count=target_count,
            resource_count=resource_count,
        )
        effective_selected = _edge_sequence(
            selected["effective_post_projection"],
            "selected_edges.effective_post_projection",
            target_count=target_count,
            resource_count=resource_count,
        )
        candidate_set = set(candidate_edges)
        if not set(candidate_selected).issubset(candidate_set):
            _fail("candidate_selected_edge_outside_mask")
        if not set(effective_selected).issubset(candidate_set):
            _fail("effective_selected_edge_outside_mask")

        teacher_mask = _mapping(
            payload["teacher_mask_observability"],
            "online_frame.teacher_mask_observability",
        )
        _require_exact_keys(
            teacher_mask,
            {
                "teacher_edge_count",
                "teacher_edges_in_candidate_mask_count",
                "all_teacher_edges_in_candidate_mask",
            },
            "teacher_mask_fields_mismatch",
        )
        teacher_edge_count = _nonnegative_integer(
            teacher_mask["teacher_edge_count"], "teacher_edge_count"
        )
        teacher_in_mask_count = _nonnegative_integer(
            teacher_mask["teacher_edges_in_candidate_mask_count"],
            "teacher_edges_in_candidate_mask_count",
        )
        teacher_all_in_mask = _boolean(
            teacher_mask["all_teacher_edges_in_candidate_mask"],
            "all_teacher_edges_in_candidate_mask",
        )
        actual_teacher_in_mask = len(set(teacher_edges) & candidate_set)
        if teacher_edge_count != len(teacher_edges):
            _fail("teacher_edge_count_mismatch")
        if teacher_in_mask_count != actual_teacher_in_mask:
            _fail("teacher_mask_count_mismatch")
        if teacher_all_in_mask != (actual_teacher_in_mask == len(teacher_edges)):
            _fail("teacher_mask_boolean_mismatch")

        ranking_raw = _mapping(
            payload["model_residual_ranking"], "online_frame.model_residual_ranking"
        )
        _require_exact_keys(
            ranking_raw,
            {"rank_direction", "items"},
            "residual_ranking_fields_mismatch",
        )
        if ranking_raw["rank_direction"] != "ascending_cost_residual_then_edge":
            _fail("residual_rank_direction_mismatch")
        items_raw = _list(ranking_raw["items"], "model_residual_ranking.items")
        ranking: list[A1V3EdgeResidualRank] = []
        for index, raw_item in enumerate(items_raw):
            item = _mapping(raw_item, f"model_residual_ranking.items[{index}]")
            _require_exact_keys(
                item,
                {"edge", "residual", "rank"},
                "residual_rank_item_fields_mismatch",
            )
            edge = _edge(
                item["edge"],
                f"model_residual_ranking.items[{index}].edge",
                target_count=target_count,
                resource_count=resource_count,
            )
            ranking.append(
                A1V3EdgeResidualRank(
                    edge=edge,
                    residual=_finite_number(
                        item["residual"],
                        f"model_residual_ranking.items[{index}].residual",
                    ),
                    rank=_positive_integer(
                        item["rank"],
                        f"model_residual_ranking.items[{index}].rank",
                    ),
                )
            )
        if tuple(item.edge for item in ranking) != candidate_edges:
            _fail("residual_rank_candidate_edge_mismatch")
        expected_ranked = sorted(
            ranking, key=lambda item: (item.residual, item.edge[0], item.edge[1])
        )
        if any(item.rank != index for index, item in enumerate(expected_ranked, start=1)):
            _fail("residual_rank_order_mismatch")

        action_mask = _mapping(payload["action_mask"], "online_frame.action_mask")
        _require_exact_keys(
            action_mask,
            {"shape", "true_count", "content_sha256"},
            "action_mask_fields_mismatch",
        )
        shape_values = _list(action_mask["shape"], "action_mask.shape")
        if len(shape_values) != 2:
            _fail("action_mask_shape_invalid")
        shape = (
            _nonnegative_integer(shape_values[0], "action_mask.shape[0]"),
            _nonnegative_integer(shape_values[1], "action_mask.shape[1]"),
        )
        if shape != (target_count, resource_count):
            _fail("action_mask_shape_count_mismatch")
        true_count = _nonnegative_integer(
            action_mask["true_count"], "action_mask.true_count"
        )
        if true_count != len(candidate_edges):
            _fail("action_mask_true_count_mismatch")
        action_sha = _sha256_value(
            action_mask["content_sha256"], "action_mask.content_sha256"
        )
        expected_action_sha = action_mask_content_sha256(shape, candidate_edges)
        if action_sha != expected_action_sha:
            _fail("action_mask_sha256_mismatch")

        near_tie = _mapping(
            payload["rule_cost_near_tie"], "online_frame.rule_cost_near_tie"
        )
        _require_exact_keys(
            near_tie,
            {
                "boundary_id",
                "maximum_absolute_gap",
                "maximum_relative_gap",
                "relative_denominator_floor",
                "qualification_logic",
                "candidate_edge_costs",
                "candidate_edge_costs_sha256",
                "evaluated_target_count",
                "qualifying_target_count",
                "target_margins",
                "reason_code",
            },
            "near_tie_fields_mismatch",
        )
        if (
            near_tie["boundary_id"] != A1_V3_NEAR_TIE_BOUNDARY_ID_V1
            or _finite_number(
                near_tie["maximum_absolute_gap"], "near_tie.maximum_absolute_gap"
            )
            != A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP
            or _finite_number(
                near_tie["maximum_relative_gap"], "near_tie.maximum_relative_gap"
            )
            != A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP
            or _finite_number(
                near_tie["relative_denominator_floor"],
                "near_tie.relative_denominator_floor",
            )
            != A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR
            or near_tie["qualification_logic"] != "absolute_and_relative"
        ):
            _fail("near_tie_boundary_mismatch")
        raw_edge_costs = _list(
            near_tie["candidate_edge_costs"], "near_tie.candidate_edge_costs"
        )
        parsed_cost_edges: list[tuple[int, int]] = []
        candidate_edge_rule_costs: list[float] = []
        for index, raw_item in enumerate(raw_edge_costs):
            item = _mapping(raw_item, f"near_tie.candidate_edge_costs[{index}]")
            _require_exact_keys(
                item,
                {"edge", "rule_cost"},
                "near_tie_candidate_edge_cost_fields_mismatch",
            )
            parsed_cost_edges.append(
                _edge(
                    item["edge"],
                    f"near_tie.candidate_edge_costs[{index}].edge",
                    target_count=target_count,
                    resource_count=resource_count,
                )
            )
            candidate_edge_rule_costs.append(
                _finite_number(
                    item["rule_cost"],
                    f"near_tie.candidate_edge_costs[{index}].rule_cost",
                )
            )
        if tuple(parsed_cost_edges) != candidate_edges:
            _fail("near_tie_candidate_edge_cost_inventory_mismatch")
        edge_cost_payload = [
            {"edge": list(edge), "rule_cost": cost}
            for edge, cost in zip(
                candidate_edges, candidate_edge_rule_costs, strict=True
            )
        ]
        edge_cost_sha = _sha256_value(
            near_tie["candidate_edge_costs_sha256"],
            "near_tie.candidate_edge_costs_sha256",
        )
        if canonical_json_sha256(edge_cost_payload) != edge_cost_sha:
            _fail("near_tie_candidate_edge_cost_sha256_mismatch")

        expected_margins = compute_a1_v3_near_tie_target_margins(
            candidate_edges,
            tuple(candidate_edge_rule_costs),
            target_count=target_count,
        )
        raw_margins = _list(near_tie["target_margins"], "near_tie.target_margins")
        parsed_margins: list[A1V3NearTieTargetMargin] = []
        for index, raw_item in enumerate(raw_margins):
            item = _mapping(raw_item, f"near_tie.target_margins[{index}]")
            _require_exact_keys(
                item,
                {
                    "target_index",
                    "best_edge",
                    "second_edge",
                    "best_rule_cost",
                    "second_rule_cost",
                    "absolute_gap",
                    "relative_gap",
                    "qualifies",
                },
                "near_tie_target_margin_fields_mismatch",
            )
            parsed_margins.append(
                A1V3NearTieTargetMargin(
                    target_index=_nonnegative_integer(
                        item["target_index"],
                        f"near_tie.target_margins[{index}].target_index",
                    ),
                    best_edge=_edge(
                        item["best_edge"],
                        f"near_tie.target_margins[{index}].best_edge",
                        target_count=target_count,
                        resource_count=resource_count,
                    ),
                    second_edge=_edge(
                        item["second_edge"],
                        f"near_tie.target_margins[{index}].second_edge",
                        target_count=target_count,
                        resource_count=resource_count,
                    ),
                    best_rule_cost=_finite_number(
                        item["best_rule_cost"],
                        f"near_tie.target_margins[{index}].best_rule_cost",
                    ),
                    second_rule_cost=_finite_number(
                        item["second_rule_cost"],
                        f"near_tie.target_margins[{index}].second_rule_cost",
                    ),
                    absolute_gap=_finite_number(
                        item["absolute_gap"],
                        f"near_tie.target_margins[{index}].absolute_gap",
                    ),
                    relative_gap=_finite_number(
                        item["relative_gap"],
                        f"near_tie.target_margins[{index}].relative_gap",
                    ),
                    qualifies=_boolean(
                        item["qualifies"],
                        f"near_tie.target_margins[{index}].qualifies",
                    ),
                )
            )
        if tuple(parsed_margins) != expected_margins:
            _fail("near_tie_target_margin_recomputation_mismatch")
        evaluated_target_count = _nonnegative_integer(
            near_tie["evaluated_target_count"], "near_tie.evaluated_target_count"
        )
        qualifying_target_count = _nonnegative_integer(
            near_tie["qualifying_target_count"],
            "near_tie.qualifying_target_count",
        )
        actual_qualifying_count = sum(item.qualifies for item in expected_margins)
        if evaluated_target_count != len(expected_margins):
            _fail("near_tie_evaluated_target_count_mismatch")
        if qualifying_target_count != actual_qualifying_count:
            _fail("near_tie_qualifying_target_count_mismatch")
        expected_reason = (
            A1_V3_NEAR_TIE_REASON_MET
            if actual_qualifying_count > 0
            else A1_V3_NEAR_TIE_REASON_NOT_MET
        )
        if near_tie["reason_code"] != expected_reason:
            _fail("near_tie_reason_code_mismatch")

        demand_raw = _list(
            payload["anonymous_target_demand_slots"],
            "anonymous_target_demand_slots",
        )
        demand_slots = tuple(
            _nonnegative_integer(value, f"anonymous_target_demand_slots[{index}]")
            for index, value in enumerate(demand_raw)
        )
        if len(demand_slots) != target_count:
            _fail("target_demand_slot_count_mismatch")
        demand_sha = _sha256_value(
            payload["target_demand_slots_sha256"],
            "target_demand_slots_sha256",
        )
        if canonical_json_sha256(list(demand_slots)) != demand_sha:
            _fail("target_demand_slot_sha256_mismatch")
        _validate_complete_selected_edges(
            teacher_edges,
            demand_slots,
            "teacher",
        )
        _validate_complete_selected_edges(
            effective_selected,
            demand_slots,
            "effective",
        )

        projection = _mapping(payload["projection"], "online_frame.projection")
        _require_exact_keys(
            projection,
            {"pre_projection_reason_codes", "post_projection_reason_codes"},
            "projection_fields_mismatch",
        )
        pre_reasons = _reason_codes(
            projection["pre_projection_reason_codes"],
            "pre_projection_reason_codes",
        )
        post_reasons = _reason_codes(
            projection["post_projection_reason_codes"],
            "post_projection_reason_codes",
        )
        if _nonnegative_integer(
            payload["online_truth_use_count"], "online_truth_use_count"
        ) != 0:
            _fail("online_truth_use_nonzero")
        ownership = _mapping(
            payload["center_identity_ownership"],
            "online_frame.center_identity_ownership",
        )
        if ownership != {
            "owner": "center",
            "learning_create_allowed": False,
            "learning_rewrite_allowed": False,
        }:
            _fail("center_identity_ownership_invalid")
        _validate_permissions(payload["permissions"], "online_frame.permissions")

        return cls(
            source=source,
            observed_target_count=target_count,
            observed_resource_count=resource_count,
            candidate_edges=candidate_edges,
            candidate_edges_sha256=candidate_sha,
            teacher_edges=teacher_edges,
            candidate_selected_edges=candidate_selected,
            effective_selected_edges=effective_selected,
            teacher_edge_count=teacher_edge_count,
            teacher_edges_in_candidate_mask_count=teacher_in_mask_count,
            all_teacher_edges_in_candidate_mask=teacher_all_in_mask,
            residual_ranking=tuple(ranking),
            action_mask_shape=shape,
            action_mask_true_count=true_count,
            action_mask_sha256=action_sha,
            candidate_edge_rule_costs=tuple(candidate_edge_rule_costs),
            candidate_edge_rule_costs_sha256=edge_cost_sha,
            near_tie_target_margins=expected_margins,
            near_tie_qualifying_target_count=actual_qualifying_count,
            near_tie_reason_code=expected_reason,
            target_demand_slots=demand_slots,
            target_demand_slots_sha256=demand_sha,
            pre_projection_reason_codes=pre_reasons,
            post_projection_reason_codes=post_reasons,
        )

    @classmethod
    def from_json_line(cls, line: str | bytes) -> "A1V3OnlineFrame":
        return cls.from_dict(_parse_json_object(line, "online_frame_json"))


@dataclass(frozen=True)
class A1V3OfflineLabel:
    """Offline-only classification and D6 identity audit sidecar."""

    split: str
    cell_id: str
    seed: int
    episode_id: str
    frame_index: int
    online_payload_sha256: str
    frame_class: str
    hard_negative: bool
    action_change_type: str
    hard_negative_type: str | None
    truth_target_labels: tuple[str, ...]
    actor_labels: tuple[str, ...]
    object_labels: tuple[str, ...]
    center_global_track_labels: tuple[str, ...]

    @property
    def frame_key(self) -> tuple[int, str, int]:
        return (self.seed, self.episode_id, self.frame_index)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
            "record_kind": "offline_d6_audit_label",
            "source_ref": {
                "split": self.split,
                "cell_id": self.cell_id,
                "seed": self.seed,
                "episode_id": self.episode_id,
                "frame_index": self.frame_index,
                "online_payload_sha256": self.online_payload_sha256,
            },
            "classification": {
                "frame_class": self.frame_class,
                "hard_negative": self.hard_negative,
                "action_change_type": self.action_change_type,
                "hard_negative_type": self.hard_negative_type,
            },
            "offline_identity_labels": {
                "truth_target_labels": list(self.truth_target_labels),
                "actor_labels": list(self.actor_labels),
                "object_labels": list(self.object_labels),
                "center_global_track_labels": list(
                    self.center_global_track_labels
                ),
            },
            "identity_provenance": {
                "global_track_id_owner": "center",
                "learning_path_created_global_track_id_count": 0,
                "learning_path_rewritten_global_track_id_count": 0,
            },
            "permissions": _false_permissions(),
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        action_change_types: frozenset[str],
        hard_negative_types: frozenset[str],
    ) -> "A1V3OfflineLabel":
        payload = _mapping(value, "offline_label")
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "record_kind",
                "source_ref",
                "classification",
                "offline_identity_labels",
                "identity_provenance",
                "permissions",
            },
            "offline_label_fields_mismatch",
        )
        if payload["schema_version"] != A1_V3_OFFLINE_LABEL_SCHEMA_V1:
            _fail("offline_label_schema_mismatch")
        if payload["record_kind"] != "offline_d6_audit_label":
            _fail("offline_label_kind_mismatch")
        source = _mapping(payload["source_ref"], "offline_label.source_ref")
        _require_exact_keys(
            source,
            {
                "split",
                "cell_id",
                "seed",
                "episode_id",
                "frame_index",
                "online_payload_sha256",
            },
            "offline_source_ref_fields_mismatch",
        )
        classification = _mapping(
            payload["classification"], "offline_label.classification"
        )
        _require_exact_keys(
            classification,
            {
                "frame_class",
                "hard_negative",
                "action_change_type",
                "hard_negative_type",
            },
            "offline_classification_fields_mismatch",
        )
        frame_class = _choice(
            classification["frame_class"], ("positive", "negative"), "frame_class"
        )
        hard_negative = _boolean(
            classification["hard_negative"], "hard_negative"
        )
        if hard_negative and frame_class != "negative":
            _fail("hard_negative_class_mismatch")
        action_change_type = _nonempty_string(
            classification["action_change_type"], "action_change_type"
        )
        if action_change_type not in action_change_types:
            _fail("action_change_type_not_requested", action_change_type)
        raw_hard_type = classification["hard_negative_type"]
        if hard_negative:
            hard_type = _nonempty_string(raw_hard_type, "hard_negative_type")
            if hard_type not in hard_negative_types:
                _fail("hard_negative_type_not_requested", hard_type)
        else:
            if raw_hard_type is not None:
                _fail("hard_negative_type_present_for_non_hard_frame")
            hard_type = None

        identity = _mapping(
            payload["offline_identity_labels"], "offline_label.offline_identity_labels"
        )
        _require_exact_keys(
            identity,
            {
                "truth_target_labels",
                "actor_labels",
                "object_labels",
                "center_global_track_labels",
            },
            "offline_identity_label_fields_mismatch",
        )
        identity_values = {
            name: _unique_string_sequence(identity[name], name)
            for name in (
                "truth_target_labels",
                "actor_labels",
                "object_labels",
                "center_global_track_labels",
            )
        }
        provenance = _mapping(
            payload["identity_provenance"], "offline_label.identity_provenance"
        )
        expected_provenance = {
            "global_track_id_owner": "center",
            "learning_path_created_global_track_id_count": 0,
            "learning_path_rewritten_global_track_id_count": 0,
        }
        if provenance != expected_provenance:
            _fail("offline_identity_provenance_invalid")
        _validate_permissions(payload["permissions"], "offline_label.permissions")
        return cls(
            split=_choice(source["split"], A1_V3_SPLITS, "source_ref.split"),
            cell_id=_nonempty_string(source["cell_id"], "source_ref.cell_id"),
            seed=_nonnegative_integer(source["seed"], "source_ref.seed"),
            episode_id=_nonempty_string(
                source["episode_id"], "source_ref.episode_id"
            ),
            frame_index=_nonnegative_integer(
                source["frame_index"], "source_ref.frame_index"
            ),
            online_payload_sha256=_sha256_value(
                source["online_payload_sha256"], "source_ref.online_payload_sha256"
            ),
            frame_class=frame_class,
            hard_negative=hard_negative,
            action_change_type=action_change_type,
            hard_negative_type=hard_type,
            truth_target_labels=identity_values["truth_target_labels"],
            actor_labels=identity_values["actor_labels"],
            object_labels=identity_values["object_labels"],
            center_global_track_labels=identity_values[
                "center_global_track_labels"
            ],
        )


@dataclass(frozen=True)
class A1V3TrainingFeatures:
    """Strict pre-decision model input with audit and label fields removed."""

    observed_target_count: int
    observed_resource_count: int
    candidate_edges: tuple[tuple[int, int], ...]
    action_mask_shape: tuple[int, int]
    target_demand_slots: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.observed_target_count < 0 or self.observed_resource_count < 0:
            _fail("training_feature_scale_invalid")
        if self.action_mask_shape != (
            self.observed_target_count,
            self.observed_resource_count,
        ):
            _fail("training_feature_action_mask_shape_mismatch")
        if len(self.target_demand_slots) != self.observed_target_count:
            _fail("training_feature_demand_slot_count_mismatch")
        if any(value < 0 for value in self.target_demand_slots):
            _fail("training_feature_demand_slot_invalid")
        if self.candidate_edges != tuple(sorted(set(self.candidate_edges))):
            _fail("training_feature_candidate_edges_invalid")
        for row, column in self.candidate_edges:
            if not (
                0 <= row < self.observed_target_count
                and 0 <= column < self.observed_resource_count
            ):
                _fail("training_feature_candidate_edge_out_of_bounds")

    @classmethod
    def from_audit_frame(cls, frame: A1V3OnlineFrame) -> "A1V3TrainingFeatures":
        return cls(
            observed_target_count=frame.observed_target_count,
            observed_resource_count=frame.observed_resource_count,
            candidate_edges=frame.candidate_edges,
            action_mask_shape=frame.action_mask_shape,
            target_demand_slots=frame.target_demand_slots,
        )

    def to_model_input_dict(self) -> dict[str, Any]:
        """Return the only mapping sanctioned as future model input."""

        return {
            "schema_version": A1_V3_TRAINING_FEATURE_SCHEMA_V1,
            "observed_scale": {
                "anonymous_target_count": self.observed_target_count,
                "anonymous_resource_count": self.observed_resource_count,
            },
            "candidate_graph": {
                "edge_indices": [list(edge) for edge in self.candidate_edges],
                "action_mask_shape": list(self.action_mask_shape),
            },
            "anonymous_target_demand_slots": list(self.target_demand_slots),
        }


@dataclass(frozen=True)
class A1V3TrainingTarget:
    """Supervision-only target kept separate from model input features."""

    teacher_edges: tuple[tuple[int, int], ...]
    teacher_edge_count: int
    teacher_edges_in_candidate_mask_count: int
    all_teacher_edges_in_candidate_mask: bool
    frame_class: str
    hard_negative: bool
    action_change_type: str
    hard_negative_type: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": A1_V3_TRAINING_TARGET_SCHEMA_V1,
            "teacher_edges": [list(edge) for edge in self.teacher_edges],
            "teacher_mask_observability": {
                "teacher_edge_count": self.teacher_edge_count,
                "teacher_edges_in_candidate_mask_count": (
                    self.teacher_edges_in_candidate_mask_count
                ),
                "all_teacher_edges_in_candidate_mask": (
                    self.all_teacher_edges_in_candidate_mask
                ),
            },
            "classification": {
                "frame_class": self.frame_class,
                "hard_negative": self.hard_negative,
                "action_change_type": self.action_change_type,
                "hard_negative_type": self.hard_negative_type,
            },
        }


@dataclass(frozen=True)
class A1V3TrainingSample:
    split: str
    features: A1V3TrainingFeatures
    target: A1V3TrainingTarget


def canonical_json_bytes(value: Any) -> bytes:
    """Return the contract's deterministic ASCII JSON representation."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        _fail("canonical_json_encoding_failed", str(exc))
    return encoded.encode("ascii")


def canonical_json_line(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def canonical_json_sha256(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def action_mask_content_sha256(
    shape: Sequence[int], edges: Sequence[tuple[int, int]]
) -> str:
    return canonical_json_sha256(
        {
            "shape": [int(shape[0]), int(shape[1])],
            "true_edge_indices": [list(edge) for edge in edges],
        }
    )


@dataclass(frozen=True)
class A1V3CollectionCell:
    cell_id: str
    scenario_family: str
    configured_target_count: int
    configured_resource_count: int
    requested_episode_count: int
    minimum_positive_frames: int
    minimum_negative_frames: int
    minimum_hard_negative_frames: int


@dataclass(frozen=True)
class A1V3FrozenRequest:
    request_id: str
    file_sha256: str
    requested_source_kind: str
    requested_episode_count: int
    requested_unique_seed_count: int
    requested_cell_count: int
    minimum_total_observable_frame_count: int
    minimum_positive_frame_count: int
    minimum_negative_frame_count: int
    minimum_hard_negative_frame_count: int
    cells: tuple[A1V3CollectionCell, ...]
    action_change_types: frozenset[str]
    hard_negative_types: frozenset[str]
    observability_requirements: tuple[str, ...]

    @property
    def cells_by_id(self) -> dict[str, A1V3CollectionCell]:
        return {cell.cell_id: cell for cell in self.cells}


@dataclass(frozen=True)
class A1V3ContractDescriptor:
    contract_id: str
    file_sha256: str
    request_file_sha256: str
    exclusion_registry_file_sha256: str


@dataclass(frozen=True)
class A1V3GeneratorConfig:
    config_id: str
    file_sha256: str
    source_git_commit: str
    repository_dirty: bool
    global_registry_path: str
    global_registry_id: str
    global_registry_content_sha256: str
    global_registry_file_sha256: str
    allocation_id: str


@dataclass(frozen=True)
class A1V3GlobalAllocation:
    registry_id: str
    content_sha256: str
    file_sha256: str
    allocation_id: str
    assigned_seeds: tuple[int, ...]
    protected_seeds: tuple[int, ...]
    other_allocation_seeds: tuple[int, ...]

    @property
    def required_forbidden_seeds(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.protected_seeds) | set(self.other_allocation_seeds)))


@dataclass(frozen=True)
class A1V3SeedRegistry:
    registry_id: str
    file_sha256: str
    global_registry_id: str
    global_registry_content_sha256: str
    global_registry_file_sha256: str
    allocation_id: str
    generator_config_id: str
    source_git_commit: str
    repository_dirty: bool
    generator_config_path: str
    generator_config_sha256: str
    assigned_seeds: tuple[int, ...]
    forbidden_seeds: tuple[int, ...]
    split_seed_values: Mapping[str, tuple[int, ...]]

    @property
    def split_by_seed(self) -> dict[int, str]:
        return {
            seed: split
            for split in A1_V3_SPLITS
            for seed in self.split_seed_values[split]
        }


@dataclass(frozen=True)
class A1V3ScheduledEpisode:
    episode_id: str
    cell_id: str
    scenario_family: str
    seed: int
    split: str
    configured_target_count: int
    configured_resource_count: int
    minimum_observable_frames: int
    minimum_positive_frames: int
    minimum_negative_frames: int
    minimum_hard_negative_frames: int

    @property
    def episode_key(self) -> tuple[int, str]:
        return (self.seed, self.episode_id)


@dataclass(frozen=True)
class A1V3GenerationSchedule:
    schedule_id: str
    file_sha256: str
    source_git_commit: str
    repository_dirty: bool
    generator_config_path: str
    generator_config_sha256: str
    episodes: tuple[A1V3ScheduledEpisode, ...]
    minimum_observable_frames: int
    minimum_positive_frames: int
    minimum_negative_frames: int
    minimum_hard_negative_frames: int

    @property
    def episodes_by_key(self) -> dict[tuple[int, str], A1V3ScheduledEpisode]:
        return {item.episode_key: item for item in self.episodes}


@dataclass(frozen=True)
class A1V3DatasetManifest:
    dataset_id: str
    source_git_commit: str
    repository_dirty: bool
    generator_config_path: str
    generator_config_sha256: str
    online_frames_sha256: str
    offline_labels_sha256: str
    cell_count: int
    episode_count: int
    unique_seed_count: int
    frame_count: int
    positive_frame_count: int
    negative_frame_count: int
    hard_negative_frame_count: int
    offline_identity_audit_availability: str
    complete_identity_label_frame_count: int
    partial_identity_label_frame_count: int
    empty_identity_label_frame_count: int
    split_seed_values: Mapping[str, tuple[int, ...]]
    cell_counts: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class A1V3ReadinessReport:
    status: str
    ready: bool
    reason_codes: tuple[str, ...]
    request_id: str | None
    registry_id: str | None
    global_registry_id: str | None
    allocation_id: str | None
    generator_config_id: str | None
    schedule_id: str | None
    source_generation_request_id: str | None
    source_generation_request_path: str
    source_generation_request_sha256: str | None
    source_generation_request_ready: bool
    cell_count: int
    episode_count: int
    unique_seed_count: int
    minimum_observable_frame_count: int
    minimum_positive_frame_count: int
    minimum_negative_frame_count: int
    minimum_hard_negative_frame_count: int

    def to_dict(self) -> dict[str, Any]:
        request_permissions = _source_generation_request_permissions(
            self.source_generation_request_ready
        )
        return {
            "schema_version": A1_V3_READINESS_REPORT_SCHEMA_V1,
            "status": self.status,
            "ready": self.ready,
            "reason_codes": list(self.reason_codes),
            "request_id": self.request_id,
            "registry_id": self.registry_id,
            "global_registry_id": self.global_registry_id,
            "allocation_id": self.allocation_id,
            "generator_config_id": self.generator_config_id,
            "schedule_id": self.schedule_id,
            "source_generation_request_id": self.source_generation_request_id,
            "source_generation_request_path": self.source_generation_request_path,
            "source_generation_request_sha256": (
                self.source_generation_request_sha256
            ),
            "source_generation_request_ready": (
                self.source_generation_request_ready
            ),
            "cell_count": self.cell_count,
            "episode_count": self.episode_count,
            "unique_seed_count": self.unique_seed_count,
            "minimum_observable_frame_count": self.minimum_observable_frame_count,
            "minimum_positive_frame_count": self.minimum_positive_frame_count,
            "minimum_negative_frame_count": self.minimum_negative_frame_count,
            "minimum_hard_negative_frame_count": (
                self.minimum_hard_negative_frame_count
            ),
            "data_generated": False,
            "model_trained": False,
            "plan_only": True,
            "request_readiness_only": True,
            "generation_authorized": False,
            "validation_payload_read": False,
            "formal_seed_payload_read": False,
            "v2_bundle_or_threshold_changed": False,
            "permissions": _false_permissions(),
            "request_permissions": request_permissions,
            "producer_capability": {
                "source_generation_request_path": (
                    self.source_generation_request_path
                ),
                "source_generation_request_sha256": (
                    self.source_generation_request_sha256
                ),
                "source_generation_request_ready": (
                    self.source_generation_request_ready
                ),
                "deterministic_sidecar_classification_required": True,
                "caller_sidecar_classification_override_allowed": False,
                "generation_authorized": False,
            },
        }


@dataclass(frozen=True)
class A1V3AuditDataset:
    manifest: A1V3DatasetManifest
    online_frames: tuple[A1V3OnlineFrame, ...]
    offline_labels: tuple[A1V3OfflineLabel, ...]


@dataclass(frozen=True)
class A1V3TrainingDataset:
    """Read-only, identity-stripped view intended for a future trainer."""

    manifest: A1V3DatasetManifest
    samples: tuple[A1V3TrainingSample, ...]


def load_a1_v3_frozen_request(
    path: str | Path = DEFAULT_A1_V3_REQUEST_PATH,
) -> A1V3FrozenRequest:
    payload, file_sha = _read_json_file(path, "v3_request")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "request_id",
            "status",
            "basis",
            "scope",
            "dataset_contract",
            "collection_cells",
            "action_change_types",
            "hard_negative_types",
            "diagnostic_observability_requirements",
            "seed_registry",
            "permissions",
        },
        "request_fields_mismatch",
    )
    if payload["schema_version"] != A1_V3_REQUEST_SCHEMA_V1:
        _fail("request_schema_mismatch")
    if payload["status"] != "request_frozen_generation_not_authorized":
        _fail("request_status_mismatch")
    expected_scope = {
        "request_only": True,
        "data_generated": False,
        "model_trained": False,
        "bundle_written": False,
        "v2_model_or_threshold_changed": False,
        "formal_holdout_read": False,
        "v2_remains_frozen_and_not_admitted": True,
    }
    if _mapping(payload["scope"], "request.scope") != expected_scope:
        _fail("request_scope_not_frozen")
    _validate_permissions(payload["permissions"], "request.permissions")

    dataset = _mapping(payload["dataset_contract"], "request.dataset_contract")
    _require_exact_keys(
        dataset,
        {
            "requested_source_kind",
            "requested_episode_count",
            "requested_unique_seed_count",
            "requested_cell_count",
            "identity_policy",
            "split_policy",
            "minimum_total_observable_frame_count",
            "minimum_positive_frame_count",
            "minimum_negative_frame_count",
            "minimum_hard_negative_frame_count",
        },
        "request_dataset_contract_fields_mismatch",
    )
    if dataset["identity_policy"] != (
        "anonymous_ordinal_tokens_no_truth_actor_object_or_global_track_identity"
    ):
        _fail("request_identity_policy_mismatch")
    if dataset["split_policy"] != "whole_episode_seed_atomic_60_20_20":
        _fail("request_split_policy_mismatch")
    requested_episode_count = _positive_integer(
        dataset["requested_episode_count"], "requested_episode_count"
    )
    requested_seed_count = _positive_integer(
        dataset["requested_unique_seed_count"], "requested_unique_seed_count"
    )
    requested_cell_count = _positive_integer(
        dataset["requested_cell_count"], "requested_cell_count"
    )
    minimum_total = _positive_integer(
        dataset["minimum_total_observable_frame_count"],
        "minimum_total_observable_frame_count",
    )
    minimum_positive = _positive_integer(
        dataset["minimum_positive_frame_count"], "minimum_positive_frame_count"
    )
    minimum_negative = _positive_integer(
        dataset["minimum_negative_frame_count"], "minimum_negative_frame_count"
    )
    minimum_hard = _positive_integer(
        dataset["minimum_hard_negative_frame_count"],
        "minimum_hard_negative_frame_count",
    )
    if (
        requested_episode_count,
        requested_seed_count,
        requested_cell_count,
        minimum_total,
        minimum_positive,
        minimum_negative,
        minimum_hard,
    ) != (300, 300, 15, 2700, 900, 900, 450):
        _fail("request_dataset_gate_mismatch")

    raw_cells = _list(payload["collection_cells"], "request.collection_cells")
    cells: list[A1V3CollectionCell] = []
    for index, raw_cell in enumerate(raw_cells):
        cell = _mapping(raw_cell, f"request.collection_cells[{index}]")
        _require_exact_keys(
            cell,
            {
                "cell_id",
                "scenario_family",
                "configured_target_count",
                "configured_resource_count",
                "requested_episode_count",
                "minimum_positive_frames",
                "minimum_negative_frames",
                "minimum_hard_negative_frames",
                "difficulty_focus",
            },
            "request_cell_fields_mismatch",
        )
        focus = _unique_string_sequence(
            cell["difficulty_focus"], f"request.collection_cells[{index}].difficulty_focus"
        )
        if not focus:
            _fail("request_cell_difficulty_focus_missing")
        cells.append(
            A1V3CollectionCell(
                cell_id=_nonempty_string(cell["cell_id"], "cell_id"),
                scenario_family=_nonempty_string(
                    cell["scenario_family"], "scenario_family"
                ),
                configured_target_count=_positive_integer(
                    cell["configured_target_count"], "configured_target_count"
                ),
                configured_resource_count=_positive_integer(
                    cell["configured_resource_count"], "configured_resource_count"
                ),
                requested_episode_count=_positive_integer(
                    cell["requested_episode_count"], "requested_episode_count"
                ),
                minimum_positive_frames=_positive_integer(
                    cell["minimum_positive_frames"], "minimum_positive_frames"
                ),
                minimum_negative_frames=_positive_integer(
                    cell["minimum_negative_frames"], "minimum_negative_frames"
                ),
                minimum_hard_negative_frames=_positive_integer(
                    cell["minimum_hard_negative_frames"],
                    "minimum_hard_negative_frames",
                ),
            )
        )
    if len(cells) != requested_cell_count:
        _fail("request_cell_count_mismatch")
    cell_ids = [cell.cell_id for cell in cells]
    if len(set(cell_ids)) != len(cell_ids):
        _fail("request_duplicate_cell_id")
    if sum(cell.requested_episode_count for cell in cells) != requested_episode_count:
        _fail("request_cell_episode_total_mismatch")
    if sum(cell.minimum_positive_frames for cell in cells) != minimum_positive:
        _fail("request_cell_positive_total_mismatch")
    if sum(cell.minimum_negative_frames for cell in cells) != minimum_negative:
        _fail("request_cell_negative_total_mismatch")
    if sum(cell.minimum_hard_negative_frames for cell in cells) != minimum_hard:
        _fail("request_cell_hard_negative_total_mismatch")

    action_type_sequence = tuple(
        _unique_string_sequence(
            payload["action_change_types"], "action_change_types"
        )
    )
    if action_type_sequence != A1_V3_ACTION_CHANGE_TYPES:
        _fail("request_action_change_type_inventory_mismatch")
    action_types = frozenset(action_type_sequence)
    hard_types = frozenset(
        _unique_string_sequence(payload["hard_negative_types"], "hard_negative_types")
    )
    observability = tuple(
        _unique_string_sequence(
            payload["diagnostic_observability_requirements"],
            "diagnostic_observability_requirements",
        )
    )
    if observability != A1_V3_OBSERVABILITY_REQUIREMENTS:
        _fail("request_observability_inventory_mismatch")
    return A1V3FrozenRequest(
        request_id=_nonempty_string(payload["request_id"], "request_id"),
        file_sha256=file_sha,
        requested_source_kind=_nonempty_string(
            dataset["requested_source_kind"], "requested_source_kind"
        ),
        requested_episode_count=requested_episode_count,
        requested_unique_seed_count=requested_seed_count,
        requested_cell_count=requested_cell_count,
        minimum_total_observable_frame_count=minimum_total,
        minimum_positive_frame_count=minimum_positive,
        minimum_negative_frame_count=minimum_negative,
        minimum_hard_negative_frame_count=minimum_hard,
        cells=tuple(cells),
        action_change_types=action_types,
        hard_negative_types=hard_types,
        observability_requirements=observability,
    )


def load_a1_v3_contract_descriptor(
    path: str | Path = DEFAULT_A1_V3_DATA_CONTRACT_PATH,
    *,
    request: A1V3FrozenRequest,
    exclusion_registry_file_sha256: str,
) -> A1V3ContractDescriptor:
    payload, file_sha = _read_json_file(path, "v3_data_contract")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "contract_id",
            "status",
            "frozen_request",
            "frozen_seed_exclusion_registry",
            "schema_versions",
            "artifact_filenames",
            "diagnostic_observability_requirements",
            "online_identity_contract",
            "trainer_interface",
            "split_contract",
            "readiness_gate",
            "permissions",
        },
        "data_contract_fields_mismatch",
    )
    if payload["schema_version"] != A1_V3_DATA_CONTRACT_SCHEMA_V1:
        _fail("data_contract_schema_mismatch")
    if payload["status"] != "implemented_contract_data_not_generated":
        _fail("data_contract_status_mismatch")
    request_binding = _mapping(payload["frozen_request"], "contract.frozen_request")
    exclusion_binding = _mapping(
        payload["frozen_seed_exclusion_registry"],
        "contract.frozen_seed_exclusion_registry",
    )
    _require_exact_keys(
        request_binding,
        {"path", "schema_version", "file_sha256"},
        "contract_request_binding_fields_mismatch",
    )
    _require_exact_keys(
        exclusion_binding,
        {"path", "schema_version", "file_sha256"},
        "contract_exclusion_binding_fields_mismatch",
    )
    if (
        request_binding["schema_version"] != A1_V3_REQUEST_SCHEMA_V1
        or request_binding["file_sha256"] != request.file_sha256
    ):
        _fail("contract_request_binding_mismatch")
    if (
        exclusion_binding["schema_version"]
        != A1_V3_EXCLUSION_REGISTRY_SCHEMA_V1
        or exclusion_binding["file_sha256"] != exclusion_registry_file_sha256
    ):
        _fail("contract_exclusion_binding_mismatch")
    expected_schemas = {
        "online_frame": A1_V3_ONLINE_FRAME_SCHEMA_V1,
        "offline_label": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
        "training_features": A1_V3_TRAINING_FEATURE_SCHEMA_V1,
        "training_target": A1_V3_TRAINING_TARGET_SCHEMA_V1,
        "main_seed_registry": A1_V3_MAIN_SEED_REGISTRY_SCHEMA_V1,
        "generation_schedule": A1_V3_GENERATION_SCHEDULE_SCHEMA_V1,
        "dataset_manifest": A1_V3_DATASET_MANIFEST_SCHEMA_V1,
        "split_policy": A1_V3_SPLIT_POLICY_V1,
        "readiness_report": A1_V3_READINESS_REPORT_SCHEMA_V1,
    }
    if _mapping(payload["schema_versions"], "contract.schema_versions") != expected_schemas:
        _fail("contract_schema_inventory_mismatch")
    if _mapping(payload["artifact_filenames"], "contract.artifact_filenames") != {
        "manifest": A1_V3_MANIFEST_FILENAME,
        "online_frames": A1_V3_ONLINE_FRAMES_FILENAME,
        "offline_labels": A1_V3_OFFLINE_LABELS_FILENAME,
    }:
        _fail("contract_artifact_inventory_mismatch")
    observability = tuple(
        _unique_string_sequence(
            payload["diagnostic_observability_requirements"],
            "contract.diagnostic_observability_requirements",
        )
    )
    if observability != request.observability_requirements:
        _fail("contract_observability_binding_mismatch")
    if _mapping(payload["online_identity_contract"], "contract.identity") != {
        "representation": "anonymous_ordinal_indices_only",
        "truth_actor_object_or_global_identity_allowed": False,
        "online_truth_use_count": 0,
        "global_track_id_owner": "center",
        "learning_path_global_track_id_create_allowed": False,
        "learning_path_global_track_id_rewrite_allowed": False,
    }:
        _fail("contract_online_identity_policy_mismatch")
    if _mapping(payload["trainer_interface"], "contract.trainer_interface") != {
        "feature_schema_version": A1_V3_TRAINING_FEATURE_SCHEMA_V1,
        "target_schema_version": A1_V3_TRAINING_TARGET_SCHEMA_V1,
        "model_input_top_level_keys": [
            "schema_version",
            "observed_scale",
            "candidate_graph",
            "anonymous_target_demand_slots",
        ],
        "full_online_frame_exposed_by_training_loader": False,
        "audit_diagnostic_fields_allowed_as_model_input": False,
        "offline_identity_fields_exposed_by_training_loader": False,
        "online_offline_hash_binding_required": True,
    }:
        _fail("contract_trainer_interface_mismatch")
    if _mapping(payload["split_contract"], "contract.split") != {
        "unit": "whole_seed_one_episode_atomic",
        "ratios_percent": A1_V3_SPLIT_PERCENT,
        "seed_counts": A1_V3_SPLIT_SEED_COUNTS,
        "cross_split_seed_overlap_allowed": False,
    }:
        _fail("contract_split_policy_mismatch")
    if _mapping(payload["readiness_gate"], "contract.readiness_gate") != {
        "required_cell_count": 15,
        "required_episode_count": 300,
        "required_unique_seed_count": 300,
        "minimum_total_observable_frame_count": 2700,
        "minimum_positive_frame_count": 900,
        "minimum_negative_frame_count": 900,
        "minimum_hard_negative_frame_count": 450,
        "missing_main_registry_status": "request_only",
        "invalid_or_incomplete_status": "fail_closed",
    }:
        _fail("contract_readiness_gate_mismatch")
    _validate_permissions(payload["permissions"], "contract.permissions")
    return A1V3ContractDescriptor(
        contract_id=_nonempty_string(payload["contract_id"], "contract_id"),
        file_sha256=file_sha,
        request_file_sha256=request.file_sha256,
        exclusion_registry_file_sha256=exclusion_registry_file_sha256,
    )


def load_a1_v3_exclusion_registry(
    path: str | Path = DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH,
) -> tuple[frozenset[int], str]:
    payload, file_sha = _read_json_file(path, "v3_exclusion_registry")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "registry_id",
            "status",
            "known_forbidden_catalogs",
            "known_forbidden_seed_count",
            "additional_d3_registry_policy",
            "requested_allocation",
            "split_request",
            "permissions",
        },
        "exclusion_registry_fields_mismatch",
    )
    if payload["schema_version"] != A1_V3_EXCLUSION_REGISTRY_SCHEMA_V1:
        _fail("exclusion_registry_schema_mismatch")
    if payload["status"] != "exclusion_registry_frozen_seed_allocation_unassigned":
        _fail("exclusion_registry_status_mismatch")
    catalogs = _list(
        payload["known_forbidden_catalogs"], "known_forbidden_catalogs"
    )
    expected_catalogs = {
        "scalable3d_training_v1": set(range(0, 100)),
        "scalable3d_formal_holdout_v1": set(range(1000, 1020)),
        "d3_a1_source_independent_evaluation_v2": set(range(20000, 20100)),
    }
    parsed_catalogs: dict[str, set[int]] = {}
    for index, raw_catalog in enumerate(catalogs):
        catalog = _mapping(raw_catalog, f"known_forbidden_catalogs[{index}]")
        _require_exact_keys(
            catalog,
            {"catalog_id", "reason", "ranges", "seed_count"},
            "exclusion_catalog_fields_mismatch",
        )
        catalog_id = _nonempty_string(catalog["catalog_id"], "catalog_id")
        if catalog_id in parsed_catalogs:
            _fail("duplicate_exclusion_catalog", catalog_id)
        _nonempty_string(catalog["reason"], "catalog.reason")
        values: set[int] = set()
        for range_index, raw_range in enumerate(
            _list(catalog["ranges"], f"catalog[{catalog_id}].ranges")
        ):
            seed_range = _mapping(
                raw_range, f"catalog[{catalog_id}].ranges[{range_index}]"
            )
            _require_exact_keys(
                seed_range,
                {"start", "stop_inclusive"},
                "exclusion_range_fields_mismatch",
            )
            start = _nonnegative_integer(seed_range["start"], "seed_range.start")
            stop = _nonnegative_integer(
                seed_range["stop_inclusive"], "seed_range.stop_inclusive"
            )
            if stop < start:
                _fail("exclusion_seed_range_invalid")
            values.update(range(start, stop + 1))
        if len(values) != _positive_integer(catalog["seed_count"], "seed_count"):
            _fail("exclusion_catalog_seed_count_mismatch", catalog_id)
        parsed_catalogs[catalog_id] = values
    if parsed_catalogs != expected_catalogs:
        _fail("exclusion_catalog_universe_mismatch")
    forbidden = frozenset().union(*parsed_catalogs.values())
    if _positive_integer(
        payload["known_forbidden_seed_count"], "known_forbidden_seed_count"
    ) != len(forbidden):
        _fail("exclusion_union_count_mismatch")
    if _mapping(
        payload["additional_d3_registry_policy"], "additional_d3_registry_policy"
    ) != {
        "canonical_registry_union_required_at_allocation": True,
        "allocation_must_fail_if_registry_union_unavailable": True,
        "overlap_with_any_registered_d3_seed_allowed": False,
        "registry_snapshot_sha256_required": True,
    }:
        _fail("exclusion_union_policy_mismatch")
    if _mapping(payload["requested_allocation"], "requested_allocation") != {
        "requested_unique_seed_count": 300,
        "assigned_seed_values": [],
        "allocation_status": "unassigned",
        "allocation_owner": "main",
        "generation_authorized": False,
    }:
        _fail("exclusion_allocation_not_frozen")
    if _mapping(payload["split_request"], "split_request") != {
        "unit": "whole_episode_grouped_by_numeric_seed",
        "train_seed_count": 180,
        "validation_seed_count": 60,
        "test_seed_count": 60,
        "seed_atomic_across_scenarios_scales_and_splits": True,
        "cross_split_seed_overlap_allowed": False,
    }:
        _fail("exclusion_split_request_mismatch")
    _validate_permissions(
        payload["permissions"],
        "exclusion_registry.permissions",
        fields=A1_V3_EXCLUSION_PERMISSION_FIELDS,
    )
    return forbidden, file_sha


def load_a1_v3_generator_config(
    path: str | Path,
    *,
    request: A1V3FrozenRequest,
    descriptor: A1V3ContractDescriptor,
    exclusion_registry_file_sha256: str,
) -> A1V3GeneratorConfig:
    payload, file_sha = _read_json_file(path, "v3_generator_config")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "config_id",
            "status",
            "source",
            "bindings",
            "generation_plan",
            "permissions",
        },
        "generator_config_fields_mismatch",
    )
    if payload["schema_version"] != A1_V3_GENERATOR_CONFIG_SCHEMA_V1:
        _fail("generator_config_schema_mismatch")
    if payload["config_id"] != A1_V3_GENERATOR_CONFIG_ID:
        _fail("generator_config_id_mismatch")
    if payload["status"] != A1_V3_GENERATOR_CONFIG_STATUS:
        _fail("generator_config_status_mismatch")

    source = _mapping(payload["source"], "generator_config.source")
    _require_exact_keys(
        source,
        {"owner", "git_commit", "repository_dirty"},
        "generator_config_source_fields_mismatch",
    )
    if source["owner"] != "main":
        _fail("generator_config_owner_mismatch")
    source_git_commit = _git_commit(
        source["git_commit"], "generator_config.source.git_commit"
    )
    repository_dirty = _boolean(
        source["repository_dirty"], "generator_config.source.repository_dirty"
    )

    bindings = _mapping(payload["bindings"], "generator_config.bindings")
    _require_exact_keys(
        bindings,
        {
            "frozen_request",
            "data_contract",
            "seed_exclusion_registry",
            "global_seed_registry",
        },
        "generator_config_binding_fields_mismatch",
    )
    expected_local_bindings = {
        "frozen_request": {
            "path": (
                "research_modules/d3_assignment_planner/configs/"
                "a1_source_independent_v3_development_data_request_v1.json"
            ),
            "schema_version": A1_V3_REQUEST_SCHEMA_V1,
            "identity": request.request_id,
            "file_sha256": request.file_sha256,
        },
        "data_contract": {
            "path": (
                "research_modules/d3_assignment_planner/configs/"
                "a1_source_independent_v3_data_contract_v1.json"
            ),
            "schema_version": A1_V3_DATA_CONTRACT_SCHEMA_V1,
            "identity": descriptor.contract_id,
            "file_sha256": descriptor.file_sha256,
        },
        "seed_exclusion_registry": {
            "path": (
                "research_modules/d3_assignment_planner/configs/"
                "a1_source_independent_v3_seed_exclusion_registry_v1.json"
            ),
            "schema_version": A1_V3_EXCLUSION_REGISTRY_SCHEMA_V1,
            "identity": "d3-a1-v3-development-source-seed-request-20260801-v1",
            "file_sha256": exclusion_registry_file_sha256,
        },
    }
    for name, expected in expected_local_bindings.items():
        binding = _mapping(bindings[name], f"generator_config.bindings.{name}")
        _require_exact_keys(
            binding,
            {"path", "schema_version", "identity", "file_sha256"},
            "generator_config_local_binding_fields_mismatch",
        )
        _safe_logical_path(binding["path"], f"generator_config.bindings.{name}.path")
        if binding != expected:
            _fail("generator_config_local_binding_mismatch", name)

    global_binding = _mapping(
        bindings["global_seed_registry"],
        "generator_config.bindings.global_seed_registry",
    )
    _require_exact_keys(
        global_binding,
        {
            "path",
            "schema_version",
            "policy_version",
            "registry_id",
            "content_sha256",
            "file_sha256",
            "allocation_id",
        },
        "generator_config_global_binding_fields_mismatch",
    )
    global_path = _safe_logical_path(
        global_binding["path"], "generator_config.global_seed_registry.path"
    )
    if global_binding != {
        "path": (
            "research_modules/scalable_3d_simulation/configs/"
            "scalable_learning_global_seed_registry_v1.json"
        ),
        "schema_version": A1_V3_GLOBAL_SEED_REGISTRY_SCHEMA_V1,
        "policy_version": A1_V3_GLOBAL_SEED_POLICY_V1,
        "registry_id": A1_V3_GLOBAL_REGISTRY_ID,
        "content_sha256": A1_V3_GLOBAL_REGISTRY_CONTENT_SHA256,
        "file_sha256": A1_V3_GLOBAL_REGISTRY_FILE_SHA256,
        "allocation_id": A1_V3_GLOBAL_ALLOCATION_ID,
    }:
        _fail("generator_config_global_binding_mismatch")

    generation_plan = _mapping(
        payload["generation_plan"], "generator_config.generation_plan"
    )
    if generation_plan != {
        "source_kind": request.requested_source_kind,
        "cell_count": 15,
        "episode_count": 300,
        "unique_seed_count": 300,
        "per_cell_split_seed_counts": A1_V3_CELL_SPLIT_SEED_COUNTS,
        "minimum_observable_frame_count": 2700,
        "minimum_positive_frame_count": 900,
        "minimum_negative_frame_count": 900,
        "minimum_hard_negative_frame_count": 450,
        "episode_payload_write_enabled": False,
        "dataset_artifact_write_enabled": False,
        "formal_payload_read_allowed": False,
        "prior_v2_payload_read_allowed": False,
    }:
        _fail("generator_config_plan_mismatch")
    _validate_permissions(payload["permissions"], "generator_config.permissions")
    return A1V3GeneratorConfig(
        config_id=A1_V3_GENERATOR_CONFIG_ID,
        file_sha256=file_sha,
        source_git_commit=source_git_commit,
        repository_dirty=repository_dirty,
        global_registry_path=global_path,
        global_registry_id=A1_V3_GLOBAL_REGISTRY_ID,
        global_registry_content_sha256=A1_V3_GLOBAL_REGISTRY_CONTENT_SHA256,
        global_registry_file_sha256=A1_V3_GLOBAL_REGISTRY_FILE_SHA256,
        allocation_id=A1_V3_GLOBAL_ALLOCATION_ID,
    )


def load_a1_v3_global_seed_allocation(
    path: str | Path,
    *,
    config: A1V3GeneratorConfig,
    request: A1V3FrozenRequest,
    descriptor: A1V3ContractDescriptor,
    exclusion_registry_file_sha256: str,
) -> A1V3GlobalAllocation:
    payload, file_sha = _read_json_file(path, "global_seed_registry")
    if file_sha != config.global_registry_file_sha256:
        _fail("global_registry_file_sha256_mismatch")
    _require_exact_keys(
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
        "global_registry_fields_mismatch",
    )
    if payload["schema_version"] != A1_V3_GLOBAL_SEED_REGISTRY_SCHEMA_V1:
        _fail("global_registry_schema_mismatch")
    if payload["policy_version"] != A1_V3_GLOBAL_SEED_POLICY_V1:
        _fail("global_registry_policy_mismatch")
    if payload["registry_id"] != config.global_registry_id:
        _fail("global_registry_id_mismatch")
    if payload["status"] != "allocations_reserved_generation_not_started":
        _fail("global_registry_status_mismatch")
    declared_content_sha = _sha256_value(
        payload["content_sha256"], "global_registry.content_sha256"
    )
    content_without_hash = dict(payload)
    content_without_hash.pop("content_sha256", None)
    reproduced_content_sha = canonical_json_sha256(content_without_hash)
    if declared_content_sha != reproduced_content_sha:
        _fail("global_registry_content_sha256_not_reproducible")
    if declared_content_sha != config.global_registry_content_sha256:
        _fail("global_registry_content_sha256_mismatch")
    if _mapping(payload["generation_state"], "global_registry.generation_state") != {
        "episode_generation_started": False,
        "sample_generation_started": False,
        "training_started": False,
        "formal_seed_payload_read": False,
        "module_readiness_required": True,
    }:
        _fail("global_registry_generation_state_mismatch")
    if _list(payload["unallocated_requests"], "global_registry.unallocated_requests"):
        _fail("global_registry_unallocated_request_present")

    protected_values: set[int] = set()
    protected_ids: set[str] = set()
    formal_payload_read_allowed: bool | None = None
    for index, raw_set in enumerate(
        _list(payload["protected_seed_sets"], "global_registry.protected_seed_sets")
    ):
        protected = _mapping(raw_set, f"global_registry.protected_seed_sets[{index}]")
        _require_exact_keys(
            protected,
            {
                "set_id",
                "purpose",
                "seeds",
                "dataset_generation_allowed",
                "payload_read_allowed",
            },
            "global_protected_set_fields_mismatch",
        )
        set_id = _nonempty_string(protected["set_id"], "global_protected_set.set_id")
        if set_id in protected_ids:
            _fail("global_protected_set_id_duplicate", set_id)
        protected_ids.add(set_id)
        _nonempty_string(protected["purpose"], "global_protected_set.purpose")
        seeds = set(_seed_sequence(protected["seeds"], "global_protected_set.seeds"))
        if protected["dataset_generation_allowed"] is not False:
            _fail("global_protected_generation_allowed", set_id)
        payload_read_allowed = _boolean(
            protected["payload_read_allowed"],
            "global_protected_set.payload_read_allowed",
        )
        overlap = protected_values & seeds
        if overlap:
            _fail("global_protected_seed_overlap", repr(sorted(overlap)))
        protected_values.update(seeds)
        if set_id == "formal-evaluation-v1":
            if seeds != set(range(1000, 1020)):
                _fail("global_formal_seed_set_mismatch")
            formal_payload_read_allowed = payload_read_allowed
    if formal_payload_read_allowed is not False:
        _fail("global_formal_payload_read_policy_mismatch")

    allocations: dict[str, Mapping[str, Any]] = {}
    allocated_values: set[int] = set()
    for index, raw_allocation in enumerate(
        _list(payload["allocations"], "global_registry.allocations")
    ):
        allocation = _mapping(raw_allocation, f"global_registry.allocations[{index}]")
        _require_exact_keys(
            allocation,
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
            "global_allocation_fields_mismatch",
        )
        allocation_id = _nonempty_string(
            allocation["allocation_id"], "global_allocation.allocation_id"
        )
        if allocation_id in allocations:
            _fail("global_allocation_id_duplicate", allocation_id)
        _nonempty_string(allocation["owner"], "global_allocation.owner")
        _nonempty_string(
            allocation["candidate_version"], "global_allocation.candidate_version"
        )
        _nonempty_string(allocation["lifecycle"], "global_allocation.lifecycle")
        _nonempty_string(allocation["usage_class"], "global_allocation.usage_class")
        _nonempty_string(allocation["split_policy"], "global_allocation.split_policy")
        _unique_string_sequence(
            allocation["permitted_operations"],
            "global_allocation.permitted_operations",
        )
        seeds = _seed_sequence(allocation["seeds"], "global_allocation.seeds")
        if _positive_integer(allocation["seed_count"], "global_allocation.seed_count") != len(seeds):
            _fail("global_allocation_seed_count_mismatch", allocation_id)
        protected_overlap = set(seeds) & protected_values
        if protected_overlap:
            _fail("global_allocation_protected_seed_overlap", allocation_id)
        allocation_overlap = set(seeds) & allocated_values
        if allocation_overlap:
            _fail("global_allocation_seed_overlap", allocation_id)
        allocated_values.update(seeds)
        _mapping(allocation["source_contract"], "global_allocation.source_contract")
        allocations[allocation_id] = allocation

    d3_allocation = allocations.get(config.allocation_id)
    if d3_allocation is None:
        _fail("global_d3_allocation_missing")
    expected_d3_source_contract = {
        "bindings": [
            {
                "path": (
                    "research_modules/d3_assignment_planner/configs/"
                    "a1_source_independent_v3_data_contract_v1.json"
                ),
                "role": "data_contract",
                "sha256": descriptor.file_sha256,
            },
            {
                "path": (
                    "research_modules/d3_assignment_planner/configs/"
                    "a1_source_independent_v3_development_data_request_v1.json"
                ),
                "role": "development_data_request",
                "sha256": request.file_sha256,
            },
            {
                "path": (
                    "research_modules/d3_assignment_planner/configs/"
                    "a1_source_independent_v3_seed_exclusion_registry_v1.json"
                ),
                "role": "seed_exclusion_registry",
                "sha256": exclusion_registry_file_sha256,
            },
        ],
        "contract_id": descriptor.contract_id,
        "request_id": request.request_id,
    }
    if d3_allocation != {
        "allocation_id": A1_V3_GLOBAL_ALLOCATION_ID,
        "owner": "D3",
        "candidate_version": A1_V3_GLOBAL_ALLOCATION_CANDIDATE,
        "lifecycle": "reserved",
        "usage_class": "train_validation_test",
        "split_policy": A1_V3_GLOBAL_ALLOCATION_SPLIT_POLICY,
        "permitted_operations": ["dataset_generation"],
        "seed_count": 300,
        "seeds": list(range(23000, 23300)),
        "source_contract": expected_d3_source_contract,
    }:
        _fail("global_d3_allocation_mismatch")
    other_seeds = tuple(
        sorted(
            seed
            for allocation_id, allocation in allocations.items()
            if allocation_id != A1_V3_GLOBAL_ALLOCATION_ID
            for seed in allocation["seeds"]
        )
    )
    if any(
        allocation["owner"] not in {"D4", "D5"}
        for allocation_id, allocation in allocations.items()
        if allocation_id != A1_V3_GLOBAL_ALLOCATION_ID
    ):
        _fail("global_other_allocation_owner_mismatch")
    return A1V3GlobalAllocation(
        registry_id=config.global_registry_id,
        content_sha256=declared_content_sha,
        file_sha256=file_sha,
        allocation_id=config.allocation_id,
        assigned_seeds=tuple(range(23000, 23300)),
        protected_seeds=tuple(sorted(protected_values)),
        other_allocation_seeds=other_seeds,
    )


def load_a1_v3_main_seed_registry(
    path: str | Path,
    *,
    request: A1V3FrozenRequest,
    exclusion_registry_file_sha256: str,
    known_forbidden_seeds: frozenset[int],
    config: A1V3GeneratorConfig,
    global_allocation: A1V3GlobalAllocation,
) -> A1V3SeedRegistry:
    payload, file_sha = _read_json_file(path, "v3_main_seed_registry")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "registry_id",
            "status",
            "request_binding",
            "global_registry_binding",
            "source",
            "allocation",
            "split",
            "permissions",
        },
        "main_seed_registry_fields_mismatch",
    )
    if payload["schema_version"] != A1_V3_MAIN_SEED_REGISTRY_SCHEMA_V1:
        _fail("main_seed_registry_schema_mismatch")
    if payload["registry_id"] != A1_V3_MAIN_REGISTRY_ID:
        _fail("main_seed_registry_id_mismatch")
    if payload["status"] != A1_V3_MAIN_REGISTRY_STATUS:
        _fail("main_seed_registry_status_mismatch")
    binding = _mapping(payload["request_binding"], "registry.request_binding")
    _require_exact_keys(
        binding,
        {
            "request_id",
            "request_file_sha256",
            "exclusion_registry_file_sha256",
        },
        "registry_request_binding_fields_mismatch",
    )
    if binding != {
        "request_id": request.request_id,
        "request_file_sha256": request.file_sha256,
        "exclusion_registry_file_sha256": exclusion_registry_file_sha256,
    }:
        _fail("registry_request_binding_mismatch")

    global_binding = _mapping(
        payload["global_registry_binding"], "registry.global_registry_binding"
    )
    _require_exact_keys(
        global_binding,
        {
            "path",
            "schema_version",
            "policy_version",
            "registry_id",
            "content_sha256",
            "file_sha256",
            "allocation_id",
            "owner",
            "candidate_version",
            "lifecycle",
            "usage_class",
            "split_policy",
            "permitted_operations",
            "exact_allocation_match",
        },
        "registry_global_binding_fields_mismatch",
    )
    _safe_logical_path(global_binding["path"], "registry.global_binding.path")
    if global_binding != {
        "path": config.global_registry_path,
        "schema_version": A1_V3_GLOBAL_SEED_REGISTRY_SCHEMA_V1,
        "policy_version": A1_V3_GLOBAL_SEED_POLICY_V1,
        "registry_id": global_allocation.registry_id,
        "content_sha256": global_allocation.content_sha256,
        "file_sha256": global_allocation.file_sha256,
        "allocation_id": global_allocation.allocation_id,
        "owner": "D3",
        "candidate_version": A1_V3_GLOBAL_ALLOCATION_CANDIDATE,
        "lifecycle": "reserved",
        "usage_class": "train_validation_test",
        "split_policy": A1_V3_GLOBAL_ALLOCATION_SPLIT_POLICY,
        "permitted_operations": ["dataset_generation"],
        "exact_allocation_match": True,
    }:
        _fail("registry_global_binding_mismatch")

    source = _mapping(payload["source"], "registry.source")
    _require_exact_keys(
        source,
        {
            "owner",
            "git_commit",
            "repository_dirty",
            "global_registry_snapshot_path",
            "global_registry_snapshot_file_sha256",
            "generator_config_path",
            "generator_config_sha256",
        },
        "registry_source_fields_mismatch",
    )
    if source["owner"] != "main":
        _fail("registry_owner_mismatch")
    source_git_commit = _git_commit(source["git_commit"], "source.git_commit")
    repository_dirty = _boolean(
        source["repository_dirty"], "source.repository_dirty"
    )
    global_snapshot_path = _safe_logical_path(
        source["global_registry_snapshot_path"],
        "source.global_registry_snapshot_path",
    )
    global_snapshot_sha = _sha256_value(
        source["global_registry_snapshot_file_sha256"],
        "source.global_registry_snapshot_file_sha256",
    )
    generator_config_path = _safe_logical_path(
        source["generator_config_path"], "source.generator_config_path"
    )
    generator_config_sha = _sha256_value(
        source["generator_config_sha256"], "source.generator_config_sha256"
    )
    if (
        source_git_commit != config.source_git_commit
        or repository_dirty != config.repository_dirty
        or global_snapshot_path != config.global_registry_path
        or global_snapshot_sha != config.global_registry_file_sha256
        or generator_config_path
        != (
            "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_generator_config_v1.json"
        )
        or generator_config_sha != config.file_sha256
    ):
        _fail("registry_generator_source_mismatch")

    allocation = _mapping(payload["allocation"], "registry.allocation")
    _require_exact_keys(
        allocation,
        {
            "unique_seed_count",
            "assigned_seed_values",
            "forbidden_seed_values",
            "forbidden_seed_count",
            "forbidden_seed_values_sha256",
            "global_protected_seed_count",
            "global_other_allocation_seed_count",
            "canonical_registry_union_complete",
            "generation_authorized",
        },
        "registry_allocation_fields_mismatch",
    )
    assigned = _seed_sequence(
        allocation["assigned_seed_values"], "allocation.assigned_seed_values"
    )
    forbidden = _seed_sequence(
        allocation["forbidden_seed_values"], "allocation.forbidden_seed_values"
    )
    if _positive_integer(
        allocation["unique_seed_count"], "allocation.unique_seed_count"
    ) != len(assigned):
        _fail("registry_assigned_seed_count_mismatch")
    if len(assigned) != request.requested_unique_seed_count:
        _fail("registry_assigned_seed_request_mismatch")
    if assigned != global_allocation.assigned_seeds:
        _fail("registry_assigned_seed_global_allocation_mismatch")
    if _nonnegative_integer(
        allocation["forbidden_seed_count"], "allocation.forbidden_seed_count"
    ) != len(forbidden):
        _fail("registry_forbidden_seed_count_mismatch")
    forbidden_sha = _sha256_value(
        allocation["forbidden_seed_values_sha256"],
        "allocation.forbidden_seed_values_sha256",
    )
    if canonical_json_sha256(list(forbidden)) != forbidden_sha:
        _fail("registry_forbidden_seed_sha256_mismatch")
    if _nonnegative_integer(
        allocation["global_protected_seed_count"],
        "allocation.global_protected_seed_count",
    ) != len(global_allocation.protected_seeds):
        _fail("registry_global_protected_seed_count_mismatch")
    if _nonnegative_integer(
        allocation["global_other_allocation_seed_count"],
        "allocation.global_other_allocation_seed_count",
    ) != len(global_allocation.other_allocation_seeds):
        _fail("registry_global_other_allocation_seed_count_mismatch")
    if allocation["canonical_registry_union_complete"] is not True:
        _fail("registry_canonical_union_incomplete")
    if allocation["generation_authorized"] is not False:
        _fail("registry_generation_permission_must_remain_false")
    if not known_forbidden_seeds.issubset(set(forbidden)):
        _fail("registry_known_exclusion_missing")
    if forbidden != global_allocation.required_forbidden_seeds:
        _fail("registry_global_forbidden_union_mismatch")
    overlap = set(assigned) & set(forbidden)
    if overlap:
        _fail("registry_seed_overlap", repr(sorted(overlap)))

    split = _mapping(payload["split"], "registry.split")
    _require_exact_keys(
        split,
        {
            "policy_version",
            "unit",
            "ratios_percent",
            "seed_counts",
            "seed_values",
            "cross_split_seed_overlap_allowed",
        },
        "registry_split_fields_mismatch",
    )
    if split["policy_version"] != A1_V3_SPLIT_POLICY_V1:
        _fail("registry_split_policy_mismatch")
    if split["unit"] != "whole_seed_one_episode_atomic":
        _fail("registry_split_unit_mismatch")
    if _mapping(split["ratios_percent"], "registry.split.ratios") != A1_V3_SPLIT_PERCENT:
        _fail("registry_split_ratio_mismatch")
    if _mapping(split["seed_counts"], "registry.split.seed_counts") != (
        A1_V3_SPLIT_SEED_COUNTS
    ):
        _fail("registry_split_seed_count_contract_mismatch")
    if split["cross_split_seed_overlap_allowed"] is not False:
        _fail("registry_cross_split_overlap_allowed")
    seed_values = _mapping(split["seed_values"], "registry.split.seed_values")
    _require_exact_keys(
        seed_values, set(A1_V3_SPLITS), "registry_split_seed_fields_mismatch"
    )
    split_seeds = {
        name: _seed_sequence(seed_values[name], f"registry.split.seed_values.{name}")
        for name in A1_V3_SPLITS
    }
    if any(
        len(split_seeds[name]) != A1_V3_SPLIT_SEED_COUNTS[name]
        for name in A1_V3_SPLITS
    ):
        _fail("registry_split_seed_count_mismatch")
    for index, left in enumerate(A1_V3_SPLITS):
        for right in A1_V3_SPLITS[index + 1 :]:
            if set(split_seeds[left]) & set(split_seeds[right]):
                _fail("registry_cross_split_seed_overlap")
    split_union = set().union(*(set(values) for values in split_seeds.values()))
    if split_union != set(assigned):
        _fail("registry_split_seed_coverage_mismatch")
    expected_split_seeds = {
        "train": tuple(range(23000, 23180)),
        "validation": tuple(range(23180, 23240)),
        "test": tuple(range(23240, 23300)),
    }
    if split_seeds != expected_split_seeds:
        _fail("registry_fixed_split_seed_assignment_mismatch")
    _validate_permissions(payload["permissions"], "registry.permissions")
    return A1V3SeedRegistry(
        registry_id=_nonempty_string(payload["registry_id"], "registry_id"),
        file_sha256=file_sha,
        global_registry_id=global_allocation.registry_id,
        global_registry_content_sha256=global_allocation.content_sha256,
        global_registry_file_sha256=global_allocation.file_sha256,
        allocation_id=global_allocation.allocation_id,
        generator_config_id=config.config_id,
        source_git_commit=source_git_commit,
        repository_dirty=repository_dirty,
        generator_config_path=generator_config_path,
        generator_config_sha256=generator_config_sha,
        assigned_seeds=assigned,
        forbidden_seeds=forbidden,
        split_seed_values=split_seeds,
    )


def _expected_a1_v3_scheduled_episodes(
    request: A1V3FrozenRequest,
    registry: A1V3SeedRegistry,
) -> tuple[A1V3ScheduledEpisode, ...]:
    episodes: list[A1V3ScheduledEpisode] = []
    for cell_index, cell in enumerate(request.cells):
        cell_episode_offset = 0
        for split in A1_V3_SPLITS:
            per_cell_count = A1_V3_CELL_SPLIT_SEED_COUNTS[split]
            split_seeds = registry.split_seed_values[split]
            start = cell_index * per_cell_count
            for split_offset, seed in enumerate(
                split_seeds[start : start + per_cell_count]
            ):
                episodes.append(
                    A1V3ScheduledEpisode(
                        episode_id=(
                            f"a1-v3-cell-{cell_index:02d}-{split}-"
                            f"{split_offset:02d}"
                        ),
                        cell_id=cell.cell_id,
                        scenario_family=cell.scenario_family,
                        seed=seed,
                        split=split,
                        configured_target_count=cell.configured_target_count,
                        configured_resource_count=cell.configured_resource_count,
                        minimum_observable_frames=9,
                        minimum_positive_frames=3,
                        minimum_negative_frames=3,
                        minimum_hard_negative_frames=(
                            2 if cell_episode_offset < 10 else 1
                        ),
                    )
                )
                cell_episode_offset += 1
    return tuple(episodes)


def load_a1_v3_generation_schedule(
    path: str | Path,
    *,
    request: A1V3FrozenRequest,
    descriptor: A1V3ContractDescriptor,
    registry: A1V3SeedRegistry,
) -> A1V3GenerationSchedule:
    payload, file_sha = _read_json_file(path, "v3_generation_schedule")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "schedule_id",
            "status",
            "bindings",
            "source",
            "record_contract",
            "episodes",
            "declared_totals",
            "permissions",
        },
        "generation_schedule_fields_mismatch",
    )
    if payload["schema_version"] != A1_V3_GENERATION_SCHEDULE_SCHEMA_V1:
        _fail("generation_schedule_schema_mismatch")
    if payload["schedule_id"] != A1_V3_GENERATION_SCHEDULE_ID:
        _fail("generation_schedule_id_mismatch")
    if payload["status"] != "planned_not_generated":
        _fail("generation_schedule_status_mismatch")
    bindings = _mapping(payload["bindings"], "schedule.bindings")
    _require_exact_keys(
        bindings,
        {
            "request_id",
            "request_file_sha256",
            "registry_id",
            "registry_file_sha256",
            "global_registry_id",
            "global_registry_content_sha256",
            "global_registry_file_sha256",
            "allocation_id",
            "generator_config_id",
            "generator_config_file_sha256",
            "contract_id",
            "contract_file_sha256",
        },
        "schedule_binding_fields_mismatch",
    )
    if bindings != {
        "request_id": request.request_id,
        "request_file_sha256": request.file_sha256,
        "registry_id": registry.registry_id,
        "registry_file_sha256": registry.file_sha256,
        "global_registry_id": registry.global_registry_id,
        "global_registry_content_sha256": registry.global_registry_content_sha256,
        "global_registry_file_sha256": registry.global_registry_file_sha256,
        "allocation_id": registry.allocation_id,
        "generator_config_id": registry.generator_config_id,
        "generator_config_file_sha256": registry.generator_config_sha256,
        "contract_id": descriptor.contract_id,
        "contract_file_sha256": descriptor.file_sha256,
    }:
        _fail("schedule_binding_mismatch")
    source = _mapping(payload["source"], "schedule.source")
    _require_exact_keys(
        source,
        {
            "git_commit",
            "repository_dirty",
            "generator_config_path",
            "generator_config_sha256",
        },
        "schedule_source_fields_mismatch",
    )
    source_git_commit = _git_commit(source["git_commit"], "source.git_commit")
    repository_dirty = _boolean(
        source["repository_dirty"], "source.repository_dirty"
    )
    generator_config_path = _safe_logical_path(
        source["generator_config_path"], "source.generator_config_path"
    )
    generator_config_sha = _sha256_value(
        source["generator_config_sha256"], "source.generator_config_sha256"
    )
    if (
        source_git_commit != registry.source_git_commit
        or repository_dirty != registry.repository_dirty
        or generator_config_path != registry.generator_config_path
        or generator_config_sha != registry.generator_config_sha256
    ):
        _fail("schedule_registry_source_mismatch")
    record_contract = _mapping(
        payload["record_contract"], "schedule.record_contract"
    )
    _require_exact_keys(
        record_contract,
        {
            "online_frame_schema_version",
            "offline_label_schema_version",
            "training_feature_schema_version",
            "training_target_schema_version",
            "split_policy_version",
            "diagnostic_observability_requirements",
            "online_identity_representation",
            "online_truth_use_count",
            "all_permissions_false",
            "plan_only",
            "per_cell_split_seed_counts",
            "full_online_frame_exposed_by_training_loader",
        },
        "schedule_record_contract_fields_mismatch",
    )
    if (
        record_contract["online_frame_schema_version"]
        != A1_V3_ONLINE_FRAME_SCHEMA_V1
        or record_contract["offline_label_schema_version"]
        != A1_V3_OFFLINE_LABEL_SCHEMA_V1
        or record_contract["training_feature_schema_version"]
        != A1_V3_TRAINING_FEATURE_SCHEMA_V1
        or record_contract["training_target_schema_version"]
        != A1_V3_TRAINING_TARGET_SCHEMA_V1
        or record_contract["split_policy_version"] != A1_V3_SPLIT_POLICY_V1
        or tuple(record_contract["diagnostic_observability_requirements"])
        != request.observability_requirements
        or record_contract["online_identity_representation"]
        != "anonymous_ordinal_indices_only"
        or record_contract["online_truth_use_count"] != 0
        or record_contract["all_permissions_false"] is not True
        or record_contract["plan_only"] is not True
        or _mapping(
            record_contract["per_cell_split_seed_counts"],
            "schedule.record_contract.per_cell_split_seed_counts",
        )
        != A1_V3_CELL_SPLIT_SEED_COUNTS
        or record_contract["full_online_frame_exposed_by_training_loader"] is not False
    ):
        _fail("schedule_record_contract_incomplete")

    raw_episodes = _list(payload["episodes"], "schedule.episodes")
    cells_by_id = request.cells_by_id
    split_by_seed = registry.split_by_seed
    episodes: list[A1V3ScheduledEpisode] = []
    for index, raw_episode in enumerate(raw_episodes):
        episode = _mapping(raw_episode, f"schedule.episodes[{index}]")
        _require_exact_keys(
            episode,
            {
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
            },
            "scheduled_episode_fields_mismatch",
        )
        cell_id = _nonempty_string(episode["cell_id"], "episode.cell_id")
        if cell_id not in cells_by_id:
            _fail("scheduled_episode_cell_unknown", cell_id)
        cell = cells_by_id[cell_id]
        seed = _nonnegative_integer(episode["seed"], "episode.seed")
        if seed not in split_by_seed:
            _fail("scheduled_episode_seed_unregistered", str(seed))
        split = _choice(episode["split"], A1_V3_SPLITS, "episode.split")
        if split_by_seed[seed] != split:
            _fail("scheduled_episode_split_mismatch", str(seed))
        if (
            episode["scenario_family"] != cell.scenario_family
            or episode["configured_target_count"] != cell.configured_target_count
            or episode["configured_resource_count"] != cell.configured_resource_count
        ):
            _fail("scheduled_episode_cell_configuration_mismatch", cell_id)
        minimum_observable = _positive_integer(
            episode["minimum_observable_frames"],
            "episode.minimum_observable_frames",
        )
        minimum_positive = _nonnegative_integer(
            episode["minimum_positive_frames"], "episode.minimum_positive_frames"
        )
        minimum_negative = _nonnegative_integer(
            episode["minimum_negative_frames"], "episode.minimum_negative_frames"
        )
        minimum_hard = _nonnegative_integer(
            episode["minimum_hard_negative_frames"],
            "episode.minimum_hard_negative_frames",
        )
        if minimum_positive + minimum_negative > minimum_observable:
            _fail("scheduled_episode_class_minimum_exceeds_frames")
        if minimum_hard > minimum_negative:
            _fail("scheduled_episode_hard_negative_minimum_invalid")
        episodes.append(
            A1V3ScheduledEpisode(
                episode_id=_nonempty_string(
                    episode["episode_id"], "episode.episode_id"
                ),
                cell_id=cell_id,
                scenario_family=cell.scenario_family,
                seed=seed,
                split=split,
                configured_target_count=cell.configured_target_count,
                configured_resource_count=cell.configured_resource_count,
                minimum_observable_frames=minimum_observable,
                minimum_positive_frames=minimum_positive,
                minimum_negative_frames=minimum_negative,
                minimum_hard_negative_frames=minimum_hard,
            )
        )
    if len(episodes) != request.requested_episode_count:
        _fail("schedule_episode_count_mismatch")
    episode_ids = [item.episode_id for item in episodes]
    episode_keys = [item.episode_key for item in episodes]
    seeds = [item.seed for item in episodes]
    if len(set(episode_ids)) != len(episode_ids):
        _fail("schedule_duplicate_episode_id")
    if len(set(episode_keys)) != len(episode_keys):
        _fail("schedule_duplicate_episode")
    if len(set(seeds)) != len(seeds):
        _fail("schedule_duplicate_seed")
    if set(seeds) != set(registry.assigned_seeds):
        _fail("schedule_registry_seed_coverage_mismatch")
    expected_episodes = _expected_a1_v3_scheduled_episodes(request, registry)
    if tuple(episodes) != expected_episodes:
        _fail("schedule_fixed_cell_seed_assignment_mismatch")
    cell_episode_counts = Counter(item.cell_id for item in episodes)
    for cell in request.cells:
        if cell_episode_counts[cell.cell_id] != cell.requested_episode_count:
            _fail("schedule_cell_episode_count_mismatch", cell.cell_id)
        cell_items = [item for item in episodes if item.cell_id == cell.cell_id]
        if sum(item.minimum_positive_frames for item in cell_items) < (
            cell.minimum_positive_frames
        ):
            _fail("schedule_cell_positive_minimum_insufficient", cell.cell_id)
        if sum(item.minimum_negative_frames for item in cell_items) < (
            cell.minimum_negative_frames
        ):
            _fail("schedule_cell_negative_minimum_insufficient", cell.cell_id)
        if sum(item.minimum_hard_negative_frames for item in cell_items) < (
            cell.minimum_hard_negative_frames
        ):
            _fail("schedule_cell_hard_negative_minimum_insufficient", cell.cell_id)
    derived_totals = {
        "cell_count": len(cell_episode_counts),
        "episode_count": len(episodes),
        "unique_seed_count": len(set(seeds)),
        "minimum_observable_frame_count": sum(
            item.minimum_observable_frames for item in episodes
        ),
        "minimum_positive_frame_count": sum(
            item.minimum_positive_frames for item in episodes
        ),
        "minimum_negative_frame_count": sum(
            item.minimum_negative_frames for item in episodes
        ),
        "minimum_hard_negative_frame_count": sum(
            item.minimum_hard_negative_frames for item in episodes
        ),
    }
    declared_totals = _mapping(payload["declared_totals"], "schedule.declared_totals")
    if declared_totals != derived_totals:
        _fail("schedule_declared_totals_mismatch")
    minimum_requirements = {
        "minimum_observable_frame_count": request.minimum_total_observable_frame_count,
        "minimum_positive_frame_count": request.minimum_positive_frame_count,
        "minimum_negative_frame_count": request.minimum_negative_frame_count,
        "minimum_hard_negative_frame_count": (
            request.minimum_hard_negative_frame_count
        ),
    }
    for field, minimum in minimum_requirements.items():
        if derived_totals[field] < minimum:
            _fail("schedule_minimum_frame_count_insufficient", field)
    _validate_permissions(payload["permissions"], "schedule.permissions")
    return A1V3GenerationSchedule(
        schedule_id=_nonempty_string(payload["schedule_id"], "schedule_id"),
        file_sha256=file_sha,
        source_git_commit=source_git_commit,
        repository_dirty=repository_dirty,
        generator_config_path=generator_config_path,
        generator_config_sha256=generator_config_sha,
        episodes=tuple(episodes),
        minimum_observable_frames=derived_totals[
            "minimum_observable_frame_count"
        ],
        minimum_positive_frames=derived_totals["minimum_positive_frame_count"],
        minimum_negative_frames=derived_totals["minimum_negative_frame_count"],
        minimum_hard_negative_frames=derived_totals[
            "minimum_hard_negative_frame_count"
        ],
    )


def validate_a1_v3_pre_generation_readiness(
    *,
    request_path: str | Path = DEFAULT_A1_V3_REQUEST_PATH,
    exclusion_registry_path: str | Path = DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH,
    contract_path: str | Path = DEFAULT_A1_V3_DATA_CONTRACT_PATH,
    generator_config_path: str | Path | None = None,
    global_registry_path: str | Path | None = None,
    registry_path: str | Path | None = None,
    schedule_path: str | Path | None = None,
    source_generation_request_path: str | Path = (
        DEFAULT_A1_V3_SOURCE_GENERATION_REQUEST_PATH
    ),
    sidecar_classification_policy_path: str | Path = (
        DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH
    ),
) -> A1V3ReadinessReport:
    """Validate the source-generation request without authorizing generation.

    Missing main-owned inputs are represented as ``request_only``.  Any
    malformed, partially supplied, or inconsistent input is ``fail_closed``.
    Only a complete registry and schedule can produce ``ready``.
    """

    request: A1V3FrozenRequest | None = None
    registry: A1V3SeedRegistry | None = None
    schedule: A1V3GenerationSchedule | None = None
    source_generation_request: Any | None = None
    try:
        request = load_a1_v3_frozen_request(request_path)
        forbidden, exclusion_sha = load_a1_v3_exclusion_registry(
            exclusion_registry_path
        )
        descriptor = load_a1_v3_contract_descriptor(
            contract_path,
            request=request,
            exclusion_registry_file_sha256=exclusion_sha,
        )
        if registry_path is None:
            if schedule_path is not None:
                _fail("schedule_supplied_without_main_registry")
            return _readiness_report(
                status="request_only",
                ready=False,
                reason_codes=("main_seed_registry_missing",),
                request=request,
                registry=None,
                schedule=None,
                source_generation_request=None,
            )
        if generator_config_path is None:
            _fail("generator_config_missing")
        if global_registry_path is None:
            _fail("global_seed_registry_missing")
        config = load_a1_v3_generator_config(
            generator_config_path,
            request=request,
            descriptor=descriptor,
            exclusion_registry_file_sha256=exclusion_sha,
        )
        global_allocation = load_a1_v3_global_seed_allocation(
            global_registry_path,
            config=config,
            request=request,
            descriptor=descriptor,
            exclusion_registry_file_sha256=exclusion_sha,
        )
        registry_payload, _ = _read_json_file(
            registry_path, "v3_main_seed_registry_probe"
        )
        if registry_payload.get("schema_version") == A1_V3_EXCLUSION_REGISTRY_SCHEMA_V1:
            if schedule_path is not None:
                _fail("unassigned_registry_cannot_bind_schedule")
            return _readiness_report(
                status="request_only",
                ready=False,
                reason_codes=("main_seed_registry_unassigned",),
                request=request,
                registry=None,
                schedule=None,
                source_generation_request=None,
            )
        registry = load_a1_v3_main_seed_registry(
            registry_path,
            request=request,
            exclusion_registry_file_sha256=exclusion_sha,
            known_forbidden_seeds=forbidden,
            config=config,
            global_allocation=global_allocation,
        )
        if schedule_path is None:
            _fail("generation_schedule_missing")
        schedule = load_a1_v3_generation_schedule(
            schedule_path,
            request=request,
            descriptor=descriptor,
            registry=registry,
        )
        from .a1_v3_source_generation_request import (
            load_a1_v3_source_generation_request_artifact,
        )

        source_generation_request = (
            load_a1_v3_source_generation_request_artifact(
                source_generation_request_path,
                request=request,
                descriptor=descriptor,
                global_allocation=global_allocation,
                registry=registry,
                schedule=schedule,
                sidecar_classification_policy_path=(
                    sidecar_classification_policy_path
                ),
            )
        )
        if not source_generation_request.ready:
            return _readiness_report(
                status="fail_closed",
                ready=False,
                reason_codes=source_generation_request.reason_codes,
                request=request,
                registry=registry,
                schedule=schedule,
                source_generation_request=source_generation_request,
            )
        return _readiness_report(
            status="ready",
            ready=True,
            reason_codes=(),
            request=request,
            registry=registry,
            schedule=schedule,
            source_generation_request=source_generation_request,
        )
    except A1V3DataContractError as exc:
        return _readiness_report(
            status="fail_closed",
            ready=False,
            reason_codes=(exc.code,),
            request=request,
            registry=registry,
            schedule=schedule,
            source_generation_request=None,
        )


def load_a1_v3_audit_dataset(
    dataset_dir: str | Path,
    *,
    request_path: str | Path = DEFAULT_A1_V3_REQUEST_PATH,
    exclusion_registry_path: str | Path = DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH,
    contract_path: str | Path = DEFAULT_A1_V3_DATA_CONTRACT_PATH,
    registry_path: str | Path,
    schedule_path: str | Path,
    generator_config_path: str | Path,
    global_registry_path: str | Path,
    source_generation_request_path: str | Path = (
        DEFAULT_A1_V3_SOURCE_GENERATION_REQUEST_PATH
    ),
) -> A1V3AuditDataset:
    """Load and fully audit generated v3 artifacts without writing any file."""

    readiness = validate_a1_v3_pre_generation_readiness(
        request_path=request_path,
        exclusion_registry_path=exclusion_registry_path,
        contract_path=contract_path,
        generator_config_path=generator_config_path,
        global_registry_path=global_registry_path,
        registry_path=registry_path,
        schedule_path=schedule_path,
        source_generation_request_path=source_generation_request_path,
    )
    if not readiness.ready:
        _fail("dataset_load_readiness_not_ready", ",".join(readiness.reason_codes))
    request = load_a1_v3_frozen_request(request_path)
    forbidden, exclusion_sha = load_a1_v3_exclusion_registry(exclusion_registry_path)
    descriptor = load_a1_v3_contract_descriptor(
        contract_path,
        request=request,
        exclusion_registry_file_sha256=exclusion_sha,
    )
    config = load_a1_v3_generator_config(
        generator_config_path,
        request=request,
        descriptor=descriptor,
        exclusion_registry_file_sha256=exclusion_sha,
    )
    global_allocation = load_a1_v3_global_seed_allocation(
        global_registry_path,
        config=config,
        request=request,
        descriptor=descriptor,
        exclusion_registry_file_sha256=exclusion_sha,
    )
    registry = load_a1_v3_main_seed_registry(
        registry_path,
        request=request,
        exclusion_registry_file_sha256=exclusion_sha,
        known_forbidden_seeds=forbidden,
        config=config,
        global_allocation=global_allocation,
    )
    schedule = load_a1_v3_generation_schedule(
        schedule_path,
        request=request,
        descriptor=descriptor,
        registry=registry,
    )
    config_file = Path(generator_config_path)
    config_sha = _file_sha256(config_file, "generator_config_read_failed")
    if config_sha != schedule.generator_config_sha256:
        _fail("generator_config_sha256_mismatch")

    root = Path(dataset_dir)
    manifest_path = root / A1_V3_MANIFEST_FILENAME
    _reject_symlink(manifest_path, "dataset_manifest_symlink_forbidden")
    manifest_payload, _ = _read_json_file(manifest_path, "dataset_manifest")
    manifest = _parse_dataset_manifest(
        manifest_payload,
        request=request,
        descriptor=descriptor,
        registry=registry,
        schedule=schedule,
        generator_config_path=config_file,
        generator_config_sha256=config_sha,
    )
    online_path = root / A1_V3_ONLINE_FRAMES_FILENAME
    offline_path = root / A1_V3_OFFLINE_LABELS_FILENAME
    _reject_symlink(online_path, "online_frames_symlink_forbidden")
    _reject_symlink(offline_path, "offline_labels_symlink_forbidden")
    online_bytes = _read_file_bytes(online_path, "online_frames_read_failed")
    offline_bytes = _read_file_bytes(offline_path, "offline_labels_read_failed")
    if sha256(online_bytes).hexdigest() != manifest.online_frames_sha256:
        _fail("online_frames_sha256_mismatch")
    if sha256(offline_bytes).hexdigest() != manifest.offline_labels_sha256:
        _fail("offline_labels_sha256_mismatch")
    online_frames = _parse_canonical_jsonl(
        online_bytes,
        "online_frames",
        A1V3OnlineFrame.from_dict,
    )
    offline_labels = _parse_canonical_jsonl(
        offline_bytes,
        "offline_labels",
        lambda value: A1V3OfflineLabel.from_dict(
            value,
            action_change_types=request.action_change_types,
            hard_negative_types=request.hard_negative_types,
        ),
    )
    _validate_generated_records(
        online_frames=online_frames,
        offline_labels=offline_labels,
        manifest=manifest,
        request=request,
        registry=registry,
        schedule=schedule,
    )
    return A1V3AuditDataset(
        manifest=manifest,
        online_frames=online_frames,
        offline_labels=offline_labels,
    )


def load_a1_v3_training_dataset(
    dataset_dir: str | Path,
    *,
    request_path: str | Path = DEFAULT_A1_V3_REQUEST_PATH,
    exclusion_registry_path: str | Path = DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH,
    contract_path: str | Path = DEFAULT_A1_V3_DATA_CONTRACT_PATH,
    registry_path: str | Path,
    schedule_path: str | Path,
    generator_config_path: str | Path,
    global_registry_path: str | Path,
    source_generation_request_path: str | Path = (
        DEFAULT_A1_V3_SOURCE_GENERATION_REQUEST_PATH
    ),
) -> A1V3TrainingDataset:
    """Return an immutable future-trainer view with audit identities removed."""

    audit = load_a1_v3_audit_dataset(
        dataset_dir,
        request_path=request_path,
        exclusion_registry_path=exclusion_registry_path,
        contract_path=contract_path,
        registry_path=registry_path,
        schedule_path=schedule_path,
        generator_config_path=generator_config_path,
        global_registry_path=global_registry_path,
        source_generation_request_path=source_generation_request_path,
    )
    samples = tuple(
        A1V3TrainingSample(
            split=frame.source.split,
            features=A1V3TrainingFeatures.from_audit_frame(frame),
            target=A1V3TrainingTarget(
                teacher_edges=frame.teacher_edges,
                teacher_edge_count=frame.teacher_edge_count,
                teacher_edges_in_candidate_mask_count=(
                    frame.teacher_edges_in_candidate_mask_count
                ),
                all_teacher_edges_in_candidate_mask=(
                    frame.all_teacher_edges_in_candidate_mask
                ),
                frame_class=label.frame_class,
                hard_negative=label.hard_negative,
                action_change_type=label.action_change_type,
                hard_negative_type=label.hard_negative_type,
            ),
        )
        for frame, label in zip(
            audit.online_frames, audit.offline_labels, strict=True
        )
    )
    return A1V3TrainingDataset(manifest=audit.manifest, samples=samples)


def _parse_dataset_manifest(
    payload: Mapping[str, Any],
    *,
    request: A1V3FrozenRequest,
    descriptor: A1V3ContractDescriptor,
    registry: A1V3SeedRegistry,
    schedule: A1V3GenerationSchedule,
    generator_config_path: Path,
    generator_config_sha256: str,
) -> A1V3DatasetManifest:
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "dataset_id",
            "status",
            "contract_bindings",
            "source",
            "artifacts",
            "counts",
            "offline_identity_audit",
            "split",
            "cell_counts",
            "state",
            "permissions",
        },
        "dataset_manifest_fields_mismatch",
    )
    if payload["schema_version"] != A1_V3_DATASET_MANIFEST_SCHEMA_V1:
        _fail("dataset_manifest_schema_mismatch")
    if payload["status"] != "generated_untrained_not_admitted":
        _fail("dataset_manifest_status_mismatch")
    bindings = _mapping(payload["contract_bindings"], "manifest.contract_bindings")
    _require_exact_keys(
        bindings,
        {
            "request_id",
            "request_file_sha256",
            "contract_id",
            "contract_file_sha256",
            "registry_id",
            "registry_file_sha256",
            "schedule_id",
            "schedule_file_sha256",
            "online_frame_schema_version",
            "offline_label_schema_version",
            "training_feature_schema_version",
            "training_target_schema_version",
            "split_policy_version",
        },
        "manifest_contract_binding_fields_mismatch",
    )
    if bindings != {
        "request_id": request.request_id,
        "request_file_sha256": request.file_sha256,
        "contract_id": descriptor.contract_id,
        "contract_file_sha256": descriptor.file_sha256,
        "registry_id": registry.registry_id,
        "registry_file_sha256": registry.file_sha256,
        "schedule_id": schedule.schedule_id,
        "schedule_file_sha256": schedule.file_sha256,
        "online_frame_schema_version": A1_V3_ONLINE_FRAME_SCHEMA_V1,
        "offline_label_schema_version": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
        "training_feature_schema_version": A1_V3_TRAINING_FEATURE_SCHEMA_V1,
        "training_target_schema_version": A1_V3_TRAINING_TARGET_SCHEMA_V1,
        "split_policy_version": A1_V3_SPLIT_POLICY_V1,
    }:
        _fail("manifest_contract_binding_mismatch")
    source = _mapping(payload["source"], "manifest.source")
    _require_exact_keys(
        source,
        {
            "git_commit",
            "repository_dirty",
            "generator_config_path",
            "generator_config_sha256",
        },
        "manifest_source_fields_mismatch",
    )
    source_git = _git_commit(source["git_commit"], "manifest.source.git_commit")
    source_dirty = _boolean(
        source["repository_dirty"], "manifest.source.repository_dirty"
    )
    config_logical_path = _safe_logical_path(
        source["generator_config_path"], "manifest.source.generator_config_path"
    )
    source_config_sha = _sha256_value(
        source["generator_config_sha256"],
        "manifest.source.generator_config_sha256",
    )
    if (
        source_git != schedule.source_git_commit
        or source_dirty != schedule.repository_dirty
        or config_logical_path != schedule.generator_config_path
        or source_config_sha != schedule.generator_config_sha256
        or source_config_sha != generator_config_sha256
        or Path(config_logical_path).name != generator_config_path.name
    ):
        _fail("manifest_source_binding_mismatch")
    artifacts = _mapping(payload["artifacts"], "manifest.artifacts")
    _require_exact_keys(
        artifacts,
        {
            "online_frames_path",
            "online_frames_sha256",
            "offline_labels_path",
            "offline_labels_sha256",
        },
        "manifest_artifact_fields_mismatch",
    )
    if artifacts["online_frames_path"] != A1_V3_ONLINE_FRAMES_FILENAME:
        _fail("manifest_online_frames_path_mismatch")
    if artifacts["offline_labels_path"] != A1_V3_OFFLINE_LABELS_FILENAME:
        _fail("manifest_offline_labels_path_mismatch")
    online_sha = _sha256_value(
        artifacts["online_frames_sha256"], "online_frames_sha256"
    )
    offline_sha = _sha256_value(
        artifacts["offline_labels_sha256"], "offline_labels_sha256"
    )
    counts = _mapping(payload["counts"], "manifest.counts")
    _require_exact_keys(
        counts,
        {
            "cell_count",
            "episode_count",
            "unique_seed_count",
            "frame_count",
            "positive_frame_count",
            "negative_frame_count",
            "hard_negative_frame_count",
            "online_truth_use_count",
            "learning_created_global_track_id_count",
            "learning_rewritten_global_track_id_count",
            "duplicate_episode_count",
            "duplicate_frame_count",
        },
        "manifest_count_fields_mismatch",
    )
    parsed_counts = {
        name: _nonnegative_integer(counts[name], f"manifest.counts.{name}")
        for name in counts
    }
    if (
        parsed_counts["cell_count"] != request.requested_cell_count
        or parsed_counts["episode_count"] != request.requested_episode_count
        or parsed_counts["unique_seed_count"] != request.requested_unique_seed_count
        or parsed_counts["frame_count"]
        < request.minimum_total_observable_frame_count
        or parsed_counts["positive_frame_count"] < request.minimum_positive_frame_count
        or parsed_counts["negative_frame_count"] < request.minimum_negative_frame_count
        or parsed_counts["hard_negative_frame_count"]
        < request.minimum_hard_negative_frame_count
    ):
        _fail("manifest_dataset_count_gate_failed")
    if parsed_counts["positive_frame_count"] + parsed_counts[
        "negative_frame_count"
    ] != parsed_counts["frame_count"]:
        _fail("manifest_class_count_mismatch")
    if parsed_counts["hard_negative_frame_count"] > parsed_counts[
        "negative_frame_count"
    ]:
        _fail("manifest_hard_negative_count_invalid")
    for zero_field in (
        "online_truth_use_count",
        "learning_created_global_track_id_count",
        "learning_rewritten_global_track_id_count",
        "duplicate_episode_count",
        "duplicate_frame_count",
    ):
        if parsed_counts[zero_field] != 0:
            _fail("manifest_zero_count_violation", zero_field)

    identity_audit = _mapping(
        payload["offline_identity_audit"], "manifest.offline_identity_audit"
    )
    _require_exact_keys(
        identity_audit,
        {
            "availability",
            "complete_identity_audit_claimed",
            "complete_identity_label_frame_count",
            "partial_identity_label_frame_count",
            "empty_identity_label_frame_count",
        },
        "manifest_offline_identity_audit_fields_mismatch",
    )
    identity_availability = _choice(
        identity_audit["availability"],
        ("complete", "partial", "unavailable"),
        "manifest.offline_identity_audit.availability",
    )
    complete_identity_count = _nonnegative_integer(
        identity_audit["complete_identity_label_frame_count"],
        "manifest.offline_identity_audit.complete_identity_label_frame_count",
    )
    partial_identity_count = _nonnegative_integer(
        identity_audit["partial_identity_label_frame_count"],
        "manifest.offline_identity_audit.partial_identity_label_frame_count",
    )
    empty_identity_count = _nonnegative_integer(
        identity_audit["empty_identity_label_frame_count"],
        "manifest.offline_identity_audit.empty_identity_label_frame_count",
    )
    complete_claimed = _boolean(
        identity_audit["complete_identity_audit_claimed"],
        "manifest.offline_identity_audit.complete_identity_audit_claimed",
    )
    if (
        complete_identity_count + partial_identity_count + empty_identity_count
        != parsed_counts["frame_count"]
    ):
        _fail("manifest_offline_identity_audit_count_mismatch")
    expected_identity_availability = (
        "complete"
        if complete_identity_count == parsed_counts["frame_count"]
        else (
            "unavailable"
            if complete_identity_count == 0 and partial_identity_count == 0
            else "partial"
        )
    )
    if identity_availability != expected_identity_availability:
        _fail("manifest_offline_identity_audit_availability_mismatch")
    if complete_claimed != (identity_availability == "complete"):
        _fail("manifest_offline_identity_audit_claim_mismatch")

    split = _mapping(payload["split"], "manifest.split")
    _require_exact_keys(
        split,
        {
            "policy_version",
            "unit",
            "ratios_percent",
            "seed_counts",
            "seed_values",
            "cross_split_seed_overlap_allowed",
        },
        "manifest_split_fields_mismatch",
    )
    if (
        split["policy_version"] != A1_V3_SPLIT_POLICY_V1
        or split["unit"] != "whole_seed_one_episode_atomic"
        or _mapping(split["ratios_percent"], "manifest.split.ratios")
        != A1_V3_SPLIT_PERCENT
        or _mapping(split["seed_counts"], "manifest.split.seed_counts")
        != A1_V3_SPLIT_SEED_COUNTS
        or split["cross_split_seed_overlap_allowed"] is not False
    ):
        _fail("manifest_split_contract_mismatch")
    raw_seed_values = _mapping(split["seed_values"], "manifest.split.seed_values")
    _require_exact_keys(
        raw_seed_values, set(A1_V3_SPLITS), "manifest_split_seed_fields_mismatch"
    )
    split_seed_values = {
        name: _seed_sequence(
            raw_seed_values[name], f"manifest.split.seed_values.{name}"
        )
        for name in A1_V3_SPLITS
    }
    if split_seed_values != dict(registry.split_seed_values):
        _fail("manifest_registry_split_mismatch")

    raw_cell_counts = _list(payload["cell_counts"], "manifest.cell_counts")
    cell_counts: list[dict[str, Any]] = []
    seen_cells: set[str] = set()
    for index, raw_item in enumerate(raw_cell_counts):
        item = _mapping(raw_item, f"manifest.cell_counts[{index}]")
        _require_exact_keys(
            item,
            {
                "cell_id",
                "episode_count",
                "frame_count",
                "positive_frame_count",
                "negative_frame_count",
                "hard_negative_frame_count",
            },
            "manifest_cell_count_fields_mismatch",
        )
        cell_id = _nonempty_string(item["cell_id"], "manifest.cell_id")
        if cell_id in seen_cells or cell_id not in request.cells_by_id:
            _fail("manifest_cell_id_invalid", cell_id)
        seen_cells.add(cell_id)
        parsed = {"cell_id": cell_id}
        parsed.update(
            {
                name: _nonnegative_integer(item[name], f"manifest.{cell_id}.{name}")
                for name in (
                    "episode_count",
                    "frame_count",
                    "positive_frame_count",
                    "negative_frame_count",
                    "hard_negative_frame_count",
                )
            }
        )
        request_cell = request.cells_by_id[cell_id]
        if (
            parsed["episode_count"] != request_cell.requested_episode_count
            or parsed["positive_frame_count"] < request_cell.minimum_positive_frames
            or parsed["negative_frame_count"] < request_cell.minimum_negative_frames
            or parsed["hard_negative_frame_count"]
            < request_cell.minimum_hard_negative_frames
            or parsed["positive_frame_count"] + parsed["negative_frame_count"]
            != parsed["frame_count"]
        ):
            _fail("manifest_cell_count_gate_failed", cell_id)
        cell_counts.append(parsed)
    if seen_cells != set(request.cells_by_id):
        _fail("manifest_cell_coverage_mismatch")
    for field in (
        "episode_count",
        "frame_count",
        "positive_frame_count",
        "negative_frame_count",
        "hard_negative_frame_count",
    ):
        if sum(int(item[field]) for item in cell_counts) != parsed_counts[field]:
            _fail("manifest_cell_total_mismatch", field)
    if _mapping(payload["state"], "manifest.state") != {
        "data_generated": True,
        "model_trained": False,
        "bundle_written": False,
        "v2_bundle_or_threshold_changed": False,
        "formal_holdout_read": False,
    }:
        _fail("manifest_state_not_untrained")
    _validate_permissions(payload["permissions"], "manifest.permissions")
    return A1V3DatasetManifest(
        dataset_id=_nonempty_string(payload["dataset_id"], "dataset_id"),
        source_git_commit=source_git,
        repository_dirty=source_dirty,
        generator_config_path=config_logical_path,
        generator_config_sha256=source_config_sha,
        online_frames_sha256=online_sha,
        offline_labels_sha256=offline_sha,
        cell_count=parsed_counts["cell_count"],
        episode_count=parsed_counts["episode_count"],
        unique_seed_count=parsed_counts["unique_seed_count"],
        frame_count=parsed_counts["frame_count"],
        positive_frame_count=parsed_counts["positive_frame_count"],
        negative_frame_count=parsed_counts["negative_frame_count"],
        hard_negative_frame_count=parsed_counts["hard_negative_frame_count"],
        offline_identity_audit_availability=identity_availability,
        complete_identity_label_frame_count=complete_identity_count,
        partial_identity_label_frame_count=partial_identity_count,
        empty_identity_label_frame_count=empty_identity_count,
        split_seed_values=split_seed_values,
        cell_counts=tuple(cell_counts),
    )


def _validate_generated_records(
    *,
    online_frames: tuple[A1V3OnlineFrame, ...],
    offline_labels: tuple[A1V3OfflineLabel, ...],
    manifest: A1V3DatasetManifest,
    request: A1V3FrozenRequest,
    registry: A1V3SeedRegistry,
    schedule: A1V3GenerationSchedule,
) -> None:
    if len(online_frames) != manifest.frame_count:
        _fail("online_frame_count_manifest_mismatch")
    if len(offline_labels) != manifest.frame_count:
        _fail("offline_label_count_manifest_mismatch")
    online_keys = tuple(item.frame_key for item in online_frames)
    offline_keys = tuple(item.frame_key for item in offline_labels)
    if len(set(online_keys)) != len(online_keys):
        _fail("duplicate_online_frame")
    if len(set(offline_keys)) != len(offline_keys):
        _fail("duplicate_offline_label")
    if online_keys != offline_keys:
        _fail("online_offline_frame_key_mismatch")
    canonical_order = tuple(
        item.frame_key
        for item in sorted(
            online_frames,
            key=lambda item: (
                item.source.cell_id,
                item.source.seed,
                item.source.episode_id,
                item.source.frame_index,
            ),
        )
    )
    if online_keys != canonical_order:
        _fail("dataset_frame_order_not_canonical")

    schedule_by_episode = schedule.episodes_by_key
    seen_episode_keys: set[tuple[int, str]] = set()
    previous_timestamp_by_episode: dict[tuple[int, str], tuple[int, float, float]] = {}
    for frame, label in zip(online_frames, offline_labels, strict=True):
        if label.online_payload_sha256 != frame.content_sha256:
            _fail("offline_online_payload_sha256_mismatch")
        if (
            label.hard_negative
            and frame.source.scenario_family == "near_tie_hard_negative"
            and label.hard_negative_type != "near_tie_but_teacher_keeps_r0"
        ):
            _fail("near_tie_cell_hard_negative_type_mismatch")
        if (
            label.hard_negative
            and label.hard_negative_type == "near_tie_but_teacher_keeps_r0"
            and (
                frame.near_tie_qualifying_target_count < 1
                or frame.near_tie_reason_code != A1_V3_NEAR_TIE_REASON_MET
            )
        ):
            _fail("near_tie_hard_negative_boundary_not_met")
        if (
            label.split != frame.source.split
            or label.cell_id != frame.source.cell_id
            or label.frame_key != frame.frame_key
        ):
            _fail("offline_online_source_ref_mismatch")
        episode_key = frame.source.episode_key
        scheduled = schedule_by_episode.get(episode_key)
        if scheduled is None:
            _fail("dataset_episode_not_scheduled", repr(episode_key))
        seen_episode_keys.add(episode_key)
        if (
            frame.source.cell_id != scheduled.cell_id
            or frame.source.scenario_family != scheduled.scenario_family
            or frame.source.split != scheduled.split
            or frame.source.configured_target_count
            != scheduled.configured_target_count
            or frame.source.configured_resource_count
            != scheduled.configured_resource_count
        ):
            _fail("dataset_frame_schedule_mismatch", repr(frame.frame_key))
        previous = previous_timestamp_by_episode.get(episode_key)
        if previous is not None:
            previous_index, previous_measurement, previous_arrival = previous
            if frame.source.frame_index <= previous_index:
                _fail("dataset_frame_index_not_increasing", repr(episode_key))
            if frame.source.measurement_timestamp_s < previous_measurement:
                _fail("dataset_measurement_timestamp_not_monotonic", repr(episode_key))
            if frame.source.arrival_timestamp_s < previous_arrival:
                _fail("dataset_arrival_timestamp_not_monotonic", repr(episode_key))
        previous_timestamp_by_episode[episode_key] = (
            frame.source.frame_index,
            frame.source.measurement_timestamp_s,
            frame.source.arrival_timestamp_s,
        )
    if seen_episode_keys != set(schedule_by_episode):
        _fail("dataset_schedule_episode_coverage_mismatch")

    labels_by_episode: dict[tuple[int, str], list[A1V3OfflineLabel]] = defaultdict(list)
    frames_by_episode: Counter[tuple[int, str]] = Counter()
    for frame, label in zip(online_frames, offline_labels, strict=True):
        frames_by_episode[frame.source.episode_key] += 1
        labels_by_episode[frame.source.episode_key].append(label)
    for episode_key, scheduled in schedule_by_episode.items():
        labels = labels_by_episode[episode_key]
        positive_count = sum(item.frame_class == "positive" for item in labels)
        negative_count = sum(item.frame_class == "negative" for item in labels)
        hard_count = sum(item.hard_negative for item in labels)
        if (
            frames_by_episode[episode_key] < scheduled.minimum_observable_frames
            or positive_count < scheduled.minimum_positive_frames
            or negative_count < scheduled.minimum_negative_frames
            or hard_count < scheduled.minimum_hard_negative_frames
        ):
            _fail("dataset_episode_minimum_not_met", repr(episode_key))

    positive_count = sum(item.frame_class == "positive" for item in offline_labels)
    negative_count = sum(item.frame_class == "negative" for item in offline_labels)
    hard_count = sum(item.hard_negative for item in offline_labels)
    if (
        positive_count != manifest.positive_frame_count
        or negative_count != manifest.negative_frame_count
        or hard_count != manifest.hard_negative_frame_count
    ):
        _fail("dataset_label_count_manifest_mismatch")
    identity_audit_counts = _offline_identity_audit_counts(offline_labels)
    if identity_audit_counts != {
        "complete": manifest.complete_identity_label_frame_count,
        "partial": manifest.partial_identity_label_frame_count,
        "empty": manifest.empty_identity_label_frame_count,
    }:
        _fail("dataset_offline_identity_audit_manifest_mismatch")
    actual_split_seeds = {
        split: tuple(
            sorted(
                {
                    frame.source.seed
                    for frame in online_frames
                    if frame.source.split == split
                }
            )
        )
        for split in A1_V3_SPLITS
    }
    if actual_split_seeds != dict(registry.split_seed_values):
        _fail("dataset_split_seed_registry_mismatch")

    actual_cell_counts: dict[str, dict[str, int]] = {}
    for cell in request.cells:
        cell_frames = [
            frame for frame in online_frames if frame.source.cell_id == cell.cell_id
        ]
        cell_labels = [
            label for label in offline_labels if label.cell_id == cell.cell_id
        ]
        actual_cell_counts[cell.cell_id] = {
            "episode_count": len(
                {frame.source.episode_key for frame in cell_frames}
            ),
            "frame_count": len(cell_frames),
            "positive_frame_count": sum(
                item.frame_class == "positive" for item in cell_labels
            ),
            "negative_frame_count": sum(
                item.frame_class == "negative" for item in cell_labels
            ),
            "hard_negative_frame_count": sum(
                item.hard_negative for item in cell_labels
            ),
        }
    manifest_cell_counts = {
        str(item["cell_id"]): {
            key: int(item[key])
            for key in (
                "episode_count",
                "frame_count",
                "positive_frame_count",
                "negative_frame_count",
                "hard_negative_frame_count",
            )
        }
        for item in manifest.cell_counts
    }
    if actual_cell_counts != manifest_cell_counts:
        _fail("dataset_cell_count_manifest_mismatch")


def _readiness_report(
    *,
    status: str,
    ready: bool,
    reason_codes: tuple[str, ...],
    request: A1V3FrozenRequest | None,
    registry: A1V3SeedRegistry | None,
    schedule: A1V3GenerationSchedule | None,
    source_generation_request: Any | None,
) -> A1V3ReadinessReport:
    return A1V3ReadinessReport(
        status=status,
        ready=ready,
        reason_codes=reason_codes,
        request_id=None if request is None else request.request_id,
        registry_id=None if registry is None else registry.registry_id,
        global_registry_id=(
            None if registry is None else registry.global_registry_id
        ),
        allocation_id=None if registry is None else registry.allocation_id,
        generator_config_id=(
            None if registry is None else registry.generator_config_id
        ),
        schedule_id=None if schedule is None else schedule.schedule_id,
        source_generation_request_id=(
            None
            if source_generation_request is None
            else source_generation_request.request_id
        ),
        source_generation_request_path=(
            A1_V3_SOURCE_GENERATION_REQUEST_LOGICAL_PATH
        ),
        source_generation_request_sha256=(
            None
            if source_generation_request is None
            else source_generation_request.file_sha256
        ),
        source_generation_request_ready=(
            ready and source_generation_request is not None
        ),
        cell_count=0 if schedule is None else len({item.cell_id for item in schedule.episodes}),
        episode_count=0 if schedule is None else len(schedule.episodes),
        unique_seed_count=(
            0 if registry is None else len(registry.assigned_seeds)
        ),
        minimum_observable_frame_count=(
            0 if schedule is None else schedule.minimum_observable_frames
        ),
        minimum_positive_frame_count=(
            0 if schedule is None else schedule.minimum_positive_frames
        ),
        minimum_negative_frame_count=(
            0 if schedule is None else schedule.minimum_negative_frames
        ),
        minimum_hard_negative_frame_count=(
            0 if schedule is None else schedule.minimum_hard_negative_frames
        ),
    )


def _false_permissions() -> dict[str, bool]:
    return {name: False for name in A1_V3_PERMISSION_FIELDS}


def _source_generation_request_permissions(ready: bool) -> dict[str, bool]:
    return {
        name: bool(ready and name == "source_generation_request")
        for name in A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS
    }


def _offline_identity_audit_counts(
    labels: Sequence[A1V3OfflineLabel],
) -> dict[str, int]:
    counts = {"complete": 0, "partial": 0, "empty": 0}
    for label in labels:
        present = (
            bool(label.truth_target_labels),
            bool(label.actor_labels),
            bool(label.object_labels),
            bool(label.center_global_track_labels),
        )
        if all(present):
            counts["complete"] += 1
        elif any(present):
            counts["partial"] += 1
        else:
            counts["empty"] += 1
    return counts


def compute_a1_v3_near_tie_target_margins(
    candidate_edges: Sequence[tuple[int, int]],
    candidate_edge_rule_costs: Sequence[float],
    *,
    target_count: int,
) -> tuple[A1V3NearTieTargetMargin, ...]:
    by_target: dict[int, list[tuple[float, tuple[int, int]]]] = defaultdict(list)
    for edge, cost in zip(
        candidate_edges, candidate_edge_rule_costs, strict=True
    ):
        by_target[edge[0]].append((float(cost), edge))
    margins: list[A1V3NearTieTargetMargin] = []
    for target_index in range(target_count):
        candidates = sorted(
            by_target.get(target_index, ()), key=lambda item: (item[0], item[1])
        )
        if len(candidates) < 2:
            continue
        best_cost, best_edge = candidates[0]
        second_cost, second_edge = candidates[1]
        absolute_gap = second_cost - best_cost
        relative_gap = absolute_gap / max(
            abs(best_cost), A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR
        )
        qualifies = (
            absolute_gap
            <= A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP + 1.0e-12
            and relative_gap
            <= A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP + 1.0e-12
        )
        margins.append(
            A1V3NearTieTargetMargin(
                target_index=target_index,
                best_edge=best_edge,
                second_edge=second_edge,
                best_rule_cost=best_cost,
                second_rule_cost=second_cost,
                absolute_gap=absolute_gap,
                relative_gap=relative_gap,
                qualifies=qualifies,
            )
        )
    return tuple(margins)


def _validate_permissions(
    value: Any,
    name: str,
    *,
    fields: Sequence[str] = A1_V3_PERMISSION_FIELDS,
) -> None:
    permissions = _mapping(value, name)
    _require_exact_keys(
        permissions, set(fields), "permission_fields_mismatch"
    )
    true_fields = [field for field in fields if permissions[field] is True]
    non_boolean = [
        field
        for field in fields
        if not isinstance(permissions[field], bool)
    ]
    if non_boolean:
        _fail("permission_value_not_boolean", repr(non_boolean))
    if true_fields:
        _fail("permission_true_forbidden", repr(true_fields))


def _validate_complete_selected_edges(
    edges: Sequence[tuple[int, int]],
    demand_slots: Sequence[int],
    label: str,
) -> None:
    resource_columns = [edge[1] for edge in edges]
    if len(set(resource_columns)) != len(resource_columns):
        _fail(f"{label}_selected_resource_duplicate")
    selected_counts = Counter(edge[0] for edge in edges)
    for target_index, demand in enumerate(demand_slots):
        if selected_counts[target_index] not in (0, int(demand)):
            _fail(f"{label}_demand_slot_incomplete", str(target_index))


def _reject_online_identity(value: Any, *, path: str = "online_frame") -> None:
    pending: list[tuple[Any, str]] = [(value, path)]
    while pending:
        current, current_path = pending.pop()
        if isinstance(current, Mapping):
            for raw_key, child in current.items():
                key = str(raw_key)
                normalized = key.lower()
                if key != "online_truth_use_count" and any(
                    marker in normalized for marker in _ONLINE_FORBIDDEN_KEY_MARKERS
                ):
                    _fail("online_identity_field_forbidden", f"{current_path}.{key}")
                pending.append((child, f"{current_path}.{key}"))
        elif isinstance(current, list):
            pending.extend(
                (child, f"{current_path}[{index}]")
                for index, child in enumerate(current)
            )
        elif isinstance(current, str):
            lowered = current.lower()
            if lowered.startswith(_ONLINE_FORBIDDEN_VALUE_PREFIXES) or (
                "global_track_id" in lowered
            ):
                _fail("online_identity_value_forbidden", current_path)


def _edge_sequence(
    value: Any,
    name: str,
    *,
    target_count: int,
    resource_count: int,
) -> tuple[tuple[int, int], ...]:
    edges = tuple(
        _edge(
            raw,
            f"{name}[{index}]",
            target_count=target_count,
            resource_count=resource_count,
        )
        for index, raw in enumerate(_list(value, name))
    )
    if tuple(sorted(edges)) != edges or len(set(edges)) != len(edges):
        _fail("edge_sequence_not_unique_sorted", name)
    return edges


def _edge(
    value: Any,
    name: str,
    *,
    target_count: int,
    resource_count: int,
) -> tuple[int, int]:
    raw = _list(value, name)
    if len(raw) != 2:
        _fail("edge_shape_invalid", name)
    row = _nonnegative_integer(raw[0], f"{name}[0]")
    column = _nonnegative_integer(raw[1], f"{name}[1]")
    if row >= target_count or column >= resource_count:
        _fail("edge_index_out_of_bounds", name)
    return (row, column)


def _reason_codes(value: Any, name: str) -> tuple[str, ...]:
    values = _unique_string_sequence(value, name)
    if not values or tuple(sorted(values)) != values:
        _fail("reason_codes_must_be_nonempty_unique_sorted", name)
    if any(_REASON_CODE.fullmatch(item) is None for item in values):
        _fail("reason_code_format_invalid", name)
    return values


def _seed_sequence(value: Any, name: str) -> tuple[int, ...]:
    seeds = tuple(
        _nonnegative_integer(item, f"{name}[{index}]")
        for index, item in enumerate(_list(value, name))
    )
    if tuple(sorted(seeds)) != seeds or len(set(seeds)) != len(seeds):
        _fail("seed_sequence_not_unique_sorted", name)
    return seeds


def _unique_string_sequence(value: Any, name: str) -> tuple[str, ...]:
    values = tuple(
        _nonempty_string(item, f"{name}[{index}]")
        for index, item in enumerate(_list(value, name))
    )
    if len(set(values)) != len(values):
        _fail("string_sequence_contains_duplicates", name)
    return values


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", name)
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("list_required", name)
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], code: str
) -> None:
    actual = set(value)
    if actual != expected:
        _fail(
            code,
            f"missing={sorted(expected - actual)!r}, extra={sorted(actual - expected)!r}",
        )


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _fail("nonempty_trimmed_string_required", name)
    return value


def _choice(value: Any, choices: Sequence[str], name: str) -> str:
    result = _nonempty_string(value, name)
    if result not in choices:
        _fail("unsupported_choice", f"{name}={result!r}")
    return result


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        _fail("boolean_required", name)
    return value


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("nonnegative_integer_required", name)
    return value


def _positive_integer(value: Any, name: str) -> int:
    result = _nonnegative_integer(value, name)
    if result < 1:
        _fail("positive_integer_required", name)
    return result


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("finite_number_required", name)
    result = float(value)
    if not isfinite(result):
        _fail("finite_number_required", name)
    return result


def _sha256_value(value: Any, name: str) -> str:
    result = _nonempty_string(value, name)
    if len(result) != 64 or not set(result).issubset(_LOWER_HEX):
        _fail("sha256_required", name)
    return result


def _git_commit(value: Any, name: str) -> str:
    result = _nonempty_string(value, name)
    if len(result) not in (40, 64) or not set(result).issubset(_LOWER_HEX):
        _fail("git_commit_required", name)
    return result


def _safe_logical_path(value: Any, name: str) -> str:
    result = _nonempty_string(value, name)
    path = Path(result)
    if path.is_absolute() or ".." in path.parts or result.endswith("/"):
        _fail("safe_relative_logical_path_required", name)
    return result


def _parse_json_object(value: str | bytes, name: str) -> Mapping[str, Any]:
    try:
        text = value.decode("utf-8") if isinstance(value, bytes) else value
        parsed = json.loads(text, object_pairs_hook=_strict_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("json_parse_failed", f"{name}: {exc}")
    return _mapping(parsed, name)


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key", key)
        result[key] = value
    return result


def _read_json_file(path: str | Path, name: str) -> tuple[Mapping[str, Any], str]:
    file_path = Path(path)
    content = _read_file_bytes(file_path, f"{name}_read_failed")
    return _parse_json_object(content, name), sha256(content).hexdigest()


def _read_file_bytes(path: Path, code: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        _fail(code, f"{path}: {exc}")


def _file_sha256(path: Path, code: str) -> str:
    return sha256(_read_file_bytes(path, code)).hexdigest()


def _reject_symlink(path: Path, code: str) -> None:
    if path.is_symlink():
        _fail(code, str(path))


def _parse_canonical_jsonl(
    content: bytes,
    name: str,
    parser: Any,
) -> tuple[Any, ...]:
    if not content or not content.endswith(b"\n"):
        _fail("canonical_jsonl_final_newline_required", name)
    items: list[Any] = []
    for line_number, line in enumerate(content.splitlines(keepends=True), start=1):
        if line == b"\n":
            _fail("canonical_jsonl_blank_line_forbidden", f"{name}:{line_number}")
        raw = _parse_json_object(line, f"{name}:{line_number}")
        if canonical_json_line(raw) != line:
            _fail("canonical_jsonl_encoding_mismatch", f"{name}:{line_number}")
        try:
            items.append(parser(raw))
        except A1V3DataContractError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            _fail("jsonl_record_validation_failed", f"{name}:{line_number}: {exc}")
    return tuple(items)


def _fail(code: str, message: str = "") -> None:
    raise A1V3DataContractError(code, message)


def build_a1_v3_contract_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate D3 A1 v3 source-generation request readiness or "
            "generated data"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    readiness = subparsers.add_parser(
        "readiness",
        help="validate the frozen plan and request-readiness artifact",
    )
    _add_common_contract_arguments(readiness)
    readiness.add_argument(
        "--generator-config",
        type=Path,
        default=DEFAULT_A1_V3_GENERATOR_CONFIG_PATH,
    )
    readiness.add_argument(
        "--global-registry",
        type=Path,
        default=DEFAULT_A1_V3_GLOBAL_SEED_REGISTRY_PATH,
    )
    readiness.add_argument(
        "--registry", type=Path, default=DEFAULT_A1_V3_MAIN_SEED_REGISTRY_PATH
    )
    readiness.add_argument(
        "--schedule", type=Path, default=DEFAULT_A1_V3_GENERATION_SCHEDULE_PATH
    )
    readiness.add_argument(
        "--source-generation-request",
        type=Path,
        default=DEFAULT_A1_V3_SOURCE_GENERATION_REQUEST_PATH,
    )
    readiness.add_argument(
        "--sidecar-classification-policy",
        type=Path,
        default=DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH,
    )
    dataset = subparsers.add_parser(
        "validate-dataset", help="strictly load generated online/offline artifacts"
    )
    _add_common_contract_arguments(dataset)
    dataset.add_argument("--registry", type=Path, required=True)
    dataset.add_argument("--schedule", type=Path, required=True)
    dataset.add_argument("--generator-config", type=Path, required=True)
    dataset.add_argument("--global-registry", type=Path, required=True)
    dataset.add_argument("--dataset", type=Path, required=True)
    return parser


def _add_common_contract_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--request", type=Path, default=DEFAULT_A1_V3_REQUEST_PATH)
    parser.add_argument(
        "--exclusion-registry",
        type=Path,
        default=DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH,
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_A1_V3_DATA_CONTRACT_PATH)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_a1_v3_contract_parser().parse_args(argv)
    if args.command == "readiness":
        report = validate_a1_v3_pre_generation_readiness(
            request_path=args.request,
            exclusion_registry_path=args.exclusion_registry,
            contract_path=args.contract,
            generator_config_path=args.generator_config,
            global_registry_path=args.global_registry,
            registry_path=args.registry,
            schedule_path=args.schedule,
            source_generation_request_path=args.source_generation_request,
            sidecar_classification_policy_path=(
                args.sidecar_classification_policy
            ),
        )
        print(json.dumps(report.to_dict(), ensure_ascii=True, indent=2, sort_keys=True))
        if report.ready:
            return 0
        return 2 if report.status == "request_only" else 1
    try:
        dataset = load_a1_v3_audit_dataset(
            args.dataset,
            request_path=args.request,
            exclusion_registry_path=args.exclusion_registry,
            contract_path=args.contract,
            registry_path=args.registry,
            schedule_path=args.schedule,
            generator_config_path=args.generator_config,
            global_registry_path=args.global_registry,
        )
    except A1V3DataContractError as exc:
        print(
            json.dumps(
                {
                    "schema_version": A1_V3_READINESS_REPORT_SCHEMA_V1,
                    "status": "fail_closed",
                    "ready": False,
                    "reason_codes": [exc.code],
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "schema_version": A1_V3_READINESS_REPORT_SCHEMA_V1,
                "status": "dataset_validated_untrained_not_admitted",
                "ready": True,
                "dataset_id": dataset.manifest.dataset_id,
                "cell_count": dataset.manifest.cell_count,
                "episode_count": dataset.manifest.episode_count,
                "frame_count": dataset.manifest.frame_count,
                "online_truth_use_count": 0,
                "trainer_identity_labels_exposed": False,
                "permissions": _false_permissions(),
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
