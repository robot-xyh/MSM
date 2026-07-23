"""Versioned in-memory episode bus with recursive online truth isolation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields, is_dataclass
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

import numpy as np

from .models import (
    BUS_SCHEMA_VERSION,
    OFFLINE_TRUTH_SCHEMA_VERSION,
    ONLINE_OBSERVATION_SCHEMA_VERSION,
    SCENARIO_SCHEMA_VERSION,
    WORLD_SCHEMA_VERSION,
    ScenarioConfig,
)


_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "entity_ids",
        "intercepted_target_indices",
        "offline_truth_labels",
    }
)
_FORBIDDEN_ONLINE_TYPES = frozenset({"OfflineTruthLabel", "WorldSnapshot", "EntitySnapshot"})


@dataclass(frozen=True)
class VersionedEnvelope:
    """One immutable message on the main-owned episode bus."""

    sequence: int
    topic: str
    source: str
    timestamp: float
    schema_version: str
    payload: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
            "payload": jsonable(self.payload),
        }


@dataclass(frozen=True)
class EpisodeManifest:
    """Reproducibility manifest written once per episode."""

    episode_id: str
    git_commit: str
    repository_dirty: bool
    config_sha256: str
    scenario_name: str
    scenario_version: str
    seed: int
    world_schema: str
    bus_schema: str
    scenario_schema: str
    online_observation_schema: str
    offline_truth_schema: str
    d1_model_version: str
    d2_model_version: str
    d3_policy_version: str
    d4_policy_version: str
    d5_model_version: str
    d5_active_vision_policy_version: str
    d7_model_version: str
    threshold_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InMemoryEpisodeBus:
    """Small deterministic bus used to connect versioned module adapters."""

    def __init__(self, *, schema_version: str = BUS_SCHEMA_VERSION) -> None:
        self.schema_version = str(schema_version)
        self._next_sequence = 1
        self._messages: list[VersionedEnvelope] = []
        self._subscribers: dict[str, list[Callable[[VersionedEnvelope], None]]] = {}

    def publish(
        self,
        *,
        topic: str,
        source: str,
        timestamp: float,
        payload: Any,
        schema_version: str | None = None,
        copy_payload: bool = True,
    ) -> VersionedEnvelope:
        if not topic or not source:
            raise ValueError("topic and source must be non-empty")
        if not np.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("timestamp must be finite and non-negative")
        assert_online_payload_truth_free(payload)
        envelope = VersionedEnvelope(
            sequence=self._next_sequence,
            topic=str(topic),
            source=str(source),
            timestamp=float(timestamp),
            schema_version=str(schema_version or self.schema_version),
            payload=copy.deepcopy(payload) if copy_payload else payload,
        )
        self._next_sequence += 1
        self._messages.append(envelope)
        for callback in tuple(self._subscribers.get(topic, ())):
            callback(envelope)
        return envelope

    def subscribe(self, topic: str, callback: Callable[[VersionedEnvelope], None]) -> None:
        if not topic:
            raise ValueError("topic must be non-empty")
        self._subscribers.setdefault(topic, []).append(callback)

    def messages(self, topic: str | None = None) -> tuple[VersionedEnvelope, ...]:
        if topic is None:
            return tuple(self._messages)
        return tuple(message for message in self._messages if message.topic == topic)

    def clear(self) -> None:
        self._messages.clear()


def assert_online_payload_truth_free(payload: Any) -> None:
    """Reject truth-bearing fields anywhere in an online payload tree."""

    pending = [payload]
    visited: set[int] = set()
    while pending:
        value = pending.pop()
        type_name = type(value).__name__
        if type_name in _FORBIDDEN_ONLINE_TYPES:
            raise ValueError(
                "online payload contains evaluator-only truth fields: "
                f"<{type_name}>"
            )
        if value is None or isinstance(
            value,
            (str, bytes, int, float, complex, np.generic, np.ndarray),
        ):
            continue
        value_id = id(value)
        if value_id in visited:
            continue
        if is_dataclass(value) and not isinstance(value, type):
            visited.add(value_id)
            for name, key in _dataclass_field_keys(type(value)):
                if _is_forbidden_key(key):
                    raise ValueError(
                        "online payload contains evaluator-only truth fields: "
                        f"{name}"
                    )
                pending.append(getattr(value, name))
            continue
        if isinstance(value, Mapping):
            visited.add(value_id)
            raw_keys = tuple(str(raw_key) for raw_key in value.keys())
            forbidden_key = _first_forbidden_mapping_key(raw_keys)
            if forbidden_key is not None:
                raise ValueError(
                    "online payload contains evaluator-only truth fields: "
                    f"{forbidden_key}"
                )
            pending.extend(value.values())
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            visited.add(value_id)
            pending.extend(value)


def build_episode_manifest(
    config: ScenarioConfig,
    *,
    repository_root: Path | None = None,
) -> EpisodeManifest:
    """Build a manifest from canonical configuration and repository state."""

    root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    config_json = json.dumps(
        config.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    config_sha = hashlib.sha256(config_json).hexdigest()
    git_commit = _git_output(root, ["rev-parse", "HEAD"], default="unknown")
    dirty_output = _git_output(root, ["status", "--porcelain"], default="")
    episode_id = f"{config.scenario_name}-s{config.seed}-{config_sha[:12]}"
    return EpisodeManifest(
        episode_id=episode_id,
        git_commit=git_commit,
        repository_dirty=bool(dirty_output.strip()),
        config_sha256=config_sha,
        scenario_name=config.scenario_name,
        scenario_version=config.scenario_version,
        seed=config.seed,
        world_schema=WORLD_SCHEMA_VERSION,
        bus_schema=BUS_SCHEMA_VERSION,
        scenario_schema=SCENARIO_SCHEMA_VERSION,
        online_observation_schema=ONLINE_OBSERVATION_SCHEMA_VERSION,
        offline_truth_schema=OFFLINE_TRUTH_SCHEMA_VERSION,
        d1_model_version=config.d1_model_version,
        d2_model_version=config.d2_model_version,
        d3_policy_version=config.d3_policy_version,
        d4_policy_version=config.d4_policy_version,
        d5_model_version=config.d5_model_version,
        d5_active_vision_policy_version=config.d5_active_vision_policy_version,
        d7_model_version=config.d7_model_version,
        threshold_version=config.threshold_version,
    )


def jsonable(value: Any) -> Any:
    """Convert dataclasses and NumPy values into JSON-compatible structures."""

    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(item) for item in value]
    return value


@lru_cache(maxsize=2048)
def _normalise_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


@lru_cache(maxsize=256)
def _dataclass_field_keys(cls: type[Any]) -> tuple[tuple[str, str], ...]:
    return tuple((item.name, _normalise_key(item.name)) for item in fields(cls))


@lru_cache(maxsize=4096)
def _first_forbidden_mapping_key(raw_keys: tuple[str, ...]) -> str | None:
    for raw_key in raw_keys:
        if _is_forbidden_key(_normalise_key(raw_key)):
            return raw_key
    return None


@lru_cache(maxsize=2048)
def _is_forbidden_key(key: str) -> bool:
    if key in _FORBIDDEN_ONLINE_KEYS:
        return True
    return key.startswith("truth_") or key.endswith("_truth_id") or key.endswith("_actor_id")


def _git_output(root: Path, arguments: Sequence[str], *, default: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return default
    return completed.stdout.strip()
