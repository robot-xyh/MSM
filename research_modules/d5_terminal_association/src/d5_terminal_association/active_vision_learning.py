"""Native PyTorch behavior-cloning and clipped-PPO research workflow.

Episodes are split only as whole ``(scenario_version, seed)`` groups.  The
network scores a finite set of safety-bounded camera intents; it never predicts
an identity, assignment, or continuous vehicle command.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .active_vision_contracts import (
    ACTIVE_VISION_ACTION_SPACE_VERSION,
    ACTIVE_VISION_FEATURE_SCHEMA_VERSION,
    ActiveVisionActionV1,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionSafetyConfigV1,
    ActiveVisionSnapshotV1,
    enumerate_safe_action_candidates,
)


ACTIVE_VISION_DATASET_SCHEMA_VERSION = "d5.active-vision-dataset.v1"
ACTIVE_VISION_MODEL_SEMANTIC_VERSION = "1.0.0"

ACTIVE_VISION_FEATURE_NAMES = (
    "camera_yaw_normalized",
    "camera_pitch_normalized",
    "camera_yaw_rate_normalized",
    "camera_pitch_rate_normalized",
    "camera_current_fov_wide",
    "camera_current_fov_zoom",
    "camera_slew_available",
    "camera_busy",
    "camera_count_log",
    "track_candidate_count_log",
    "assigned_target_count_log",
    "plan_version_log",
    "coalition_version_log",
    "communication_version_log",
    "communication_age_normalized",
    "communication_healthy",
    "intent_observe",
    "intent_search",
    "intent_hold",
    "intent_reacquire",
    "action_fov_wide",
    "action_fov_zoom",
    "action_yaw_delta_normalized",
    "action_pitch_delta_normalized",
    "action_has_target",
    "projection_available",
    "projection_yaw_error_normalized",
    "projection_pitch_error_normalized",
    "projection_uncertainty_log",
    "visibility_probability",
    "occlusion_fraction",
    "association_confidence",
    "projection_age_normalized",
    "projection_in_fov",
    "exclusive_peer_reservation_count_log",
)


@dataclass(frozen=True)
class ActiveVisionTransition:
    snapshot: ActiveVisionSnapshotV1
    camera_id: str
    selected_action: ActiveVisionActionV1
    reward: float = 0.0
    done: bool = False

    def __post_init__(self) -> None:
        reward = float(self.reward)
        if not np.isfinite(reward):
            raise ValueError("active-vision reward must be finite")
        self.snapshot.camera(self.camera_id)
        object.__setattr__(self, "camera_id", str(self.camera_id))
        object.__setattr__(self, "reward", reward)


@dataclass(frozen=True)
class ActiveVisionResearchEpisode:
    scenario_version: str
    seed: int
    episode_id: str
    transitions: tuple[ActiveVisionTransition, ...]
    synthetic_fixture: bool = False

    def __post_init__(self) -> None:
        scenario = str(self.scenario_version).strip()
        episode_id = str(self.episode_id).strip()
        if not scenario or not episode_id:
            raise ValueError("scenario_version and episode_id must be non-empty")
        transitions = tuple(self.transitions)
        if not transitions:
            raise ValueError("active-vision episode must contain transitions")
        object.__setattr__(self, "scenario_version", scenario)
        object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "episode_id", episode_id)
        object.__setattr__(self, "transitions", transitions)

    @property
    def group_key(self) -> tuple[str, int]:
        return (self.scenario_version, self.seed)


@dataclass(frozen=True)
class ActiveVisionDatasetSplit:
    episodes: tuple[ActiveVisionResearchEpisode, ...]
    split_by_group: Mapping[tuple[str, int], str]
    split_seed: int
    validation_fraction: float
    test_fraction: float
    manifest_sha256: str
    split_sha256: str
    training_set_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "episodes", tuple(self.episodes))
        object.__setattr__(self, "split_by_group", MappingProxyType(dict(self.split_by_group)))

    def split(self, name: str) -> tuple[ActiveVisionResearchEpisode, ...]:
        if name not in {"train", "validation", "test"}:
            raise ValueError("split must be train, validation, or test")
        return tuple(
            episode
            for episode in self.episodes
            if self.split_by_group[episode.group_key] == name
        )

    def manifest(self) -> Mapping[str, Any]:
        groups = [
            {
                "scenario_version": scenario,
                "seed": seed,
                "split": split,
                "synthetic_fixture": all(
                    episode.synthetic_fixture
                    for episode in self.episodes
                    if episode.group_key == (scenario, seed)
                ),
            }
            for (scenario, seed), split in sorted(self.split_by_group.items())
        ]
        return MappingProxyType(
            {
                "schema_version": ACTIVE_VISION_DATASET_SCHEMA_VERSION,
                "feature_schema_version": ACTIVE_VISION_FEATURE_SCHEMA_VERSION,
                "action_space_version": ACTIVE_VISION_ACTION_SPACE_VERSION,
                "feature_names": list(ACTIVE_VISION_FEATURE_NAMES),
                "split_policy": {
                    "unit": "whole_episode_grouped_by_scenario_version_and_seed",
                    "edge_or_transition_level_random_split": False,
                    "split_seed": self.split_seed,
                    "validation_fraction": self.validation_fraction,
                    "test_fraction": self.test_fraction,
                },
                "groups": groups,
                "manifest_sha256": self.manifest_sha256,
                "split_sha256": self.split_sha256,
                "training_set_sha256": self.training_set_sha256,
            }
        )


@dataclass(frozen=True)
class ActiveVisionFeatureBounds:
    minimum: tuple[float, ...]
    maximum: tuple[float, ...]

    def __post_init__(self) -> None:
        minimum = np.asarray(self.minimum, dtype=float).reshape(-1)
        maximum = np.asarray(self.maximum, dtype=float).reshape(-1)
        if minimum.shape != (len(ACTIVE_VISION_FEATURE_NAMES),) or maximum.shape != minimum.shape:
            raise ValueError("active-vision feature bounds have the wrong dimension")
        if not np.all(np.isfinite(minimum)) or not np.all(np.isfinite(maximum)):
            raise ValueError("active-vision feature bounds must be finite")
        if np.any(minimum > maximum):
            raise ValueError("active-vision feature bounds are inverted")
        object.__setattr__(self, "minimum", tuple(float(value) for value in minimum))
        object.__setattr__(self, "maximum", tuple(float(value) for value in maximum))

    def contains(self, features: np.ndarray, *, margin: float = 0.05) -> bool:
        values = np.asarray(features, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(self.minimum) or not np.all(np.isfinite(values)):
            return False
        lower = np.asarray(self.minimum)
        upper = np.asarray(self.maximum)
        span = np.maximum(upper - lower, 1.0e-6)
        return bool(np.all(values >= lower - margin * span) and np.all(values <= upper + margin * span))


@dataclass(frozen=True)
class ActiveVisionCandidateBatch:
    actions: tuple[ActiveVisionActionV1, ...]
    features: np.ndarray

    def __post_init__(self) -> None:
        actions = tuple(self.actions)
        values = np.asarray(self.features, dtype=np.float32).copy()
        if not actions or values.shape != (len(actions), len(ACTIVE_VISION_FEATURE_NAMES)):
            raise ValueError("candidate features must align with the finite action set")
        if not np.all(np.isfinite(values)):
            raise ValueError("candidate features must be finite")
        values.setflags(write=False)
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "features", values)


class ActiveVisionActorCritic(nn.Module):
    """Small native-PyTorch actor/critic over variable-size action candidates."""

    def __init__(self, *, hidden_dim: int = 64) -> None:
        super().__init__()
        hidden = int(hidden_dim)
        if hidden <= 0:
            raise ValueError("hidden_dim must be positive")
        self.feature_dim = len(ACTIVE_VISION_FEATURE_NAMES)
        self.hidden_dim = hidden
        self.encoder = nn.Sequential(
            nn.Linear(self.feature_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
        )
        self.actor = nn.Linear(hidden, 1)
        self.critic = nn.Sequential(nn.Linear(hidden, hidden), nn.Tanh(), nn.Linear(hidden, 1))

    def forward(self, candidate_features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if candidate_features.ndim != 2 or candidate_features.shape[1] != self.feature_dim:
            raise ValueError("candidate_features have the wrong shape")
        encoded = self.encoder(candidate_features)
        logits = self.actor(encoded).squeeze(-1)
        value = self.critic(encoded.mean(dim=0, keepdim=True)).reshape(())
        return logits, value


@dataclass(frozen=True)
class BehaviorCloningConfig:
    seed: int = 20260720
    epochs: int = 20
    learning_rate: float = 3.0e-4
    hidden_dim: int = 64
    device: str = "cpu"


@dataclass(frozen=True)
class ClippedPpoConfig:
    seed: int = 20260720
    epochs: int = 10
    learning_rate: float = 3.0e-4
    clip_ratio: float = 0.2
    discount: float = 0.99
    value_loss_coefficient: float = 0.5
    entropy_coefficient: float = 0.01
    max_grad_norm: float = 1.0
    device: str = "cpu"


@dataclass(frozen=True)
class ActiveVisionTrainingResult:
    model: ActiveVisionActorCritic
    epoch_losses: tuple[float, ...]
    feature_bounds: ActiveVisionFeatureBounds
    transition_count: int
    config: Mapping[str, Any]


def split_active_vision_episode_groups(
    episodes: Iterable[ActiveVisionResearchEpisode],
    *,
    split_seed: int = 20260720,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> ActiveVisionDatasetSplit:
    """Assign complete scenario/seed groups to exactly one dataset split."""

    items = tuple(episodes)
    if not items:
        raise ValueError("no active-vision episodes were provided")
    if not 0.0 < validation_fraction < 1.0 or not 0.0 < test_fraction < 1.0:
        raise ValueError("validation/test fractions must be in (0, 1)")
    if validation_fraction + test_fraction >= 1.0:
        raise ValueError("validation and test fractions leave no training data")
    groups = sorted({item.group_key for item in items})
    if len(groups) < 3:
        raise ValueError("at least three scenario/seed groups are required")
    ordered = sorted(
        groups,
        key=lambda key: hashlib.sha256(
            f"{int(split_seed)}\0{key[0]}\0{key[1]}".encode("utf-8")
        ).hexdigest(),
    )
    test_count = max(1, min(len(groups) - 2, round(len(groups) * test_fraction)))
    validation_count = max(
        1,
        min(len(groups) - test_count - 1, round(len(groups) * validation_fraction)),
    )
    split_by_group: dict[tuple[str, int], str] = {}
    for index, group in enumerate(ordered):
        if index < test_count:
            split = "test"
        elif index < test_count + validation_count:
            split = "validation"
        else:
            split = "train"
        split_by_group[group] = split
    group_payload = [
        {"scenario_version": key[0], "seed": key[1], "split": split_by_group[key]}
        for key in sorted(groups)
    ]
    manifest_payload = {
        "schema_version": ACTIVE_VISION_DATASET_SCHEMA_VERSION,
        "feature_schema_version": ACTIVE_VISION_FEATURE_SCHEMA_VERSION,
        "action_space_version": ACTIVE_VISION_ACTION_SPACE_VERSION,
        "feature_names": list(ACTIVE_VISION_FEATURE_NAMES),
        "split_seed": int(split_seed),
        "validation_fraction": float(validation_fraction),
        "test_fraction": float(test_fraction),
        "groups": group_payload,
    }
    split_sha = _sha256_json(group_payload)
    manifest_payload["split_sha256"] = split_sha
    manifest_sha = _sha256_json(manifest_payload)
    training_payload = [item for item in group_payload if item["split"] == "train"]
    training_sha = _sha256_json(training_payload)
    return ActiveVisionDatasetSplit(
        episodes=items,
        split_by_group=split_by_group,
        split_seed=int(split_seed),
        validation_fraction=float(validation_fraction),
        test_fraction=float(test_fraction),
        manifest_sha256=manifest_sha,
        split_sha256=split_sha,
        training_set_sha256=training_sha,
    )


def active_vision_candidate_batch(
    snapshot: ActiveVisionSnapshotV1,
    *,
    camera_id: str,
    current_timestamp: float | None = None,
    safety_config: ActiveVisionSafetyConfigV1 | None = None,
) -> ActiveVisionCandidateBatch:
    cfg = safety_config or ActiveVisionSafetyConfigV1()
    now = snapshot.snapshot_timestamp if current_timestamp is None else float(current_timestamp)
    actions = enumerate_safe_action_candidates(
        snapshot,
        camera_id=camera_id,
        current_timestamp=now,
        config=cfg,
    )
    camera = snapshot.camera(camera_id)
    assigned_ids = snapshot.assigned_target_ids(camera_id)
    peer_count = sum(
        1
        for item in snapshot.communication.peer_reservations
        if item.exclusive and item.expires_timestamp >= now
    )
    rows: list[list[float]] = []
    for action in actions:
        evidence = (
            None
            if action.target_global_track_id is None
            else snapshot.projection(camera_id, action.target_global_track_id)
        )
        projection_age = (
            cfg.reacquire_evidence_age_s * 2.0
            if evidence is None
            else max(0.0, now - evidence.measurement_timestamp)
        )
        busy = bool(
            camera.action_in_progress_until is not None
            and camera.action_in_progress_until > now
        )
        rows.append(
            [
                camera.yaw_deg / 180.0,
                camera.pitch_deg / 90.0,
                camera.yaw_rate_deg_s / camera.max_yaw_rate_deg_s,
                camera.pitch_rate_deg_s / camera.max_pitch_rate_deg_s,
                float(camera.current_fov_mode is ActiveVisionFovMode.WIDE),
                float(camera.current_fov_mode is ActiveVisionFovMode.ZOOM),
                float(camera.slew_available),
                float(busy),
                math.log1p(len(snapshot.cameras)) / math.log(257.0),
                math.log1p(len(snapshot.tracks)) / math.log(257.0),
                math.log1p(len(assigned_ids)) / math.log(65.0),
                math.log1p(snapshot.plan.plan_version) / 20.0,
                math.log1p(snapshot.plan.coalition_version) / 20.0,
                math.log1p(snapshot.communication.communication_version) / 20.0,
                max(0.0, now - snapshot.communication.update_timestamp)
                / cfg.max_communication_age_s,
                float(snapshot.communication.healthy),
                float(action.intent is ActiveVisionIntent.OBSERVE_TARGET),
                float(action.intent is ActiveVisionIntent.SEARCH_SECTOR),
                float(action.intent is ActiveVisionIntent.HOLD),
                float(action.intent is ActiveVisionIntent.REACQUIRE),
                float(action.fov_mode is ActiveVisionFovMode.WIDE),
                float(action.fov_mode is ActiveVisionFovMode.ZOOM),
                action.yaw_delta_deg / cfg.max_gimbal_increment_deg,
                action.pitch_delta_deg / cfg.max_gimbal_increment_deg,
                float(action.target_global_track_id is not None),
                float(evidence is not None),
                0.0 if evidence is None else evidence.yaw_error_deg / 180.0,
                0.0 if evidence is None else evidence.pitch_error_deg / 90.0,
                0.0
                if evidence is None
                else math.log1p(evidence.uncertainty_trace_deg2) / 10.0,
                0.0 if evidence is None else evidence.visibility_probability,
                1.0 if evidence is None else evidence.occlusion_fraction,
                0.0 if evidence is None else evidence.association_confidence,
                projection_age / cfg.reacquire_evidence_age_s,
                float(evidence is not None and evidence.in_fov),
                math.log1p(peer_count) / math.log(65.0),
            ]
        )
    return ActiveVisionCandidateBatch(actions=actions, features=np.asarray(rows, dtype=np.float32))


def fit_active_vision_feature_bounds(
    episodes: Sequence[ActiveVisionResearchEpisode],
    *,
    safety_config: ActiveVisionSafetyConfigV1 | None = None,
) -> ActiveVisionFeatureBounds:
    batches = [
        active_vision_candidate_batch(
            transition.snapshot,
            camera_id=transition.camera_id,
            safety_config=safety_config,
        ).features
        for episode in episodes
        for transition in episode.transitions
    ]
    if not batches:
        raise ValueError("no transitions are available for feature bounds")
    values = np.concatenate(batches, axis=0).astype(float, copy=False)
    return ActiveVisionFeatureBounds(
        minimum=tuple(np.min(values, axis=0).tolist()),
        maximum=tuple(np.max(values, axis=0).tolist()),
    )


def train_behavior_cloning(
    dataset: ActiveVisionDatasetSplit,
    *,
    config: BehaviorCloningConfig | None = None,
    safety_config: ActiveVisionSafetyConfigV1 | None = None,
) -> ActiveVisionTrainingResult:
    cfg = config or BehaviorCloningConfig()
    _validate_training_config(cfg.epochs, cfg.learning_rate)
    _seed_everything(cfg.seed)
    device = torch.device(cfg.device)
    model = ActiveVisionActorCritic(hidden_dim=cfg.hidden_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.learning_rate)
    examples = _training_examples(dataset.split("train"), safety_config=safety_config)
    bounds = fit_active_vision_feature_bounds(dataset.split("train"), safety_config=safety_config)
    epoch_losses: list[float] = []
    for epoch in range(cfg.epochs):
        order = list(range(len(examples)))
        random.Random(cfg.seed + epoch).shuffle(order)
        losses: list[float] = []
        for index in order:
            features, selected_index = examples[index]
            tensor = torch.as_tensor(
                np.array(features, copy=True), dtype=torch.float32, device=device
            )
            logits, _ = model(tensor)
            loss = F.cross_entropy(logits.reshape(1, -1), torch.tensor([selected_index], device=device))
            if not bool(torch.isfinite(loss)):
                raise RuntimeError("non-finite behavior-cloning loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        epoch_losses.append(float(np.mean(losses)))
    model.eval()
    return ActiveVisionTrainingResult(
        model=model,
        epoch_losses=tuple(epoch_losses),
        feature_bounds=bounds,
        transition_count=len(examples),
        config=MappingProxyType(asdict(cfg)),
    )


def train_clipped_ppo(
    model: ActiveVisionActorCritic,
    episodes: Sequence[ActiveVisionResearchEpisode],
    *,
    config: ClippedPpoConfig | None = None,
    safety_config: ActiveVisionSafetyConfigV1 | None = None,
) -> ActiveVisionTrainingResult:
    """Offline research PPO update over recorded, safety-projected rollouts."""

    cfg = config or ClippedPpoConfig()
    _validate_training_config(cfg.epochs, cfg.learning_rate)
    if not 0.0 < cfg.clip_ratio < 1.0 or not 0.0 <= cfg.discount <= 1.0:
        raise ValueError("PPO clip ratio or discount is invalid")
    _seed_everything(cfg.seed)
    device = torch.device(cfg.device)
    model.to(device)
    examples: list[tuple[np.ndarray, int, float, bool]] = []
    episode_lengths: list[int] = []
    for episode in episodes:
        before = len(examples)
        for transition in episode.transitions:
            batch = active_vision_candidate_batch(
                transition.snapshot,
                camera_id=transition.camera_id,
                safety_config=safety_config,
            )
            selected_index = _selected_action_index(batch.actions, transition.selected_action)
            examples.append((batch.features, selected_index, transition.reward, transition.done))
        episode_lengths.append(len(examples) - before)
    if not examples:
        raise ValueError("PPO requires at least one transition")
    old_log_probabilities: list[float] = []
    old_values: list[float] = []
    model.eval()
    with torch.no_grad():
        for features, selected_index, _, _ in examples:
            logits, value = model(
                torch.as_tensor(np.array(features, copy=True), dtype=torch.float32, device=device)
            )
            old_log_probabilities.append(float(F.log_softmax(logits, dim=0)[selected_index].cpu()))
            old_values.append(float(value.cpu()))
    returns: list[float] = []
    cursor = 0
    for length in episode_lengths:
        episode_examples = examples[cursor : cursor + length]
        discounted = 0.0
        episode_returns = [0.0] * length
        for index in range(length - 1, -1, -1):
            _, _, reward, done = episode_examples[index]
            if done:
                discounted = 0.0
            discounted = reward + cfg.discount * discounted
            episode_returns[index] = discounted
        returns.extend(episode_returns)
        cursor += length
    advantages = np.asarray(returns, dtype=float) - np.asarray(old_values, dtype=float)
    if len(advantages) > 1 and float(np.std(advantages)) > 1.0e-9:
        advantages = (advantages - float(np.mean(advantages))) / (float(np.std(advantages)) + 1.0e-8)
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.learning_rate)
    epoch_losses: list[float] = []
    for _ in range(cfg.epochs):
        losses: list[torch.Tensor] = []
        for index, (features, selected_index, _, _) in enumerate(examples):
            logits, value = model(
                torch.as_tensor(np.array(features, copy=True), dtype=torch.float32, device=device)
            )
            log_probabilities = F.log_softmax(logits, dim=0)
            probabilities = torch.softmax(logits, dim=0)
            ratio = torch.exp(
                log_probabilities[selected_index]
                - torch.tensor(old_log_probabilities[index], dtype=torch.float32, device=device)
            )
            advantage = torch.tensor(float(advantages[index]), dtype=torch.float32, device=device)
            unclipped = ratio * advantage
            clipped = torch.clamp(ratio, 1.0 - cfg.clip_ratio, 1.0 + cfg.clip_ratio) * advantage
            policy_loss = -torch.minimum(unclipped, clipped)
            value_target = torch.tensor(returns[index], dtype=torch.float32, device=device)
            value_loss = F.mse_loss(value, value_target)
            entropy = -(probabilities * log_probabilities).sum()
            losses.append(
                policy_loss
                + cfg.value_loss_coefficient * value_loss
                - cfg.entropy_coefficient * entropy
            )
        loss = torch.stack(losses).mean()
        if not bool(torch.isfinite(loss)):
            raise RuntimeError("non-finite PPO loss")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.max_grad_norm)
        optimizer.step()
        epoch_losses.append(float(loss.detach().cpu()))
    model.eval()
    bounds = fit_active_vision_feature_bounds(episodes, safety_config=safety_config)
    return ActiveVisionTrainingResult(
        model=model,
        epoch_losses=tuple(epoch_losses),
        feature_bounds=bounds,
        transition_count=len(examples),
        config=MappingProxyType(asdict(cfg)),
    )


def _training_examples(
    episodes: Sequence[ActiveVisionResearchEpisode],
    *,
    safety_config: ActiveVisionSafetyConfigV1 | None,
) -> list[tuple[np.ndarray, int]]:
    examples: list[tuple[np.ndarray, int]] = []
    for episode in episodes:
        for transition in episode.transitions:
            batch = active_vision_candidate_batch(
                transition.snapshot,
                camera_id=transition.camera_id,
                safety_config=safety_config,
            )
            examples.append(
                (batch.features, _selected_action_index(batch.actions, transition.selected_action))
            )
    if not examples:
        raise ValueError("training split contains no active-vision transitions")
    return examples


def _selected_action_index(
    candidates: Sequence[ActiveVisionActionV1], selected: ActiveVisionActionV1
) -> int:
    matches = [index for index, candidate in enumerate(candidates) if candidate.action_key == selected.action_key]
    if len(matches) != 1:
        raise ValueError("recorded action is not a unique member of the finite action set")
    return matches[0]


def _validate_training_config(epochs: int, learning_rate: float) -> None:
    if int(epochs) <= 0 or not np.isfinite(learning_rate) or learning_rate <= 0.0:
        raise ValueError("training epochs and learning rate must be positive")


def _seed_everything(seed: int) -> None:
    random.seed(int(seed))
    np.random.seed(int(seed))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ACTIVE_VISION_DATASET_SCHEMA_VERSION",
    "ACTIVE_VISION_FEATURE_NAMES",
    "ACTIVE_VISION_MODEL_SEMANTIC_VERSION",
    "ActiveVisionActorCritic",
    "ActiveVisionCandidateBatch",
    "ActiveVisionDatasetSplit",
    "ActiveVisionFeatureBounds",
    "ActiveVisionResearchEpisode",
    "ActiveVisionTrainingResult",
    "ActiveVisionTransition",
    "BehaviorCloningConfig",
    "ClippedPpoConfig",
    "active_vision_candidate_batch",
    "fit_active_vision_feature_bounds",
    "split_active_vision_episode_groups",
    "train_behavior_cloning",
    "train_clipped_ppo",
]
