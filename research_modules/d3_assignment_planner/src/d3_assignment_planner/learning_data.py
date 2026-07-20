"""Reproducible, identity-free datasets for optional D3 learning research."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import sqlite3
import tempfile
from types import MappingProxyType
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

from .learning import EDGE_FEATURE_NAMES, build_candidate_edge_batch
from .models import AssignmentPlan, PlannerConfig, ResourceState, TargetTrack
from .planner import AssignmentPlanner


LEARNING_DATASET_SCHEMA_V1 = "d3_learning_dataset_v1"
LEARNING_DATASET_SPLIT_POLICY_V1 = "d3_scenario_seed_group_split_v1"
LEARNING_DATASET_SCHEMA_V2 = "d3_learning_dataset_v2"
LEARNING_DATASET_SPLIT_POLICY_V2 = "d3_numeric_seed_atomic_split_v2"
DATASET_MANIFEST_FILENAME = "dataset_manifest.json"
DATASET_FRAMES_FILENAME = "frames.jsonl"
DATASET_SPLITS = ("train", "validation", "test")
UNASSIGNED_DATASET_SPLIT = "unassigned"
DEFAULT_DATASET_SPLIT_SEED = 20260720
DEFAULT_VALIDATION_FRACTION = 0.2
DEFAULT_TEST_FRACTION = 0.2
DEFAULT_MINIMUM_UNSEEN_SEED_COUNT = 20

_OFFLINE_REWARD_FIELDS = frozenset(
    {
        "high_threat_coverage",
        "rule_total_cost",
        "unmet_demand_slots",
        "reassignment_churn",
        "plan_expired",
        "safety_rejections",
    }
)
_LEARNING_FRAME_FIELDS = frozenset(
    {
        "schema_version",
        "scenario_version",
        "seed",
        "episode",
        "frame_index",
        "timestamp_s",
        "split",
        "anonymous_targets",
        "anonymous_resources",
        "candidate_edge_indices",
        "candidate_features",
        "action_mask",
        "rule_cost_matrix",
        "rule_costs",
        "unassigned_costs",
        "rule_selected_edges",
        "previous_selected_edges",
        "previous_plan_version",
        "feedback_result",
        "hysteresis_result",
        "hold_label",
        "replan_label",
        "advice_allowed",
        "target_threat_scores",
        "target_demand_slots",
        "hard_reject_reason_counts",
        "reward_components",
    }
)


@dataclass(frozen=True)
class OfflineRewardComponents:
    """Auditable raw terms used by BC diagnostics and PPO reward shaping."""

    high_threat_coverage: float
    rule_total_cost: float
    unmet_demand_slots: int
    reassignment_churn: int
    plan_expired: int
    safety_rejections: int

    def __post_init__(self) -> None:
        values = (self.high_threat_coverage, self.rule_total_cost)
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("reward components must be finite")
        if not 0.0 <= float(self.high_threat_coverage) <= 1.0:
            raise ValueError("high_threat_coverage must be in [0, 1]")
        if float(self.rule_total_cost) < 0.0:
            raise ValueError("rule_total_cost must be non-negative")
        for name in (
            "unmet_demand_slots",
            "reassignment_churn",
            "plan_expired",
            "safety_rejections",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")

    def weighted_total(
        self,
        *,
        coverage_weight: float = 2.0,
        cost_weight: float = 0.05,
        unmet_weight: float = 2.0,
        churn_weight: float = 0.5,
        expiry_weight: float = 2.0,
        rejection_weight: float = 2.0,
    ) -> float:
        """Return the explicit offline reward used by the native PPO pipeline."""

        return float(
            coverage_weight * self.high_threat_coverage
            - cost_weight * self.rule_total_cost
            - unmet_weight * self.unmet_demand_slots
            - churn_weight * self.reassignment_churn
            - expiry_weight * self.plan_expired
            - rejection_weight * self.safety_rejections
        )

    def to_dict(self) -> dict[str, float | int]:
        return {
            "high_threat_coverage": float(self.high_threat_coverage),
            "rule_total_cost": float(self.rule_total_cost),
            "unmet_demand_slots": int(self.unmet_demand_slots),
            "reassignment_churn": int(self.reassignment_churn),
            "plan_expired": int(self.plan_expired),
            "safety_rejections": int(self.safety_rejections),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OfflineRewardComponents":
        if not isinstance(value, Mapping) or set(value) != _OFFLINE_REWARD_FIELDS:
            raise ValueError("offline reward component fields do not match schema v2")
        return cls(
            high_threat_coverage=float(value["high_threat_coverage"]),
            rule_total_cost=float(value["rule_total_cost"]),
            unmet_demand_slots=int(value["unmet_demand_slots"]),
            reassignment_churn=int(value["reassignment_churn"]),
            plan_expired=int(value["plan_expired"]),
            safety_rejections=int(value["safety_rejections"]),
        )


@dataclass(frozen=True)
class LearningFrameRecord:
    """One planner frame with sparse actions and no operational identity fields."""

    scenario_version: str
    seed: int
    episode: str
    frame_index: int
    timestamp_s: float
    split: str
    anonymous_targets: tuple[Mapping[str, Any], ...]
    anonymous_resources: tuple[Mapping[str, Any], ...]
    candidate_edge_indices: tuple[tuple[int, int], ...]
    candidate_features: np.ndarray
    action_mask: np.ndarray
    rule_cost_matrix: np.ndarray
    rule_costs: np.ndarray
    unassigned_costs: np.ndarray
    rule_selected_edges: tuple[tuple[int, int], ...]
    previous_selected_edges: tuple[tuple[int, int], ...]
    previous_plan_version: int
    feedback_result: str
    hysteresis_result: str
    hold_label: bool
    replan_label: bool
    advice_allowed: bool
    target_threat_scores: tuple[float, ...]
    target_demand_slots: tuple[int, ...]
    hard_reject_reason_counts: Mapping[str, int]
    reward_components: OfflineRewardComponents

    def __post_init__(self) -> None:
        scenario_version = str(self.scenario_version).strip()
        episode = str(self.episode).strip()
        split = str(self.split).strip().lower()
        if not scenario_version or not episode:
            raise ValueError("scenario_version and episode are required")
        if split not in (*DATASET_SPLITS, UNASSIGNED_DATASET_SPLIT):
            raise ValueError(f"unsupported dataset split: {split}")
        seed = int(self.seed)
        if seed < 0:
            raise ValueError("dataset seed must be non-negative")
        if int(self.frame_index) < 0 or int(self.previous_plan_version) < 0:
            raise ValueError("frame and plan versions must be non-negative")
        if not isfinite(float(self.timestamp_s)):
            raise ValueError("timestamp_s must be finite")

        target_count = len(self.anonymous_targets)
        resource_count = len(self.anonymous_resources)
        features = np.asarray(self.candidate_features, dtype=np.float32)
        mask = np.asarray(self.action_mask, dtype=bool)
        matrix = np.asarray(self.rule_cost_matrix, dtype=float)
        rule_costs = np.asarray(self.rule_costs, dtype=float).reshape(-1)
        unassigned = np.asarray(self.unassigned_costs, dtype=float).reshape(-1)
        if features.shape != (len(self.candidate_edge_indices), len(EDGE_FEATURE_NAMES)):
            raise ValueError("candidate_features have the wrong sparse-edge shape")
        if mask.shape != (target_count, resource_count):
            raise ValueError("action_mask has the wrong target-resource shape")
        if matrix.shape != mask.shape:
            raise ValueError("rule_cost_matrix must match action_mask")
        if rule_costs.shape != (len(self.candidate_edge_indices),):
            raise ValueError("rule_costs must match candidate edges")
        if unassigned.shape != (target_count,):
            raise ValueError("unassigned_costs must match target count")
        if len(self.target_threat_scores) != target_count:
            raise ValueError("target_threat_scores must match target count")
        if len(self.target_demand_slots) != target_count:
            raise ValueError("target_demand_slots must match target count")
        if not np.all(np.isfinite(features)) or not np.all(np.isfinite(matrix)):
            raise ValueError("dataset feature and cost matrices must be finite")
        if not np.all(np.isfinite(rule_costs)) or not np.all(np.isfinite(unassigned)):
            raise ValueError("dataset costs must be finite")

        candidate_set = set(self.candidate_edge_indices)
        for edge in candidate_set | set(self.rule_selected_edges) | set(
            self.previous_selected_edges
        ):
            row, column = edge
            if not (0 <= row < target_count and 0 <= column < resource_count):
                raise ValueError("edge index lies outside the frame matrix")
        if candidate_set != set(zip(*np.nonzero(mask))):
            raise ValueError("candidate edges must exactly match the deterministic mask")
        if not set(self.rule_selected_edges).issubset(candidate_set):
            raise ValueError("rule-selected edges must be allowed by the action mask")

        _validate_anonymous_entities(self.anonymous_targets, "target")
        _validate_anonymous_entities(self.anonymous_resources, "resource")
        object.__setattr__(self, "scenario_version", scenario_version)
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "episode", episode)
        object.__setattr__(self, "split", split)
        object.__setattr__(self, "candidate_features", features)
        object.__setattr__(self, "action_mask", mask)
        object.__setattr__(self, "rule_cost_matrix", matrix)
        object.__setattr__(self, "rule_costs", rule_costs)
        object.__setattr__(self, "unassigned_costs", unassigned)

    @property
    def episode_group(self) -> tuple[str, int, str]:
        return (self.scenario_version, int(self.seed), self.episode)

    @property
    def seed_group(self) -> int:
        """Return the v2 split identity, global across scenario and scale."""

        return int(self.seed)

    @property
    def selected_edge_labels(self) -> np.ndarray:
        selected = set(self.rule_selected_edges)
        return np.asarray(
            [edge in selected for edge in self.candidate_edge_indices],
            dtype=np.float32,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LEARNING_DATASET_SCHEMA_V2,
            "scenario_version": self.scenario_version,
            "seed": int(self.seed),
            "episode": self.episode,
            "frame_index": int(self.frame_index),
            "timestamp_s": float(self.timestamp_s),
            "split": self.split,
            "anonymous_targets": [dict(value) for value in self.anonymous_targets],
            "anonymous_resources": [dict(value) for value in self.anonymous_resources],
            "candidate_edge_indices": [list(edge) for edge in self.candidate_edge_indices],
            "candidate_features": self.candidate_features.tolist(),
            "action_mask": self.action_mask.tolist(),
            "rule_cost_matrix": self.rule_cost_matrix.tolist(),
            "rule_costs": self.rule_costs.tolist(),
            "unassigned_costs": self.unassigned_costs.tolist(),
            "rule_selected_edges": [list(edge) for edge in self.rule_selected_edges],
            "previous_selected_edges": [list(edge) for edge in self.previous_selected_edges],
            "previous_plan_version": int(self.previous_plan_version),
            "feedback_result": str(self.feedback_result),
            "hysteresis_result": str(self.hysteresis_result),
            "hold_label": bool(self.hold_label),
            "replan_label": bool(self.replan_label),
            "advice_allowed": bool(self.advice_allowed),
            "target_threat_scores": [float(value) for value in self.target_threat_scores],
            "target_demand_slots": [int(value) for value in self.target_demand_slots],
            "hard_reject_reason_counts": {
                str(key): int(value)
                for key, value in sorted(self.hard_reject_reason_counts.items())
            },
            "reward_components": self.reward_components.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LearningFrameRecord":
        if not isinstance(value, Mapping):
            raise ValueError("D3 learning dataset frame must be a JSON object")
        _reject_identity_fields(value)
        if set(value) != _LEARNING_FRAME_FIELDS:
            raise ValueError(
                "learning frame fields do not match schema v2; "
                "extensions require a new schema version"
            )
        schema_version = value.get("schema_version")
        if schema_version != LEARNING_DATASET_SCHEMA_V2:
            raise ValueError(
                "unsupported D3 learning dataset frame schema: "
                f"{schema_version!r}; {LEARNING_DATASET_SCHEMA_V2} is required"
            )
        return cls(
            scenario_version=str(value["scenario_version"]),
            seed=int(value["seed"]),
            episode=str(value["episode"]),
            frame_index=int(value["frame_index"]),
            timestamp_s=float(value["timestamp_s"]),
            split=str(value["split"]),
            anonymous_targets=tuple(dict(item) for item in value["anonymous_targets"]),
            anonymous_resources=tuple(
                dict(item) for item in value["anonymous_resources"]
            ),
            candidate_edge_indices=tuple(
                (int(item[0]), int(item[1]))
                for item in value["candidate_edge_indices"]
            ),
            candidate_features=np.asarray(value["candidate_features"], dtype=np.float32),
            action_mask=np.asarray(value["action_mask"], dtype=bool),
            rule_cost_matrix=np.asarray(value["rule_cost_matrix"], dtype=float),
            rule_costs=np.asarray(value["rule_costs"], dtype=float),
            unassigned_costs=np.asarray(value["unassigned_costs"], dtype=float),
            rule_selected_edges=tuple(
                (int(item[0]), int(item[1])) for item in value["rule_selected_edges"]
            ),
            previous_selected_edges=tuple(
                (int(item[0]), int(item[1]))
                for item in value["previous_selected_edges"]
            ),
            previous_plan_version=int(value["previous_plan_version"]),
            feedback_result=str(value["feedback_result"]),
            hysteresis_result=str(value["hysteresis_result"]),
            hold_label=bool(value["hold_label"]),
            replan_label=bool(value["replan_label"]),
            advice_allowed=bool(value["advice_allowed"]),
            target_threat_scores=tuple(float(item) for item in value["target_threat_scores"]),
            target_demand_slots=tuple(int(item) for item in value["target_demand_slots"]),
            hard_reject_reason_counts={
                str(key): int(item)
                for key, item in value["hard_reject_reason_counts"].items()
            },
            reward_components=OfflineRewardComponents.from_dict(
                value["reward_components"]
            ),
        )


@dataclass(frozen=True)
class LearningDatasetManifest:
    schema_version: str
    split_policy_version: str
    feature_names: tuple[str, ...]
    split_hash: str
    frames_sha256: str
    frame_count: int
    episode_count: int
    unique_seed_count: int
    split_frame_counts: Mapping[str, int]
    split_episode_counts: Mapping[str, int]
    split_seed_values: Mapping[str, tuple[int, ...]]
    split_seed: int
    validation_fraction: float
    test_fraction: float
    minimum_unseen_seed_count: int
    unseen_test_seed_count: int
    source_kind: str

    def __post_init__(self) -> None:
        if self.schema_version != LEARNING_DATASET_SCHEMA_V2:
            raise ValueError("unsupported D3 learning dataset manifest schema")
        if self.split_policy_version != LEARNING_DATASET_SPLIT_POLICY_V2:
            raise ValueError("unsupported D3 learning dataset split policy")
        if self.feature_names != EDGE_FEATURE_NAMES:
            raise ValueError("dataset feature schema does not match this D3 build")
        if len(self.split_hash) != 64 or len(self.frames_sha256) != 64:
            raise ValueError("dataset split and frame SHA256 values are required")
        lowercase_hex = frozenset("0123456789abcdef")
        if (
            not set(self.split_hash).issubset(lowercase_hex)
            or not set(self.frames_sha256).issubset(lowercase_hex)
        ):
            raise ValueError("dataset hashes must be lowercase hexadecimal SHA256")
        if self.frame_count < 1 or self.episode_count < 1 or self.unique_seed_count < 3:
            raise ValueError("dataset manifest counts are invalid")
        if not str(self.source_kind).strip():
            raise ValueError("dataset source_kind is required")
        _validate_split_parameters(
            validation_fraction=self.validation_fraction,
            test_fraction=self.test_fraction,
            minimum_unseen_seed_count=self.minimum_unseen_seed_count,
        )
        seed_sets = {
            split: set(int(seed) for seed in self.split_seed_values.get(split, ()))
            for split in DATASET_SPLITS
        }
        if any(
            tuple(self.split_seed_values.get(split, ()))
            != tuple(sorted(seed_sets[split]))
            for split in DATASET_SPLITS
        ):
            raise ValueError("dataset manifest split seed values must be unique and sorted")
        if any(not values for values in seed_sets.values()):
            raise ValueError("dataset manifest requires non-empty train/validation/test seeds")
        if any(
            seed_sets[left] & seed_sets[right]
            for index, left in enumerate(DATASET_SPLITS)
            for right in DATASET_SPLITS[index + 1 :]
        ):
            raise ValueError("dataset manifest seed values overlap across splits")
        if len(set().union(*seed_sets.values())) != self.unique_seed_count:
            raise ValueError("dataset manifest unique seed count is inconsistent")
        if len(seed_sets["test"]) != self.unseen_test_seed_count:
            raise ValueError("dataset manifest unseen test seed count is inconsistent")
        if self.unseen_test_seed_count < self.minimum_unseen_seed_count:
            raise ValueError("dataset manifest has insufficient unseen test seeds")
        frame_counts = tuple(
            int(self.split_frame_counts.get(split, 0)) for split in DATASET_SPLITS
        )
        episode_counts = tuple(
            int(self.split_episode_counts.get(split, 0)) for split in DATASET_SPLITS
        )
        if any(count < 1 for count in frame_counts) or sum(frame_counts) != self.frame_count:
            raise ValueError("dataset manifest split frame counts are inconsistent")
        if any(count < 1 for count in episode_counts) or sum(episode_counts) != self.episode_count:
            raise ValueError("dataset manifest split episode counts are inconsistent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "split_policy_version": self.split_policy_version,
            "feature_names": list(self.feature_names),
            "split_hash": self.split_hash,
            "frames_sha256": self.frames_sha256,
            "frame_count": int(self.frame_count),
            "episode_count": int(self.episode_count),
            "unique_seed_count": int(self.unique_seed_count),
            "split_frame_counts": {
                split: int(self.split_frame_counts.get(split, 0))
                for split in DATASET_SPLITS
            },
            "split_episode_counts": {
                split: int(self.split_episode_counts.get(split, 0))
                for split in DATASET_SPLITS
            },
            "split_seed_values": {
                split: [int(seed) for seed in self.split_seed_values.get(split, ())]
                for split in DATASET_SPLITS
            },
            "split_policy": {
                "unit": "whole_episode_grouped_by_numeric_seed_across_scenarios",
                "shared_seed_values_atomic_across_scenarios": True,
                "split_seed": int(self.split_seed),
                "validation_fraction": float(self.validation_fraction),
                "test_fraction": float(self.test_fraction),
                "minimum_unseen_seed_count": int(self.minimum_unseen_seed_count),
                "unseen_test_seed_count": int(self.unseen_test_seed_count),
            },
            "source_kind": self.source_kind,
            "identity_policy": "anonymous_ordinal_tokens_no_truth_metadata",
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LearningDatasetManifest":
        if value.get("identity_policy") != "anonymous_ordinal_tokens_no_truth_metadata":
            raise ValueError("unsupported D3 learning dataset identity policy")
        split_policy = value["split_policy"]
        if not isinstance(split_policy, Mapping):
            raise ValueError("D3 learning dataset split policy must be a JSON object")
        expected_policy_fields = {
            "unit",
            "shared_seed_values_atomic_across_scenarios",
            "split_seed",
            "validation_fraction",
            "test_fraction",
            "minimum_unseen_seed_count",
            "unseen_test_seed_count",
        }
        if set(split_policy) != expected_policy_fields:
            raise ValueError("D3 learning dataset split policy fields are invalid")
        if split_policy.get("unit") != "whole_episode_grouped_by_numeric_seed_across_scenarios":
            raise ValueError("unsupported D3 learning dataset split unit")
        if split_policy.get("shared_seed_values_atomic_across_scenarios") is not True:
            raise ValueError("numeric seed atomicity is required across all scenarios")
        return cls(
            schema_version=str(value["schema_version"]),
            split_policy_version=str(value["split_policy_version"]),
            feature_names=tuple(str(item) for item in value["feature_names"]),
            split_hash=str(value["split_hash"]),
            frames_sha256=str(value["frames_sha256"]),
            frame_count=int(value["frame_count"]),
            episode_count=int(value["episode_count"]),
            unique_seed_count=int(value["unique_seed_count"]),
            split_frame_counts={
                str(key): int(item)
                for key, item in value["split_frame_counts"].items()
            },
            split_episode_counts={
                str(key): int(item)
                for key, item in value["split_episode_counts"].items()
            },
            split_seed_values={
                str(key): tuple(int(item) for item in items)
                for key, items in value["split_seed_values"].items()
            },
            split_seed=int(split_policy["split_seed"]),
            validation_fraction=float(split_policy["validation_fraction"]),
            test_fraction=float(split_policy["test_fraction"]),
            minimum_unseen_seed_count=int(split_policy["minimum_unseen_seed_count"]),
            unseen_test_seed_count=int(split_policy["unseen_test_seed_count"]),
            source_kind=str(value["source_kind"]),
        )


def assign_episode_split(
    scenario_version: str,
    seed: int,
    episode: str | int,
    *,
    seed_values: Iterable[int],
    split_seed: int = DEFAULT_DATASET_SPLIT_SEED,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    minimum_unseen_seed_count: int = 1,
) -> str:
    """Resolve one episode from a complete numeric-seed catalog under v2."""

    if not str(scenario_version).strip() or not str(episode).strip():
        raise ValueError("scenario_version and episode are required")
    split_by_seed = assign_seed_splits(
        seed_values,
        split_seed=split_seed,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
        minimum_unseen_seed_count=minimum_unseen_seed_count,
    )
    try:
        return split_by_seed[int(seed)]
    except KeyError as exc:
        raise ValueError("seed is absent from the complete dataset seed catalog") from exc


def assign_seed_splits(
    seed_values: Iterable[int],
    *,
    split_seed: int = DEFAULT_DATASET_SPLIT_SEED,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    minimum_unseen_seed_count: int = 1,
) -> Mapping[int, str]:
    """Allocate exact split counts over unique numeric seeds, independent of input order."""

    _validate_split_parameters(
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
        minimum_unseen_seed_count=minimum_unseen_seed_count,
    )
    seeds = sorted({int(seed) for seed in seed_values})
    if any(seed < 0 for seed in seeds):
        raise ValueError("dataset seeds must be non-negative")
    if len(seeds) < 3:
        raise ValueError("at least three unique numeric seeds are required for dataset splits")
    ordered = sorted(
        seeds,
        key=lambda seed: (
            sha256(
                f"{LEARNING_DATASET_SPLIT_POLICY_V2}|{int(split_seed)}\0{seed}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            seed,
        ),
    )
    test_count = max(1, min(len(seeds) - 2, round(len(seeds) * test_fraction)))
    validation_count = max(
        1,
        min(
            len(seeds) - test_count - 1,
            round(len(seeds) * validation_fraction),
        ),
    )
    if test_count < int(minimum_unseen_seed_count):
        raise ValueError(
            "test split has fewer unique numeric seeds than the declared unseen minimum"
        )
    split_by_seed = {
        seed: (
            "test"
            if index < test_count
            else "validation"
            if index < test_count + validation_count
            else "train"
        )
        for index, seed in enumerate(ordered)
    }
    return MappingProxyType(split_by_seed)


def validate_split_integrity(
    records: Iterable[LearningFrameRecord],
    *,
    minimum_unseen_seed_count: int = 1,
) -> None:
    """Reject frame/episode splitting and all cross-split seed leakage."""

    if int(minimum_unseen_seed_count) < 1:
        raise ValueError("minimum unseen seed count must be positive")
    episode_splits: dict[tuple[str, int, str], str] = {}
    seed_splits: dict[int, str] = {}
    seen_frames: set[tuple[str, int, str, int]] = set()
    for record in records:
        if record.split == UNASSIGNED_DATASET_SPLIT:
            raise ValueError("unassigned staging records are not a finalized dataset")
        frame_key = (*record.episode_group, int(record.frame_index))
        if frame_key in seen_frames:
            raise ValueError(f"duplicate dataset frame: {frame_key}")
        seen_frames.add(frame_key)
        prior_episode = episode_splits.setdefault(record.episode_group, record.split)
        if prior_episode != record.split:
            raise ValueError("one episode appears in multiple dataset splits")
        prior_seed = seed_splits.setdefault(record.seed_group, record.split)
        if prior_seed != record.split:
            raise ValueError("one numeric seed appears in multiple dataset splits")
    if len(seed_splits) < 3:
        raise ValueError("at least three unique numeric seeds are required")
    if set(seed_splits.values()) != set(DATASET_SPLITS):
        raise ValueError("train, validation, and test must all contain numeric seeds")
    test_seed_count = sum(split == "test" for split in seed_splits.values())
    if test_seed_count < int(minimum_unseen_seed_count):
        raise ValueError("test split has insufficient declared unseen numeric seeds")


def compute_split_hash(records: Iterable[LearningFrameRecord]) -> str:
    items = tuple(records)
    validate_split_integrity(items)
    seed_splits = {
        int(record.seed): record.split
        for record in items
    }
    episode_splits = sorted(
        {
            (record.scenario_version, int(record.seed), record.episode, record.split)
            for record in items
        }
    )
    return _split_hash_from_metadata(seed_splits, episode_splits)


def build_learning_frame_record(
    *,
    scenario_version: str,
    seed: int,
    episode: str | int,
    frame_index: int,
    timestamp_s: float,
    matrix_result: Any,
    tracks: Sequence[TargetTrack],
    resources: Sequence[ResourceState],
    plan: AssignmentPlan,
    previous_plan: AssignmentPlan | None,
    feedback_result: str | None = None,
    advice_interval: int = 5,
) -> LearningFrameRecord:
    """Convert one rule-planner frame into the identity-free dataset contract."""

    if advice_interval < 1:
        raise ValueError("advice_interval must be positive")
    previous_version = 0 if previous_plan is None else int(previous_plan.version)
    batch = build_candidate_edge_batch(
        matrix_result,
        list(tracks),
        list(resources),
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
        previous_plan=previous_plan,
    )
    target_index = {value: index for index, value in enumerate(matrix_result.target_ids)}
    resource_index = {
        value: index for index, value in enumerate(matrix_result.resource_ids)
    }

    def plan_edges(value: AssignmentPlan | None) -> tuple[tuple[int, int], ...]:
        if value is None:
            return ()
        edges = {
            (target_index[item.target_id], resource_index[item.resource_id])
            for item in value.assignments
            if item.target_id in target_index and item.resource_id in resource_index
        }
        return tuple(sorted(edges))

    selected_edges = plan_edges(plan)
    previous_edges = plan_edges(previous_plan)
    required = tuple(track.effective_demand.required_resource_count for track in tracks)
    assigned_by_target = {
        row: sum(1 for edge in selected_edges if edge[0] == row)
        for row in range(len(tracks))
    }
    high_threat_rows = [
        index for index, track in enumerate(tracks) if float(track.threat_score) >= 0.7
    ]
    if high_threat_rows:
        high_threat_coverage = float(
            np.mean(
                [
                    min(1.0, assigned_by_target[row] / max(1, required[row]))
                    for row in high_threat_rows
                ]
            )
        )
    else:
        high_threat_coverage = 1.0
    unmet = sum(
        max(0, required[row] - assigned_by_target[row]) for row in range(len(tracks))
    )
    churn = len(set(selected_edges).symmetric_difference(previous_edges))
    decision = str(plan.decision_state)
    hold_label = decision.startswith("held") or decision == "unchanged"
    replan_label = previous_plan is not None and bool(plan.changed) and not hold_label
    hard_counts = _hard_reject_counts(matrix_result.reject_reasons)
    reward = OfflineRewardComponents(
        high_threat_coverage=high_threat_coverage,
        rule_total_cost=max(0.0, float(plan.total_cost)),
        unmet_demand_slots=unmet,
        reassignment_churn=churn,
        plan_expired=int("stale" in decision or "expired" in decision),
        safety_rejections=int(bool(plan.duplicate_terminal_lock_risk)),
    )
    return LearningFrameRecord(
        scenario_version=scenario_version,
        seed=int(seed),
        episode=str(episode),
        frame_index=int(frame_index),
        timestamp_s=float(timestamp_s),
        split=UNASSIGNED_DATASET_SPLIT,
        anonymous_targets=tuple(
            {
                "token": f"target_{index:04d}",
                "threat_score": float(track.threat_score),
                "covariance_squashed": _squash_nonnegative(track.covariance),
                "window_cost": float(track.window_cost),
                "required_resource_count": int(
                    track.effective_demand.required_resource_count
                ),
                "primary_resource_count": int(
                    track.effective_demand.primary_resource_count
                ),
                "assignable": bool(track.assignable),
            }
            for index, track in enumerate(tracks)
        ),
        anonymous_resources=tuple(
            {
                "token": f"resource_{index:04d}",
                "available": resource.status == "available"
                and not resource.operator_hold,
                "health_score": float(resource.health_score),
                "energy_fraction": float(resource.energy_fraction),
                "availability_score": float(resource.availability_score),
                "current_load": float(resource.current_load),
                "assignment_capacity": int(resource.assignment_capacity),
            }
            for index, resource in enumerate(resources)
        ),
        candidate_edge_indices=batch.edge_indices,
        candidate_features=batch.features,
        action_mask=batch.action_mask.mask,
        rule_cost_matrix=np.asarray(matrix_result.matrix, dtype=float).copy(),
        rule_costs=batch.rule_costs,
        unassigned_costs=np.asarray(matrix_result.unassigned_costs, dtype=float),
        rule_selected_edges=selected_edges,
        previous_selected_edges=previous_edges,
        previous_plan_version=previous_version,
        feedback_result=(
            str(feedback_result)
            if feedback_result is not None
            else str(plan.terminal_feedback_state or "none")
        ),
        hysteresis_result=decision,
        hold_label=hold_label,
        replan_label=replan_label,
        advice_allowed=(int(frame_index) % int(advice_interval) == 0),
        target_threat_scores=tuple(float(track.threat_score) for track in tracks),
        target_demand_slots=required,
        hard_reject_reason_counts=hard_counts,
        reward_components=reward,
    )


def build_latest_learning_frame_record(
    planner: AssignmentPlanner,
    *,
    scenario_version: str,
    seed: int,
    episode: str | int,
    frame_index: int,
    feedback_result: str | None = None,
    advice_interval: int = 5,
) -> LearningFrameRecord:
    """Convert the planner's latest complete local evidence into one record."""

    evidence = planner.latest_planning_evidence
    if not evidence.available:
        raise RuntimeError(
            f"latest D3 planning evidence is unavailable: {evidence.reason}"
        )
    required = (
        evidence.timestamp_s,
        evidence.rule_matrix_result,
        evidence.plan,
    )
    if any(value is None for value in required):
        raise RuntimeError("latest D3 planning evidence is incomplete")
    return build_learning_frame_record(
        scenario_version=scenario_version,
        seed=seed,
        episode=episode,
        frame_index=frame_index,
        timestamp_s=float(evidence.timestamp_s),
        matrix_result=evidence.rule_matrix_result,
        tracks=evidence.tracks,
        resources=evidence.resources,
        plan=evidence.plan,
        previous_plan=evidence.previous_plan,
        feedback_result=feedback_result,
        advice_interval=advice_interval,
    )


def write_learning_dataset(
    output_dir: str | Path,
    records: Iterable[LearningFrameRecord],
    *,
    source_kind: str,
    split_seed: int = DEFAULT_DATASET_SPLIT_SEED,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    minimum_unseen_seed_count: int = DEFAULT_MINIMUM_UNSEEN_SEED_COUNT,
    staging_batch_size: int = 128,
) -> LearningDatasetManifest:
    """Finalize an iterable into canonical v2 JSONL with bounded process memory."""

    source = str(source_kind).strip()
    if not source:
        raise ValueError("source_kind is required")
    if int(staging_batch_size) < 1:
        raise ValueError("staging_batch_size must be positive")
    _validate_split_parameters(
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
        minimum_unseen_seed_count=minimum_unseen_seed_count,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".d3_dataset_staging_", dir=output) as staging:
        staging_path = Path(staging)
        database_path = staging_path / "frames.sqlite3"
        connection = sqlite3.connect(database_path)
        try:
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute(
                """
                CREATE TABLE frames (
                    scenario_version TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    episode TEXT NOT NULL,
                    frame_index INTEGER NOT NULL,
                    supplied_split TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (scenario_version, seed, episode, frame_index)
                )
                """
            )
            frame_count = 0
            for record in records:
                if not isinstance(record, LearningFrameRecord):
                    raise TypeError("records must contain LearningFrameRecord values")
                payload = json.dumps(
                    record.to_dict(),
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                try:
                    connection.execute(
                        "INSERT INTO frames VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            record.scenario_version,
                            int(record.seed),
                            record.episode,
                            int(record.frame_index),
                            record.split,
                            payload,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ValueError(
                        f"duplicate dataset frame: {(*record.episode_group, record.frame_index)}"
                    ) from exc
                frame_count += 1
                if frame_count % int(staging_batch_size) == 0:
                    connection.commit()
            connection.commit()
            if frame_count == 0:
                raise ValueError("at least one dataset frame is required")

            seed_values = tuple(
                int(row[0])
                for row in connection.execute("SELECT DISTINCT seed FROM frames ORDER BY seed")
            )
            split_by_seed = assign_seed_splits(
                seed_values,
                split_seed=split_seed,
                validation_fraction=validation_fraction,
                test_fraction=test_fraction,
                minimum_unseen_seed_count=minimum_unseen_seed_count,
            )
            for seed, supplied_split in connection.execute(
                "SELECT DISTINCT seed, supplied_split FROM frames"
            ):
                expected_split = split_by_seed[int(seed)]
                if supplied_split not in {UNASSIGNED_DATASET_SPLIT, expected_split}:
                    raise ValueError(
                        "record split conflicts with the numeric-seed-atomic v2 policy: "
                        f"seed={seed}, supplied={supplied_split}, expected={expected_split}"
                    )

            episode_splits = [
                (str(scenario), int(seed), str(episode), split_by_seed[int(seed)])
                for scenario, seed, episode in connection.execute(
                    """
                    SELECT DISTINCT scenario_version, seed, episode
                    FROM frames
                    ORDER BY scenario_version COLLATE BINARY, seed, episode COLLATE BINARY
                    """
                )
            ]
            split_frame_counts = {split: 0 for split in DATASET_SPLITS}
            split_episode_counts = {split: 0 for split in DATASET_SPLITS}
            for _, _, _, split in episode_splits:
                split_episode_counts[split] += 1

            temporary_frames = staging_path / DATASET_FRAMES_FILENAME
            frames_digest = sha256()
            with temporary_frames.open("wb") as stream:
                rows = connection.execute(
                    """
                    SELECT seed, payload FROM frames
                    ORDER BY scenario_version COLLATE BINARY, seed,
                             episode COLLATE BINARY, frame_index
                    """
                )
                for seed, payload in rows:
                    record = LearningFrameRecord.from_dict(json.loads(str(payload)))
                    finalized = replace(record, split=split_by_seed[int(seed)])
                    line = (
                        json.dumps(
                            finalized.to_dict(),
                            ensure_ascii=True,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("ascii")
                    stream.write(line)
                    frames_digest.update(line)
                    split_frame_counts[finalized.split] += 1

            split_seed_values = {
                split: tuple(
                    sorted(seed for seed, assigned in split_by_seed.items() if assigned == split)
                )
                for split in DATASET_SPLITS
            }
            manifest = LearningDatasetManifest(
                schema_version=LEARNING_DATASET_SCHEMA_V2,
                split_policy_version=LEARNING_DATASET_SPLIT_POLICY_V2,
                feature_names=EDGE_FEATURE_NAMES,
                split_hash=_split_hash_from_metadata(split_by_seed, episode_splits),
                frames_sha256=frames_digest.hexdigest(),
                frame_count=frame_count,
                episode_count=len(episode_splits),
                unique_seed_count=len(seed_values),
                split_frame_counts=split_frame_counts,
                split_episode_counts=split_episode_counts,
                split_seed_values=split_seed_values,
                split_seed=int(split_seed),
                validation_fraction=float(validation_fraction),
                test_fraction=float(test_fraction),
                minimum_unseen_seed_count=int(minimum_unseen_seed_count),
                unseen_test_seed_count=len(split_seed_values["test"]),
                source_kind=source,
            )
            temporary_manifest = staging_path / DATASET_MANIFEST_FILENAME
            with temporary_manifest.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    manifest.to_dict(),
                    stream,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
                stream.write("\n")
            os.replace(temporary_frames, output / DATASET_FRAMES_FILENAME)
            os.replace(temporary_manifest, output / DATASET_MANIFEST_FILENAME)
            return manifest
        finally:
            connection.close()


def load_learning_dataset(
    input_dir: str | Path,
) -> tuple[LearningDatasetManifest, tuple[LearningFrameRecord, ...]]:
    input_path = Path(input_dir)
    with (input_path / DATASET_MANIFEST_FILENAME).open(encoding="utf-8") as stream:
        raw_manifest = json.load(stream)
    if not isinstance(raw_manifest, Mapping):
        raise ValueError("D3 learning dataset manifest must be a JSON object")
    schema_version = raw_manifest.get("schema_version")
    if schema_version != LEARNING_DATASET_SCHEMA_V2:
        legacy = (
            "; v1 scenario/seed splits are not compatible"
            if schema_version == LEARNING_DATASET_SCHEMA_V1
            else ""
        )
        raise ValueError(
            "unsupported D3 learning dataset manifest schema: "
            f"{schema_version!r}{legacy}; {LEARNING_DATASET_SCHEMA_V2} is required"
        )
    split_policy_version = raw_manifest.get("split_policy_version")
    if split_policy_version != LEARNING_DATASET_SPLIT_POLICY_V2:
        raise ValueError(
            "unsupported D3 learning dataset split policy: "
            f"{split_policy_version!r}; {LEARNING_DATASET_SPLIT_POLICY_V2} is required"
        )
    manifest = LearningDatasetManifest.from_dict(raw_manifest)
    frame_path = input_path / DATASET_FRAMES_FILENAME
    if _file_sha256(frame_path) != manifest.frames_sha256:
        raise ValueError("dataset frames SHA256 does not match manifest")
    items = tuple(iter_learning_frame_records(frame_path))
    validate_split_integrity(
        items,
        minimum_unseen_seed_count=manifest.minimum_unseen_seed_count,
    )
    if len(items) != manifest.frame_count:
        raise ValueError("dataset frame count does not match manifest")
    keys = tuple(
        (item.scenario_version, item.seed, item.episode, item.frame_index) for item in items
    )
    if keys != tuple(sorted(keys)):
        raise ValueError("dataset frames are not in canonical deterministic order")
    split_by_seed = assign_seed_splits(
        (item.seed for item in items),
        split_seed=manifest.split_seed,
        validation_fraction=manifest.validation_fraction,
        test_fraction=manifest.test_fraction,
        minimum_unseen_seed_count=manifest.minimum_unseen_seed_count,
    )
    for item in items:
        if item.split != split_by_seed[item.seed]:
            raise ValueError("dataset split assignment does not match the v2 policy")
    if compute_split_hash(items) != manifest.split_hash:
        raise ValueError("dataset split hash does not match manifest")
    episode_splits = {
        (item.scenario_version, item.seed, item.episode, item.split) for item in items
    }
    if len(episode_splits) != manifest.episode_count:
        raise ValueError("dataset episode count does not match manifest")
    actual_frame_counts = {
        split: sum(item.split == split for item in items) for split in DATASET_SPLITS
    }
    actual_episode_counts = {
        split: sum(item[3] == split for item in episode_splits) for split in DATASET_SPLITS
    }
    actual_seed_values = {
        split: tuple(sorted(seed for seed, assigned in split_by_seed.items() if assigned == split))
        for split in DATASET_SPLITS
    }
    if actual_frame_counts != dict(manifest.split_frame_counts):
        raise ValueError("dataset split frame counts do not match manifest")
    if actual_episode_counts != dict(manifest.split_episode_counts):
        raise ValueError("dataset split episode counts do not match manifest")
    if actual_seed_values != dict(manifest.split_seed_values):
        raise ValueError("dataset split seed values do not match manifest")
    return manifest, items


def iter_learning_frame_records(path: str | Path) -> Iterator[LearningFrameRecord]:
    """Parse v2 frame JSONL lazily for staging/finalization pipelines."""

    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                yield LearningFrameRecord.from_dict(payload)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid dataset frame at line {line_number}") from exc


def generate_synthetic_learning_dataset(
    output_dir: str | Path,
    *,
    seeds: Sequence[int] = tuple(range(30)),
    episodes_per_seed: int = 2,
    frames_per_episode: int = 4,
    scenario_version: str = "d3_synthetic_sparse_v1",
) -> LearningDatasetManifest:
    """Generate deterministic 3v5/5v3 smoke data; not promotion evidence."""

    if not seeds or episodes_per_seed < 1 or frames_per_episode < 1:
        raise ValueError("seeds, episodes_per_seed, and frames_per_episode are required")
    records: list[LearningFrameRecord] = []
    roster_shapes = ((3, 5), (5, 3))
    for seed in sorted({int(value) for value in seeds}):
        for episode_index in range(int(episodes_per_seed)):
            target_count, resource_count = roster_shapes[(seed + episode_index) % 2]
            rng = np.random.default_rng(seed * 10_007 + episode_index)
            config = PlannerConfig.scalable_3d(
                enable_hysteresis=True,
                min_dwell=0.0,
                max_candidate_edges_per_target=min(4, resource_count),
            )
            planner = AssignmentPlanner(config=config)
            previous_plan: AssignmentPlan | None = None
            base_target_y = rng.uniform(-80.0, 80.0, size=target_count)
            base_resource_y = rng.uniform(-100.0, 100.0, size=resource_count)
            for frame_index in range(int(frames_per_episode)):
                timestamp_s = float(frame_index)
                tracks = [
                    TargetTrack(
                        track_id=f"internal_track_{index}",
                        threat_score=float(0.35 + 0.6 * rng.random()),
                        covariance=float(0.05 + 0.15 * rng.random()),
                        window_cost=float(0.15 * rng.random()),
                        position_ned=(
                            500.0 - 12.0 * frame_index + 15.0 * index,
                            float(base_target_y[index]),
                            -100.0,
                        ),
                        velocity_ned=(-12.0, 0.0, 0.0),
                        region_id="synthetic",
                    )
                    for index in range(target_count)
                ]
                resources = [
                    ResourceState(
                        resource_id=f"internal_resource_{index}",
                        position_ned=(0.0, float(base_resource_y[index]), -100.0),
                        velocity_ned=(0.0, 0.0, 0.0),
                        max_speed_mps=45.0 + 2.0 * (index % 3),
                        health_score=float(0.8 + 0.2 * rng.random()),
                        energy_fraction=float(0.75 + 0.25 * rng.random()),
                        region_id="synthetic",
                    )
                    for index in range(resource_count)
                ]
                plan = planner.plan(
                    tracks,
                    resources,
                    timestamp=timestamp_s,
                    previous_plan=previous_plan,
                    expected_previous_version=(
                        None if previous_plan is None else previous_plan.version
                    ),
                )
                records.append(
                    build_latest_learning_frame_record(
                        planner,
                        scenario_version=scenario_version,
                        seed=seed,
                        episode=f"episode_{episode_index:03d}",
                        frame_index=frame_index,
                    )
                )
                previous_plan = plan
    return write_learning_dataset(
        output_dir,
        records,
        source_kind="synthetic_smoke",
        minimum_unseen_seed_count=1,
    )


def _validate_split_parameters(
    *,
    validation_fraction: float,
    test_fraction: float,
    minimum_unseen_seed_count: int,
) -> None:
    fractions = (float(validation_fraction), float(test_fraction))
    if not all(isfinite(value) and 0.0 < value < 1.0 for value in fractions):
        raise ValueError("validation and test fractions must be finite and in (0, 1)")
    if sum(fractions) >= 1.0:
        raise ValueError("validation and test fractions leave no training split")
    if int(minimum_unseen_seed_count) < 1:
        raise ValueError("minimum unseen seed count must be positive")


def _split_hash_from_metadata(
    split_by_seed: Mapping[int, str],
    episode_splits: Sequence[tuple[str, int, str, str]],
) -> str:
    payload = {
        "dataset_schema_version": LEARNING_DATASET_SCHEMA_V2,
        "split_policy_version": LEARNING_DATASET_SPLIT_POLICY_V2,
        "seed_identity_scope": "numeric_seed_global_across_scenarios",
        "seed_assignments": [
            [int(seed), str(split)] for seed, split in sorted(split_by_seed.items())
        ],
        "episode_assignments": [
            [str(scenario), int(seed), str(episode), str(split)]
            for scenario, seed, episode, split in sorted(episode_splits)
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("ascii")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_anonymous_entities(
    entities: Sequence[Mapping[str, Any]],
    kind: str,
) -> None:
    allowed = {
        "target": {
            "token",
            "threat_score",
            "covariance_squashed",
            "window_cost",
            "required_resource_count",
            "primary_resource_count",
            "assignable",
        },
        "resource": {
            "token",
            "available",
            "health_score",
            "energy_fraction",
            "availability_score",
            "current_load",
            "assignment_capacity",
        },
    }[kind]
    prefix = f"{kind}_"
    for index, entity in enumerate(entities):
        if set(entity) != allowed:
            raise ValueError(f"anonymous {kind} schema contains unsupported fields")
        token = str(entity["token"])
        if token != f"{prefix}{index:04d}":
            raise ValueError(f"anonymous {kind} token is not ordinal")
        if kind == "target":
            _bounded_number(entity["threat_score"], "threat_score", 0.0, 1.0)
            _bounded_number(
                entity["covariance_squashed"], "covariance_squashed", 0.0, 1.0
            )
            _bounded_number(entity["window_cost"], "window_cost", 0.0, 1.0)
            required = _nonnegative_integer(
                entity["required_resource_count"], "required_resource_count"
            )
            primary = _nonnegative_integer(
                entity["primary_resource_count"], "primary_resource_count"
            )
            if required < 1 or not 1 <= primary <= required:
                raise ValueError("anonymous target demand counts are invalid")
            _boolean(entity["assignable"], "assignable")
        else:
            _boolean(entity["available"], "available")
            _bounded_number(entity["health_score"], "health_score", 0.0, 1.0)
            _bounded_number(
                entity["energy_fraction"], "energy_fraction", 0.0, 1.0
            )
            _bounded_number(
                entity["availability_score"], "availability_score", 0.0, 1.0
            )
            _bounded_number(entity["current_load"], "current_load", 0.0, None)
            _nonnegative_integer(
                entity["assignment_capacity"], "assignment_capacity"
            )


def _reject_identity_fields(value: Any, *, path: str = "frame") -> None:
    """Reject identity-bearing schema fields before unknown fields are discarded."""

    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower().replace("-", "_")
            dynamic_reject_reason = path == "frame.hard_reject_reason_counts"
            forbidden = (
                "truth" in key
                or "actor" in key
                or key in {"id", "uuid", "vehicle_name"}
                or key.endswith("_id")
                or key.endswith("_ids")
                or ("identity" in key and not dynamic_reject_reason)
            )
            if forbidden:
                raise ValueError(f"identity-bearing learning frame field is forbidden: {path}.{key}")
            _reject_identity_fields(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_identity_fields(item, path=f"{path}[{index}]")


def _bounded_number(
    value: Any,
    name: str,
    minimum: float,
    maximum: float | None,
) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError(f"anonymous entity {name} must be numeric")
    number = float(value)
    if not isfinite(number) or number < minimum or (
        maximum is not None and number > maximum
    ):
        raise ValueError(f"anonymous entity {name} is outside its allowed range")
    return number


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"anonymous entity {name} must be an integer")
    number = int(value)
    if number < 0:
        raise ValueError(f"anonymous entity {name} must be non-negative")
    return number


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"anonymous entity {name} must be boolean")
    return bool(value)


def _hard_reject_counts(
    reject_reasons: Sequence[Sequence[str | None]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in reject_reasons:
        for reason in row:
            if reason is not None:
                counts[str(reason)] = counts.get(str(reason), 0) + 1
    return dict(sorted(counts.items()))


def _squash_nonnegative(value: Any) -> float:
    number = max(0.0, float(value))
    return number / (1.0 + number)
