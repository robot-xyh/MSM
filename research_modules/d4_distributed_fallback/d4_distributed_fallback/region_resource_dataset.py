"""Versioned, truth-free episode datasets for D4 regional learning.

The dataset boundary is intentionally separate from D4 authority and fallback
control.  It persists complete regional-learning episodes and exposes verified
loaders; it never elects an owner, changes a lease, or authorizes an action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .region_resource import (
    DETERMINISTIC_RESOURCE_PROJECTOR_NAME,
    DETERMINISTIC_RESOURCE_PROJECTOR_VERSION,
    REGION_RESOURCE_FEATURE_SCHEMA,
    REGION_RESOURCE_RECOMMENDATION_SCHEMA,
    REGION_RESOURCE_SNAPSHOT_SCHEMA,
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceProjectionConfig,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    split_scenario_seed_groups,
)


REGION_LEARNING_EPISODE_SCHEMA = "d4-region-learning-episode-v1"
REGION_LEARNING_FRAME_SCHEMA = "d4-region-learning-frame-v1"
REGION_LEARNING_SOURCE_SCHEMA = "d4-region-learning-source-v1"
REGION_LEARNING_TARGET_SCHEMA = "d4-region-learning-target-v1"
REGION_LEARNING_REWARD_SCHEMA = "d4-region-learning-reward-v1"
REGION_LEARNING_DATASET_SCHEMA = "d4-region-learning-dataset-v1"
REGION_LEARNING_SPLIT_SCHEMA = "d4-region-learning-seed-split-v1"
REGION_LEARNING_SPLIT_ALGORITHM = "d4-numeric-seed-atomic-sha256-v1"

_FORBIDDEN_DATASET_KEYS = {
    "actor_id",
    "actor_name",
    "actor_truth_id",
    "evaluator_truth",
    "evaluator_truth_id",
    "global_track_id",
    "object_id",
    "object_name",
    "object_truth_id",
    "offline_truth",
    "segmentation_id",
    "target_id",
    "target_truth_id",
    "truth_id",
}

_LEARNING_TARGET_PROJECTION_CONFIG = RegionResourceProjectionConfig()

REGION_LEARNING_FEATURE_SEMANTICS: dict[str, Any] = {
    "schema": REGION_RESOURCE_FEATURE_SCHEMA,
    "snapshot_schema": REGION_RESOURCE_SNAPSHOT_SCHEMA,
    "representation": "truth-free variable-size regional graph",
    "node_fields": [
        "target_demand",
        "high_threat_backlog",
        "d1_uncertainty",
        "d2_uncertainty",
        "d5_visibility",
        "d5_consistency",
        "available_resources",
        "reserve_resources",
        "committed_resources",
        "secondary_coverage",
        "secondary_readiness",
        "communication_capacity",
        "communication_latency_s",
        "packet_loss_rate",
        "current_owner_layer",
        "lease_expires_at_s",
        "coalition_ack_complete",
        "owner_active",
        "fault_fenced",
        "assignment_conflict_count",
        "degradation_failed",
    ],
    "edge_fields": [
        "transferable_resources",
        "distance_m",
        "transfer_time_s",
        "bandwidth_mbps",
        "communication_available",
        "maneuver_available",
        "partitioned",
    ],
    "identity_policy": (
        "region and authority/plan fencing identity only; target, actor, evaluator "
        "truth, and global-track identity are forbidden"
    ),
}
REGION_LEARNING_TARGET_SEMANTICS: dict[str, Any] = {
    "schema": REGION_LEARNING_TARGET_SCHEMA,
    "recommendation_schema": REGION_RESOURCE_RECOMMENDATION_SCHEMA,
    "available_kinds": ["formal", "rule"],
    "unavailable_semantics": "explicit label with a non-empty reason; never imputed",
    "safety_projection": {
        "name": DETERMINISTIC_RESOURCE_PROJECTOR_NAME,
        "version": DETERMINISTIC_RESOURCE_PROJECTOR_VERSION,
        "minimum_reserve_ratio": (
            _LEARNING_TARGET_PROJECTION_CONFIG.minimum_reserve_ratio
        ),
        "minimum_reserve_resources": (
            _LEARNING_TARGET_PROJECTION_CONFIG.minimum_reserve_resources
        ),
    },
    "action_semantics": (
        "projected regional quota/transfer/reserve/reconnaissance/hold-replan advice; "
        "never a resource-target assignment"
    ),
}
REGION_LEARNING_REWARD_SEMANTICS: dict[str, Any] = {
    "schema": REGION_LEARNING_REWARD_SCHEMA,
    "value_semantics": "finite caller-supplied scalar for the recorded frame",
    "unavailable_semantics": "explicit label with a non-empty reason; never zero-filled",
}


class RegionLearningDatasetError(RuntimeError):
    pass


class RegionLearningDatasetValidationError(RegionLearningDatasetError):
    pass


class RegionLearningDataUnavailableError(RegionLearningDatasetError):
    pass


class RegionLearningAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class RegionLearningTargetKind(str, Enum):
    RULE = "rule"
    FORMAL = "formal"


class RegionLearningSplit(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


@dataclass(frozen=True)
class RegionLearningEpisodeSource:
    scenario_id: str
    scenario_version: str
    seed: int
    episode_id: str
    git_commit: str
    git_dirty: bool
    config_sha256: str
    scenario_scale: str | None = None
    schema: str = REGION_LEARNING_SOURCE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_LEARNING_SOURCE_SCHEMA:
            raise ValueError("unsupported region-learning source schema")
        if not self.scenario_id or not self.scenario_version or not self.episode_id:
            raise ValueError("scenario and episode identity must not be empty")
        if int(self.seed) < 0:
            raise ValueError("source seed must be non-negative")
        if type(self.git_dirty) is not bool:
            raise ValueError("git_dirty must be a boolean")
        commit = str(self.git_commit).lower()
        config_digest = str(self.config_sha256).lower()
        if len(commit) not in {40, 64} or not _is_hex(commit):
            raise ValueError("git_commit must be a full 40- or 64-character hex id")
        if len(config_digest) != 64 or not _is_hex(config_digest):
            raise ValueError("config_sha256 must be a SHA256 hex digest")
        if self.scenario_scale is not None and not str(self.scenario_scale).strip():
            raise ValueError("scenario_scale must be non-empty when supplied")
        object.__setattr__(self, "git_commit", commit)
        object.__setattr__(self, "config_sha256", config_digest)
        if self.scenario_scale is not None:
            object.__setattr__(self, "scenario_scale", str(self.scenario_scale))

    @property
    def scenario_seed_group(self) -> tuple[str, int]:
        scale = self.scenario_scale or "unspecified"
        return (f"{self.scenario_id}@{self.scenario_version}#{scale}", int(self.seed))

    @property
    def identity_sha256(self) -> str:
        return _sha256_bytes(_canonical_bytes(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "scenario_scale": self.scenario_scale,
            "seed": int(self.seed),
            "episode_id": self.episode_id,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "config_sha256": self.config_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionLearningEpisodeSource":
        _reject_truth_identifiers(value, path="source")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionLearningTarget:
    availability: RegionLearningAvailability | str
    kind: RegionLearningTargetKind | str | None = None
    recommendation: RegionResourceRecommendation | None = None
    unavailable_reason: str | None = None
    schema: str = REGION_LEARNING_TARGET_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_LEARNING_TARGET_SCHEMA:
            raise ValueError("unsupported region-learning target schema")
        availability = _availability(self.availability)
        object.__setattr__(self, "availability", availability)
        if availability == RegionLearningAvailability.AVAILABLE:
            if self.kind is None or self.recommendation is None:
                raise ValueError("available target requires kind and recommendation")
            kind = (
                self.kind
                if isinstance(self.kind, RegionLearningTargetKind)
                else RegionLearningTargetKind(str(self.kind))
            )
            if self.unavailable_reason is not None:
                raise ValueError("available target must not carry an unavailable reason")
            if kind == RegionLearningTargetKind.RULE and (
                self.recommendation.source != RecommendationSource.RULE
            ):
                raise ValueError("rule target must carry a rule recommendation")
            object.__setattr__(self, "kind", kind)
        else:
            if self.kind is not None or self.recommendation is not None:
                raise ValueError("unavailable target must not carry target values")
            if not self.unavailable_reason:
                raise ValueError("unavailable target requires a reason")

    @classmethod
    def available(
        cls,
        kind: RegionLearningTargetKind | str,
        recommendation: RegionResourceRecommendation,
    ) -> "RegionLearningTarget":
        return cls(
            availability=RegionLearningAvailability.AVAILABLE,
            kind=kind,
            recommendation=recommendation,
        )

    @classmethod
    def unavailable(cls, reason: str) -> "RegionLearningTarget":
        return cls(
            availability=RegionLearningAvailability.UNAVAILABLE,
            unavailable_reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "availability": self.availability.value,
            "kind": self.kind.value if self.kind is not None else None,
            "recommendation": (
                self.recommendation.to_dict() if self.recommendation is not None else None
            ),
            "unavailable_reason": self.unavailable_reason,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionLearningTarget":
        _reject_truth_identifiers(value, path="frame.target")
        payload = dict(value)
        if payload.get("recommendation") is not None:
            payload["recommendation"] = RegionResourceRecommendation.from_dict(
                payload["recommendation"]
            )
        return cls(**payload)


@dataclass(frozen=True)
class RegionLearningReward:
    availability: RegionLearningAvailability | str
    value: float | None = None
    unavailable_reason: str | None = None
    schema: str = REGION_LEARNING_REWARD_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_LEARNING_REWARD_SCHEMA:
            raise ValueError("unsupported region-learning reward schema")
        availability = _availability(self.availability)
        object.__setattr__(self, "availability", availability)
        if availability == RegionLearningAvailability.AVAILABLE:
            if self.value is None or not isfinite(float(self.value)):
                raise ValueError("available reward must be finite")
            if self.unavailable_reason is not None:
                raise ValueError("available reward must not carry an unavailable reason")
            object.__setattr__(self, "value", float(self.value))
        else:
            if self.value is not None:
                raise ValueError("unavailable reward must not carry a value")
            if not self.unavailable_reason:
                raise ValueError("unavailable reward requires a reason")

    @classmethod
    def available(cls, value: float) -> "RegionLearningReward":
        return cls(availability=RegionLearningAvailability.AVAILABLE, value=value)

    @classmethod
    def unavailable(cls, reason: str) -> "RegionLearningReward":
        return cls(
            availability=RegionLearningAvailability.UNAVAILABLE,
            unavailable_reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "availability": self.availability.value,
            "value": self.value,
            "unavailable_reason": self.unavailable_reason,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionLearningReward":
        _reject_truth_identifiers(value, path="frame.reward")
        return cls(**dict(value))


@dataclass(frozen=True)
class RegionLearningFrame:
    frame_index: int
    timestamp_s: float
    snapshot: RegionResourceSnapshot
    target: RegionLearningTarget
    reward: RegionLearningReward
    recommendation: RegionResourceRecommendation | None = None
    schema: str = REGION_LEARNING_FRAME_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_LEARNING_FRAME_SCHEMA:
            raise ValueError("unsupported region-learning frame schema")
        if int(self.frame_index) < 0:
            raise ValueError("frame_index must be non-negative")
        if not isfinite(float(self.timestamp_s)) or float(self.timestamp_s) < 0.0:
            raise ValueError("timestamp_s must be finite and non-negative")
        if abs(float(self.timestamp_s) - float(self.snapshot.timestamp_s)) > 1e-9:
            raise ValueError("frame timestamp must match snapshot timestamp")
        if self.target.recommendation is not None:
            _validate_recommendation_identity(
                self.snapshot,
                self.target.recommendation,
                require_projected=True,
                require_complete_actions=True,
            )
        if self.recommendation is not None:
            _validate_recommendation_identity(
                self.snapshot,
                self.recommendation,
                require_projected=False,
                require_complete_actions=False,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "frame_index": int(self.frame_index),
            "timestamp_s": float(self.timestamp_s),
            "snapshot": self.snapshot.to_dict(),
            "target": self.target.to_dict(),
            "reward": self.reward.to_dict(),
            "recommendation": (
                self.recommendation.to_dict() if self.recommendation is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionLearningFrame":
        _reject_truth_identifiers(value, path="frame")
        payload = dict(value)
        payload["snapshot"] = RegionResourceSnapshot.from_dict(payload["snapshot"])
        payload["target"] = RegionLearningTarget.from_dict(payload["target"])
        payload["reward"] = RegionLearningReward.from_dict(payload["reward"])
        if payload.get("recommendation") is not None:
            payload["recommendation"] = RegionResourceRecommendation.from_dict(
                payload["recommendation"]
            )
        return cls(**payload)


@dataclass(frozen=True)
class StagedRegionLearningEpisode:
    path: Path
    source: RegionLearningEpisodeSource
    frame_count: int
    episode_sha256: str


@dataclass(frozen=True)
class RegionLearningEpisodeManifest:
    relative_path: str
    episode_sha256: str
    source: RegionLearningEpisodeSource
    frame_count: int
    first_frame_index: int
    last_frame_index: int
    first_timestamp_s: float
    last_timestamp_s: float
    target_available_count: int
    target_unavailable_count: int
    reward_available_count: int
    reward_unavailable_count: int
    recommendation_available_count: int
    split: RegionLearningSplit | str

    def __post_init__(self) -> None:
        split = (
            self.split
            if isinstance(self.split, RegionLearningSplit)
            else RegionLearningSplit(str(self.split))
        )
        object.__setattr__(self, "split", split)
        if Path(self.relative_path).is_absolute() or ".." in Path(self.relative_path).parts:
            raise ValueError("episode path must remain inside the dataset")
        if len(self.episode_sha256) != 64 or not _is_hex(self.episode_sha256):
            raise ValueError("episode_sha256 must be a SHA256 digest")
        if int(self.frame_count) <= 0:
            raise ValueError("episode manifest requires at least one frame")
        if self.first_frame_index != 0 or self.last_frame_index != self.frame_count - 1:
            raise ValueError("episode manifest must describe a complete contiguous episode")
        if (
            not isfinite(float(self.first_timestamp_s))
            or not isfinite(float(self.last_timestamp_s))
            or self.first_timestamp_s < 0.0
            or self.last_timestamp_s < self.first_timestamp_s
        ):
            raise ValueError("episode manifest timestamps must be finite and monotonic")
        counts = (
            self.target_available_count,
            self.target_unavailable_count,
            self.reward_available_count,
            self.reward_unavailable_count,
            self.recommendation_available_count,
        )
        if any(int(value) < 0 for value in counts):
            raise ValueError("episode availability counts must be non-negative")
        if self.target_available_count + self.target_unavailable_count != self.frame_count:
            raise ValueError("target availability does not cover every frame")
        if self.reward_available_count + self.reward_unavailable_count != self.frame_count:
            raise ValueError("reward availability does not cover every frame")
        if self.recommendation_available_count > self.frame_count:
            raise ValueError("recommendation availability exceeds frame count")

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "episode_sha256": self.episode_sha256,
            "source": self.source.to_dict(),
            "frame_count": int(self.frame_count),
            "first_frame_index": int(self.first_frame_index),
            "last_frame_index": int(self.last_frame_index),
            "first_timestamp_s": float(self.first_timestamp_s),
            "last_timestamp_s": float(self.last_timestamp_s),
            "target_available_count": int(self.target_available_count),
            "target_unavailable_count": int(self.target_unavailable_count),
            "reward_available_count": int(self.reward_available_count),
            "reward_unavailable_count": int(self.reward_unavailable_count),
            "recommendation_available_count": int(
                self.recommendation_available_count
            ),
            "split": self.split.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionLearningEpisodeManifest":
        payload = dict(value)
        payload["source"] = RegionLearningEpisodeSource.from_dict(payload["source"])
        return cls(**payload)


@dataclass(frozen=True)
class RegionLearningSplitManifest:
    split_seed: int
    train_fraction: float
    validation_fraction: float
    minimum_unique_seeds: int
    minimum_unseen_seeds: int
    unique_seed_count: int
    unseen_seed_count: int
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    test_seeds: tuple[int, ...]
    split_sha256: str
    algorithm: str = REGION_LEARNING_SPLIT_ALGORITHM
    schema: str = REGION_LEARNING_SPLIT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_LEARNING_SPLIT_SCHEMA:
            raise ValueError("unsupported region-learning split schema")
        if self.algorithm != REGION_LEARNING_SPLIT_ALGORITHM:
            raise ValueError("unsupported region-learning split algorithm")
        if not 0.0 < float(self.train_fraction) < 1.0:
            raise ValueError("train_fraction must be in (0, 1)")
        if not 0.0 <= float(self.validation_fraction) < 1.0:
            raise ValueError("validation_fraction must be in [0, 1)")
        if self.train_fraction + self.validation_fraction >= 1.0:
            raise ValueError("split fractions must leave a test split")
        if int(self.minimum_unique_seeds) < 3:
            raise ValueError("minimum_unique_seeds must be at least 3")
        if int(self.minimum_unseen_seeds) < 2:
            raise ValueError("minimum_unseen_seeds must be at least 2")
        train = tuple(sorted(int(value) for value in self.train_seeds))
        validation = tuple(sorted(int(value) for value in self.validation_seeds))
        test = tuple(sorted(int(value) for value in self.test_seeds))
        object.__setattr__(self, "train_seeds", train)
        object.__setattr__(self, "validation_seeds", validation)
        object.__setattr__(self, "test_seeds", test)
        sets = (set(train), set(validation), set(test))
        if any(not values for values in sets):
            raise ValueError("train, validation, and test seed sets must be non-empty")
        if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
            raise ValueError("train, validation, and test seeds must be disjoint")
        if len(set.union(*sets)) != int(self.unique_seed_count):
            raise ValueError("split unique_seed_count mismatch")
        if len(validation) + len(test) != int(self.unseen_seed_count):
            raise ValueError("split unseen_seed_count mismatch")
        if self.unique_seed_count < self.minimum_unique_seeds:
            raise ValueError("fewer_than_minimum_unique_seeds")
        if self.unseen_seed_count < self.minimum_unseen_seeds:
            raise ValueError("fewer_than_minimum_unseen_seeds")
        if len(self.split_sha256) != 64 or not _is_hex(self.split_sha256):
            raise ValueError("split_sha256 must be a SHA256 digest")
        expected_split_digest = _sha256_bytes(
            _canonical_bytes(
                {
                    "algorithm": self.algorithm,
                    "split_seed": int(self.split_seed),
                    "train": list(train),
                    "validation": list(validation),
                    "test": list(test),
                }
            )
        )
        if self.split_sha256 != expected_split_digest:
            raise ValueError("split_sha256 does not match numeric seed assignment")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "split_seed": int(self.split_seed),
            "train_fraction": float(self.train_fraction),
            "validation_fraction": float(self.validation_fraction),
            "minimum_unique_seeds": int(self.minimum_unique_seeds),
            "minimum_unseen_seeds": int(self.minimum_unseen_seeds),
            "unique_seed_count": int(self.unique_seed_count),
            "unseen_seed_count": int(self.unseen_seed_count),
            "train_seeds": list(self.train_seeds),
            "validation_seeds": list(self.validation_seeds),
            "test_seeds": list(self.test_seeds),
            "split_sha256": self.split_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionLearningSplitManifest":
        payload = dict(value)
        for key in ("train_seeds", "validation_seeds", "test_seeds"):
            payload[key] = tuple(payload.get(key, ()))
        return cls(**payload)


@dataclass(frozen=True)
class RegionLearningAvailabilityManifest:
    episode_count: int
    frame_count: int
    dirty_episode_count: int
    target_available_count: int
    target_unavailable_count: int
    reward_available_count: int
    reward_unavailable_count: int
    recommendation_available_count: int
    behavior_cloning_available: bool
    ppo_available: bool
    unavailable_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.episode_count <= 0 or self.frame_count <= 0:
            raise ValueError("dataset availability requires episodes and frames")
        counts = (
            self.dirty_episode_count,
            self.target_available_count,
            self.target_unavailable_count,
            self.reward_available_count,
            self.reward_unavailable_count,
            self.recommendation_available_count,
        )
        if any(int(value) < 0 for value in counts):
            raise ValueError("dataset availability counts must be non-negative")
        if self.dirty_episode_count > self.episode_count:
            raise ValueError("dirty episode count exceeds episode count")
        if self.recommendation_available_count > self.frame_count:
            raise ValueError("recommendation availability exceeds frame count")
        if self.target_available_count + self.target_unavailable_count != self.frame_count:
            raise ValueError("dataset target counts do not cover every frame")
        if self.reward_available_count + self.reward_unavailable_count != self.frame_count:
            raise ValueError("dataset reward counts do not cover every frame")
        expected_bc = self.dirty_episode_count == 0 and self.target_unavailable_count == 0
        expected_ppo = expected_bc and self.reward_unavailable_count == 0
        if self.behavior_cloning_available != expected_bc:
            raise ValueError("behavior cloning availability is inconsistent")
        if self.ppo_available != expected_ppo:
            raise ValueError("PPO availability is inconsistent")
        object.__setattr__(self, "unavailable_reasons", tuple(sorted(set(self.unavailable_reasons))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_count": int(self.episode_count),
            "frame_count": int(self.frame_count),
            "dirty_episode_count": int(self.dirty_episode_count),
            "target_available_count": int(self.target_available_count),
            "target_unavailable_count": int(self.target_unavailable_count),
            "reward_available_count": int(self.reward_available_count),
            "reward_unavailable_count": int(self.reward_unavailable_count),
            "recommendation_available_count": int(
                self.recommendation_available_count
            ),
            "behavior_cloning_available": bool(self.behavior_cloning_available),
            "ppo_available": bool(self.ppo_available),
            "unavailable_reasons": list(self.unavailable_reasons),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "RegionLearningAvailabilityManifest":
        payload = dict(value)
        payload["unavailable_reasons"] = tuple(payload.get("unavailable_reasons", ()))
        return cls(**payload)


@dataclass(frozen=True)
class RegionLearningDatasetManifest:
    created_at_utc: str
    episodes: tuple[RegionLearningEpisodeManifest, ...]
    split: RegionLearningSplitManifest
    availability: RegionLearningAvailabilityManifest
    dataset_sha256: str
    dataset_id: str
    feature_semantics: Mapping[str, Any] = field(
        default_factory=lambda: dict(REGION_LEARNING_FEATURE_SEMANTICS)
    )
    target_semantics: Mapping[str, Any] = field(
        default_factory=lambda: dict(REGION_LEARNING_TARGET_SEMANTICS)
    )
    reward_semantics: Mapping[str, Any] = field(
        default_factory=lambda: dict(REGION_LEARNING_REWARD_SEMANTICS)
    )
    schema: str = REGION_LEARNING_DATASET_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_LEARNING_DATASET_SCHEMA:
            raise ValueError("unsupported region-learning dataset schema")
        if not self.created_at_utc:
            raise ValueError("dataset created_at_utc must not be empty")
        episodes = tuple(self.episodes)
        object.__setattr__(self, "episodes", episodes)
        if not episodes:
            raise ValueError("dataset manifest requires at least one episode")
        if episodes != tuple(sorted(episodes, key=lambda item: _source_sort_key(item.source))):
            raise ValueError("dataset episodes must use canonical source order")
        identities = [episode.source.identity_sha256 for episode in episodes]
        paths = [episode.relative_path for episode in episodes]
        if len(set(identities)) != len(identities) or len(set(paths)) != len(paths):
            raise ValueError("dataset episode identity and path must be unique")
        expected_availability = _availability_manifest_from_entries(episodes)
        if _canonical_bytes(self.availability.to_dict()) != _canonical_bytes(
            expected_availability.to_dict()
        ):
            raise ValueError("dataset availability does not match episode inventory")
        if _canonical_bytes(self.feature_semantics) != _canonical_bytes(
            REGION_LEARNING_FEATURE_SEMANTICS
        ):
            raise ValueError("dataset feature semantics mismatch")
        if _canonical_bytes(self.target_semantics) != _canonical_bytes(
            REGION_LEARNING_TARGET_SEMANTICS
        ):
            raise ValueError("dataset target semantics mismatch")
        if _canonical_bytes(self.reward_semantics) != _canonical_bytes(
            REGION_LEARNING_REWARD_SEMANTICS
        ):
            raise ValueError("dataset reward semantics mismatch")
        if len(self.dataset_sha256) != 64 or not _is_hex(self.dataset_sha256):
            raise ValueError("dataset_sha256 must be a SHA256 digest")
        if self.dataset_id != f"d4-region-learning-dataset-{self.dataset_sha256}":
            raise ValueError("dataset_id does not match dataset_sha256")
        expected_digest = _sha256_bytes(_canonical_bytes(self.content_dict()))
        if expected_digest != self.dataset_sha256:
            raise ValueError("dataset_sha256 does not match manifest content")
        split_by_seed = {
            seed: RegionLearningSplit.TRAIN
            for seed in self.split.train_seeds
        }
        split_by_seed.update(
            {seed: RegionLearningSplit.VALIDATION for seed in self.split.validation_seeds}
        )
        split_by_seed.update(
            {seed: RegionLearningSplit.TEST for seed in self.split.test_seeds}
        )
        if any(
            split_by_seed.get(int(episode.source.seed)) != episode.split
            for episode in episodes
        ):
            raise ValueError("episode split does not match its numeric seed")
        try:
            expected_split = split_scenario_seed_groups(
                tuple(episode.source for episode in episodes),
                train_fraction=self.split.train_fraction,
                validation_fraction=self.split.validation_fraction,
                split_seed=self.split.split_seed,
                minimum_unique_seeds=self.split.minimum_unique_seeds,
                minimum_unseen_seeds=self.split.minimum_unseen_seeds,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("dataset split cannot be reproduced") from exc
        if (
            expected_split.train_seeds != self.split.train_seeds
            or expected_split.validation_seeds != self.split.validation_seeds
            or expected_split.test_seeds != self.split.test_seeds
            or expected_split.split_sha256 != self.split.split_sha256
        ):
            raise ValueError("dataset split does not match episode inventory")

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "created_at_utc": self.created_at_utc,
            "feature_semantics": dict(self.feature_semantics),
            "target_semantics": dict(self.target_semantics),
            "reward_semantics": dict(self.reward_semantics),
            "split": self.split.to_dict(),
            "availability": self.availability.to_dict(),
            "episodes": [episode.to_dict() for episode in self.episodes],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.content_dict()
        payload["dataset_sha256"] = self.dataset_sha256
        payload["dataset_id"] = self.dataset_id
        return payload

    @classmethod
    def create(
        cls,
        *,
        created_at_utc: str,
        episodes: Sequence[RegionLearningEpisodeManifest],
        split: RegionLearningSplitManifest,
        availability: RegionLearningAvailabilityManifest,
    ) -> "RegionLearningDatasetManifest":
        content = {
            "schema": REGION_LEARNING_DATASET_SCHEMA,
            "created_at_utc": created_at_utc,
            "feature_semantics": REGION_LEARNING_FEATURE_SEMANTICS,
            "target_semantics": REGION_LEARNING_TARGET_SEMANTICS,
            "reward_semantics": REGION_LEARNING_REWARD_SEMANTICS,
            "split": split.to_dict(),
            "availability": availability.to_dict(),
            "episodes": [episode.to_dict() for episode in episodes],
        }
        digest = _sha256_bytes(_canonical_bytes(content))
        return cls(
            created_at_utc=created_at_utc,
            episodes=tuple(episodes),
            split=split,
            availability=availability,
            dataset_sha256=digest,
            dataset_id=f"d4-region-learning-dataset-{digest}",
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegionLearningDatasetManifest":
        _reject_truth_identifiers(value, path="manifest")
        payload = dict(value)
        payload["episodes"] = tuple(
            RegionLearningEpisodeManifest.from_dict(item)
            for item in payload.get("episodes", ())
        )
        payload["split"] = RegionLearningSplitManifest.from_dict(payload["split"])
        payload["availability"] = RegionLearningAvailabilityManifest.from_dict(
            payload["availability"]
        )
        return cls(**payload)


@dataclass(frozen=True)
class LoadedRegionLearningEpisode:
    source: RegionLearningEpisodeSource
    frames: tuple[RegionLearningFrame, ...]
    split: RegionLearningSplit
    manifest: RegionLearningEpisodeManifest


@dataclass(frozen=True)
class LoadedRegionLearningDataset:
    root: Path
    manifest: RegionLearningDatasetManifest
    episode_records: tuple[LoadedRegionLearningEpisode, ...]

    def episodes(
        self, split: RegionLearningSplit | str | None = None
    ) -> tuple[LoadedRegionLearningEpisode, ...]:
        if split is None:
            return self.episode_records
        resolved = split if isinstance(split, RegionLearningSplit) else RegionLearningSplit(split)
        return tuple(item for item in self.episode_records if item.split == resolved)

    def iter_frames(
        self, split: RegionLearningSplit | str | None = None
    ) -> Iterator[RegionLearningFrame]:
        for episode in self.episodes(split):
            yield from episode.frames


def stage_region_learning_episode(
    staging_dir: str | Path,
    source: RegionLearningEpisodeSource,
    frames: Iterable[RegionLearningFrame],
) -> StagedRegionLearningEpisode:
    """Validate and atomically stage one complete episode as canonical JSONL."""

    ordered_frames = tuple(sorted(frames, key=lambda item: int(item.frame_index)))
    _validate_complete_episode(source, ordered_frames)
    destination = Path(staging_dir)
    destination.mkdir(parents=True, exist_ok=True)
    final_path = destination / f"episode-{source.identity_sha256}.jsonl"
    descriptor, payload = _episode_payload(source, ordered_frames, final_path)
    if final_path.exists():
        if final_path.read_bytes() != payload:
            raise RegionLearningDatasetValidationError(
                "staged episode identity already exists with different content"
            )
        return descriptor
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{final_path.name}.", suffix=".tmp", dir=destination
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(final_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return StagedRegionLearningEpisode(
        path=final_path,
        source=descriptor.source,
        frame_count=descriptor.frame_count,
        episode_sha256=descriptor.episode_sha256,
    )


def finalize_region_learning_dataset(
    staging_dir: str | Path,
    dataset_dir: str | Path,
    *,
    created_at_utc: str,
    split_seed: int,
    minimum_unseen_seeds: int,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    minimum_unique_seeds: int = 3,
) -> RegionLearningDatasetManifest:
    """Freeze staged complete episodes into a content-verified dataset."""

    staging = Path(staging_dir)
    staged_paths = sorted(staging.glob("episode-*.jsonl"))
    if not staged_paths:
        raise RegionLearningDatasetValidationError("no complete staged episodes found")
    parsed = [_read_episode_artifact(path) for path in staged_paths]
    identities = [item[0].identity_sha256 for item in parsed]
    if len(set(identities)) != len(identities):
        raise RegionLearningDatasetValidationError("duplicate episode source identity")
    parsed.sort(key=lambda item: _source_sort_key(item[0]))
    sources = [item[0] for item in parsed]
    try:
        split = split_scenario_seed_groups(
            sources,
            train_fraction=train_fraction,
            validation_fraction=validation_fraction,
            split_seed=split_seed,
            minimum_unique_seeds=minimum_unique_seeds,
            minimum_unseen_seeds=minimum_unseen_seeds,
        )
    except (TypeError, ValueError) as exc:
        raise RegionLearningDatasetValidationError(str(exc)) from exc
    seed_to_split = {
        seed: RegionLearningSplit.TRAIN for seed in split.train_seeds
    }
    seed_to_split.update(
        {seed: RegionLearningSplit.VALIDATION for seed in split.validation_seeds}
    )
    seed_to_split.update({seed: RegionLearningSplit.TEST for seed in split.test_seeds})

    destination = Path(dataset_dir)
    if destination.exists():
        raise RegionLearningDatasetValidationError("dataset destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    try:
        episode_dir = temporary_root / "episodes"
        episode_dir.mkdir()
        entries: list[RegionLearningEpisodeManifest] = []
        loaded_for_availability: list[tuple[RegionLearningEpisodeSource, tuple[RegionLearningFrame, ...]]] = []
        for source, frames, episode_digest, source_path in parsed:
            relative_path = f"episodes/episode-{source.identity_sha256}.jsonl"
            target_path = temporary_root / relative_path
            shutil.copyfile(source_path, target_path)
            entry = _episode_manifest(
                relative_path=relative_path,
                episode_sha256=episode_digest,
                source=source,
                frames=frames,
                split=seed_to_split[int(source.seed)],
            )
            entries.append(entry)
            loaded_for_availability.append((source, frames))
        entries.sort(key=lambda item: _source_sort_key(item.source))
        split_manifest = RegionLearningSplitManifest(
            split_seed=int(split_seed),
            train_fraction=float(train_fraction),
            validation_fraction=float(validation_fraction),
            minimum_unique_seeds=int(minimum_unique_seeds),
            minimum_unseen_seeds=int(minimum_unseen_seeds),
            unique_seed_count=split.unique_seed_count,
            unseen_seed_count=len(split.validation_seeds) + len(split.test_seeds),
            train_seeds=split.train_seeds,
            validation_seeds=split.validation_seeds,
            test_seeds=split.test_seeds,
            split_sha256=split.split_sha256,
        )
        availability = _availability_manifest(loaded_for_availability)
        manifest = RegionLearningDatasetManifest.create(
            created_at_utc=created_at_utc,
            episodes=entries,
            split=split_manifest,
            availability=availability,
        )
        (temporary_root / "manifest.json").write_text(
            json.dumps(
                manifest.to_dict(),
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary_root.replace(destination)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    return manifest


def load_region_learning_dataset(
    dataset_dir: str | Path,
) -> LoadedRegionLearningDataset:
    """Load a dataset only after manifest, split, episode, and truth checks pass."""

    root = Path(dataset_dir)
    try:
        payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest = RegionLearningDatasetManifest.from_dict(payload)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RegionLearningDatasetValidationError(
            f"dataset_manifest_invalid:{type(exc).__name__}"
        ) from exc
    records: list[LoadedRegionLearningEpisode] = []
    summaries: list[tuple[RegionLearningEpisodeSource, tuple[RegionLearningFrame, ...]]] = []
    for entry in manifest.episodes:
        path = (root / entry.relative_path).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise RegionLearningDatasetValidationError("episode path escapes dataset") from exc
        try:
            source, frames, digest, _ = _read_episode_artifact(path)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            if isinstance(exc, RegionLearningDatasetValidationError):
                raise
            raise RegionLearningDatasetValidationError(
                f"episode_invalid:{entry.source.episode_id}:{type(exc).__name__}"
            ) from exc
        if digest != entry.episode_sha256:
            raise RegionLearningDatasetValidationError(
                f"episode_sha256_mismatch:{entry.source.episode_id}"
            )
        expected_entry = _episode_manifest(
            relative_path=entry.relative_path,
            episode_sha256=digest,
            source=source,
            frames=frames,
            split=entry.split,
        )
        if _canonical_bytes(expected_entry.to_dict()) != _canonical_bytes(entry.to_dict()):
            raise RegionLearningDatasetValidationError(
                f"episode_manifest_mismatch:{entry.source.episode_id}"
            )
        records.append(
            LoadedRegionLearningEpisode(
                source=source,
                frames=frames,
                split=entry.split,
                manifest=entry,
            )
        )
        summaries.append((source, frames))
    if _canonical_bytes(_availability_manifest(summaries).to_dict()) != _canonical_bytes(
        manifest.availability.to_dict()
    ):
        raise RegionLearningDatasetValidationError("dataset availability manifest mismatch")
    _verify_manifest_split(manifest, [record.source for record in records])
    return LoadedRegionLearningDataset(
        root=root,
        manifest=manifest,
        episode_records=tuple(records),
    )


def load_region_learning_dataset_splits(
    dataset_dir: str | Path,
    *,
    splits: Iterable[RegionLearningSplit | str],
) -> LoadedRegionLearningDataset:
    """Load and verify only explicitly selected dataset payload splits.

    The complete manifest is still parsed so its immutable split assignment and
    provenance remain bound. Episode payloads outside ``splits`` are not read.
    This is used by candidate construction paths that must leave test and
    external holdout observations untouched.
    """

    selected = tuple(
        sorted(
            {
                item
                if isinstance(item, RegionLearningSplit)
                else RegionLearningSplit(str(item))
                for item in splits
            },
            key=lambda item: item.value,
        )
    )
    if not selected:
        raise ValueError("at least one dataset split must be selected")

    root = Path(dataset_dir)
    try:
        payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest = RegionLearningDatasetManifest.from_dict(payload)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RegionLearningDatasetValidationError(
            f"dataset_manifest_invalid:{type(exc).__name__}"
        ) from exc

    selected_set = set(selected)
    records: list[LoadedRegionLearningEpisode] = []
    for entry in manifest.episodes:
        if entry.split not in selected_set:
            continue
        path = (root / entry.relative_path).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise RegionLearningDatasetValidationError(
                "episode path escapes dataset"
            ) from exc
        try:
            source, frames, digest, _ = _read_episode_artifact(path)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            if isinstance(exc, RegionLearningDatasetValidationError):
                raise
            raise RegionLearningDatasetValidationError(
                f"episode_invalid:{entry.source.episode_id}:{type(exc).__name__}"
            ) from exc
        if digest != entry.episode_sha256:
            raise RegionLearningDatasetValidationError(
                f"episode_sha256_mismatch:{entry.source.episode_id}"
            )
        expected_entry = _episode_manifest(
            relative_path=entry.relative_path,
            episode_sha256=digest,
            source=source,
            frames=frames,
            split=entry.split,
        )
        if _canonical_bytes(expected_entry.to_dict()) != _canonical_bytes(
            entry.to_dict()
        ):
            raise RegionLearningDatasetValidationError(
                f"episode_manifest_mismatch:{entry.source.episode_id}"
            )
        records.append(
            LoadedRegionLearningEpisode(
                source=source,
                frames=frames,
                split=entry.split,
                manifest=entry,
            )
        )

    observed = {record.split for record in records}
    if observed != selected_set:
        missing = sorted(item.value for item in selected_set - observed)
        raise RegionLearningDatasetValidationError(
            "selected dataset split has no verified episode:" + ",".join(missing)
        )
    return LoadedRegionLearningDataset(
        root=root,
        manifest=manifest,
        episode_records=tuple(records),
    )


def _episode_payload(
    source: RegionLearningEpisodeSource,
    frames: Sequence[RegionLearningFrame],
    path: Path,
) -> tuple[StagedRegionLearningEpisode, bytes]:
    header = {
        "record_type": "episode_header",
        "schema": REGION_LEARNING_EPISODE_SCHEMA,
        "source": source.to_dict(),
    }
    frame_lines = [_canonical_bytes({"record_type": "frame", "frame": frame.to_dict()}) for frame in frames]
    frames_digest = _sha256_bytes(b"\n".join(frame_lines) + b"\n")
    footer = {
        "record_type": "episode_footer",
        "schema": REGION_LEARNING_EPISODE_SCHEMA,
        "complete": True,
        "frame_count": len(frames),
        "frames_sha256": frames_digest,
    }
    payload = b"\n".join([_canonical_bytes(header), *frame_lines, _canonical_bytes(footer)]) + b"\n"
    digest = _sha256_bytes(payload)
    return (
        StagedRegionLearningEpisode(
            path=path,
            source=source,
            frame_count=len(frames),
            episode_sha256=digest,
        ),
        payload,
    )


def _read_episode_artifact(
    path: Path,
) -> tuple[
    RegionLearningEpisodeSource,
    tuple[RegionLearningFrame, ...],
    str,
    Path,
]:
    payload = path.read_bytes()
    digest = _sha256_bytes(payload)
    raw_lines = payload.splitlines()
    if len(raw_lines) < 3:
        raise RegionLearningDatasetValidationError("episode artifact is incomplete")
    records = [json.loads(line) for line in raw_lines]
    _reject_truth_identifiers(records, path="episode")
    header = records[0]
    footer = records[-1]
    if (
        header.get("record_type") != "episode_header"
        or header.get("schema") != REGION_LEARNING_EPISODE_SCHEMA
    ):
        raise RegionLearningDatasetValidationError("episode header is invalid")
    if (
        footer.get("record_type") != "episode_footer"
        or footer.get("schema") != REGION_LEARNING_EPISODE_SCHEMA
        or footer.get("complete") is not True
    ):
        raise RegionLearningDatasetValidationError("episode footer is incomplete")
    frame_records = records[1:-1]
    if any(record.get("record_type") != "frame" for record in frame_records):
        raise RegionLearningDatasetValidationError("episode contains an unknown record")
    source = RegionLearningEpisodeSource.from_dict(header["source"])
    frames = tuple(RegionLearningFrame.from_dict(record["frame"]) for record in frame_records)
    _validate_complete_episode(source, frames)
    canonical_frame_lines = [
        _canonical_bytes({"record_type": "frame", "frame": frame.to_dict()})
        for frame in frames
    ]
    frames_digest = _sha256_bytes(b"\n".join(canonical_frame_lines) + b"\n")
    if int(footer.get("frame_count", -1)) != len(frames):
        raise RegionLearningDatasetValidationError("episode footer frame count mismatch")
    if footer.get("frames_sha256") != frames_digest:
        raise RegionLearningDatasetValidationError("episode frame hash mismatch")
    return source, frames, digest, path


def _validate_complete_episode(
    source: RegionLearningEpisodeSource,
    frames: Sequence[RegionLearningFrame],
) -> None:
    if not frames:
        raise RegionLearningDatasetValidationError("episode requires at least one frame")
    indices = tuple(int(frame.frame_index) for frame in frames)
    if indices != tuple(range(len(frames))):
        raise RegionLearningDatasetValidationError(
            "complete episode frame indices must be contiguous from zero"
        )
    timestamps = tuple(float(frame.timestamp_s) for frame in frames)
    if any(current < previous for previous, current in zip(timestamps, timestamps[1:])):
        raise RegionLearningDatasetValidationError("episode timestamps must be monotonic")
    snapshot_ids = [frame.snapshot.snapshot_id for frame in frames]
    if len(set(snapshot_ids)) != len(snapshot_ids):
        raise RegionLearningDatasetValidationError("episode snapshot ids must be unique")
    for frame in frames:
        snapshot = frame.snapshot
        if (
            snapshot.scenario_id != source.scenario_id
            or snapshot.scenario_version != source.scenario_version
            or int(snapshot.seed) != int(source.seed)
        ):
            raise RegionLearningDatasetValidationError(
                "episode source identity does not match frame snapshot"
            )


def _episode_manifest(
    *,
    relative_path: str,
    episode_sha256: str,
    source: RegionLearningEpisodeSource,
    frames: Sequence[RegionLearningFrame],
    split: RegionLearningSplit,
) -> RegionLearningEpisodeManifest:
    target_available = sum(
        frame.target.availability == RegionLearningAvailability.AVAILABLE
        for frame in frames
    )
    reward_available = sum(
        frame.reward.availability == RegionLearningAvailability.AVAILABLE
        for frame in frames
    )
    return RegionLearningEpisodeManifest(
        relative_path=relative_path,
        episode_sha256=episode_sha256,
        source=source,
        frame_count=len(frames),
        first_frame_index=frames[0].frame_index,
        last_frame_index=frames[-1].frame_index,
        first_timestamp_s=frames[0].timestamp_s,
        last_timestamp_s=frames[-1].timestamp_s,
        target_available_count=target_available,
        target_unavailable_count=len(frames) - target_available,
        reward_available_count=reward_available,
        reward_unavailable_count=len(frames) - reward_available,
        recommendation_available_count=sum(
            frame.recommendation is not None for frame in frames
        ),
        split=split,
    )


def _availability_manifest(
    episodes: Sequence[
        tuple[RegionLearningEpisodeSource, Sequence[RegionLearningFrame]]
    ],
) -> RegionLearningAvailabilityManifest:
    frame_count = sum(len(frames) for _, frames in episodes)
    dirty_count = sum(source.git_dirty for source, _ in episodes)
    target_available = sum(
        frame.target.availability == RegionLearningAvailability.AVAILABLE
        for _, frames in episodes
        for frame in frames
    )
    reward_available = sum(
        frame.reward.availability == RegionLearningAvailability.AVAILABLE
        for _, frames in episodes
        for frame in frames
    )
    recommendation_available = sum(
        frame.recommendation is not None
        for _, frames in episodes
        for frame in frames
    )
    reasons: list[str] = []
    if dirty_count:
        reasons.append("dirty_source")
    if target_available != frame_count:
        reasons.append("target_unavailable")
    if reward_available != frame_count:
        reasons.append("reward_unavailable")
    return RegionLearningAvailabilityManifest(
        episode_count=len(episodes),
        frame_count=frame_count,
        dirty_episode_count=dirty_count,
        target_available_count=target_available,
        target_unavailable_count=frame_count - target_available,
        reward_available_count=reward_available,
        reward_unavailable_count=frame_count - reward_available,
        recommendation_available_count=recommendation_available,
        behavior_cloning_available=dirty_count == 0 and target_available == frame_count,
        ppo_available=(
            dirty_count == 0
            and target_available == frame_count
            and reward_available == frame_count
        ),
        unavailable_reasons=tuple(reasons),
    )


def _availability_manifest_from_entries(
    episodes: Sequence[RegionLearningEpisodeManifest],
) -> RegionLearningAvailabilityManifest:
    frame_count = sum(episode.frame_count for episode in episodes)
    dirty_count = sum(episode.source.git_dirty for episode in episodes)
    target_available = sum(episode.target_available_count for episode in episodes)
    reward_available = sum(episode.reward_available_count for episode in episodes)
    recommendation_available = sum(
        episode.recommendation_available_count for episode in episodes
    )
    reasons: list[str] = []
    if dirty_count:
        reasons.append("dirty_source")
    if target_available != frame_count:
        reasons.append("target_unavailable")
    if reward_available != frame_count:
        reasons.append("reward_unavailable")
    return RegionLearningAvailabilityManifest(
        episode_count=len(episodes),
        frame_count=frame_count,
        dirty_episode_count=dirty_count,
        target_available_count=target_available,
        target_unavailable_count=frame_count - target_available,
        reward_available_count=reward_available,
        reward_unavailable_count=frame_count - reward_available,
        recommendation_available_count=recommendation_available,
        behavior_cloning_available=dirty_count == 0 and target_available == frame_count,
        ppo_available=(
            dirty_count == 0
            and target_available == frame_count
            and reward_available == frame_count
        ),
        unavailable_reasons=tuple(reasons),
    )


def _verify_manifest_split(
    manifest: RegionLearningDatasetManifest,
    sources: Sequence[RegionLearningEpisodeSource],
) -> None:
    try:
        split = split_scenario_seed_groups(
            sources,
            train_fraction=manifest.split.train_fraction,
            validation_fraction=manifest.split.validation_fraction,
            split_seed=manifest.split.split_seed,
            minimum_unique_seeds=manifest.split.minimum_unique_seeds,
            minimum_unseen_seeds=manifest.split.minimum_unseen_seeds,
        )
    except (TypeError, ValueError) as exc:
        raise RegionLearningDatasetValidationError("dataset split cannot be reproduced") from exc
    expected = (
        split.train_seeds,
        split.validation_seeds,
        split.test_seeds,
        split.split_sha256,
    )
    actual = (
        manifest.split.train_seeds,
        manifest.split.validation_seeds,
        manifest.split.test_seeds,
        manifest.split.split_sha256,
    )
    if expected != actual:
        raise RegionLearningDatasetValidationError("dataset split hash mismatch")


def _validate_recommendation_identity(
    snapshot: RegionResourceSnapshot,
    recommendation: RegionResourceRecommendation,
    *,
    require_projected: bool,
    require_complete_actions: bool,
) -> None:
    if (
        recommendation.snapshot_id != snapshot.snapshot_id
        or recommendation.scenario_id != snapshot.scenario_id
        or recommendation.scenario_version != snapshot.scenario_version
        or int(recommendation.seed) != int(snapshot.seed)
        or recommendation.authority_digest != snapshot.authority_digest
    ):
        raise ValueError("recommendation identity does not match snapshot")
    if require_projected and not recommendation.projected:
        raise ValueError("learning target must be safety projected")
    if require_complete_actions and {
        action.region_id for action in recommendation.actions
    } != {region.region_id for region in snapshot.regions}:
        raise ValueError("learning target must cover every snapshot region exactly once")
    if require_projected:
        projector = DeterministicResourceProjector(
            _LEARNING_TARGET_PROJECTION_CONFIG
        )
        advisory = projector.build_advisory_contract(snapshot, recommendation)
        if advisory.publication_rejections:
            reasons = ",".join(advisory.publication_rejections)
            raise ValueError(
                f"learning target failed deterministic safety validation:{reasons}"
            )


def _source_sort_key(source: RegionLearningEpisodeSource) -> tuple[Any, ...]:
    return (
        int(source.seed),
        source.scenario_id,
        source.scenario_version,
        source.scenario_scale or "",
        source.episode_id,
        source.git_commit,
        source.config_sha256,
        source.git_dirty,
    )


def _availability(value: RegionLearningAvailability | str) -> RegionLearningAvailability:
    return value if isinstance(value, RegionLearningAvailability) else RegionLearningAvailability(str(value))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _is_hex(value: str) -> bool:
    return bool(value) and all(character in "0123456789abcdef" for character in value.lower())


def _reject_truth_identifiers(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if (
                normalized in _FORBIDDEN_DATASET_KEYS
                or normalized.startswith("truth_")
                or normalized.endswith("_truth_id")
                or normalized.endswith("_global_track_id")
                or normalized.endswith("_target_id")
                or normalized.endswith("_object_id")
                or normalized.endswith("_actor_name")
                or "evaluator_truth" in normalized
                or "offline_truth" in normalized
            ):
                raise ValueError(f"truth or target identity is forbidden at {path}.{key}")
            _reject_truth_identifiers(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_truth_identifiers(item, f"{path}[{index}]")
