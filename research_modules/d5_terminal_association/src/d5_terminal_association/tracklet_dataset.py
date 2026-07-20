"""Versioned offline dataset contract for anonymous D5 tracklet graphs.

Graph archives are produced from the already-built online D5 sparse graph and
contain no evaluator identity.  Evaluator labels are written to a separate
JSON file and are joined only by offline training/evaluation code.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .sparse_tracklet_graph import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    SparseTrackletGraph,
)
from .tracklet_gnn import OfflineTrackletTruthLabel


DATASET_SCHEMA_VERSION = "d5.tracklet-dataset.v2"
EPISODE_DESCRIPTOR_SCHEMA_VERSION = "d5.tracklet-episode.v1"
GRAPH_SCHEMA_VERSION = "d5.sparse-tracklet-graph.v1"
EVALUATOR_LABEL_SCHEMA_VERSION = "d5.tracklet-evaluator-labels.v1"
NODE_FEATURE_VERSION = "d5.tracklet-node-features.v1"
EDGE_FEATURE_VERSION = "d5.tracklet-edge-features.v1"

DEFAULT_HARD_NEGATIVE_PROVENANCE: Mapping[str, Any] = MappingProxyType(
    {
        "source": "anonymous_online_candidate_edges_after_geometry_gates",
        "strategy": "lowest_geometry_gate_score_first",
        "selection_stage": "offline_after_evaluator_label_join",
        "random_edge_sampling": False,
    }
)

_GRAPH_ARRAY_KEYS = frozenset(
    {
        "graph_schema_version",
        "node_feature_version",
        "edge_feature_version",
        "node_feature_names",
        "edge_feature_names",
        "episode_uid",
        "scenario_version",
        "seed",
        "episode_id",
        "node_features",
        "edge_index",
        "edge_features",
        "tracklet_keys",
        "camera_keys",
        "measurement_timestamps",
        "arrival_timestamps",
        "gate_scores",
        "candidate_count_names",
        "candidate_count_values",
    }
)


class TrackletDatasetValidationError(ValueError):
    """Raised when an offline dataset fails closed during validation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class LoadedTrackletGraph:
    """Truth-free numeric graph loaded with ``allow_pickle=False``."""

    episode_uid: str
    scenario_version: str
    seed: int
    episode_id: str
    node_features: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    tracklet_keys: tuple[str, ...]
    camera_keys: tuple[str, ...]
    measurement_timestamps: np.ndarray
    arrival_timestamps: np.ndarray
    gate_scores: np.ndarray
    candidate_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        for name in (
            "node_features",
            "edge_index",
            "edge_features",
            "measurement_timestamps",
            "arrival_timestamps",
            "gate_scores",
        ):
            array = np.asarray(getattr(self, name)).copy()
            array.setflags(write=False)
            object.__setattr__(self, name, array)
        object.__setattr__(self, "tracklet_keys", tuple(self.tracklet_keys))
        object.__setattr__(self, "camera_keys", tuple(self.camera_keys))
        object.__setattr__(
            self,
            "candidate_counts",
            MappingProxyType({str(key): int(value) for key, value in self.candidate_counts.items()}),
        )

    @property
    def node_count(self) -> int:
        return int(self.node_features.shape[0])

    @property
    def edge_count(self) -> int:
        return int(self.edge_features.shape[0])


@dataclass(frozen=True)
class LoadedEvaluatorLabels:
    """Evaluator-only labels loaded from the independent label artifact."""

    episode_uid: str
    labels: tuple[OfflineTrackletTruthLabel, ...]
    labels_complete: bool
    candidate_recall_available: bool

    @property
    def by_tracklet_key(self) -> Mapping[str, OfflineTrackletTruthLabel]:
        return MappingProxyType({label.tracklet_key: label for label in self.labels})


@dataclass(frozen=True)
class LoadedTrackletEpisode:
    graph: LoadedTrackletGraph
    evaluator_labels: LoadedEvaluatorLabels
    split: str
    graph_sha256: str
    labels_sha256: str
    class_balance: Mapping[str, int]
    hard_negative_provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.split not in {"train", "validation", "test"}:
            raise ValueError("invalid dataset split")
        object.__setattr__(
            self,
            "class_balance",
            MappingProxyType({str(key): int(value) for key, value in self.class_balance.items()}),
        )
        object.__setattr__(
            self,
            "hard_negative_provenance",
            MappingProxyType(dict(self.hard_negative_provenance)),
        )


@dataclass(frozen=True)
class LoadedTrackletDataset:
    root: Path
    manifest: Mapping[str, Any]
    manifest_sha256: str
    episodes: tuple[LoadedTrackletEpisode, ...]

    def split(self, name: str) -> tuple[LoadedTrackletEpisode, ...]:
        if name not in {"train", "validation", "test"}:
            raise ValueError("split must be train, validation, or test")
        return tuple(episode for episode in self.episodes if episode.split == name)


@dataclass(frozen=True)
class OfflineObservationLabelJoinResult:
    """Audited offline join from source observations to anonymous tracklets."""

    tracklet_labels: tuple[OfflineTrackletTruthLabel, ...]
    labels_complete: bool
    missing_tracklet_keys: tuple[str, ...]
    unmatched_observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tracklet_labels", tuple(self.tracklet_labels))
        object.__setattr__(self, "missing_tracklet_keys", tuple(self.missing_tracklet_keys))
        object.__setattr__(
            self,
            "unmatched_observation_ids",
            tuple(self.unmatched_observation_ids),
        )


def join_offline_observation_labels(
    graph: SparseTrackletGraph,
    evaluator_observation_labels: Iterable[Any],
    *,
    max_timestamp_delta_s: float = 1.0e-6,
) -> OfflineObservationLabelJoinResult:
    """Join main's evaluator-only ``observation_id`` labels after graph build.

    ``source_observation_id`` remains an audit key only.  It is never copied to
    ``local_track_id`` or ``global_track_id`` and is absent from model features.
    """

    tolerance = float(max_timestamp_delta_s)
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("max_timestamp_delta_s must be finite and non-negative")
    by_observation_id: dict[str, tuple[str, float]] = {}
    for item in evaluator_observation_labels:
        observation_id = str(_offline_field(item, "observation_id")).strip()
        truth_entity_id = str(_offline_field(item, "truth_entity_id")).strip()
        timestamp = float(_offline_field(item, "measurement_timestamp"))
        if not observation_id or not truth_entity_id or not np.isfinite(timestamp):
            raise ValueError("offline observation label fields must be non-empty and finite")
        if observation_id in by_observation_id:
            raise ValueError(f"duplicate offline observation label: {observation_id}")
        by_observation_id[observation_id] = (truth_entity_id, timestamp)

    frame_links: set[tuple[float, str]] = set()
    consumed: set[str] = set()
    missing: list[str] = []
    labels: list[OfflineTrackletTruthLabel] = []
    for node in graph.nodes:
        source_id = node.source_observation_id
        if source_id is None:
            missing.append(node.tracklet_key)
            continue
        frame_link = (node.measurement_timestamp, source_id)
        if frame_link in frame_links:
            raise ValueError("one source observation maps to multiple tracklets in one frame")
        frame_links.add(frame_link)
        offline = by_observation_id.get(source_id)
        if offline is None:
            missing.append(node.tracklet_key)
            continue
        truth_entity_id, label_timestamp = offline
        if abs(label_timestamp - node.measurement_timestamp) > tolerance:
            raise ValueError(
                f"offline observation label timestamp does not align with {node.tracklet_key}"
            )
        consumed.add(source_id)
        labels.append(
            OfflineTrackletTruthLabel(
                tracklet_key=node.tracklet_key,
                truth_entity_id=truth_entity_id,
                measurement_timestamp=node.measurement_timestamp,
            )
        )
    unmatched = tuple(sorted(set(by_observation_id) - consumed))
    return OfflineObservationLabelJoinResult(
        tracklet_labels=tuple(sorted(labels, key=lambda item: item.tracklet_key)),
        labels_complete=not missing and len(labels) == graph.node_count,
        missing_tracklet_keys=tuple(sorted(missing)),
        unmatched_observation_ids=unmatched,
    )


def stage_tracklet_dataset_episode(
    dataset_dir: str | Path,
    graph: SparseTrackletGraph,
    evaluator_labels: Iterable[OfflineTrackletTruthLabel],
    *,
    scenario_version: str,
    seed: int,
    episode_id: str,
    generation_config: Mapping[str, Any],
    labels_complete: bool,
    candidate_recall_available: bool | None = None,
    hard_negative_provenance: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Write one graph/label pair into a dataset staging directory.

    The graph archive is deliberately reconstructed from public numeric graph
    arrays.  ``SparseCandidateEdge.shared_global_track_ids`` is not persisted,
    and evaluator ``truth_entity_id`` values occur only in the label JSON.
    """

    if not isinstance(graph, SparseTrackletGraph):
        raise TypeError("graph must be a SparseTrackletGraph")
    scenario = _non_empty_text(scenario_version, "scenario_version")
    episode = _non_empty_text(episode_id, "episode_id")
    seed_value = int(seed)
    root = Path(dataset_dir)
    root.mkdir(parents=True, exist_ok=True)
    config_sha256 = _ensure_generation_config(root, generation_config)
    labels = tuple(evaluator_labels)
    label_by_key = _validated_label_map(graph, labels)
    complete = bool(labels_complete)
    if complete and len(label_by_key) != graph.node_count:
        raise ValueError("labels_complete requires exactly one label for every graph node")
    recall_available = complete if candidate_recall_available is None else bool(candidate_recall_available)
    if recall_available and not complete:
        raise ValueError("candidate recall cannot be available without complete evaluator labels")

    episode_uid = _episode_uid(scenario, seed_value, episode)
    graph_relpath = Path("graphs") / f"{episode_uid}.graph.npz"
    labels_relpath = Path("labels") / f"{episode_uid}.labels.json"
    descriptor_relpath = Path("episodes") / f"{episode_uid}.episode.json"
    for relative in (graph_relpath, labels_relpath, descriptor_relpath):
        path = root / relative
        if path.exists():
            raise FileExistsError(f"dataset episode artifact already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    candidate_names = tuple(sorted(str(key) for key in graph.candidate_counts))
    graph_payload = {
        "graph_schema_version": np.asarray(GRAPH_SCHEMA_VERSION),
        "node_feature_version": np.asarray(NODE_FEATURE_VERSION),
        "edge_feature_version": np.asarray(EDGE_FEATURE_VERSION),
        "node_feature_names": np.asarray(NODE_FEATURE_NAMES, dtype=np.str_),
        "edge_feature_names": np.asarray(EDGE_FEATURE_NAMES, dtype=np.str_),
        "episode_uid": np.asarray(episode_uid),
        "scenario_version": np.asarray(scenario),
        "seed": np.asarray(seed_value, dtype=np.int64),
        "episode_id": np.asarray(episode),
        "node_features": np.asarray(graph.node_features, dtype=np.float32),
        "edge_index": np.asarray(graph.edge_index, dtype=np.int64),
        "edge_features": np.asarray(graph.edge_features, dtype=np.float32),
        "tracklet_keys": np.asarray([node.tracklet_key for node in graph.nodes], dtype=np.str_),
        "camera_keys": np.asarray([node.camera_key for node in graph.nodes], dtype=np.str_),
        "measurement_timestamps": np.asarray(
            [node.measurement_timestamp for node in graph.nodes], dtype=np.float64
        ),
        "arrival_timestamps": np.asarray(
            [node.arrival_timestamp for node in graph.nodes], dtype=np.float64
        ),
        "gate_scores": np.asarray([edge.gate_score for edge in graph.edges], dtype=np.float32),
        "candidate_count_names": np.asarray(candidate_names, dtype=np.str_),
        "candidate_count_values": np.asarray(
            [graph.candidate_counts[name] for name in candidate_names], dtype=np.int64
        ),
    }
    _write_npz_atomic(root / graph_relpath, graph_payload)

    labels_payload = {
        "schema_version": EVALUATOR_LABEL_SCHEMA_VERSION,
        "episode_uid": episode_uid,
        "scenario_version": scenario,
        "seed": seed_value,
        "episode_id": episode,
        "labels_complete": complete,
        "candidate_recall_available": recall_available,
        "labels": [
            {
                "tracklet_key": label.tracklet_key,
                "measurement_timestamp": float(label.measurement_timestamp),
                "truth_entity_id": label.truth_entity_id,
            }
            for label in sorted(labels, key=lambda item: item.tracklet_key)
        ],
    }
    _write_json_atomic(root / labels_relpath, labels_payload)

    class_balance = _class_balance_from_arrays(
        np.asarray(graph.edge_index, dtype=np.int64),
        tuple(node.tracklet_key for node in graph.nodes),
        label_by_key,
    )
    provenance = _json_object(
        dict(DEFAULT_HARD_NEGATIVE_PROVENANCE)
        if hard_negative_provenance is None
        else hard_negative_provenance,
        "hard_negative_provenance",
    )
    descriptor = {
        "schema_version": EPISODE_DESCRIPTOR_SCHEMA_VERSION,
        "episode_uid": episode_uid,
        "scenario_version": scenario,
        "seed": seed_value,
        "episode_id": episode,
        "graph_file": graph_relpath.as_posix(),
        "graph_sha256": sha256_file(root / graph_relpath),
        "labels_file": labels_relpath.as_posix(),
        "labels_sha256": sha256_file(root / labels_relpath),
        "config_sha256": config_sha256,
        "node_count": graph.node_count,
        "edge_count": graph.edge_count,
        "class_balance": class_balance,
        "labels_complete": complete,
        "candidate_recall_available": recall_available,
        "hard_negative_provenance": provenance,
    }
    _write_json_atomic(root / descriptor_relpath, descriptor)
    return MappingProxyType(descriptor)


def finalize_tracklet_dataset(
    dataset_dir: str | Path,
    *,
    split_seed: int = 20260720,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> Mapping[str, Any]:
    """Assign whole groups and shared seed values, then write the manifest."""

    root = Path(dataset_dir)
    descriptors = tuple(
        _read_json(path) for path in sorted((root / "episodes").glob("*.episode.json"))
    )
    if not descriptors:
        raise ValueError("no staged dataset episodes were found")
    for descriptor in descriptors:
        _validate_descriptor_shape(descriptor)
    config_path = root / "dataset_config.json"
    if not config_path.is_file():
        raise ValueError("dataset_config.json is missing")
    config_sha256 = sha256_file(config_path)
    if any(descriptor["config_sha256"] != config_sha256 for descriptor in descriptors):
        raise ValueError("staged episodes do not share the dataset generation config")

    assignments = split_episode_groups(
        descriptors,
        split_seed=split_seed,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
    )
    episodes: list[dict[str, Any]] = []
    for descriptor in sorted(descriptors, key=lambda item: item["episode_uid"]):
        item = dict(descriptor)
        item["split"] = assignments[item["episode_uid"]]
        episodes.append(item)

    split_payload = _split_payload(episodes)
    split_sha256 = sha256_json(split_payload)
    training_set_sha256 = _training_set_sha256(episodes)
    class_balance_by_split = {
        split: _sum_class_balance(item for item in episodes if item["split"] == split)
        for split in ("train", "validation", "test")
    }
    available_count = sum(bool(item["candidate_recall_available"]) for item in episodes)
    if available_count == len(episodes):
        availability = "available"
    elif available_count:
        availability = "partial"
    else:
        availability = "unavailable"
    provenance_by_hash: dict[str, Mapping[str, Any]] = {}
    for item in episodes:
        provenance = item["hard_negative_provenance"]
        provenance_by_hash[sha256_json(provenance)] = provenance

    manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "evaluator_label_schema_version": EVALUATOR_LABEL_SCHEMA_VERSION,
        "node_feature_version": NODE_FEATURE_VERSION,
        "edge_feature_version": EDGE_FEATURE_VERSION,
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "dataset_config_file": config_path.name,
        "config_sha256": config_sha256,
        "split_policy": {
            "unit": "whole_episode_grouped_by_scenario_version_and_seed",
            "edge_level_random_split": False,
            "shared_seed_values_atomic_across_scenarios": True,
            "split_seed": int(split_seed),
            "validation_fraction": float(validation_fraction),
            "test_fraction": float(test_fraction),
        },
        "split_sha256": split_sha256,
        "training_set_sha256": training_set_sha256,
        "class_balance_by_split": class_balance_by_split,
        "candidate_recall_availability": {
            "status": availability,
            "available_episode_count": available_count,
            "episode_count": len(episodes),
        },
        "hard_negative_provenance": [
            provenance_by_hash[key] for key in sorted(provenance_by_hash)
        ],
        "episodes": episodes,
    }
    _write_json_atomic(root / "manifest.json", manifest)
    load_tracklet_dataset(root)
    return MappingProxyType(manifest)


def split_episode_groups(
    descriptors: Sequence[Mapping[str, Any]],
    *,
    split_seed: int,
    validation_fraction: float,
    test_fraction: float,
) -> Mapping[str, str]:
    """Return deterministic whole-group assignments without seed leakage."""

    if not 0.0 < validation_fraction < 1.0 or not 0.0 < test_fraction < 1.0:
        raise ValueError("validation_fraction and test_fraction must be in (0, 1)")
    if validation_fraction + test_fraction >= 1.0:
        raise ValueError("validation_fraction + test_fraction must be below 1")
    groups: dict[tuple[str, int], list[str]] = {}
    seen_episode_uids: set[str] = set()
    for descriptor in descriptors:
        scenario = _non_empty_text(descriptor.get("scenario_version"), "scenario_version")
        seed = int(descriptor.get("seed"))
        episode_uid = _non_empty_text(descriptor.get("episode_uid"), "episode_uid")
        if episode_uid in seen_episode_uids:
            raise ValueError(f"duplicate episode_uid: {episode_uid}")
        seen_episode_uids.add(episode_uid)
        groups.setdefault((scenario, seed), []).append(episode_uid)
    seed_values = sorted({seed for _, seed in groups})
    if len(seed_values) < 3:
        raise ValueError("at least three unique seed values are required")

    ordered_seeds = sorted(
        seed_values,
        key=lambda seed: (
            hashlib.sha256(f"{int(split_seed)}\0{seed}".encode("utf-8")).hexdigest(),
            seed,
        ),
    )
    seed_count = len(ordered_seeds)
    validation_count = max(1, int(round(seed_count * validation_fraction)))
    test_count = max(1, int(round(seed_count * test_fraction)))
    while validation_count + test_count >= seed_count:
        if validation_count >= test_count and validation_count > 1:
            validation_count -= 1
        elif test_count > 1:
            test_count -= 1
        else:
            raise ValueError("split fractions leave no training group")
    validation_seeds = set(ordered_seeds[:validation_count])
    test_seeds = set(ordered_seeds[validation_count : validation_count + test_count])
    assignments: dict[str, str] = {}
    for group, episode_uids in groups.items():
        seed = group[1]
        split = "validation" if seed in validation_seeds else "test" if seed in test_seeds else "train"
        for episode_uid in episode_uids:
            assignments[episode_uid] = split
    return MappingProxyType(assignments)


def load_tracklet_dataset(
    dataset_dir: str | Path,
    *,
    expected_config_sha256: str | None = None,
) -> LoadedTrackletDataset:
    """Load and validate every graph, label, hash, version, and split contract."""

    root = Path(dataset_dir).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise TrackletDatasetValidationError("manifest_missing", "dataset manifest.json is missing")
    manifest = _read_json(manifest_path)
    _expect_equal(manifest.get("schema_version"), DATASET_SCHEMA_VERSION, "dataset_schema_mismatch")
    _expect_equal(manifest.get("graph_schema_version"), GRAPH_SCHEMA_VERSION, "graph_schema_mismatch")
    _expect_equal(
        manifest.get("evaluator_label_schema_version"),
        EVALUATOR_LABEL_SCHEMA_VERSION,
        "label_schema_mismatch",
    )
    _expect_equal(manifest.get("node_feature_version"), NODE_FEATURE_VERSION, "node_feature_version_mismatch")
    _expect_equal(manifest.get("edge_feature_version"), EDGE_FEATURE_VERSION, "edge_feature_version_mismatch")
    _expect_equal(tuple(manifest.get("node_feature_names", ())), NODE_FEATURE_NAMES, "node_feature_order_mismatch")
    _expect_equal(tuple(manifest.get("edge_feature_names", ())), EDGE_FEATURE_NAMES, "edge_feature_order_mismatch")

    config_path = _safe_relative_path(root, manifest.get("dataset_config_file"))
    config_sha256 = sha256_file(config_path)
    _expect_equal(config_sha256, manifest.get("config_sha256"), "config_sha_mismatch")
    if expected_config_sha256 is not None:
        _expect_equal(config_sha256, expected_config_sha256, "unexpected_config_sha")

    raw_episodes = manifest.get("episodes")
    if not isinstance(raw_episodes, list) or not raw_episodes:
        raise TrackletDatasetValidationError("episodes_missing", "dataset contains no episodes")
    split_policy = manifest.get("split_policy")
    if not isinstance(split_policy, Mapping):
        raise TrackletDatasetValidationError("split_policy_missing", "dataset split policy is missing")
    _expect_equal(
        set(split_policy),
        {
            "unit",
            "edge_level_random_split",
            "shared_seed_values_atomic_across_scenarios",
            "split_seed",
            "validation_fraction",
            "test_fraction",
        },
        "split_policy_fields_mismatch",
    )
    _expect_equal(
        split_policy.get("unit"),
        "whole_episode_grouped_by_scenario_version_and_seed",
        "split_unit_mismatch",
    )
    _expect_equal(
        split_policy.get("edge_level_random_split"),
        False,
        "edge_random_split_forbidden",
    )
    _expect_equal(
        split_policy.get("shared_seed_values_atomic_across_scenarios"),
        True,
        "shared_seed_split_policy_mismatch",
    )
    try:
        split_seed = int(split_policy["split_seed"])
        validation_fraction = float(split_policy["validation_fraction"])
        test_fraction = float(split_policy["test_fraction"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TrackletDatasetValidationError("split_policy_invalid", "split policy is invalid") from exc
    expected_assignments = split_episode_groups(
        raw_episodes,
        split_seed=split_seed,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
    )
    loaded: list[LoadedTrackletEpisode] = []
    groups_to_split: dict[tuple[str, int], str] = {}
    seeds_to_split: dict[int, str] = {}
    seen_uids: set[str] = set()
    for descriptor in raw_episodes:
        if not isinstance(descriptor, Mapping):
            raise TrackletDatasetValidationError("descriptor_invalid", "episode descriptor is not an object")
        _validate_descriptor_shape(descriptor)
        episode_uid = str(descriptor["episode_uid"])
        if episode_uid in seen_uids:
            raise TrackletDatasetValidationError("episode_duplicate", f"duplicate episode {episode_uid}")
        seen_uids.add(episode_uid)
        split = str(descriptor.get("split"))
        if split not in {"train", "validation", "test"}:
            raise TrackletDatasetValidationError("split_invalid", f"invalid split for {episode_uid}")
        _expect_equal(split, expected_assignments[episode_uid], "split_assignment_mismatch")
        _expect_equal(descriptor["config_sha256"], config_sha256, "episode_config_sha_mismatch")
        group = (str(descriptor["scenario_version"]), int(descriptor["seed"]))
        previous_split = groups_to_split.setdefault(group, split)
        if previous_split != split:
            raise TrackletDatasetValidationError(
                "seed_leakage",
                f"scenario/seed group {group} appears in multiple splits",
            )
        seed = group[1]
        previous_seed_split = seeds_to_split.setdefault(seed, split)
        if previous_seed_split != split:
            raise TrackletDatasetValidationError(
                "seed_leakage",
                f"seed value {seed} appears in multiple splits",
            )
        graph_path = _safe_relative_path(root, descriptor["graph_file"])
        labels_path = _safe_relative_path(root, descriptor["labels_file"])
        _expect_equal(sha256_file(graph_path), descriptor["graph_sha256"], "graph_sha_mismatch")
        _expect_equal(sha256_file(labels_path), descriptor["labels_sha256"], "labels_sha_mismatch")
        graph = _load_graph_archive(graph_path, descriptor)
        labels = _load_label_file(labels_path, graph, descriptor)
        class_balance = _class_balance_from_arrays(
            graph.edge_index,
            graph.tracklet_keys,
            labels.by_tracklet_key,
        )
        _expect_equal(class_balance, descriptor["class_balance"], "class_balance_mismatch")
        loaded.append(
            LoadedTrackletEpisode(
                graph=graph,
                evaluator_labels=labels,
                split=split,
                graph_sha256=str(descriptor["graph_sha256"]),
                labels_sha256=str(descriptor["labels_sha256"]),
                class_balance=class_balance,
                hard_negative_provenance=_json_object(
                    descriptor["hard_negative_provenance"], "hard_negative_provenance"
                ),
            )
        )

    split_payload = _split_payload(raw_episodes)
    _expect_equal(sha256_json(split_payload), manifest.get("split_sha256"), "split_sha_mismatch")
    _expect_equal(
        _training_set_sha256(raw_episodes),
        manifest.get("training_set_sha256"),
        "training_set_sha_mismatch",
    )
    expected_balance_by_split = {
        split: _sum_class_balance(item for item in raw_episodes if item["split"] == split)
        for split in ("train", "validation", "test")
    }
    _expect_equal(
        manifest.get("class_balance_by_split"),
        expected_balance_by_split,
        "class_balance_summary_mismatch",
    )
    available_count = sum(bool(item["candidate_recall_available"]) for item in raw_episodes)
    availability_status = (
        "available"
        if available_count == len(raw_episodes)
        else "partial"
        if available_count
        else "unavailable"
    )
    expected_availability = {
        "status": availability_status,
        "available_episode_count": available_count,
        "episode_count": len(raw_episodes),
    }
    _expect_equal(
        manifest.get("candidate_recall_availability"),
        expected_availability,
        "candidate_recall_summary_mismatch",
    )
    provenance_by_hash = {
        sha256_json(item["hard_negative_provenance"]): item["hard_negative_provenance"]
        for item in raw_episodes
    }
    expected_provenance = [provenance_by_hash[key] for key in sorted(provenance_by_hash)]
    _expect_equal(
        manifest.get("hard_negative_provenance"),
        expected_provenance,
        "hard_negative_provenance_mismatch",
    )
    if set(groups_to_split.values()) != {"train", "validation", "test"}:
        raise TrackletDatasetValidationError("split_empty", "train/validation/test must all be non-empty")
    return LoadedTrackletDataset(
        root=root,
        manifest=MappingProxyType(dict(manifest)),
        manifest_sha256=sha256_file(manifest_path),
        episodes=tuple(sorted(loaded, key=lambda item: item.graph.episode_uid)),
    )


def edge_targets(episode: LoadedTrackletEpisode) -> tuple[np.ndarray, np.ndarray]:
    """Return evaluator targets and an availability mask for candidate edges."""

    label_by_key = episode.evaluator_labels.by_tracklet_key
    targets = np.zeros(episode.graph.edge_count, dtype=np.float32)
    eligible = np.zeros(episode.graph.edge_count, dtype=bool)
    for edge_number, (source, target) in enumerate(episode.graph.edge_index.T):
        left = label_by_key.get(episode.graph.tracklet_keys[int(source)])
        right = label_by_key.get(episode.graph.tracklet_keys[int(target)])
        if left is None or right is None:
            continue
        eligible[edge_number] = True
        targets[edge_number] = float(left.truth_entity_id == right.truth_entity_id)
    targets.setflags(write=False)
    eligible.setflags(write=False)
    return targets, eligible


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _load_graph_archive(
    path: Path,
    descriptor: Mapping[str, Any],
) -> LoadedTrackletGraph:
    try:
        with np.load(path, allow_pickle=False) as archive:
            keys = frozenset(archive.files)
            if keys != _GRAPH_ARRAY_KEYS:
                raise TrackletDatasetValidationError(
                    "graph_fields_mismatch",
                    f"unexpected graph fields: {sorted(keys ^ _GRAPH_ARRAY_KEYS)}",
                )
            values = {key: np.array(archive[key], copy=True) for key in archive.files}
    except TrackletDatasetValidationError:
        raise
    except Exception as exc:
        raise TrackletDatasetValidationError("graph_archive_invalid", f"cannot load {path.name}") from exc

    _expect_equal(_scalar_text(values["graph_schema_version"]), GRAPH_SCHEMA_VERSION, "graph_schema_mismatch")
    _expect_equal(_scalar_text(values["node_feature_version"]), NODE_FEATURE_VERSION, "node_feature_version_mismatch")
    _expect_equal(_scalar_text(values["edge_feature_version"]), EDGE_FEATURE_VERSION, "edge_feature_version_mismatch")
    _expect_equal(tuple(str(item) for item in values["node_feature_names"].tolist()), NODE_FEATURE_NAMES, "node_feature_order_mismatch")
    _expect_equal(tuple(str(item) for item in values["edge_feature_names"].tolist()), EDGE_FEATURE_NAMES, "edge_feature_order_mismatch")
    episode_uid = _scalar_text(values["episode_uid"])
    scenario_version = _scalar_text(values["scenario_version"])
    seed = int(np.asarray(values["seed"]).item())
    episode_id = _scalar_text(values["episode_id"])
    _expect_equal(episode_uid, descriptor["episode_uid"], "episode_identity_mismatch")
    _expect_equal(scenario_version, descriptor["scenario_version"], "episode_identity_mismatch")
    _expect_equal(seed, int(descriptor["seed"]), "episode_identity_mismatch")
    _expect_equal(episode_id, descriptor["episode_id"], "episode_identity_mismatch")

    node_features = np.asarray(values["node_features"], dtype=np.float32)
    edge_index = np.asarray(values["edge_index"], dtype=np.int64)
    edge_features = np.asarray(values["edge_features"], dtype=np.float32)
    tracklet_keys = tuple(str(value) for value in values["tracklet_keys"].tolist())
    camera_keys = tuple(str(value) for value in values["camera_keys"].tolist())
    measurement_timestamps = np.asarray(values["measurement_timestamps"], dtype=np.float64)
    arrival_timestamps = np.asarray(values["arrival_timestamps"], dtype=np.float64)
    gate_scores = np.asarray(values["gate_scores"], dtype=np.float32)
    node_count = len(tracklet_keys)
    edge_count = edge_features.shape[0] if edge_features.ndim == 2 else -1
    if node_features.shape != (node_count, len(NODE_FEATURE_NAMES)):
        raise TrackletDatasetValidationError("node_shape_mismatch", "node feature shape is invalid")
    if edge_index.shape != (2, edge_count):
        raise TrackletDatasetValidationError("edge_index_shape_mismatch", "edge index shape is invalid")
    if edge_features.shape != (edge_count, len(EDGE_FEATURE_NAMES)):
        raise TrackletDatasetValidationError("edge_shape_mismatch", "edge feature shape is invalid")
    if len(camera_keys) != node_count or measurement_timestamps.shape != (node_count,):
        raise TrackletDatasetValidationError("node_metadata_shape_mismatch", "node metadata shape is invalid")
    if arrival_timestamps.shape != (node_count,) or gate_scores.shape != (edge_count,):
        raise TrackletDatasetValidationError("graph_metadata_shape_mismatch", "graph metadata shape is invalid")
    numeric_arrays = (node_features, edge_features, measurement_timestamps, arrival_timestamps, gate_scores)
    if any(not np.all(np.isfinite(array)) for array in numeric_arrays):
        raise TrackletDatasetValidationError("graph_non_finite", "graph contains non-finite numeric values")
    if len(tracklet_keys) != len(set(tracklet_keys)) or any(not value for value in tracklet_keys):
        raise TrackletDatasetValidationError("tracklet_key_invalid", "tracklet keys must be unique and non-empty")
    if any(not value for value in camera_keys):
        raise TrackletDatasetValidationError("camera_key_invalid", "camera keys must be non-empty")
    if np.any(arrival_timestamps + 1.0e-12 < measurement_timestamps):
        raise TrackletDatasetValidationError("timestamp_order_invalid", "arrival timestamp precedes measurement")
    if edge_index.size:
        if edge_index.min() < 0 or edge_index.max() >= node_count:
            raise TrackletDatasetValidationError("edge_index_invalid", "edge references an unknown node")
        if np.any(edge_index[0] >= edge_index[1]):
            raise TrackletDatasetValidationError("edge_index_noncanonical", "edges must be canonical pairs")
        pairs = tuple((int(left), int(right)) for left, right in edge_index.T)
        if len(pairs) != len(set(pairs)):
            raise TrackletDatasetValidationError("edge_duplicate", "candidate edges must be unique")
    count_names = tuple(str(value) for value in values["candidate_count_names"].tolist())
    count_values = np.asarray(values["candidate_count_values"], dtype=np.int64)
    if count_values.shape != (len(count_names),) or len(count_names) != len(set(count_names)):
        raise TrackletDatasetValidationError("candidate_counts_invalid", "candidate counts are malformed")
    if np.any(count_values < 0):
        raise TrackletDatasetValidationError("candidate_counts_negative", "candidate counts must be non-negative")
    _expect_equal(node_count, int(descriptor["node_count"]), "node_count_mismatch")
    _expect_equal(edge_count, int(descriptor["edge_count"]), "edge_count_mismatch")
    return LoadedTrackletGraph(
        episode_uid=episode_uid,
        scenario_version=scenario_version,
        seed=seed,
        episode_id=episode_id,
        node_features=node_features,
        edge_index=edge_index,
        edge_features=edge_features,
        tracklet_keys=tracklet_keys,
        camera_keys=camera_keys,
        measurement_timestamps=measurement_timestamps,
        arrival_timestamps=arrival_timestamps,
        gate_scores=gate_scores,
        candidate_counts=dict(zip(count_names, count_values.tolist(), strict=True)),
    )


def _load_label_file(
    path: Path,
    graph: LoadedTrackletGraph,
    descriptor: Mapping[str, Any],
) -> LoadedEvaluatorLabels:
    payload = _read_json(path)
    expected_keys = {
        "schema_version",
        "episode_uid",
        "scenario_version",
        "seed",
        "episode_id",
        "labels_complete",
        "candidate_recall_available",
        "labels",
    }
    if set(payload) != expected_keys:
        raise TrackletDatasetValidationError("label_fields_mismatch", "label artifact fields are invalid")
    _expect_equal(payload["schema_version"], EVALUATOR_LABEL_SCHEMA_VERSION, "label_schema_mismatch")
    _expect_equal(payload["episode_uid"], graph.episode_uid, "label_episode_mismatch")
    _expect_equal(payload["scenario_version"], graph.scenario_version, "label_episode_mismatch")
    _expect_equal(int(payload["seed"]), graph.seed, "label_episode_mismatch")
    _expect_equal(payload["episode_id"], graph.episode_id, "label_episode_mismatch")
    raw_labels = payload["labels"]
    if not isinstance(raw_labels, list):
        raise TrackletDatasetValidationError("labels_invalid", "labels must be a list")
    labels: list[OfflineTrackletTruthLabel] = []
    node_time = dict(zip(graph.tracklet_keys, graph.measurement_timestamps.tolist(), strict=True))
    seen: set[str] = set()
    for item in raw_labels:
        if not isinstance(item, Mapping) or set(item) != {
            "tracklet_key",
            "measurement_timestamp",
            "truth_entity_id",
        }:
            raise TrackletDatasetValidationError("label_record_invalid", "label record fields are invalid")
        try:
            label = OfflineTrackletTruthLabel(
                tracklet_key=str(item["tracklet_key"]),
                truth_entity_id=str(item["truth_entity_id"]),
                measurement_timestamp=float(item["measurement_timestamp"]),
            )
        except (TypeError, ValueError) as exc:
            raise TrackletDatasetValidationError("label_record_invalid", "label record is invalid") from exc
        if label.tracklet_key in seen:
            raise TrackletDatasetValidationError("label_duplicate", "duplicate evaluator label")
        seen.add(label.tracklet_key)
        expected_time = node_time.get(label.tracklet_key)
        if expected_time is None:
            raise TrackletDatasetValidationError("label_unknown_tracklet", "label references unknown tracklet")
        if abs(expected_time - label.measurement_timestamp) > 1.0e-6:
            raise TrackletDatasetValidationError("label_timestamp_mismatch", "label timestamp does not align")
        labels.append(label)
    labels_complete = bool(payload["labels_complete"])
    recall_available = bool(payload["candidate_recall_available"])
    if labels_complete and seen != set(graph.tracklet_keys):
        raise TrackletDatasetValidationError("labels_incomplete", "complete label file omits graph nodes")
    if recall_available and not labels_complete:
        raise TrackletDatasetValidationError(
            "candidate_recall_without_truth",
            "candidate recall cannot be available without complete labels",
        )
    _expect_equal(labels_complete, bool(descriptor["labels_complete"]), "label_completeness_mismatch")
    _expect_equal(
        recall_available,
        bool(descriptor["candidate_recall_available"]),
        "candidate_recall_availability_mismatch",
    )
    return LoadedEvaluatorLabels(
        episode_uid=graph.episode_uid,
        labels=tuple(labels),
        labels_complete=labels_complete,
        candidate_recall_available=recall_available,
    )


def _validated_label_map(
    graph: SparseTrackletGraph,
    labels: Sequence[OfflineTrackletTruthLabel],
) -> Mapping[str, OfflineTrackletTruthLabel]:
    node_time = {node.tracklet_key: node.measurement_timestamp for node in graph.nodes}
    result: dict[str, OfflineTrackletTruthLabel] = {}
    for label in labels:
        if not isinstance(label, OfflineTrackletTruthLabel):
            raise TypeError("evaluator_labels must contain OfflineTrackletTruthLabel")
        if label.tracklet_key in result:
            raise ValueError(f"duplicate evaluator label for {label.tracklet_key}")
        expected_time = node_time.get(label.tracklet_key)
        if expected_time is None:
            raise ValueError(f"evaluator label references unknown tracklet {label.tracklet_key}")
        if abs(expected_time - label.measurement_timestamp) > 1.0e-6:
            raise ValueError(f"evaluator label timestamp does not align with {label.tracklet_key}")
        result[label.tracklet_key] = label
    return MappingProxyType(result)


def _class_balance_from_arrays(
    edge_index: np.ndarray,
    tracklet_keys: Sequence[str],
    labels: Mapping[str, OfflineTrackletTruthLabel],
) -> dict[str, int]:
    positive = 0
    negative = 0
    unlabeled = 0
    for source, target in np.asarray(edge_index, dtype=np.int64).T:
        left = labels.get(tracklet_keys[int(source)])
        right = labels.get(tracklet_keys[int(target)])
        if left is None or right is None:
            unlabeled += 1
        elif left.truth_entity_id == right.truth_entity_id:
            positive += 1
        else:
            negative += 1
    return {
        "positive_candidate_edges": positive,
        "negative_candidate_edges": negative,
        "unlabeled_candidate_edges": unlabeled,
        "candidate_edges": positive + negative + unlabeled,
    }


def _sum_class_balance(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    totals = {
        "positive_candidate_edges": 0,
        "negative_candidate_edges": 0,
        "unlabeled_candidate_edges": 0,
        "candidate_edges": 0,
    }
    for item in items:
        for key in totals:
            totals[key] += int(item["class_balance"][key])
    return totals


def _split_payload(episodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "episode_uid": str(item["episode_uid"]),
            "scenario_version": str(item["scenario_version"]),
            "seed": int(item["seed"]),
            "episode_id": str(item["episode_id"]),
            "split": str(item["split"]),
        }
        for item in sorted(episodes, key=lambda value: value["episode_uid"])
    ]


def _training_set_sha256(episodes: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "episode_uid": item["episode_uid"],
            "graph_sha256": item["graph_sha256"],
            "labels_sha256": item["labels_sha256"],
        }
        for item in sorted(episodes, key=lambda value: value["episode_uid"])
        if item.get("split") == "train"
    ]
    return sha256_json(payload)


def _episode_uid(scenario_version: str, seed: int, episode_id: str) -> str:
    raw = f"{scenario_version}\0{seed}\0{episode_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _ensure_generation_config(root: Path, config: Mapping[str, Any]) -> str:
    payload = _json_object(config, "generation_config")
    path = root / "dataset_config.json"
    encoded = _canonical_json_bytes(payload)
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("all staged episodes must use the same generation_config")
    else:
        _write_bytes_atomic(path, encoded)
    return sha256_file(path)


def _validate_descriptor_shape(descriptor: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "episode_uid",
        "scenario_version",
        "seed",
        "episode_id",
        "graph_file",
        "graph_sha256",
        "labels_file",
        "labels_sha256",
        "config_sha256",
        "node_count",
        "edge_count",
        "class_balance",
        "labels_complete",
        "candidate_recall_available",
        "hard_negative_provenance",
    }
    if not required.issubset(descriptor):
        missing = sorted(required - set(descriptor))
        raise TrackletDatasetValidationError("descriptor_fields_missing", f"missing fields: {missing}")
    _expect_equal(
        descriptor.get("schema_version"),
        EPISODE_DESCRIPTOR_SCHEMA_VERSION,
        "descriptor_schema_mismatch",
    )


def _safe_relative_path(root: Path, raw_relative: Any) -> Path:
    relative = Path(_non_empty_text(raw_relative, "relative path"))
    if relative.is_absolute():
        raise TrackletDatasetValidationError("path_invalid", "dataset artifact path must be relative")
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise TrackletDatasetValidationError("path_escape", "dataset artifact escapes dataset root")
    if not path.is_file():
        raise TrackletDatasetValidationError("artifact_missing", f"dataset artifact is missing: {relative}")
    return path


def _expect_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        raise TrackletDatasetValidationError(code, f"expected {expected!r}, received {actual!r}")


def _scalar_text(value: np.ndarray) -> str:
    array = np.asarray(value)
    if array.shape != ():
        raise TrackletDatasetValidationError("scalar_invalid", "expected a scalar string")
    return str(array.item())


def _non_empty_text(value: Any, name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{name} must be non-empty")
    return text


def _json_object(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    try:
        decoded = json.loads(_canonical_json_bytes(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite JSON data") from exc
    if not isinstance(decoded, dict):
        raise TypeError(f"{name} must encode a JSON object")
    return decoded


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


def _write_npz_atomic(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as handle:
            np.savez_compressed(handle, **arrays)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(value))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
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
        raise TrackletDatasetValidationError("json_invalid", f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise TrackletDatasetValidationError("json_object_required", f"{path.name} must contain an object")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


def _offline_field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    elif hasattr(value, name):
        return getattr(value, name)
    raise ValueError(f"offline observation label is missing {name}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finalize or validate a D5 tracklet graph dataset")
    subparsers = parser.add_subparsers(dest="command", required=True)
    finalize = subparsers.add_parser("finalize", help="split staged whole episodes and write manifest")
    finalize.add_argument("--dataset-dir", required=True)
    finalize.add_argument("--split-seed", type=int, default=20260720)
    finalize.add_argument("--validation-fraction", type=float, default=0.2)
    finalize.add_argument("--test-fraction", type=float, default=0.2)
    validate = subparsers.add_parser("validate", help="fail closed on any contract mismatch")
    validate.add_argument("--dataset-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "finalize":
        manifest = finalize_tracklet_dataset(
            args.dataset_dir,
            split_seed=args.split_seed,
            validation_fraction=args.validation_fraction,
            test_fraction=args.test_fraction,
        )
        print(json.dumps({"episode_count": len(manifest["episodes"]), "status": "finalized"}))
        return 0
    dataset = load_tracklet_dataset(args.dataset_dir)
    print(
        json.dumps(
            {
                "episode_count": len(dataset.episodes),
                "manifest_sha256": dataset.manifest_sha256,
                "status": "valid",
            }
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = [
    "DATASET_SCHEMA_VERSION",
    "EDGE_FEATURE_VERSION",
    "EPISODE_DESCRIPTOR_SCHEMA_VERSION",
    "EVALUATOR_LABEL_SCHEMA_VERSION",
    "GRAPH_SCHEMA_VERSION",
    "LoadedEvaluatorLabels",
    "LoadedTrackletDataset",
    "LoadedTrackletEpisode",
    "LoadedTrackletGraph",
    "NODE_FEATURE_VERSION",
    "OfflineObservationLabelJoinResult",
    "TrackletDatasetValidationError",
    "edge_targets",
    "finalize_tracklet_dataset",
    "load_tracklet_dataset",
    "join_offline_observation_labels",
    "sha256_file",
    "sha256_json",
    "split_episode_groups",
    "stage_tracklet_dataset_episode",
]
