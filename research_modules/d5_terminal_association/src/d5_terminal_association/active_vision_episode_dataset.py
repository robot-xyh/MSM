"""Detached whole-episode dataset contract for D5 active vision.

Online policy records and evaluator-only labels are deliberately stored in
different files.  Online records are truth-free and contain only center-owned
track references.  Reward, outcome, counterfactual, and causal labels are
joined after an episode by stable sample/observation keys and never copied
back into :class:`ActiveVisionSnapshotV1`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .active_vision_contracts import (
    ACTIVE_VISION_ACTION_SCHEMA_VERSION,
    ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION,
    ActiveVisionActionV1,
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionDecisionV1,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionRuntimeMode,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    FriendlyObservationReservation,
    assert_truth_free_active_vision_payload,
    enumerate_safe_action_candidates,
)
from .active_vision_evaluation import MINIMUM_UNSEEN_ASSIST_SEEDS
from .active_vision_learning import (
    ACTIVE_VISION_REWARD_MAXIMUM,
    ACTIVE_VISION_REWARD_MINIMUM,
    ActiveVisionResearchEpisode,
    ActiveVisionTransition,
)


ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION = "d5.active-vision-episode-dataset.v2"
ACTIVE_VISION_EPISODE_DESCRIPTOR_SCHEMA_VERSION = "d5.active-vision-episode-descriptor.v1"
ACTIVE_VISION_EPISODE_RECORD_SCHEMA_VERSION = "d5.active-vision-episode-record.v1"
ACTIVE_VISION_SAMPLE_SCHEMA_VERSION = "d5.active-vision-sample.v1"
ACTIVE_VISION_CAMERA_FEEDBACK_SCHEMA_VERSION = "d5.active-vision-camera-feedback.v1"
ACTIVE_VISION_RUNTIME_ACK_SCHEMA_VERSION = "d5.active-vision-runtime-ack.v1"
ACTIVE_VISION_OFFLINE_LABELS_SCHEMA_VERSION = "d5.active-vision-offline-labels.v1"
ACTIVE_VISION_OFFLINE_LABEL_SCHEMA_VERSION = "d5.active-vision-offline-label.v1"
ACTIVE_VISION_SOURCE_IDENTITY_SCHEMA_VERSION = "d5.active-vision-source-identity.v1"
ACTIVE_VISION_DATASET_CONFIG_SCHEMA_VERSION = "d5.active-vision-dataset-config.v1"

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_COMMIT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+-]*")


class ActiveVisionDatasetValidationError(ValueError):
    """A stable fail-closed error from active-vision dataset auditing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class ActiveVisionSourceIdentityV1:
    """Exact source revision and externally archived episode-config identity."""

    git_commit: str
    git_dirty: bool
    config_sha256: str
    schema_version: str = ACTIVE_VISION_SOURCE_IDENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_SOURCE_IDENTITY_SCHEMA_VERSION:
            raise ValueError("active-vision source identity schema mismatch")
        commit = str(self.git_commit).strip().lower()
        config_sha = str(self.config_sha256).strip().lower()
        if _GIT_COMMIT_PATTERN.fullmatch(commit) is None:
            raise ValueError("git_commit must be a full lowercase Git object ID")
        if _SHA256_PATTERN.fullmatch(config_sha) is None:
            raise ValueError("config_sha256 must be a lowercase SHA256")
        object.__setattr__(self, "git_commit", commit)
        object.__setattr__(self, "git_dirty", _input_bool(self.git_dirty, "git_dirty"))
        object.__setattr__(self, "config_sha256", config_sha)


@dataclass(frozen=True)
class ActiveVisionCameraFeedbackV1:
    """Truth-free camera state observed after or alongside one decision."""

    camera_state: ActiveVisionCameraState
    last_accepted_command_version: int | None = None
    schema_version: str = ACTIVE_VISION_CAMERA_FEEDBACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_CAMERA_FEEDBACK_SCHEMA_VERSION:
            raise ValueError("active-vision camera feedback schema mismatch")
        if not isinstance(self.camera_state, ActiveVisionCameraState):
            raise TypeError("camera_state must be ActiveVisionCameraState")
        version = self.last_accepted_command_version
        if version is not None:
            version = int(version)
            if version < 0:
                raise ValueError("last_accepted_command_version must be non-negative")
        object.__setattr__(self, "last_accepted_command_version", version)
        assert_truth_free_active_vision_payload(self)


@dataclass(frozen=True)
class ActiveVisionRuntimeAckV1:
    """Optional truth-free acknowledgement from a camera-command runtime."""

    sample_key: str
    camera_id: str
    command_version: int
    ack_timestamp: float
    accepted: bool
    status_code: str
    plan_version: int
    coalition_version: int
    communication_version: int
    schema_version: str = ACTIVE_VISION_RUNTIME_ACK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_key", _key(self.sample_key, "sample_key"))
        object.__setattr__(self, "camera_id", _key(self.camera_id, "camera_id"))
        object.__setattr__(self, "status_code", _key(self.status_code, "status_code"))
        if self.schema_version != ACTIVE_VISION_RUNTIME_ACK_SCHEMA_VERSION:
            raise ValueError("active-vision runtime ACK schema mismatch")
        for name in (
            "command_version",
            "plan_version",
            "coalition_version",
            "communication_version",
        ):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "ack_timestamp", _finite(self.ack_timestamp, "ack_timestamp"))
        object.__setattr__(self, "accepted", _input_bool(self.accepted, "accepted"))
        assert_truth_free_active_vision_payload(self)


@dataclass(frozen=True)
class ActiveVisionEpisodeSampleV1:
    """One audited camera decision from a whole unified 3D episode."""

    sample_key: str
    observation_key: str
    sequence_index: int
    camera_id: str
    snapshot: ActiveVisionSnapshotV1
    rule_demonstration_action: ActiveVisionActionV1
    requested_action: ActiveVisionActionV1 | None
    effective_action: ActiveVisionActionV1
    requested_mode: ActiveVisionRuntimeMode
    effective_mode: ActiveVisionRuntimeMode
    fallback_reason: str | None
    plan_version: int
    coalition_version: int
    communication_version: int
    camera_feedback: ActiveVisionCameraFeedbackV1
    runtime_ack: ActiveVisionRuntimeAckV1 | None = None
    schema_version: str = ACTIVE_VISION_SAMPLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_SAMPLE_SCHEMA_VERSION:
            raise ValueError("active-vision sample schema mismatch")
        object.__setattr__(self, "sample_key", _key(self.sample_key, "sample_key"))
        object.__setattr__(self, "observation_key", _key(self.observation_key, "observation_key"))
        object.__setattr__(self, "camera_id", _key(self.camera_id, "camera_id"))
        sequence_index = int(self.sequence_index)
        if sequence_index < 0:
            raise ValueError("sequence_index must be non-negative")
        object.__setattr__(self, "sequence_index", sequence_index)
        object.__setattr__(self, "requested_mode", ActiveVisionRuntimeMode(self.requested_mode))
        object.__setattr__(self, "effective_mode", ActiveVisionRuntimeMode(self.effective_mode))
        fallback = None if self.fallback_reason is None else str(self.fallback_reason).strip()
        object.__setattr__(self, "fallback_reason", fallback or None)
        if not isinstance(self.snapshot, ActiveVisionSnapshotV1):
            raise TypeError("snapshot must be ActiveVisionSnapshotV1")
        camera = self.snapshot.camera(self.camera_id)
        _validate_snapshot_center_references(self.snapshot)
        versions = (
            self.snapshot.plan.plan_version,
            self.snapshot.plan.coalition_version,
            self.snapshot.communication.communication_version,
        )
        provided_versions = (
            int(self.plan_version),
            int(self.coalition_version),
            int(self.communication_version),
        )
        if provided_versions != versions:
            raise ValueError("sample plan/coalition/communication versions do not match snapshot")
        object.__setattr__(self, "plan_version", provided_versions[0])
        object.__setattr__(self, "coalition_version", provided_versions[1])
        object.__setattr__(self, "communication_version", provided_versions[2])
        for name, action in (
            ("rule_demonstration_action", self.rule_demonstration_action),
            ("effective_action", self.effective_action),
        ):
            _validate_action_reference(
                action,
                self.snapshot,
                self.camera_id,
                require_current_versions=True,
                field_name=name,
            )
        if self.requested_action is not None:
            _validate_action_reference(
                self.requested_action,
                self.snapshot,
                self.camera_id,
                require_current_versions=False,
                field_name="requested_action",
            )
        candidate_keys = {
            action.action_key
            for action in enumerate_safe_action_candidates(
                self.snapshot,
                camera_id=self.camera_id,
                current_timestamp=self.rule_demonstration_action.issued_timestamp,
            )
        }
        if self.rule_demonstration_action.action_key not in candidate_keys:
            raise ValueError("rule demonstration is outside the finite active-vision action set")
        if self.effective_action.action_key not in candidate_keys:
            raise ValueError("effective action is outside the finite active-vision action set")
        feedback = self.camera_feedback
        if not isinstance(feedback, ActiveVisionCameraFeedbackV1):
            raise TypeError("camera_feedback must be ActiveVisionCameraFeedbackV1")
        if (
            feedback.camera_state.camera_id != self.camera_id
            or feedback.camera_state.resource_id != camera.resource_id
        ):
            raise ValueError("camera feedback does not match the sampled camera/resource")
        if feedback.camera_state.state_timestamp + 1.0e-9 < camera.state_timestamp:
            raise ValueError("camera feedback timestamp precedes snapshot camera state")
        ack = self.runtime_ack
        if ack is not None:
            if not isinstance(ack, ActiveVisionRuntimeAckV1):
                raise TypeError("runtime_ack must be ActiveVisionRuntimeAckV1")
            if ack.sample_key != self.sample_key or ack.camera_id != self.camera_id:
                raise ValueError("runtime ACK does not match sample/camera")
            if (
                ack.plan_version,
                ack.coalition_version,
                ack.communication_version,
            ) != versions:
                raise ValueError("runtime ACK versions do not match the sample")
            if ack.ack_timestamp + 1.0e-9 < self.effective_action.issued_timestamp:
                raise ValueError("runtime ACK precedes the effective action")
            accepted_version = feedback.last_accepted_command_version
            if ack.accepted and accepted_version is not None and ack.command_version != accepted_version:
                raise ValueError("accepted runtime ACK disagrees with camera feedback version")
        assert_truth_free_active_vision_payload(self)


@dataclass(frozen=True)
class ActiveVisionEpisodeRecordV1:
    """Complete online, truth-free record for one episode."""

    scenario_version: str
    seed: int
    episode_id: str
    source_identity: ActiveVisionSourceIdentityV1
    samples: tuple[ActiveVisionEpisodeSampleV1, ...]
    synthetic_fixture: bool = False
    schema_version: str = ACTIVE_VISION_EPISODE_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_EPISODE_RECORD_SCHEMA_VERSION:
            raise ValueError("active-vision episode record schema mismatch")
        scenario = _key(self.scenario_version, "scenario_version")
        episode = _key(self.episode_id, "episode_id")
        samples = tuple(self.samples)
        if not samples:
            raise ValueError("active-vision episode must contain at least one sample")
        if not isinstance(self.source_identity, ActiveVisionSourceIdentityV1):
            raise TypeError("source_identity must be ActiveVisionSourceIdentityV1")
        if tuple(item.sequence_index for item in samples) != tuple(range(len(samples))):
            raise ValueError("sample sequence_index values must be contiguous from zero")
        sample_keys = tuple(item.sample_key for item in samples)
        observation_keys = tuple(item.observation_key for item in samples)
        if len(sample_keys) != len(set(sample_keys)):
            raise ValueError("sample_key values must be unique within an episode")
        if len(observation_keys) != len(set(observation_keys)):
            raise ValueError("observation_key values must be unique within an episode")
        timestamps = tuple(item.snapshot.snapshot_timestamp for item in samples)
        if any(right + 1.0e-9 < left for left, right in zip(timestamps, timestamps[1:])):
            raise ValueError("episode sample timestamps must be non-decreasing")
        previous_versions = (-1, -1, -1)
        center_track_state: dict[str, tuple[int, float]] = {}
        for sample in samples:
            versions = (
                sample.plan_version,
                sample.coalition_version,
                sample.communication_version,
            )
            if any(current < previous for current, previous in zip(versions, previous_versions)):
                raise ValueError("episode plan/coalition/communication versions must not decrease")
            previous_versions = versions
            for track in sample.snapshot.tracks:
                previous = center_track_state.get(track.global_track_id)
                if previous is not None and (
                    track.track_version < previous[0]
                    or track.measurement_timestamp + 1.0e-9 < previous[1]
                ):
                    raise ValueError("center-owned track reference regressed within the episode")
                center_track_state[track.global_track_id] = (
                    track.track_version,
                    track.measurement_timestamp,
                )
        object.__setattr__(self, "scenario_version", scenario)
        object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "episode_id", episode)
        object.__setattr__(self, "samples", samples)
        object.__setattr__(
            self,
            "synthetic_fixture",
            _input_bool(self.synthetic_fixture, "synthetic_fixture"),
        )
        assert_truth_free_active_vision_payload(self)

    @property
    def group_key(self) -> tuple[str, int]:
        return (self.scenario_version, self.seed)

    @property
    def episode_uid(self) -> str:
        return _episode_uid(self.scenario_version, self.seed, self.episode_id)


@dataclass(frozen=True)
class ActiveVisionOfflineLabelV1:
    """Evaluator-only label joined after the online episode has closed."""

    sample_key: str
    observation_key: str
    reward_available: bool = False
    reward: float | None = None
    reward_provenance: str | None = None
    outcome_available: bool = False
    outcome: Mapping[str, Any] | None = None
    counterfactual_available: bool = False
    counterfactual_reward: float | None = None
    counterfactual_provenance: str | None = None
    causal_label_available: bool = False
    causal_label: Mapping[str, Any] | None = None
    schema_version: str = ACTIVE_VISION_OFFLINE_LABEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_OFFLINE_LABEL_SCHEMA_VERSION:
            raise ValueError("active-vision offline label schema mismatch")
        object.__setattr__(self, "sample_key", _key(self.sample_key, "sample_key"))
        object.__setattr__(self, "observation_key", _key(self.observation_key, "observation_key"))
        reward_available = _input_bool(self.reward_available, "reward_available")
        outcome_available = _input_bool(self.outcome_available, "outcome_available")
        counterfactual_available = _input_bool(
            self.counterfactual_available, "counterfactual_available"
        )
        causal_available = _input_bool(
            self.causal_label_available, "causal_label_available"
        )
        reward = _optional_bounded_reward(self.reward, "reward")
        counterfactual_reward = _optional_bounded_reward(
            self.counterfactual_reward, "counterfactual_reward"
        )
        reward_provenance = _optional_text(self.reward_provenance)
        counterfactual_provenance = _optional_text(self.counterfactual_provenance)
        outcome = None if self.outcome is None else _immutable_json_object(self.outcome, "outcome")
        causal_label = (
            None
            if self.causal_label is None
            else _immutable_json_object(self.causal_label, "causal_label")
        )
        if reward_available:
            if reward is None or reward_provenance is None or not outcome_available:
                raise ValueError("available reward requires a bounded value, provenance, and outcome")
        elif reward is not None or reward_provenance is not None:
            raise ValueError("unavailable reward must use null value/provenance, never zero padding")
        if outcome_available != (outcome is not None):
            raise ValueError("outcome availability does not match outcome payload")
        if counterfactual_available:
            if counterfactual_reward is None or counterfactual_provenance is None:
                raise ValueError("available counterfactual requires bounded reward and provenance")
        elif counterfactual_reward is not None or counterfactual_provenance is not None:
            raise ValueError("unavailable counterfactual must use null value/provenance")
        if causal_available:
            if causal_label is None or not outcome_available or not counterfactual_available:
                raise ValueError("causal label requires factual outcome and counterfactual evidence")
        elif causal_label is not None:
            raise ValueError("unavailable causal label must be null")
        object.__setattr__(self, "reward_available", reward_available)
        object.__setattr__(self, "reward", reward)
        object.__setattr__(self, "reward_provenance", reward_provenance)
        object.__setattr__(self, "outcome_available", outcome_available)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "counterfactual_available", counterfactual_available)
        object.__setattr__(self, "counterfactual_reward", counterfactual_reward)
        object.__setattr__(self, "counterfactual_provenance", counterfactual_provenance)
        object.__setattr__(self, "causal_label_available", causal_available)
        object.__setattr__(self, "causal_label", causal_label)


@dataclass(frozen=True)
class LoadedActiveVisionEpisode:
    record: ActiveVisionEpisodeRecordV1
    offline_labels: tuple[ActiveVisionOfflineLabelV1, ...]
    split: str
    online_sha256: str
    offline_sha256: str

    def __post_init__(self) -> None:
        if self.split not in {"train", "validation", "test"}:
            raise ValueError("invalid active-vision dataset split")
        object.__setattr__(self, "offline_labels", tuple(self.offline_labels))

    @property
    def labels_by_sample_key(self) -> Mapping[str, ActiveVisionOfflineLabelV1]:
        return MappingProxyType({item.sample_key: item for item in self.offline_labels})


@dataclass(frozen=True)
class LoadedActiveVisionEpisodeDataset:
    root: Path
    manifest: Mapping[str, Any]
    manifest_sha256: str
    episodes: tuple[LoadedActiveVisionEpisode, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))
        object.__setattr__(self, "manifest", _freeze_json(self.manifest))
        object.__setattr__(self, "episodes", tuple(self.episodes))

    def split(self, name: str) -> tuple[LoadedActiveVisionEpisode, ...]:
        if name not in {"train", "validation", "test"}:
            raise ValueError("split must be train, validation, or test")
        return tuple(item for item in self.episodes if item.split == name)

    def behavior_cloning_episodes(self, split: str = "train") -> tuple[ActiveVisionResearchEpisode, ...]:
        """Return rule-demonstration episodes without importing offline labels."""

        return tuple(_behavior_cloning_episode(item) for item in self.split(split))

    def ppo_episodes(self, split: str = "train") -> tuple[ActiveVisionResearchEpisode, ...]:
        """Return effective-action rollouts only when every reward is available."""

        return tuple(_ppo_episode(item) for item in self.split(split))


def active_vision_sample_from_decision(
    *,
    sample_key: str,
    observation_key: str,
    sequence_index: int,
    camera_id: str,
    snapshot: ActiveVisionSnapshotV1,
    decision: ActiveVisionDecisionV1,
    camera_feedback: ActiveVisionCameraFeedbackV1,
    runtime_ack: ActiveVisionRuntimeAckV1 | None = None,
) -> ActiveVisionEpisodeSampleV1:
    """Build a record sample from the existing online decision contract."""

    if not isinstance(decision, ActiveVisionDecisionV1):
        raise TypeError("decision must be ActiveVisionDecisionV1")
    return ActiveVisionEpisodeSampleV1(
        sample_key=sample_key,
        observation_key=observation_key,
        sequence_index=sequence_index,
        camera_id=camera_id,
        snapshot=snapshot,
        rule_demonstration_action=decision.rule_action,
        requested_action=decision.requested_action,
        effective_action=decision.effective_action,
        requested_mode=decision.requested_mode,
        effective_mode=decision.effective_mode,
        fallback_reason=decision.fallback_reason,
        plan_version=decision.plan_version,
        coalition_version=decision.coalition_version,
        communication_version=decision.communication_version,
        camera_feedback=camera_feedback,
        runtime_ack=runtime_ack,
    )


def unavailable_active_vision_offline_labels(
    record: ActiveVisionEpisodeRecordV1,
) -> tuple[ActiveVisionOfflineLabelV1, ...]:
    """Create explicit unavailable joins without inventing numeric zero labels."""

    if not isinstance(record, ActiveVisionEpisodeRecordV1):
        raise TypeError("record must be ActiveVisionEpisodeRecordV1")
    return tuple(
        ActiveVisionOfflineLabelV1(
            sample_key=sample.sample_key,
            observation_key=sample.observation_key,
        )
        for sample in record.samples
    )


def stage_active_vision_episode_record(
    dataset_dir: str | Path,
    record: ActiveVisionEpisodeRecordV1,
    *,
    generation_config: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Stage one closed online episode without any evaluator labels."""

    if not isinstance(record, ActiveVisionEpisodeRecordV1):
        raise TypeError("record must be ActiveVisionEpisodeRecordV1")
    root = Path(dataset_dir)
    _ensure_not_finalized(root)
    root.mkdir(parents=True, exist_ok=True)
    config_sha256 = _ensure_generation_config(root, generation_config)
    uid = record.episode_uid
    online_relative = Path("online") / f"{uid}.online.json"
    descriptor_relative = Path("episodes") / f"{uid}.episode.json"
    for relative in (online_relative, descriptor_relative):
        path = root / relative
        if path.exists():
            raise FileExistsError(f"active-vision episode artifact already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    online_payload = _episode_record_to_payload(record)
    try:
        assert_truth_free_active_vision_payload(online_payload)
    except ValueError as exc:
        raise ActiveVisionDatasetValidationError(
            "online_truth_identity_forbidden",
            "online active-vision episode contains evaluator/simulator identity",
        ) from exc
    _write_json_atomic(root / online_relative, online_payload)
    _make_read_only(root / online_relative)
    descriptor = {
        "schema_version": ACTIVE_VISION_EPISODE_DESCRIPTOR_SCHEMA_VERSION,
        "episode_uid": uid,
        "scenario_version": record.scenario_version,
        "seed": record.seed,
        "episode_id": record.episode_id,
        "source_identity": _source_identity_to_payload(record.source_identity),
        "synthetic_fixture": record.synthetic_fixture,
        "dataset_config_sha256": config_sha256,
        "online_file": online_relative.as_posix(),
        "online_sha256": sha256_file(root / online_relative),
        "offline_file": None,
        "offline_sha256": None,
        "sample_count": len(record.samples),
        "availability": None,
        "split": None,
    }
    _write_json_atomic(root / descriptor_relative, descriptor)
    return MappingProxyType(descriptor)


def stage_active_vision_offline_labels(
    dataset_dir: str | Path,
    episode_uid: str,
    labels: Iterable[ActiveVisionOfflineLabelV1],
) -> Mapping[str, Any]:
    """Join evaluator labels after online episode closure by both stable keys."""

    root = Path(dataset_dir)
    _ensure_not_finalized(root)
    uid = _key(episode_uid, "episode_uid")
    descriptor_path = root / "episodes" / f"{uid}.episode.json"
    if not descriptor_path.is_file():
        raise FileNotFoundError(f"staged active-vision episode is missing: {uid}")
    descriptor = _read_json(descriptor_path)
    _validate_descriptor(descriptor, finalized=False)
    if descriptor["episode_uid"] != uid:
        raise ActiveVisionDatasetValidationError(
            "episode_identity_mismatch", "descriptor episode UID does not match its filename"
        )
    if descriptor["offline_file"] is not None or descriptor["offline_sha256"] is not None:
        raise FileExistsError(f"offline labels already exist for active-vision episode {uid}")
    online_path = _safe_relative_file(root, descriptor["online_file"])
    _expect_sha(online_path, descriptor["online_sha256"], "online_sha_mismatch")
    record = load_active_vision_episode_record(online_path)
    items = tuple(labels)
    if any(not isinstance(item, ActiveVisionOfflineLabelV1) for item in items):
        raise TypeError("labels must contain ActiveVisionOfflineLabelV1")
    online_keys = {
        sample.sample_key: sample.observation_key for sample in record.samples
    }
    label_keys: dict[str, str] = {}
    for item in items:
        if item.sample_key in label_keys:
            raise ValueError(f"duplicate offline label for sample {item.sample_key}")
        label_keys[item.sample_key] = item.observation_key
    if label_keys != online_keys:
        raise ActiveVisionDatasetValidationError(
            "offline_label_join_mismatch",
            "offline labels must match every online sample and observation key exactly",
        )
    offline_relative = Path("offline") / f"{uid}.offline.json"
    offline_path = root / offline_relative
    if offline_path.exists():
        raise FileExistsError(f"offline label artifact already exists: {offline_path}")
    offline_path.parent.mkdir(parents=True, exist_ok=True)
    offline_payload = {
        "schema_version": ACTIVE_VISION_OFFLINE_LABELS_SCHEMA_VERSION,
        "episode_uid": uid,
        "scenario_version": record.scenario_version,
        "seed": record.seed,
        "episode_id": record.episode_id,
        "reward_bounds": {
            "minimum": ACTIVE_VISION_REWARD_MINIMUM,
            "maximum": ACTIVE_VISION_REWARD_MAXIMUM,
        },
        "labels": [_offline_label_to_payload(item) for item in items],
    }
    _write_json_atomic(offline_path, offline_payload)
    _make_read_only(offline_path)
    descriptor["offline_file"] = offline_relative.as_posix()
    descriptor["offline_sha256"] = sha256_file(offline_path)
    descriptor["availability"] = _availability_summary(items)
    _write_json_atomic(descriptor_path, descriptor)
    return MappingProxyType(descriptor)


def finalize_active_vision_episode_dataset(
    dataset_dir: str | Path,
    *,
    split_seed: int = 20260720,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
    minimum_unseen_seed_count: int = MINIMUM_UNSEEN_ASSIST_SEEDS,
) -> Mapping[str, Any]:
    """Freeze staged episodes into deterministic whole-group dataset splits."""

    root = Path(dataset_dir)
    _ensure_not_finalized(root)
    config_path = root / "dataset_config.json"
    if not config_path.is_file():
        raise ActiveVisionDatasetValidationError(
            "dataset_config_missing", "dataset_config.json is missing"
        )
    descriptors = tuple(
        _read_json(path) for path in sorted((root / "episodes").glob("*.episode.json"))
    )
    if not descriptors:
        raise ActiveVisionDatasetValidationError(
            "episodes_missing", "no staged active-vision episodes were found"
        )
    config_sha = sha256_file(config_path)
    for descriptor in descriptors:
        _validate_descriptor(descriptor, finalized=False)
        if descriptor["offline_file"] is None:
            raise ActiveVisionDatasetValidationError(
                "offline_labels_missing",
                "every episode requires an explicit offline label file, including unavailable labels",
            )
        if descriptor["dataset_config_sha256"] != config_sha:
            raise ActiveVisionDatasetValidationError(
                "episode_config_sha_mismatch", "episode generation config hash mismatch"
            )
        _load_staged_episode(root, descriptor)
    split_by_uid, unseen_count = _split_episode_descriptors(
        descriptors,
        split_seed=split_seed,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
        minimum_unseen_seed_count=minimum_unseen_seed_count,
    )
    finalized_descriptors: list[dict[str, Any]] = []
    for descriptor in sorted(descriptors, key=lambda item: str(item["episode_uid"])):
        finalized = dict(descriptor)
        finalized["split"] = split_by_uid[str(descriptor["episode_uid"])]
        descriptor_path = root / "episodes" / f"{descriptor['episode_uid']}.episode.json"
        _write_json_atomic(descriptor_path, finalized)
        finalized_descriptors.append(finalized)
    split_payload = _split_payload(finalized_descriptors)
    manifest = {
        "schema_version": ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION,
        "episode_descriptor_schema_version": ACTIVE_VISION_EPISODE_DESCRIPTOR_SCHEMA_VERSION,
        "episode_record_schema_version": ACTIVE_VISION_EPISODE_RECORD_SCHEMA_VERSION,
        "sample_schema_version": ACTIVE_VISION_SAMPLE_SCHEMA_VERSION,
        "snapshot_schema_version": ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION,
        "action_schema_version": ACTIVE_VISION_ACTION_SCHEMA_VERSION,
        "camera_feedback_schema_version": ACTIVE_VISION_CAMERA_FEEDBACK_SCHEMA_VERSION,
        "runtime_ack_schema_version": ACTIVE_VISION_RUNTIME_ACK_SCHEMA_VERSION,
        "offline_labels_schema_version": ACTIVE_VISION_OFFLINE_LABELS_SCHEMA_VERSION,
        "offline_label_schema_version": ACTIVE_VISION_OFFLINE_LABEL_SCHEMA_VERSION,
        "dataset_config_file": config_path.name,
        "dataset_config_sha256": config_sha,
        "storage_contract": {
            "online_truth_free": True,
            "offline_labels_physically_separate": True,
            "detached": True,
            "immutable": True,
            "missing_numeric_labels_use_null": True,
        },
        "reward_contract": {
            "minimum": ACTIVE_VISION_REWARD_MINIMUM,
            "maximum": ACTIVE_VISION_REWARD_MAXIMUM,
            "unavailable_value": None,
            "reward_requires_offline_outcome": True,
            "causal_label_requires_outcome_and_counterfactual": True,
        },
        "split_policy": {
            "unit": "whole_episode_grouped_by_scenario_version_and_seed",
            "sample_or_transition_level_random_split": False,
            "shared_seed_values_atomic_across_scenarios": True,
            "split_seed": int(split_seed),
            "validation_fraction": float(validation_fraction),
            "test_fraction": float(test_fraction),
            "minimum_unseen_seed_count": int(minimum_unseen_seed_count),
            "unseen_test_seed_count": unseen_count,
        },
        "split_sha256": sha256_json(split_payload),
        "training_set_sha256": _training_set_sha256(finalized_descriptors),
        "source_identity_summary": _source_identity_summary(finalized_descriptors),
        "availability": _dataset_availability(finalized_descriptors),
        "episodes": finalized_descriptors,
    }
    manifest_path = root / "manifest.json"
    _write_json_atomic(manifest_path, manifest)
    artifact_paths = tuple(
        sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS"
        )
    )
    checksums_path = root / "SHA256SUMS"
    checksum_lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}\n"
        for path in artifact_paths
    ]
    _write_bytes_atomic(checksums_path, "".join(checksum_lines).encode("ascii"))
    for path in (*artifact_paths, checksums_path):
        _make_read_only(path)
    loaded = load_active_vision_episode_dataset(root)
    if len(loaded.episodes) != len(finalized_descriptors):
        raise RuntimeError("finalized active-vision dataset episode count changed during audit")
    return MappingProxyType(manifest)


def load_active_vision_episode_record(path: str | Path) -> ActiveVisionEpisodeRecordV1:
    """Load and audit one standalone truth-free online episode artifact."""

    payload = _read_json(Path(path))
    try:
        assert_truth_free_active_vision_payload(payload)
    except ValueError as exc:
        raise ActiveVisionDatasetValidationError(
            "online_truth_identity_forbidden",
            "online active-vision episode contains evaluator/simulator identity",
        ) from exc
    try:
        return _episode_record_from_payload(payload)
    except ActiveVisionDatasetValidationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ActiveVisionDatasetValidationError(
            "online_record_invalid", "online active-vision episode failed contract validation"
        ) from exc


def load_active_vision_episode_dataset(
    dataset_dir: str | Path,
    *,
    expected_generation_config_sha256: str | None = None,
) -> LoadedActiveVisionEpisodeDataset:
    """Audit hashes, versions, split isolation, identities, and offline joins."""

    root = Path(dataset_dir).resolve()
    manifest_path = root / "manifest.json"
    checksums_path = root / "SHA256SUMS"
    if not manifest_path.is_file():
        raise ActiveVisionDatasetValidationError("manifest_missing", "manifest.json is missing")
    if not checksums_path.is_file():
        raise ActiveVisionDatasetValidationError("checksums_missing", "SHA256SUMS is missing")
    checksums = _read_checksums(checksums_path)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != checksums_path
    }
    if set(checksums) != actual_files:
        raise ActiveVisionDatasetValidationError(
            "artifact_set_mismatch", "SHA256SUMS does not exactly cover dataset artifacts"
        )
    for relative, expected_sha in checksums.items():
        path = _safe_relative_file(root, relative)
        _expect_sha(path, expected_sha, "artifact_sha_mismatch")
        _require_read_only(path)
    _require_read_only(checksums_path)
    manifest = _read_json(manifest_path)
    expected_manifest_fields = {
        "schema_version",
        "episode_descriptor_schema_version",
        "episode_record_schema_version",
        "sample_schema_version",
        "snapshot_schema_version",
        "action_schema_version",
        "camera_feedback_schema_version",
        "runtime_ack_schema_version",
        "offline_labels_schema_version",
        "offline_label_schema_version",
        "dataset_config_file",
        "dataset_config_sha256",
        "storage_contract",
        "reward_contract",
        "split_policy",
        "split_sha256",
        "training_set_sha256",
        "source_identity_summary",
        "availability",
        "episodes",
    }
    _expect_fields(manifest, expected_manifest_fields, "manifest_fields_mismatch")
    _expect_equal(
        manifest["schema_version"],
        ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION,
        "dataset_schema_mismatch",
    )
    version_expectations = {
        "episode_descriptor_schema_version": ACTIVE_VISION_EPISODE_DESCRIPTOR_SCHEMA_VERSION,
        "episode_record_schema_version": ACTIVE_VISION_EPISODE_RECORD_SCHEMA_VERSION,
        "sample_schema_version": ACTIVE_VISION_SAMPLE_SCHEMA_VERSION,
        "snapshot_schema_version": ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION,
        "action_schema_version": ACTIVE_VISION_ACTION_SCHEMA_VERSION,
        "camera_feedback_schema_version": ACTIVE_VISION_CAMERA_FEEDBACK_SCHEMA_VERSION,
        "runtime_ack_schema_version": ACTIVE_VISION_RUNTIME_ACK_SCHEMA_VERSION,
        "offline_labels_schema_version": ACTIVE_VISION_OFFLINE_LABELS_SCHEMA_VERSION,
        "offline_label_schema_version": ACTIVE_VISION_OFFLINE_LABEL_SCHEMA_VERSION,
    }
    for field_name, expected in version_expectations.items():
        _expect_equal(manifest[field_name], expected, f"{field_name}_mismatch")
    storage_contract = manifest["storage_contract"]
    expected_storage = {
        "online_truth_free": True,
        "offline_labels_physically_separate": True,
        "detached": True,
        "immutable": True,
        "missing_numeric_labels_use_null": True,
    }
    _expect_equal(storage_contract, expected_storage, "storage_contract_mismatch")
    expected_reward_contract = {
        "minimum": ACTIVE_VISION_REWARD_MINIMUM,
        "maximum": ACTIVE_VISION_REWARD_MAXIMUM,
        "unavailable_value": None,
        "reward_requires_offline_outcome": True,
        "causal_label_requires_outcome_and_counterfactual": True,
    }
    _expect_equal(manifest["reward_contract"], expected_reward_contract, "reward_contract_mismatch")
    config_path = _safe_relative_file(root, manifest["dataset_config_file"])
    config_sha = sha256_file(config_path)
    _expect_equal(config_sha, manifest["dataset_config_sha256"], "dataset_config_sha_mismatch")
    if expected_generation_config_sha256 is not None:
        _expect_equal(
            config_sha,
            _sha256(expected_generation_config_sha256, "expected_generation_config_sha256"),
            "unexpected_dataset_config_sha",
        )
    config_payload = _read_json(config_path)
    _expect_equal(
        config_payload.get("schema_version"),
        ACTIVE_VISION_DATASET_CONFIG_SCHEMA_VERSION,
        "dataset_config_schema_mismatch",
    )
    try:
        assert_truth_free_active_vision_payload(config_payload)
    except ValueError as exc:
        raise ActiveVisionDatasetValidationError(
            "dataset_config_truth_identity_forbidden",
            "dataset generation config contains evaluator/simulator identity",
        ) from exc
    raw_episodes = manifest["episodes"]
    if not isinstance(raw_episodes, list) or not raw_episodes:
        raise ActiveVisionDatasetValidationError("episodes_missing", "manifest contains no episodes")
    split_policy = manifest["split_policy"]
    if not isinstance(split_policy, Mapping):
        raise ActiveVisionDatasetValidationError("split_policy_invalid", "split policy is not an object")
    expected_split_fields = {
        "unit",
        "sample_or_transition_level_random_split",
        "shared_seed_values_atomic_across_scenarios",
        "split_seed",
        "validation_fraction",
        "test_fraction",
        "minimum_unseen_seed_count",
        "unseen_test_seed_count",
    }
    _expect_fields(split_policy, expected_split_fields, "split_policy_fields_mismatch")
    _expect_equal(
        split_policy["unit"],
        "whole_episode_grouped_by_scenario_version_and_seed",
        "split_unit_mismatch",
    )
    _expect_equal(
        split_policy["sample_or_transition_level_random_split"],
        False,
        "sample_random_split_forbidden",
    )
    _expect_equal(
        split_policy["shared_seed_values_atomic_across_scenarios"],
        True,
        "shared_seed_split_policy_mismatch",
    )
    expected_splits, unseen_count = _split_episode_descriptors(
        raw_episodes,
        split_seed=int(split_policy["split_seed"]),
        validation_fraction=float(split_policy["validation_fraction"]),
        test_fraction=float(split_policy["test_fraction"]),
        minimum_unseen_seed_count=int(split_policy["minimum_unseen_seed_count"]),
    )
    _expect_equal(
        unseen_count,
        int(split_policy["unseen_test_seed_count"]),
        "unseen_seed_count_mismatch",
    )
    loaded: list[LoadedActiveVisionEpisode] = []
    seen_uids: set[str] = set()
    groups_to_split: dict[tuple[str, int], str] = {}
    for descriptor in raw_episodes:
        if not isinstance(descriptor, Mapping):
            raise ActiveVisionDatasetValidationError(
                "descriptor_invalid", "episode descriptor is not an object"
            )
        _validate_descriptor(descriptor, finalized=True)
        uid = str(descriptor["episode_uid"])
        if uid in seen_uids:
            raise ActiveVisionDatasetValidationError(
                "episode_duplicate", f"duplicate episode descriptor: {uid}"
            )
        seen_uids.add(uid)
        split = str(descriptor["split"])
        _expect_equal(split, expected_splits[uid], "split_assignment_mismatch")
        group = (str(descriptor["scenario_version"]), int(descriptor["seed"]))
        previous_split = groups_to_split.setdefault(group, split)
        if previous_split != split:
            raise ActiveVisionDatasetValidationError(
                "seed_group_leakage", f"scenario/seed group appears in multiple splits: {group}"
            )
        loaded_episode = _load_staged_episode(root, descriptor)
        loaded.append(
            LoadedActiveVisionEpisode(
                record=loaded_episode[0],
                offline_labels=loaded_episode[1],
                split=split,
                online_sha256=str(descriptor["online_sha256"]),
                offline_sha256=str(descriptor["offline_sha256"]),
            )
        )
    if set(groups_to_split.values()) != {"train", "validation", "test"}:
        raise ActiveVisionDatasetValidationError(
            "split_empty", "train, validation, and test splits must all be non-empty"
        )
    split_payload = _split_payload(raw_episodes)
    _expect_equal(sha256_json(split_payload), manifest["split_sha256"], "split_sha_mismatch")
    _expect_equal(
        _training_set_sha256(raw_episodes),
        manifest["training_set_sha256"],
        "training_set_sha_mismatch",
    )
    _expect_equal(
        _source_identity_summary(raw_episodes),
        manifest["source_identity_summary"],
        "source_identity_summary_mismatch",
    )
    _expect_equal(
        _dataset_availability(raw_episodes),
        manifest["availability"],
        "availability_summary_mismatch",
    )
    return LoadedActiveVisionEpisodeDataset(
        root=root,
        manifest=manifest,
        manifest_sha256=sha256_file(manifest_path),
        episodes=tuple(sorted(loaded, key=lambda item: item.record.episode_uid)),
    )


def audit_active_vision_episode_dataset(dataset_dir: str | Path) -> Mapping[str, Any]:
    """Return an immutable high-level audit after full fail-closed loading."""

    dataset = load_active_vision_episode_dataset(dataset_dir)
    split_counts = {
        split: len(dataset.split(split)) for split in ("train", "validation", "test")
    }
    sample_count = sum(len(item.record.samples) for item in dataset.episodes)
    return MappingProxyType(
        {
            "schema_version": ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION,
            "manifest_sha256": dataset.manifest_sha256,
            "episode_count": len(dataset.episodes),
            "sample_count": sample_count,
            "split_episode_counts": split_counts,
            "availability": dataset.manifest["availability"],
            "status": "valid_detached_immutable_dataset",
        }
    )


def _episode_record_to_payload(record: ActiveVisionEpisodeRecordV1) -> dict[str, Any]:
    return {
        "schema_version": record.schema_version,
        "episode_uid": record.episode_uid,
        "scenario_version": record.scenario_version,
        "seed": record.seed,
        "episode_id": record.episode_id,
        "source_identity": _source_identity_to_payload(record.source_identity),
        "synthetic_fixture": record.synthetic_fixture,
        "samples": [_sample_to_payload(item) for item in record.samples],
    }


def _episode_record_from_payload(payload: Mapping[str, Any]) -> ActiveVisionEpisodeRecordV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "episode_uid",
            "scenario_version",
            "seed",
            "episode_id",
            "source_identity",
            "synthetic_fixture",
            "samples",
        },
        "online_record_fields_mismatch",
    )
    raw_samples = payload["samples"]
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ActiveVisionDatasetValidationError(
            "online_samples_invalid", "online episode samples must be a non-empty list"
        )
    record = ActiveVisionEpisodeRecordV1(
        scenario_version=str(payload["scenario_version"]),
        seed=int(payload["seed"]),
        episode_id=str(payload["episode_id"]),
        source_identity=_source_identity_from_payload(_mapping(payload["source_identity"])),
        samples=tuple(_sample_from_payload(_mapping(item)) for item in raw_samples),
        synthetic_fixture=_strict_bool(payload["synthetic_fixture"], "synthetic_fixture"),
        schema_version=str(payload["schema_version"]),
    )
    _expect_equal(record.episode_uid, payload["episode_uid"], "episode_uid_mismatch")
    return record


def _source_identity_to_payload(value: ActiveVisionSourceIdentityV1) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "git_commit": value.git_commit,
        "git_dirty": value.git_dirty,
        "config_sha256": value.config_sha256,
    }


def _source_identity_from_payload(payload: Mapping[str, Any]) -> ActiveVisionSourceIdentityV1:
    _expect_fields(
        payload,
        {"schema_version", "git_commit", "git_dirty", "config_sha256"},
        "source_identity_fields_mismatch",
    )
    return ActiveVisionSourceIdentityV1(
        git_commit=str(payload["git_commit"]),
        git_dirty=_strict_bool(payload["git_dirty"], "git_dirty"),
        config_sha256=str(payload["config_sha256"]),
        schema_version=str(payload["schema_version"]),
    )


def _sample_to_payload(sample: ActiveVisionEpisodeSampleV1) -> dict[str, Any]:
    return {
        "schema_version": sample.schema_version,
        "sample_key": sample.sample_key,
        "observation_key": sample.observation_key,
        "sequence_index": sample.sequence_index,
        "camera_id": sample.camera_id,
        "snapshot": _snapshot_to_payload(sample.snapshot),
        "rule_demonstration_action": _action_to_payload(sample.rule_demonstration_action),
        "requested_action": (
            None if sample.requested_action is None else _action_to_payload(sample.requested_action)
        ),
        "effective_action": _action_to_payload(sample.effective_action),
        "requested_mode": sample.requested_mode.value,
        "effective_mode": sample.effective_mode.value,
        "fallback_reason": sample.fallback_reason,
        "plan_version": sample.plan_version,
        "coalition_version": sample.coalition_version,
        "communication_version": sample.communication_version,
        "camera_feedback": _feedback_to_payload(sample.camera_feedback),
        "runtime_ack": None if sample.runtime_ack is None else _ack_to_payload(sample.runtime_ack),
    }


def _sample_from_payload(payload: Mapping[str, Any]) -> ActiveVisionEpisodeSampleV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "sample_key",
            "observation_key",
            "sequence_index",
            "camera_id",
            "snapshot",
            "rule_demonstration_action",
            "requested_action",
            "effective_action",
            "requested_mode",
            "effective_mode",
            "fallback_reason",
            "plan_version",
            "coalition_version",
            "communication_version",
            "camera_feedback",
            "runtime_ack",
        },
        "sample_fields_mismatch",
    )
    requested_payload = payload["requested_action"]
    ack_payload = payload["runtime_ack"]
    return ActiveVisionEpisodeSampleV1(
        sample_key=str(payload["sample_key"]),
        observation_key=str(payload["observation_key"]),
        sequence_index=int(payload["sequence_index"]),
        camera_id=str(payload["camera_id"]),
        snapshot=_snapshot_from_payload(_mapping(payload["snapshot"])),
        rule_demonstration_action=_action_from_payload(
            _mapping(payload["rule_demonstration_action"])
        ),
        requested_action=(
            None
            if requested_payload is None
            else _action_from_payload(_mapping(requested_payload))
        ),
        effective_action=_action_from_payload(_mapping(payload["effective_action"])),
        requested_mode=ActiveVisionRuntimeMode(str(payload["requested_mode"])),
        effective_mode=ActiveVisionRuntimeMode(str(payload["effective_mode"])),
        fallback_reason=(
            None if payload["fallback_reason"] is None else str(payload["fallback_reason"])
        ),
        plan_version=int(payload["plan_version"]),
        coalition_version=int(payload["coalition_version"]),
        communication_version=int(payload["communication_version"]),
        camera_feedback=_feedback_from_payload(_mapping(payload["camera_feedback"])),
        runtime_ack=None if ack_payload is None else _ack_from_payload(_mapping(ack_payload)),
        schema_version=str(payload["schema_version"]),
    )


def _snapshot_to_payload(snapshot: ActiveVisionSnapshotV1) -> dict[str, Any]:
    return {
        "schema_version": snapshot.schema_version,
        "snapshot_timestamp": snapshot.snapshot_timestamp,
        "plan": {
            "plan_version": snapshot.plan.plan_version,
            "coalition_version": snapshot.plan.coalition_version,
            "assignments": [
                {
                    "resource_id": item.resource_id,
                    "camera_id": item.camera_id,
                    "global_track_id": item.global_track_id,
                }
                for item in snapshot.plan.assignments
            ],
        },
        "communication": {
            "communication_version": snapshot.communication.communication_version,
            "plan_version": snapshot.communication.plan_version,
            "coalition_version": snapshot.communication.coalition_version,
            "update_timestamp": snapshot.communication.update_timestamp,
            "healthy": snapshot.communication.healthy,
            "peer_reservations": [
                {
                    "owner_resource_id": item.owner_resource_id,
                    "camera_id": item.camera_id,
                    "communication_version": item.communication_version,
                    "coalition_version": item.coalition_version,
                    "expires_timestamp": item.expires_timestamp,
                    "exclusive": item.exclusive,
                    "global_track_id": item.global_track_id,
                    "sector_deg": None if item.sector_deg is None else list(item.sector_deg),
                }
                for item in snapshot.communication.peer_reservations
            ],
        },
        "tracks": [
            {
                "global_track_id": item.global_track_id,
                "track_version": item.track_version,
                "measurement_timestamp": item.measurement_timestamp,
            }
            for item in snapshot.tracks
        ],
        "cameras": [_camera_to_payload(item) for item in snapshot.cameras],
        "projections": [
            {
                "camera_id": item.camera_id,
                "global_track_id": item.global_track_id,
                "measurement_timestamp": item.measurement_timestamp,
                "arrival_timestamp": item.arrival_timestamp,
                "yaw_error_deg": item.yaw_error_deg,
                "pitch_error_deg": item.pitch_error_deg,
                "projection_covariance_deg2": list(item.projection_covariance_deg2),
                "visibility_probability": item.visibility_probability,
                "occlusion_fraction": item.occlusion_fraction,
                "association_confidence": item.association_confidence,
                "in_fov": item.in_fov,
            }
            for item in snapshot.projections
        ],
    }


def _snapshot_from_payload(payload: Mapping[str, Any]) -> ActiveVisionSnapshotV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "snapshot_timestamp",
            "plan",
            "communication",
            "tracks",
            "cameras",
            "projections",
        },
        "snapshot_fields_mismatch",
    )
    plan_payload = _mapping(payload["plan"])
    _expect_fields(
        plan_payload,
        {"plan_version", "coalition_version", "assignments"},
        "plan_fields_mismatch",
    )
    assignments = _list(payload=plan_payload["assignments"], name="assignments")
    assignment_values: list[ActiveVisionAssignmentReference] = []
    for raw in assignments:
        item = _mapping(raw)
        _expect_fields(
            item,
            {"resource_id", "camera_id", "global_track_id"},
            "assignment_fields_mismatch",
        )
        assignment_values.append(
            ActiveVisionAssignmentReference(
                resource_id=str(item["resource_id"]),
                camera_id=str(item["camera_id"]),
                global_track_id=str(item["global_track_id"]),
            )
        )
    communication_payload = _mapping(payload["communication"])
    _expect_fields(
        communication_payload,
        {
            "communication_version",
            "plan_version",
            "coalition_version",
            "update_timestamp",
            "healthy",
            "peer_reservations",
        },
        "communication_fields_mismatch",
    )
    reservations: list[FriendlyObservationReservation] = []
    for raw in _list(communication_payload["peer_reservations"], "peer_reservations"):
        item = _mapping(raw)
        _expect_fields(
            item,
            {
                "owner_resource_id",
                "camera_id",
                "communication_version",
                "coalition_version",
                "expires_timestamp",
                "exclusive",
                "global_track_id",
                "sector_deg",
            },
            "reservation_fields_mismatch",
        )
        reservations.append(
            FriendlyObservationReservation(
                owner_resource_id=str(item["owner_resource_id"]),
                camera_id=str(item["camera_id"]),
                communication_version=int(item["communication_version"]),
                coalition_version=int(item["coalition_version"]),
                expires_timestamp=float(item["expires_timestamp"]),
                exclusive=_strict_bool(item["exclusive"], "exclusive"),
                global_track_id=(
                    None if item["global_track_id"] is None else str(item["global_track_id"])
                ),
                sector_deg=(
                    None if item["sector_deg"] is None else tuple(item["sector_deg"])
                ),
            )
        )
    tracks: list[ActiveVisionTrackReference] = []
    for raw in _list(payload["tracks"], "tracks"):
        item = _mapping(raw)
        _expect_fields(
            item,
            {"global_track_id", "track_version", "measurement_timestamp"},
            "track_fields_mismatch",
        )
        tracks.append(
            ActiveVisionTrackReference(
                global_track_id=str(item["global_track_id"]),
                track_version=int(item["track_version"]),
                measurement_timestamp=float(item["measurement_timestamp"]),
            )
        )
    cameras = tuple(
        _camera_from_payload(_mapping(item)) for item in _list(payload["cameras"], "cameras")
    )
    projections: list[ActiveVisionProjectionEvidence] = []
    for raw in _list(payload["projections"], "projections"):
        item = _mapping(raw)
        _expect_fields(
            item,
            {
                "camera_id",
                "global_track_id",
                "measurement_timestamp",
                "arrival_timestamp",
                "yaw_error_deg",
                "pitch_error_deg",
                "projection_covariance_deg2",
                "visibility_probability",
                "occlusion_fraction",
                "association_confidence",
                "in_fov",
            },
            "projection_fields_mismatch",
        )
        projections.append(
            ActiveVisionProjectionEvidence(
                camera_id=str(item["camera_id"]),
                global_track_id=str(item["global_track_id"]),
                measurement_timestamp=float(item["measurement_timestamp"]),
                arrival_timestamp=float(item["arrival_timestamp"]),
                yaw_error_deg=float(item["yaw_error_deg"]),
                pitch_error_deg=float(item["pitch_error_deg"]),
                projection_covariance_deg2=tuple(item["projection_covariance_deg2"]),
                visibility_probability=float(item["visibility_probability"]),
                occlusion_fraction=float(item["occlusion_fraction"]),
                association_confidence=float(item["association_confidence"]),
                in_fov=_strict_bool(item["in_fov"], "in_fov"),
            )
        )
    return ActiveVisionSnapshotV1(
        snapshot_timestamp=float(payload["snapshot_timestamp"]),
        plan=ActiveVisionPlanReference(
            plan_version=int(plan_payload["plan_version"]),
            coalition_version=int(plan_payload["coalition_version"]),
            assignments=tuple(assignment_values),
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=int(communication_payload["communication_version"]),
            plan_version=int(communication_payload["plan_version"]),
            coalition_version=int(communication_payload["coalition_version"]),
            update_timestamp=float(communication_payload["update_timestamp"]),
            healthy=_strict_bool(communication_payload["healthy"], "healthy"),
            peer_reservations=tuple(reservations),
        ),
        tracks=tuple(tracks),
        cameras=cameras,
        projections=tuple(projections),
        schema_version=str(payload["schema_version"]),
    )


def _camera_to_payload(camera: ActiveVisionCameraState) -> dict[str, Any]:
    return {
        "camera_id": camera.camera_id,
        "resource_id": camera.resource_id,
        "state_timestamp": camera.state_timestamp,
        "yaw_deg": camera.yaw_deg,
        "pitch_deg": camera.pitch_deg,
        "yaw_rate_deg_s": camera.yaw_rate_deg_s,
        "pitch_rate_deg_s": camera.pitch_rate_deg_s,
        "yaw_limits_deg": list(camera.yaw_limits_deg),
        "pitch_limits_deg": list(camera.pitch_limits_deg),
        "max_yaw_rate_deg_s": camera.max_yaw_rate_deg_s,
        "max_pitch_rate_deg_s": camera.max_pitch_rate_deg_s,
        "max_slew_deg_s": camera.max_slew_deg_s,
        "current_fov_mode": camera.current_fov_mode.value,
        "supported_fov_modes": [item.value for item in camera.supported_fov_modes],
        "wide_horizontal_fov_deg": camera.wide_horizontal_fov_deg,
        "zoom_horizontal_fov_deg": camera.zoom_horizontal_fov_deg,
        "slew_available": camera.slew_available,
        "action_in_progress_until": camera.action_in_progress_until,
    }


def _camera_from_payload(payload: Mapping[str, Any]) -> ActiveVisionCameraState:
    _expect_fields(
        payload,
        {
            "camera_id",
            "resource_id",
            "state_timestamp",
            "yaw_deg",
            "pitch_deg",
            "yaw_rate_deg_s",
            "pitch_rate_deg_s",
            "yaw_limits_deg",
            "pitch_limits_deg",
            "max_yaw_rate_deg_s",
            "max_pitch_rate_deg_s",
            "max_slew_deg_s",
            "current_fov_mode",
            "supported_fov_modes",
            "wide_horizontal_fov_deg",
            "zoom_horizontal_fov_deg",
            "slew_available",
            "action_in_progress_until",
        },
        "camera_fields_mismatch",
    )
    return ActiveVisionCameraState(
        camera_id=str(payload["camera_id"]),
        resource_id=str(payload["resource_id"]),
        state_timestamp=float(payload["state_timestamp"]),
        yaw_deg=float(payload["yaw_deg"]),
        pitch_deg=float(payload["pitch_deg"]),
        yaw_rate_deg_s=float(payload["yaw_rate_deg_s"]),
        pitch_rate_deg_s=float(payload["pitch_rate_deg_s"]),
        yaw_limits_deg=tuple(payload["yaw_limits_deg"]),
        pitch_limits_deg=tuple(payload["pitch_limits_deg"]),
        max_yaw_rate_deg_s=float(payload["max_yaw_rate_deg_s"]),
        max_pitch_rate_deg_s=float(payload["max_pitch_rate_deg_s"]),
        max_slew_deg_s=float(payload["max_slew_deg_s"]),
        current_fov_mode=ActiveVisionFovMode(str(payload["current_fov_mode"])),
        supported_fov_modes=tuple(
            ActiveVisionFovMode(str(item)) for item in payload["supported_fov_modes"]
        ),
        wide_horizontal_fov_deg=float(payload["wide_horizontal_fov_deg"]),
        zoom_horizontal_fov_deg=float(payload["zoom_horizontal_fov_deg"]),
        slew_available=_strict_bool(payload["slew_available"], "slew_available"),
        action_in_progress_until=(
            None
            if payload["action_in_progress_until"] is None
            else float(payload["action_in_progress_until"])
        ),
    )


def _action_to_payload(action: ActiveVisionActionV1) -> dict[str, Any]:
    return {
        "schema_version": action.schema_version,
        "camera_id": action.camera_id,
        "issued_timestamp": action.issued_timestamp,
        "expires_timestamp": action.expires_timestamp,
        "plan_version": action.plan_version,
        "coalition_version": action.coalition_version,
        "communication_version": action.communication_version,
        "intent": action.intent.value,
        "yaw_delta_deg": action.yaw_delta_deg,
        "pitch_delta_deg": action.pitch_delta_deg,
        "fov_mode": action.fov_mode.value,
        "target_global_track_id": action.target_global_track_id,
        "search_sector_deg": (
            None if action.search_sector_deg is None else list(action.search_sector_deg)
        ),
        "reason": action.reason,
    }


def _action_from_payload(payload: Mapping[str, Any]) -> ActiveVisionActionV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "camera_id",
            "issued_timestamp",
            "expires_timestamp",
            "plan_version",
            "coalition_version",
            "communication_version",
            "intent",
            "yaw_delta_deg",
            "pitch_delta_deg",
            "fov_mode",
            "target_global_track_id",
            "search_sector_deg",
            "reason",
        },
        "action_fields_mismatch",
    )
    return ActiveVisionActionV1(
        camera_id=str(payload["camera_id"]),
        issued_timestamp=float(payload["issued_timestamp"]),
        expires_timestamp=float(payload["expires_timestamp"]),
        plan_version=int(payload["plan_version"]),
        coalition_version=int(payload["coalition_version"]),
        communication_version=int(payload["communication_version"]),
        intent=ActiveVisionIntent(str(payload["intent"])),
        yaw_delta_deg=float(payload["yaw_delta_deg"]),
        pitch_delta_deg=float(payload["pitch_delta_deg"]),
        fov_mode=ActiveVisionFovMode(str(payload["fov_mode"])),
        target_global_track_id=(
            None
            if payload["target_global_track_id"] is None
            else str(payload["target_global_track_id"])
        ),
        search_sector_deg=(
            None if payload["search_sector_deg"] is None else tuple(payload["search_sector_deg"])
        ),
        reason=str(payload["reason"]),
        schema_version=str(payload["schema_version"]),
    )


def _feedback_to_payload(feedback: ActiveVisionCameraFeedbackV1) -> dict[str, Any]:
    return {
        "schema_version": feedback.schema_version,
        "camera_state": _camera_to_payload(feedback.camera_state),
        "last_accepted_command_version": feedback.last_accepted_command_version,
    }


def _feedback_from_payload(payload: Mapping[str, Any]) -> ActiveVisionCameraFeedbackV1:
    _expect_fields(
        payload,
        {"schema_version", "camera_state", "last_accepted_command_version"},
        "camera_feedback_fields_mismatch",
    )
    return ActiveVisionCameraFeedbackV1(
        camera_state=_camera_from_payload(_mapping(payload["camera_state"])),
        last_accepted_command_version=(
            None
            if payload["last_accepted_command_version"] is None
            else int(payload["last_accepted_command_version"])
        ),
        schema_version=str(payload["schema_version"]),
    )


def _ack_to_payload(ack: ActiveVisionRuntimeAckV1) -> dict[str, Any]:
    return {
        "schema_version": ack.schema_version,
        "sample_key": ack.sample_key,
        "camera_id": ack.camera_id,
        "command_version": ack.command_version,
        "ack_timestamp": ack.ack_timestamp,
        "accepted": ack.accepted,
        "status_code": ack.status_code,
        "plan_version": ack.plan_version,
        "coalition_version": ack.coalition_version,
        "communication_version": ack.communication_version,
    }


def _ack_from_payload(payload: Mapping[str, Any]) -> ActiveVisionRuntimeAckV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "sample_key",
            "camera_id",
            "command_version",
            "ack_timestamp",
            "accepted",
            "status_code",
            "plan_version",
            "coalition_version",
            "communication_version",
        },
        "runtime_ack_fields_mismatch",
    )
    return ActiveVisionRuntimeAckV1(
        sample_key=str(payload["sample_key"]),
        camera_id=str(payload["camera_id"]),
        command_version=int(payload["command_version"]),
        ack_timestamp=float(payload["ack_timestamp"]),
        accepted=_strict_bool(payload["accepted"], "accepted"),
        status_code=str(payload["status_code"]),
        plan_version=int(payload["plan_version"]),
        coalition_version=int(payload["coalition_version"]),
        communication_version=int(payload["communication_version"]),
        schema_version=str(payload["schema_version"]),
    )


def _offline_label_to_payload(label: ActiveVisionOfflineLabelV1) -> dict[str, Any]:
    return {
        "schema_version": label.schema_version,
        "sample_key": label.sample_key,
        "observation_key": label.observation_key,
        "reward": {
            "available": label.reward_available,
            "value": label.reward,
            "minimum": ACTIVE_VISION_REWARD_MINIMUM,
            "maximum": ACTIVE_VISION_REWARD_MAXIMUM,
            "provenance": label.reward_provenance,
        },
        "outcome": {
            "available": label.outcome_available,
            "value": None if label.outcome is None else _thaw_json(label.outcome),
        },
        "counterfactual": {
            "available": label.counterfactual_available,
            "reward": label.counterfactual_reward,
            "minimum": ACTIVE_VISION_REWARD_MINIMUM,
            "maximum": ACTIVE_VISION_REWARD_MAXIMUM,
            "provenance": label.counterfactual_provenance,
        },
        "causal_label": {
            "available": label.causal_label_available,
            "value": None if label.causal_label is None else _thaw_json(label.causal_label),
        },
    }


def _offline_label_from_payload(payload: Mapping[str, Any]) -> ActiveVisionOfflineLabelV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "sample_key",
            "observation_key",
            "reward",
            "outcome",
            "counterfactual",
            "causal_label",
        },
        "offline_label_fields_mismatch",
    )
    reward = _mapping(payload["reward"])
    outcome = _mapping(payload["outcome"])
    counterfactual = _mapping(payload["counterfactual"])
    causal = _mapping(payload["causal_label"])
    _expect_fields(
        reward,
        {"available", "value", "minimum", "maximum", "provenance"},
        "reward_fields_mismatch",
    )
    _expect_fields(outcome, {"available", "value"}, "outcome_fields_mismatch")
    _expect_fields(
        counterfactual,
        {"available", "reward", "minimum", "maximum", "provenance"},
        "counterfactual_fields_mismatch",
    )
    _expect_fields(causal, {"available", "value"}, "causal_label_fields_mismatch")
    _expect_equal(reward["minimum"], ACTIVE_VISION_REWARD_MINIMUM, "reward_bounds_mismatch")
    _expect_equal(reward["maximum"], ACTIVE_VISION_REWARD_MAXIMUM, "reward_bounds_mismatch")
    _expect_equal(
        counterfactual["minimum"],
        ACTIVE_VISION_REWARD_MINIMUM,
        "counterfactual_bounds_mismatch",
    )
    _expect_equal(
        counterfactual["maximum"],
        ACTIVE_VISION_REWARD_MAXIMUM,
        "counterfactual_bounds_mismatch",
    )
    outcome_value = outcome["value"]
    causal_value = causal["value"]
    return ActiveVisionOfflineLabelV1(
        sample_key=str(payload["sample_key"]),
        observation_key=str(payload["observation_key"]),
        reward_available=_strict_bool(reward["available"], "reward.available"),
        reward=None if reward["value"] is None else float(reward["value"]),
        reward_provenance=(
            None if reward["provenance"] is None else str(reward["provenance"])
        ),
        outcome_available=_strict_bool(outcome["available"], "outcome.available"),
        outcome=None if outcome_value is None else _mapping(outcome_value),
        counterfactual_available=_strict_bool(
            counterfactual["available"], "counterfactual.available"
        ),
        counterfactual_reward=(
            None if counterfactual["reward"] is None else float(counterfactual["reward"])
        ),
        counterfactual_provenance=(
            None
            if counterfactual["provenance"] is None
            else str(counterfactual["provenance"])
        ),
        causal_label_available=_strict_bool(causal["available"], "causal_label.available"),
        causal_label=None if causal_value is None else _mapping(causal_value),
        schema_version=str(payload["schema_version"]),
    )


def _load_staged_episode(
    root: Path,
    descriptor: Mapping[str, Any],
) -> tuple[ActiveVisionEpisodeRecordV1, tuple[ActiveVisionOfflineLabelV1, ...]]:
    online_path = _safe_relative_file(root, descriptor["online_file"])
    offline_path = _safe_relative_file(root, descriptor["offline_file"])
    if online_path.parent.name != "online" or offline_path.parent.name != "offline":
        raise ActiveVisionDatasetValidationError(
            "physical_separation_invalid", "online and offline artifacts must use separate directories"
        )
    if online_path == offline_path:
        raise ActiveVisionDatasetValidationError(
            "physical_separation_invalid", "online and offline artifacts cannot be the same file"
        )
    _expect_sha(online_path, descriptor["online_sha256"], "online_sha_mismatch")
    _expect_sha(offline_path, descriptor["offline_sha256"], "offline_sha_mismatch")
    record = load_active_vision_episode_record(online_path)
    expected_identity = (
        str(descriptor["episode_uid"]),
        str(descriptor["scenario_version"]),
        int(descriptor["seed"]),
        str(descriptor["episode_id"]),
    )
    actual_identity = (
        record.episode_uid,
        record.scenario_version,
        record.seed,
        record.episode_id,
    )
    _expect_equal(actual_identity, expected_identity, "online_episode_identity_mismatch")
    _expect_equal(
        _source_identity_to_payload(record.source_identity),
        descriptor["source_identity"],
        "source_identity_mismatch",
    )
    _expect_equal(record.synthetic_fixture, descriptor["synthetic_fixture"], "fixture_flag_mismatch")
    _expect_equal(len(record.samples), int(descriptor["sample_count"]), "sample_count_mismatch")
    labels = _load_offline_labels(offline_path, record)
    _expect_equal(
        _availability_summary(labels),
        descriptor["availability"],
        "episode_availability_mismatch",
    )
    return record, labels


def _load_offline_labels(
    path: Path,
    record: ActiveVisionEpisodeRecordV1,
) -> tuple[ActiveVisionOfflineLabelV1, ...]:
    payload = _read_json(path)
    _expect_fields(
        payload,
        {
            "schema_version",
            "episode_uid",
            "scenario_version",
            "seed",
            "episode_id",
            "reward_bounds",
            "labels",
        },
        "offline_labels_fields_mismatch",
    )
    _expect_equal(
        payload["schema_version"],
        ACTIVE_VISION_OFFLINE_LABELS_SCHEMA_VERSION,
        "offline_labels_schema_mismatch",
    )
    _expect_equal(payload["episode_uid"], record.episode_uid, "offline_episode_mismatch")
    _expect_equal(payload["scenario_version"], record.scenario_version, "offline_episode_mismatch")
    _expect_equal(int(payload["seed"]), record.seed, "offline_episode_mismatch")
    _expect_equal(payload["episode_id"], record.episode_id, "offline_episode_mismatch")
    _expect_equal(
        payload["reward_bounds"],
        {
            "minimum": ACTIVE_VISION_REWARD_MINIMUM,
            "maximum": ACTIVE_VISION_REWARD_MAXIMUM,
        },
        "reward_bounds_mismatch",
    )
    raw_labels = payload["labels"]
    if not isinstance(raw_labels, list):
        raise ActiveVisionDatasetValidationError(
            "offline_labels_invalid", "offline labels must be a list"
        )
    try:
        labels = tuple(_offline_label_from_payload(_mapping(item)) for item in raw_labels)
    except ActiveVisionDatasetValidationError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise ActiveVisionDatasetValidationError(
            "offline_label_invalid", "offline label failed contract validation"
        ) from exc
    expected_keys = {sample.sample_key: sample.observation_key for sample in record.samples}
    actual_keys: dict[str, str] = {}
    for label in labels:
        if label.sample_key in actual_keys:
            raise ActiveVisionDatasetValidationError(
                "offline_label_duplicate", f"duplicate label for sample {label.sample_key}"
            )
        actual_keys[label.sample_key] = label.observation_key
    _expect_equal(actual_keys, expected_keys, "offline_label_join_mismatch")
    return labels


def _validate_descriptor(descriptor: Mapping[str, Any], *, finalized: bool) -> None:
    _expect_fields(
        descriptor,
        {
            "schema_version",
            "episode_uid",
            "scenario_version",
            "seed",
            "episode_id",
            "source_identity",
            "synthetic_fixture",
            "dataset_config_sha256",
            "online_file",
            "online_sha256",
            "offline_file",
            "offline_sha256",
            "sample_count",
            "availability",
            "split",
        },
        "descriptor_fields_mismatch",
    )
    _expect_equal(
        descriptor["schema_version"],
        ACTIVE_VISION_EPISODE_DESCRIPTOR_SCHEMA_VERSION,
        "descriptor_schema_mismatch",
    )
    scenario = _key(descriptor["scenario_version"], "scenario_version")
    episode_id = _key(descriptor["episode_id"], "episode_id")
    expected_uid = _episode_uid(scenario, int(descriptor["seed"]), episode_id)
    _expect_equal(descriptor["episode_uid"], expected_uid, "descriptor_episode_uid_mismatch")
    _source_identity_from_payload(_mapping(descriptor["source_identity"]))
    _strict_bool(descriptor["synthetic_fixture"], "synthetic_fixture")
    _sha256(descriptor["dataset_config_sha256"], "dataset_config_sha256")
    _sha256(descriptor["online_sha256"], "online_sha256")
    sample_count = int(descriptor["sample_count"])
    if sample_count <= 0:
        raise ActiveVisionDatasetValidationError(
            "sample_count_invalid", "episode sample_count must be positive"
        )
    offline_values = (descriptor["offline_file"], descriptor["offline_sha256"])
    if (offline_values[0] is None) != (offline_values[1] is None):
        raise ActiveVisionDatasetValidationError(
            "offline_descriptor_invalid", "offline file and hash availability disagree"
        )
    if offline_values[0] is None:
        if descriptor["availability"] is not None:
            raise ActiveVisionDatasetValidationError(
                "offline_descriptor_invalid", "availability exists without offline labels"
            )
    else:
        _sha256(offline_values[1], "offline_sha256")
        _validate_availability_summary(_mapping(descriptor["availability"]), sample_count)
    split = descriptor["split"]
    if finalized:
        if split not in {"train", "validation", "test"} or offline_values[0] is None:
            raise ActiveVisionDatasetValidationError(
                "descriptor_not_finalized", "finalized descriptor lacks split or offline labels"
            )
    elif split is not None:
        raise ActiveVisionDatasetValidationError(
            "staged_split_forbidden", "staged descriptor cannot pre-assign a dataset split"
        )


def _split_episode_descriptors(
    descriptors: Sequence[Mapping[str, Any]],
    *,
    split_seed: int,
    validation_fraction: float,
    test_fraction: float,
    minimum_unseen_seed_count: int,
) -> tuple[Mapping[str, str], int]:
    if not 0.0 < validation_fraction < 1.0 or not 0.0 < test_fraction < 1.0:
        raise ActiveVisionDatasetValidationError(
            "split_fraction_invalid", "validation/test fractions must be in (0, 1)"
        )
    if validation_fraction + test_fraction >= 1.0:
        raise ActiveVisionDatasetValidationError(
            "split_fraction_invalid", "validation and test fractions leave no training data"
        )
    minimum_unseen = int(minimum_unseen_seed_count)
    if minimum_unseen < 1:
        raise ActiveVisionDatasetValidationError(
            "minimum_unseen_seed_invalid", "minimum unseen seed count must be positive"
        )
    groups: dict[tuple[str, int], list[str]] = {}
    seen_uids: set[str] = set()
    for descriptor in descriptors:
        scenario = _key(descriptor.get("scenario_version"), "scenario_version")
        seed = int(descriptor.get("seed"))
        uid = _key(descriptor.get("episode_uid"), "episode_uid")
        if uid in seen_uids:
            raise ActiveVisionDatasetValidationError(
                "episode_duplicate", f"duplicate episode UID: {uid}"
            )
        seen_uids.add(uid)
        groups.setdefault((scenario, seed), []).append(uid)
    seed_values = sorted({seed for _, seed in groups})
    if len(seed_values) < 3:
        raise ActiveVisionDatasetValidationError(
            "insufficient_split_groups",
            "at least three unique seed values are required for independent splits",
        )
    ordered_seeds = sorted(
        seed_values,
        key=lambda seed: (
            hashlib.sha256(f"{int(split_seed)}\0{seed}".encode("utf-8")).hexdigest(),
            seed,
        ),
    )
    test_count = max(
        1,
        min(len(seed_values) - 2, round(len(seed_values) * test_fraction)),
    )
    validation_count = max(
        1,
        min(
            len(seed_values) - test_count - 1,
            round(len(seed_values) * validation_fraction),
        ),
    )
    split_by_seed: dict[int, str] = {}
    for index, seed in enumerate(ordered_seeds):
        if index < test_count:
            split = "test"
        elif index < test_count + validation_count:
            split = "validation"
        else:
            split = "train"
        split_by_seed[seed] = split
    split_by_group = {group: split_by_seed[group[1]] for group in groups}
    unseen_test_seeds = {
        seed for seed, split in split_by_seed.items() if split == "test"
    }
    if len(unseen_test_seeds) < minimum_unseen:
        raise ActiveVisionDatasetValidationError(
            "insufficient_unseen_test_seeds",
            "test split does not contain the declared number of unseen seed values",
        )
    assignments = {
        uid: split_by_group[group]
        for group, uids in groups.items()
        for uid in uids
    }
    return MappingProxyType(assignments), len(unseen_test_seeds)


def _split_payload(descriptors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "episode_uid": str(item["episode_uid"]),
            "scenario_version": str(item["scenario_version"]),
            "seed": int(item["seed"]),
            "episode_id": str(item["episode_id"]),
            "split": str(item["split"]),
        }
        for item in sorted(descriptors, key=lambda value: str(value["episode_uid"]))
    ]


def _training_set_sha256(descriptors: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "episode_uid": str(item["episode_uid"]),
            "online_sha256": str(item["online_sha256"]),
            "offline_sha256": str(item["offline_sha256"]),
            "source_identity": item["source_identity"],
        }
        for item in sorted(descriptors, key=lambda value: str(value["episode_uid"]))
        if item.get("split") == "train"
    ]
    return sha256_json(payload)


def _source_identity_summary(descriptors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    identities = [_mapping(item["source_identity"]) for item in descriptors]
    commits = sorted({str(item["git_commit"]) for item in identities})
    config_hashes = sorted({str(item["config_sha256"]) for item in identities})
    dirty_count = sum(_strict_bool(item["git_dirty"], "git_dirty") for item in identities)
    return {
        "git_commits": commits,
        "source_config_sha256_values": config_hashes,
        "dirty_episode_count": dirty_count,
        "clean_episode_count": len(identities) - dirty_count,
        "episode_count": len(identities),
    }


def _availability_summary(labels: Sequence[ActiveVisionOfflineLabelV1]) -> dict[str, Any]:
    count = len(labels)
    values = {
        "reward": sum(item.reward_available for item in labels),
        "outcome": sum(item.outcome_available for item in labels),
        "counterfactual": sum(item.counterfactual_available for item in labels),
        "causal_label": sum(item.causal_label_available for item in labels),
    }
    return {
        name: {
            "status": _availability_status(available_count, count),
            "available_sample_count": available_count,
            "sample_count": count,
        }
        for name, available_count in values.items()
    }


def _dataset_availability(descriptors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals = {
        name: {"available_sample_count": 0, "sample_count": 0}
        for name in ("reward", "outcome", "counterfactual", "causal_label")
    }
    for descriptor in descriptors:
        availability = _mapping(descriptor["availability"])
        for name in totals:
            item = _mapping(availability[name])
            totals[name]["available_sample_count"] += int(item["available_sample_count"])
            totals[name]["sample_count"] += int(item["sample_count"])
    return {
        name: {
            "status": _availability_status(
                values["available_sample_count"], values["sample_count"]
            ),
            **values,
        }
        for name, values in totals.items()
    }


def _validate_availability_summary(payload: Mapping[str, Any], sample_count: int) -> None:
    _expect_fields(
        payload,
        {"reward", "outcome", "counterfactual", "causal_label"},
        "availability_fields_mismatch",
    )
    for name in ("reward", "outcome", "counterfactual", "causal_label"):
        item = _mapping(payload[name])
        _expect_fields(
            item,
            {"status", "available_sample_count", "sample_count"},
            "availability_item_fields_mismatch",
        )
        available = int(item["available_sample_count"])
        total = int(item["sample_count"])
        if total != sample_count or not 0 <= available <= total:
            raise ActiveVisionDatasetValidationError(
                "availability_count_invalid", f"{name} availability count is invalid"
            )
        _expect_equal(
            item["status"],
            _availability_status(available, total),
            "availability_status_mismatch",
        )


def _availability_status(available_count: int, total_count: int) -> str:
    if total_count <= 0:
        raise ValueError("availability requires at least one sample")
    if available_count == total_count:
        return "available"
    if available_count == 0:
        return "unavailable"
    return "partial"


def _behavior_cloning_episode(item: LoadedActiveVisionEpisode) -> ActiveVisionResearchEpisode:
    transitions = tuple(
        ActiveVisionTransition(
            snapshot=sample.snapshot,
            camera_id=sample.camera_id,
            selected_action=sample.rule_demonstration_action,
            reward=None,
            done=index == len(item.record.samples) - 1,
        )
        for index, sample in enumerate(item.record.samples)
    )
    return ActiveVisionResearchEpisode(
        scenario_version=item.record.scenario_version,
        seed=item.record.seed,
        episode_id=item.record.episode_id,
        transitions=transitions,
        synthetic_fixture=item.record.synthetic_fixture,
    )


def _ppo_episode(item: LoadedActiveVisionEpisode) -> ActiveVisionResearchEpisode:
    labels = item.labels_by_sample_key
    transitions: list[ActiveVisionTransition] = []
    for index, sample in enumerate(item.record.samples):
        label = labels[sample.sample_key]
        if not label.reward_available or label.reward is None:
            raise ActiveVisionDatasetValidationError(
                "ppo_reward_unavailable",
                "PPO requires bounded offline reward for every selected sample; zero padding is forbidden",
            )
        transitions.append(
            ActiveVisionTransition(
                snapshot=sample.snapshot,
                camera_id=sample.camera_id,
                selected_action=sample.effective_action,
                reward=label.reward,
                done=index == len(item.record.samples) - 1,
            )
        )
    return ActiveVisionResearchEpisode(
        scenario_version=item.record.scenario_version,
        seed=item.record.seed,
        episode_id=item.record.episode_id,
        transitions=tuple(transitions),
        synthetic_fixture=item.record.synthetic_fixture,
    )


def _validate_snapshot_center_references(snapshot: ActiveVisionSnapshotV1) -> None:
    center_ids = {item.global_track_id for item in snapshot.tracks}
    for track_id in center_ids:
        try:
            assert_truth_free_active_vision_payload({"opaque_center_reference": track_id})
        except ValueError as exc:
            raise ActiveVisionDatasetValidationError(
                "center_reference_identity_forbidden",
                "center global_track_id contains simulator/evaluator identity",
            ) from exc
    referenced_ids = {
        item.global_track_id for item in snapshot.plan.assignments
    } | {
        item.global_track_id for item in snapshot.projections
    } | {
        item.global_track_id
        for item in snapshot.communication.peer_reservations
        if item.global_track_id is not None
    }
    unknown = referenced_ids - center_ids
    if unknown:
        raise ActiveVisionDatasetValidationError(
            "unknown_center_reference",
            f"snapshot contains unknown center global_track_id references: {sorted(unknown)}",
        )


def _validate_action_reference(
    action: ActiveVisionActionV1,
    snapshot: ActiveVisionSnapshotV1,
    camera_id: str,
    *,
    require_current_versions: bool,
    field_name: str,
) -> None:
    if not isinstance(action, ActiveVisionActionV1):
        raise TypeError(f"{field_name} must be ActiveVisionActionV1")
    if action.camera_id != camera_id:
        raise ValueError(f"{field_name} camera does not match the sample")
    center_ids = {item.global_track_id for item in snapshot.tracks}
    target_id = action.target_global_track_id
    if target_id is not None:
        if target_id not in center_ids:
            raise ActiveVisionDatasetValidationError(
                "unknown_center_reference",
                f"{field_name} references an unknown center global_track_id",
            )
        if target_id not in set(snapshot.assigned_target_ids(camera_id)):
            raise ActiveVisionDatasetValidationError(
                "global_track_id_local_rewrite",
                f"{field_name} locally rebinds a center global_track_id",
            )
    if require_current_versions and (
        action.plan_version,
        action.coalition_version,
        action.communication_version,
    ) != (
        snapshot.plan.plan_version,
        snapshot.plan.coalition_version,
        snapshot.communication.communication_version,
    ):
        raise ValueError(f"{field_name} versions do not match the center snapshot")


def _ensure_generation_config(root: Path, generation_config: Mapping[str, Any]) -> str:
    config = _json_object(generation_config, "generation_config")
    payload = {
        "schema_version": ACTIVE_VISION_DATASET_CONFIG_SCHEMA_VERSION,
        "generation_config": config,
    }
    try:
        assert_truth_free_active_vision_payload(payload)
    except ValueError as exc:
        raise ActiveVisionDatasetValidationError(
            "dataset_config_truth_identity_forbidden",
            "dataset generation config must not persist evaluator/simulator identity",
        ) from exc
    path = root / "dataset_config.json"
    encoded = _canonical_json_bytes(payload)
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("all active-vision episodes must share generation_config")
    else:
        _write_bytes_atomic(path, encoded)
        _make_read_only(path)
    return sha256_file(path)


def _ensure_not_finalized(root: Path) -> None:
    if (root / "manifest.json").exists() or (root / "SHA256SUMS").exists():
        raise ActiveVisionDatasetValidationError(
            "dataset_immutable", "finalized active-vision dataset cannot be modified"
        )


def _episode_uid(scenario_version: str, seed: int, episode_id: str) -> str:
    raw = f"{scenario_version}\0{int(seed)}\0{episode_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _key(value: Any, name: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result or _KEY_PATTERN.fullmatch(result) is None:
        raise ValueError(f"{name} must be a non-empty portable key")
    return result


def _finite(value: Any, name: str) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _optional_bounded_reward(value: Any, name: str) -> float | None:
    if value is None:
        return None
    result = _finite(value, name)
    if not ACTIVE_VISION_REWARD_MINIMUM <= result <= ACTIVE_VISION_REWARD_MAXIMUM:
        raise ValueError(
            f"{name} must be in [{ACTIVE_VISION_REWARD_MINIMUM}, {ACTIVE_VISION_REWARD_MAXIMUM}]"
        )
    return result


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ActiveVisionDatasetValidationError(
            "boolean_type_invalid", f"{name} must be a JSON boolean"
        )
    return value


def _input_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _sha256(value: Any, name: str) -> str:
    result = str(value).strip().lower()
    if _SHA256_PATTERN.fullmatch(result) is None:
        raise ActiveVisionDatasetValidationError(
            "sha256_invalid", f"{name} must be a lowercase SHA256"
        )
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ActiveVisionDatasetValidationError(
            "json_object_required", "dataset contract field must be a JSON object"
        )
    return value


def _list(payload: Any, name: str) -> list[Any]:
    if not isinstance(payload, list):
        raise ActiveVisionDatasetValidationError(
            "json_list_required", f"{name} must be a JSON list"
        )
    return payload


def _expect_fields(payload: Mapping[str, Any], expected: set[str], code: str) -> None:
    if set(payload) != expected:
        raise ActiveVisionDatasetValidationError(
            code,
            f"expected fields {sorted(expected)}, received {sorted(str(key) for key in payload)}",
        )


def _expect_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        raise ActiveVisionDatasetValidationError(
            code, f"dataset contract mismatch: expected {expected!r}, received {actual!r}"
        )


def _json_object(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    try:
        decoded = json.loads(_canonical_json_bytes(_thaw_json(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite JSON data") from exc
    if not isinstance(decoded, dict):
        raise TypeError(f"{name} must encode a JSON object")
    return decoded


def _immutable_json_object(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    return _freeze_json(_json_object(value, name))


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expect_sha(path: Path, expected: Any, code: str) -> None:
    expected_sha = _sha256(expected, f"{path.name} SHA256")
    if sha256_file(path) != expected_sha:
        raise ActiveVisionDatasetValidationError(code, f"SHA256 mismatch for {path.name}")


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(value))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: _reject_json_constant(token),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ActiveVisionDatasetValidationError(
            "json_invalid", f"cannot load finite JSON object from {path.name}"
        ) from exc
    if not isinstance(value, dict):
        raise ActiveVisionDatasetValidationError(
            "json_object_required", f"{path.name} must contain a JSON object"
        )
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


def _safe_relative_file(root: Path, raw_relative: Any) -> Path:
    relative = Path(str(raw_relative))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ActiveVisionDatasetValidationError(
            "artifact_path_invalid", "dataset artifact path must be relative and contained"
        )
    candidate = root / relative
    current = candidate
    while current != root:
        if current.is_symlink():
            raise ActiveVisionDatasetValidationError(
                "artifact_symlink_forbidden", f"dataset artifact uses a symlink: {relative}"
            )
        current = current.parent
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ActiveVisionDatasetValidationError(
            "artifact_path_escape", f"dataset artifact escapes root: {relative}"
        )
    if not resolved.is_file():
        raise ActiveVisionDatasetValidationError(
            "artifact_missing", f"dataset artifact is missing: {relative}"
        )
    return resolved


def _read_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ActiveVisionDatasetValidationError(
            "checksums_invalid", "cannot read SHA256SUMS"
        ) from exc
    result: dict[str, str] = {}
    previous_relative = ""
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise ActiveVisionDatasetValidationError(
                "checksums_invalid", "SHA256SUMS line format is invalid"
            )
        sha = _sha256(parts[0], "checksum")
        relative = Path(parts[1]).as_posix()
        if relative in result or relative <= previous_relative:
            raise ActiveVisionDatasetValidationError(
                "checksums_invalid", "SHA256SUMS paths must be unique and sorted"
            )
        previous_relative = relative
        result[relative] = sha
    if not result:
        raise ActiveVisionDatasetValidationError("checksums_invalid", "SHA256SUMS is empty")
    return result


def _make_read_only(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode & ~0o222)


def _require_read_only(path: Path) -> None:
    if stat.S_IMODE(path.stat().st_mode) & 0o222:
        raise ActiveVisionDatasetValidationError(
            "artifact_mutable", f"finalized dataset artifact is writable: {path.name}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Finalize or audit a detached D5 active-vision episode dataset"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    finalize = subparsers.add_parser("finalize", help="split and freeze staged episodes")
    finalize.add_argument("--dataset-dir", required=True)
    finalize.add_argument("--split-seed", type=int, default=20260720)
    finalize.add_argument("--validation-fraction", type=float, default=0.2)
    finalize.add_argument("--test-fraction", type=float, default=0.2)
    finalize.add_argument(
        "--minimum-unseen-seeds",
        type=int,
        default=MINIMUM_UNSEEN_ASSIST_SEEDS,
    )
    validate = subparsers.add_parser("validate", help="fail closed on any audit mismatch")
    validate.add_argument("--dataset-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "finalize":
        manifest = finalize_active_vision_episode_dataset(
            args.dataset_dir,
            split_seed=args.split_seed,
            validation_fraction=args.validation_fraction,
            test_fraction=args.test_fraction,
            minimum_unseen_seed_count=args.minimum_unseen_seeds,
        )
        print(
            json.dumps(
                {
                    "episode_count": len(manifest["episodes"]),
                    "status": "finalized_detached_immutable_dataset",
                },
                sort_keys=True,
            )
        )
        return 0
    print(json.dumps(dict(audit_active_vision_episode_dataset(args.dataset_dir)), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = [
    "ACTIVE_VISION_CAMERA_FEEDBACK_SCHEMA_VERSION",
    "ACTIVE_VISION_DATASET_CONFIG_SCHEMA_VERSION",
    "ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION",
    "ACTIVE_VISION_EPISODE_DESCRIPTOR_SCHEMA_VERSION",
    "ACTIVE_VISION_EPISODE_RECORD_SCHEMA_VERSION",
    "ACTIVE_VISION_OFFLINE_LABEL_SCHEMA_VERSION",
    "ACTIVE_VISION_OFFLINE_LABELS_SCHEMA_VERSION",
    "ACTIVE_VISION_REWARD_MAXIMUM",
    "ACTIVE_VISION_REWARD_MINIMUM",
    "ACTIVE_VISION_RUNTIME_ACK_SCHEMA_VERSION",
    "ACTIVE_VISION_SAMPLE_SCHEMA_VERSION",
    "ACTIVE_VISION_SOURCE_IDENTITY_SCHEMA_VERSION",
    "ActiveVisionCameraFeedbackV1",
    "ActiveVisionDatasetValidationError",
    "ActiveVisionEpisodeRecordV1",
    "ActiveVisionEpisodeSampleV1",
    "ActiveVisionOfflineLabelV1",
    "ActiveVisionRuntimeAckV1",
    "ActiveVisionSourceIdentityV1",
    "LoadedActiveVisionEpisode",
    "LoadedActiveVisionEpisodeDataset",
    "active_vision_sample_from_decision",
    "audit_active_vision_episode_dataset",
    "finalize_active_vision_episode_dataset",
    "load_active_vision_episode_dataset",
    "load_active_vision_episode_record",
    "sha256_file",
    "sha256_json",
    "stage_active_vision_episode_record",
    "stage_active_vision_offline_labels",
    "unavailable_active_vision_offline_labels",
]
