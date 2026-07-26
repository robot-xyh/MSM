"""Independent reserved-seed production and evaluation for D5 tracklet graphs.

The held-out corpus is deliberately outside the formal and supplemental
training contracts.  Online graph artifacts contain anonymous camera-local
tracklets only; evaluator identity is stored in separate label and lineage
artifacts.  A development model bundle is evaluated with its frozen validation
temperature and decision threshold.  No held-out result can grant G1, assist,
or control authority.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import uuid

import numpy as np
import torch

from .sparse_tracklet_graph import SparseTrackletGraphConfig
from .tracklet_dataset import (
    LoadedEvaluatorLabels,
    LoadedTrackletGraph,
    TrackletDatasetValidationError,
    _class_balance_from_arrays,
    _load_graph_archive,
    _load_label_file,
    edge_targets,
    join_offline_observation_labels,
    sha256_file,
    stage_tracklet_dataset_episode,
)
from .tracklet_model_bundle import (
    MANIFEST_FILENAME,
    WEIGHTS_FILENAME,
    load_tracklet_model_bundle,
)
from .tracklet_supplemental_curriculum import (
    CAMERA_LOCAL_ANGULAR_RATE_SIGMA_RAD_S,
    CAMERA_LOCAL_BBOX_LOG_SIDE_SIGMA,
    CAMERA_LOCAL_MEASUREMENT_MODEL_VERSION,
    CAMERA_LOCAL_SCALE_RATE_SIGMA_S,
    FORMAL_SCENARIO_CELLS,
    _build_curriculum_frame,
    _clutter_truth_id_from_record,
    _edge_balance,
    _truth_entity_id,
)
from .tracklet_training import _edge_and_cluster_metrics
from .tracklet_training_audit import TrackletReadinessCriteria


HELDOUT_ROLE = "held_out_evaluation"
HELDOUT_RESERVED_SEEDS = tuple(range(1000, 1020))
HELDOUT_EXPECTED_FRAME_COUNT = len(HELDOUT_RESERVED_SEEDS) * len(
    FORMAL_SCENARIO_CELLS
)
HELDOUT_CORPUS_SCHEMA_VERSION = "d5.tracklet-heldout-corpus.v1"
HELDOUT_EPISODE_SCHEMA_VERSION = "d5.tracklet-heldout-episode.v1"
HELDOUT_LINEAGE_SCHEMA_VERSION = "d5.tracklet-heldout-lineage.v1"
HELDOUT_EVALUATION_SCHEMA_VERSION = "d5.tracklet-heldout-model-evaluation.v1"
HELDOUT_FULL_PROFILE_VERSION = "d5-tracklet-heldout-1000-1019-full-v1"
HELDOUT_SMOKE_PROFILE_VERSION = "d5-tracklet-heldout-reserved-smoke-v1"
HELDOUT_CONFIG_FILENAME = "heldout_config.json"
HELDOUT_MANIFEST_FILENAME = "heldout_manifest.json"
HELDOUT_EVALUATION_FILENAME = "heldout_evaluation.json"
HELDOUT_REPORT_FILENAME = "HELDOUT_EVALUATION_REPORT_CN.md"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SCENARIO_VERSION_BY_CELL = MappingProxyType(
    {
        (scenario, scale): f"{scenario}-{scale}v{scale}-v1"
        for scenario, scale in FORMAL_SCENARIO_CELLS
    }
)
_IMPLEMENTATION_FILES = (
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
    "tracklet_supplemental_curriculum.py",
    "tracklet_heldout_evaluation.py",
)
_BASE_DESCRIPTOR_FIELDS = frozenset(
    {
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
)
_HELDOUT_DESCRIPTOR_FIELDS = _BASE_DESCRIPTOR_FIELDS | {
    "schema_version",
    "evaluation_role",
    "split",
    "scenario",
    "scale",
}


class TrackletHeldoutEvaluationError(ValueError):
    """Stable fail-closed producer, loader, or evaluator error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class HeldoutGenerationConfig:
    """Frozen full profile plus an explicit test-only reserved-seed subset."""

    profile_version: str = HELDOUT_FULL_PROFILE_VERSION
    seeds: tuple[int, ...] = HELDOUT_RESERVED_SEEDS
    scenario_cells: tuple[tuple[str, int], ...] = FORMAL_SCENARIO_CELLS
    frames_per_seed_cell: int = 1

    def __post_init__(self) -> None:
        seeds = tuple(int(seed) for seed in self.seeds)
        cells = tuple((str(scenario), int(scale)) for scenario, scale in self.scenario_cells)
        object.__setattr__(self, "seeds", seeds)
        object.__setattr__(self, "scenario_cells", cells)
        if self.frames_per_seed_cell != 1:
            _fail("frame_profile_changed", "held-out profile requires one graph per seed/cell")
        if not seeds or len(seeds) != len(set(seeds)) or tuple(sorted(seeds)) != seeds:
            _fail("heldout_seed_catalog_invalid", "held-out seeds must be unique and sorted")
        if any(seed not in HELDOUT_RESERVED_SEEDS for seed in seeds):
            _fail("training_seed_leakage", f"non-reserved seed entered held-out profile: {seeds}")
        if not cells or len(cells) != len(set(cells)):
            _fail("scenario_cell_catalog_invalid", "scenario cells must be unique and non-empty")
        if any(cell not in FORMAL_SCENARIO_CELLS for cell in cells):
            _fail("scenario_cell_catalog_invalid", "held-out cells must use the frozen catalog")
        if self.profile_version == HELDOUT_FULL_PROFILE_VERSION:
            if seeds != HELDOUT_RESERVED_SEEDS:
                _fail("heldout_seed_catalog_mismatch", "full profile requires seeds 1000-1019")
            if cells != FORMAL_SCENARIO_CELLS:
                _fail("scenario_cell_catalog_mismatch", "full profile requires all 45 cells")
        elif self.profile_version != HELDOUT_SMOKE_PROFILE_VERSION:
            _fail("heldout_profile_mismatch", "unknown held-out profile")

    def to_payload(self) -> dict[str, Any]:
        return {
            "profile_version": self.profile_version,
            "evaluation_role": HELDOUT_ROLE,
            "seeds": list(self.seeds),
            "scenario_cells": [
                {"scenario": scenario, "scale": scale}
                for scenario, scale in self.scenario_cells
            ],
            "frames_per_seed_cell": self.frames_per_seed_cell,
            "expected_frame_count": len(self.seeds) * len(self.scenario_cells),
            "training_split_registry_used": False,
        }


@dataclass(frozen=True)
class HeldoutEvaluationPolicy:
    """Evaluation controls; calibration and model updates are forbidden."""

    device: str = "cpu"
    ece_bins: int = 10
    latency_repeats: int = 3
    temperature_override: float | None = None
    decision_threshold_override: float | None = None
    update_weights: bool = False

    def __post_init__(self) -> None:
        torch.device(self.device)
        if self.ece_bins <= 0 or self.latency_repeats <= 0:
            _fail("evaluation_config_invalid", "ECE bins and latency repeats must be positive")
        if self.temperature_override is not None:
            _fail("heldout_temperature_selection_forbidden", "held-out data cannot tune temperature")
        if self.decision_threshold_override is not None:
            _fail("heldout_threshold_selection_forbidden", "held-out data cannot select a threshold")
        if self.update_weights:
            _fail("heldout_weight_update_forbidden", "held-out data cannot update model weights")


@dataclass(frozen=True)
class LoadedHeldoutEpisode:
    graph: LoadedTrackletGraph
    evaluator_labels: LoadedEvaluatorLabels
    evaluation_role: str
    graph_sha256: str
    labels_sha256: str
    class_balance: Mapping[str, int]
    hard_negative_provenance: Mapping[str, Any]
    scenario: str
    scale: int

    def __post_init__(self) -> None:
        if self.evaluation_role != HELDOUT_ROLE:
            _fail("heldout_role_mismatch", self.evaluation_role)
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
class LoadedHeldoutCorpus:
    root: Path
    manifest: Mapping[str, Any]
    manifest_sha256: str
    config: Mapping[str, Any]
    episodes: tuple[LoadedHeldoutEpisode, ...]


def generate_tracklet_heldout_corpus(
    output_dir: str | Path,
    *,
    formal_dataset_dir: str | Path,
    supplemental_root: str | Path,
    created_at_utc: str,
    source_git_commit: str,
    source_repository_dirty: bool,
    config: HeldoutGenerationConfig | None = None,
) -> LoadedHeldoutCorpus:
    """Generate reserved graphs in a new directory and publish atomically."""

    cfg = config or HeldoutGenerationConfig()
    destination = Path(output_dir).resolve()
    formal_root = Path(formal_dataset_dir).resolve()
    supplemental_dir = Path(supplemental_root).resolve()
    _validate_destination(destination, (formal_root, supplemental_dir))
    if destination.exists():
        _fail("destination_exists", str(destination))
    timestamp = str(created_at_utc).strip()
    if not timestamp:
        _fail("created_at_missing", "created_at_utc must be non-empty")
    commit = _validate_commit(source_git_commit)
    if type(source_repository_dirty) is not bool:
        _fail("dirty_flag_invalid", "source_repository_dirty must be boolean")
    source_binding = _training_source_binding(formal_root, supplemental_dir)
    source_before = _source_hash_snapshot(formal_root, supplemental_dir)

    temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        dataset_root = temporary / "heldout_dataset"
        evaluator_root = temporary / "evaluator"
        evaluator_root.mkdir()
        gate_config = SparseTrackletGraphConfig()
        gate_payload = asdict(gate_config)
        gate_sha256 = _sha256_json(gate_payload)
        generation_config = {
            "schema_version": HELDOUT_CORPUS_SCHEMA_VERSION,
            "evaluation_role": HELDOUT_ROLE,
            "profile": cfg.to_payload(),
            "created_at_utc": timestamp,
            "source_git_commit": commit,
            "source_repository_dirty": source_repository_dirty,
            "candidate_gate_config": gate_payload,
            "candidate_gate_config_sha256": gate_sha256,
            "camera_local_measurement_model": {
                "version": CAMERA_LOCAL_MEASUREMENT_MODEL_VERSION,
                "bbox_log_side_sigma": CAMERA_LOCAL_BBOX_LOG_SIDE_SIGMA,
                "bbox_scale_rate_sigma_s": CAMERA_LOCAL_SCALE_RATE_SIGMA_S,
                "angular_rate_sigma_rad_s": (
                    CAMERA_LOCAL_ANGULAR_RATE_SIGMA_RAD_S
                ),
                "truth_or_edge_label_accessed": False,
            },
            "online_truth_policy": "forbidden",
            "evaluator_truth_policy": "physically_separate_exact_observation_lineage",
            "training_use_forbidden": True,
            "threshold_selection_forbidden": True,
            "weight_update_forbidden": True,
        }
        lineage_records: list[dict[str, Any]] = []
        descriptors: list[dict[str, Any]] = []
        class_counts: Counter[str] = Counter()
        gate_counts: Counter[str] = Counter()
        factor_counts: Counter[str] = Counter()

        for seed in cfg.seeds:
            for scenario, scale in cfg.scenario_cells:
                graph, offline, lineage, factors = _build_curriculum_frame(
                    seed,
                    scenario=scenario,
                    scale=scale,
                    frame_index=0,
                    gate_config=gate_config,
                )
                joined = join_offline_observation_labels(graph, offline)
                if not joined.labels_complete or joined.unmatched_observation_ids:
                    _fail("heldout_truth_join_incomplete", f"{seed}:{scenario}:{scale}")
                positive, negative, unlabeled = _edge_balance(graph, joined.tracklet_labels)
                if positive <= 0 or negative <= 0 or unlabeled:
                    _fail(
                        "heldout_dual_class_failure",
                        f"{seed}:{scenario}:{scale}:positive={positive};negative={negative};unlabeled={unlabeled}",
                    )
                scenario_version = _SCENARIO_VERSION_BY_CELL[(scenario, scale)]
                episode_id = f"d5-heldout-{scenario}-{scale}v{scale}-s{seed:04d}-frame-000000"
                raw = stage_tracklet_dataset_episode(
                    dataset_root,
                    graph,
                    joined.tracklet_labels,
                    scenario_version=scenario_version,
                    seed=seed,
                    episode_id=episode_id,
                    generation_config=generation_config,
                    labels_complete=True,
                    candidate_recall_available=True,
                    hard_negative_provenance={
                        "source": "heldout_physical_projection_after_default_geometry_gates",
                        "truth_use": "offline_exact_observation_lineage_only",
                        "candidate_gate_config_sha256": gate_sha256,
                        "evaluation_role": HELDOUT_ROLE,
                    },
                )
                descriptor = dict(raw)
                descriptor.update(
                    {
                        "schema_version": HELDOUT_EPISODE_SCHEMA_VERSION,
                        "evaluation_role": HELDOUT_ROLE,
                        "split": HELDOUT_ROLE,
                        "scenario": scenario,
                        "scale": scale,
                    }
                )
                descriptor_path = dataset_root / "episodes" / f"{descriptor['episode_uid']}.episode.json"
                _write_json_atomic(descriptor_path, descriptor)
                descriptors.append(descriptor)
                for record in lineage:
                    item = dict(record)
                    item.update(
                        {
                            "episode_uid": descriptor["episode_uid"],
                            "scenario_version": scenario_version,
                            "seed": seed,
                            "evaluation_role": HELDOUT_ROLE,
                        }
                    )
                    lineage_records.append(item)
                class_counts.update(descriptor["class_balance"])
                gate_counts.update(graph.candidate_counts)
                factor_counts.update(factors)

        staged_config = dataset_root / "dataset_config.json"
        heldout_config = dataset_root / HELDOUT_CONFIG_FILENAME
        if not staged_config.is_file() or heldout_config.exists():
            _fail("heldout_config_staging_failed", str(dataset_root))
        os.replace(staged_config, heldout_config)
        lineage_path = evaluator_root / "observation_lineage.json.gz"
        _write_lineage(
            lineage_path,
            lineage_records,
            candidate_gate_config_sha256=gate_sha256,
        )
        source_after = _source_hash_snapshot(formal_root, supplemental_dir)
        if source_after != source_before:
            _fail("training_source_changed_during_generation", str(source_after))

        artifacts = _artifact_inventory(temporary)
        manifest = _build_manifest(
            descriptors=descriptors,
            artifacts=artifacts,
            config=cfg,
            generation_config=generation_config,
            source_binding=source_binding,
            source_git_commit=commit,
            source_repository_dirty=source_repository_dirty,
            created_at_utc=timestamp,
            lineage_path=lineage_path.relative_to(temporary),
            lineage_record_count=len(lineage_records),
            class_counts=class_counts,
            gate_counts=gate_counts,
            factor_counts=factor_counts,
        )
        _write_json_atomic(temporary / HELDOUT_MANIFEST_FILENAME, manifest)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return load_tracklet_heldout_corpus(
        destination,
        require_full_profile=cfg.profile_version == HELDOUT_FULL_PROFILE_VERSION,
    )


def load_tracklet_heldout_corpus(
    corpus_dir: str | Path,
    *,
    require_full_profile: bool = True,
) -> LoadedHeldoutCorpus:
    """Strictly verify the held-out catalog, artifacts, labels, and lineage."""

    root = Path(corpus_dir).resolve()
    manifest_path = root / HELDOUT_MANIFEST_FILENAME
    manifest = _read_json(manifest_path)
    _verify_content_hash(manifest, "heldout_manifest_content_hash_mismatch")
    if manifest.get("schema_version") != HELDOUT_CORPUS_SCHEMA_VERSION:
        _fail("heldout_manifest_schema_mismatch", str(manifest.get("schema_version")))
    if manifest.get("evaluation_role") != HELDOUT_ROLE:
        _fail("heldout_role_mismatch", str(manifest.get("evaluation_role")))

    profile = _profile_from_payload(manifest.get("profile"), require_full_profile)
    if manifest.get("training_split_registry_used") is not False:
        _fail("training_split_registry_forbidden", "held-out corpus used a training split registry")
    candidate_gate = manifest.get("candidate_gate")
    default_gate = asdict(SparseTrackletGraphConfig())
    if not isinstance(candidate_gate, Mapping):
        _fail("candidate_gate_missing", "held-out candidate gate is missing")
    if candidate_gate.get("config") != default_gate:
        _fail("candidate_gate_lowered_or_changed", "held-out corpus changed default geometry gates")
    if candidate_gate.get("config_sha256") != _sha256_json(default_gate):
        _fail("candidate_gate_hash_mismatch", "held-out candidate gate hash changed")

    inventory = manifest.get("artifact_inventory")
    _validate_inventory(root, inventory)
    config_meta = manifest.get("config")
    if not isinstance(config_meta, Mapping):
        _fail("heldout_config_missing", "held-out config metadata is missing")
    config_path = _safe_artifact(root, config_meta.get("file"))
    if sha256_file(config_path) != config_meta.get("sha256"):
        _fail("heldout_config_hash_mismatch", str(config_path))
    config = _read_json(config_path)
    if config.get("evaluation_role") != HELDOUT_ROLE:
        _fail("heldout_config_role_mismatch", str(config_path))
    if config.get("profile") != profile.to_payload():
        _fail("heldout_config_profile_mismatch", str(config_path))
    if config.get("candidate_gate_config") != default_gate:
        _fail("candidate_gate_lowered_or_changed", str(config_path))
    if config.get("candidate_gate_config_sha256") != _sha256_json(default_gate):
        _fail("candidate_gate_hash_mismatch", str(config_path))
    for policy_name in (
        "training_use_forbidden",
        "threshold_selection_forbidden",
        "weight_update_forbidden",
    ):
        if config.get(policy_name) is not True:
            _fail("heldout_policy_mismatch", policy_name)

    raw_descriptors = manifest.get("episodes")
    expected_count = len(profile.seeds) * len(profile.scenario_cells)
    if not isinstance(raw_descriptors, list) or len(raw_descriptors) != expected_count:
        _fail("heldout_episode_count_mismatch", f"actual={len(raw_descriptors or [])};expected={expected_count}")
    dataset_root = root / "heldout_dataset"
    loaded: list[LoadedHeldoutEpisode] = []
    seen_uids: set[str] = set()
    seen_seed_cells: set[tuple[int, str, int]] = set()
    graph_hashes: set[str] = set()
    for raw in raw_descriptors:
        if not isinstance(raw, Mapping):
            _fail("heldout_descriptor_invalid", "episode descriptor is not an object")
        descriptor = dict(raw)
        _validate_heldout_descriptor(descriptor, profile)
        uid = str(descriptor["episode_uid"])
        if uid in seen_uids:
            _fail("heldout_episode_duplicate", uid)
        seen_uids.add(uid)
        key = (int(descriptor["seed"]), str(descriptor["scenario"]), int(descriptor["scale"]))
        if key in seen_seed_cells:
            _fail("heldout_seed_cell_duplicate", str(key))
        seen_seed_cells.add(key)
        descriptor_path = _safe_artifact(dataset_root, f"episodes/{uid}.episode.json")
        if _read_json(descriptor_path) != descriptor:
            _fail("heldout_descriptor_manifest_mismatch", uid)
        if descriptor["config_sha256"] != config_meta["sha256"]:
            _fail("heldout_episode_config_hash_mismatch", uid)
        graph_path = _safe_artifact(dataset_root, descriptor["graph_file"])
        labels_path = _safe_artifact(dataset_root, descriptor["labels_file"])
        if sha256_file(graph_path) != descriptor["graph_sha256"]:
            _fail("heldout_graph_hash_mismatch", uid)
        if sha256_file(labels_path) != descriptor["labels_sha256"]:
            _fail("heldout_labels_hash_mismatch", uid)
        try:
            graph = _load_graph_archive(graph_path, descriptor)
            labels = _load_label_file(labels_path, graph, descriptor)
        except TrackletDatasetValidationError as exc:
            _fail("heldout_artifact_validation_failed", f"{exc.code}:{uid}")
        class_balance = _class_balance_from_arrays(
            graph.edge_index,
            graph.tracklet_keys,
            labels.by_tracklet_key,
        )
        if class_balance != descriptor["class_balance"]:
            _fail("heldout_class_balance_mismatch", uid)
        if not labels.labels_complete or not labels.candidate_recall_available:
            _fail("heldout_labels_incomplete", uid)
        if class_balance.get("unlabeled_candidate_edges") != 0:
            _fail("heldout_unlabeled_candidate_edge", uid)
        if class_balance.get("positive_candidate_edges", 0) <= 0 or class_balance.get(
            "negative_candidate_edges", 0
        ) <= 0:
            _fail("heldout_dual_class_failure", uid)
        for source, target in graph.edge_index.T:
            if graph.camera_keys[int(source)] == graph.camera_keys[int(target)]:
                _fail("heldout_same_camera_candidate_edge", uid)
        if descriptor["graph_sha256"] in graph_hashes:
            _fail("heldout_graph_duplicate", descriptor["graph_sha256"])
        graph_hashes.add(str(descriptor["graph_sha256"]))
        loaded.append(
            LoadedHeldoutEpisode(
                graph=graph,
                evaluator_labels=labels,
                evaluation_role=HELDOUT_ROLE,
                graph_sha256=str(descriptor["graph_sha256"]),
                labels_sha256=str(descriptor["labels_sha256"]),
                class_balance=class_balance,
                hard_negative_provenance=dict(descriptor["hard_negative_provenance"]),
                scenario=str(descriptor["scenario"]),
                scale=int(descriptor["scale"]),
            )
        )

    expected_seed_cells = {
        (seed, scenario, scale)
        for seed in profile.seeds
        for scenario, scale in profile.scenario_cells
    }
    if seen_seed_cells != expected_seed_cells:
        _fail(
            "heldout_seed_cell_catalog_mismatch",
            f"missing={sorted(expected_seed_cells-seen_seed_cells)};extra={sorted(seen_seed_cells-expected_seed_cells)}",
        )
    if set(seed for seed, _, _ in seen_seed_cells) & set(range(100)):
        _fail("training_seed_leakage", "training seed entered held-out corpus")

    lineage_meta = manifest.get("evaluator_lineage")
    if not isinstance(lineage_meta, Mapping):
        _fail("heldout_lineage_missing", "lineage metadata is missing")
    lineage_path = _safe_artifact(root, lineage_meta.get("file"))
    if sha256_file(lineage_path) != lineage_meta.get("sha256"):
        _fail("heldout_lineage_hash_mismatch", str(lineage_path))
    lineage = _load_lineage(lineage_path)
    if lineage.get("candidate_gate_config_sha256") != candidate_gate["config_sha256"]:
        _fail("heldout_lineage_gate_hash_mismatch", str(lineage_path))

    corpus = LoadedHeldoutCorpus(
        root=root,
        manifest=MappingProxyType(dict(manifest)),
        manifest_sha256=sha256_file(manifest_path),
        config=MappingProxyType(dict(config)),
        episodes=tuple(sorted(loaded, key=lambda item: item.graph.episode_uid)),
    )
    _validate_lineage(corpus, lineage)
    _validate_manifest_counts(corpus)
    return corpus


def evaluate_heldout_development_bundle(
    heldout_corpus_dir: str | Path,
    development_bundle_dir: str | Path,
    output_dir: str | Path,
    *,
    evaluated_at_utc: str,
    policy: HeldoutEvaluationPolicy | None = None,
    require_full_profile: bool = True,
) -> Mapping[str, Any]:
    """Evaluate without calibration, threshold selection, or weight updates."""

    cfg = policy or HeldoutEvaluationPolicy()
    timestamp = str(evaluated_at_utc).strip()
    if not timestamp:
        _fail("evaluated_at_missing", "evaluated_at_utc must be non-empty")
    corpus_root = Path(heldout_corpus_dir).resolve()
    bundle_root = Path(development_bundle_dir).resolve()
    destination = Path(output_dir).resolve()
    _validate_destination(destination, (corpus_root, bundle_root))
    if destination.exists():
        _fail("evaluation_destination_exists", str(destination))
    corpus = load_tracklet_heldout_corpus(
        corpus_root,
        require_full_profile=require_full_profile,
    )
    corpus_manifest_before = sha256_file(corpus_root / HELDOUT_MANIFEST_FILENAME)
    bundle_manifest_path = bundle_root / MANIFEST_FILENAME
    weights_path = bundle_root / WEIGHTS_FILENAME
    bundle_manifest_before = sha256_file(bundle_manifest_path)
    weights_before = sha256_file(weights_path)
    scorer = load_tracklet_model_bundle(bundle_root, device=cfg.device)
    admission = scorer.manifest["admission"]
    if admission.get("status") != "development_only_fail_closed":
        _fail("development_bundle_required", str(admission.get("status")))
    if admission.get("default_model") is not False or admission.get("g1_assist_eligible") is not False:
        _fail("development_bundle_authority_invalid", str(admission))

    probabilities_by_episode, latency_by_episode = _run_frozen_inference(
        corpus.episodes,
        scorer.model,
        temperature=scorer.temperature,
        device=scorer.device,
        latency_repeats=cfg.latency_repeats,
    )
    overall = _evaluate_episode_group(
        corpus.episodes,
        probabilities_by_episode,
        latency_by_episode,
        threshold=scorer.decision_threshold,
        temperature=scorer.temperature,
        ece_bins=cfg.ece_bins,
        device=str(scorer.device),
    )
    by_cell: dict[tuple[str, int], list[LoadedHeldoutEpisode]] = {}
    for episode in corpus.episodes:
        by_cell.setdefault((episode.scenario, episode.scale), []).append(episode)
    cell_metrics: list[dict[str, Any]] = []
    for scenario, scale in FORMAL_SCENARIO_CELLS:
        episodes = tuple(by_cell.get((scenario, scale), ()))
        if require_full_profile and len(episodes) != len(HELDOUT_RESERVED_SEEDS):
            _fail("heldout_cell_missing", f"{scenario}:{scale}:{len(episodes)}")
        if not episodes:
            continue
        cell_metrics.append(
            {
                "cell_id": f"{scenario}-{scale}v{scale}",
                "scenario": scenario,
                "scale": scale,
                **_evaluate_episode_group(
                    episodes,
                    probabilities_by_episode,
                    latency_by_episode,
                    threshold=scorer.decision_threshold,
                    temperature=scorer.temperature,
                    ece_bins=cfg.ece_bins,
                    device=str(scorer.device),
                ),
            }
        )

    assessment = _assess_heldout_metrics(
        overall,
        cell_metrics,
        expected_cell_count=(len(FORMAL_SCENARIO_CELLS) if require_full_profile else len(by_cell)),
    )
    if sha256_file(weights_path) != weights_before:
        _fail("heldout_weight_mutation_detected", str(weights_path))
    if sha256_file(bundle_manifest_path) != bundle_manifest_before:
        _fail("heldout_model_config_mutation_detected", str(bundle_manifest_path))
    if sha256_file(corpus_root / HELDOUT_MANIFEST_FILENAME) != corpus_manifest_before:
        _fail("heldout_corpus_mutation_detected", str(corpus_root))

    authority_blockers = ["paired_shadow_not_run", "internal_model_test_report_not_bound"]
    if not assessment["passed"]:
        authority_blockers.insert(0, "held_out_1000_1019_not_passed")
    report: dict[str, Any] = {
        "schema_version": HELDOUT_EVALUATION_SCHEMA_VERSION,
        "evaluated_at_utc": timestamp,
        "evaluation_role": HELDOUT_ROLE,
        "heldout_corpus": {
            "manifest_sha256": corpus.manifest_sha256,
            "manifest_content_sha256": corpus.manifest["content_sha256"],
            "profile_version": corpus.manifest["profile"]["profile_version"],
            "episode_count": len(corpus.episodes),
            "seed_values": sorted({episode.graph.seed for episode in corpus.episodes}),
            "scenario_scale_cell_count": len(by_cell),
        },
        "development_model": {
            "model_id": f"d5-tracklet-development-{weights_before[:16]}",
            "bundle_manifest_sha256": scorer.bundle_manifest_sha256,
            "weights_sha256": scorer.bundle_weights_sha256,
            "training_dataset": dict(scorer.manifest["training_dataset"]),
            "admission_status": admission["status"],
        },
        "frozen_decision": {
            "temperature": scorer.temperature,
            "decision_threshold": scorer.decision_threshold,
            "source": "development_bundle_validation_calibration",
            "temperature_or_threshold_selection_performed": False,
            "weight_update_performed": False,
        },
        "overall": overall,
        "cell_metrics": cell_metrics,
        "heldout_assessment": assessment,
        "identity_and_truth_safety": {
            "online_truth_feature_count": 0,
            "same_camera_candidate_edge_count": 0,
            "unlabeled_candidate_edge_count": 0,
            "global_track_id_created_or_rebound": False,
            "truth_scope": "physically_separate_evaluator_only",
            "model_weights_unchanged": True,
            "model_config_unchanged": True,
            "heldout_corpus_unchanged": True,
        },
        "layers": {
            "data_support": {"status": "pass", "passed": True},
            "internal_model_test": {
                "status": "source_bundle_development_only",
                "passed": False,
                "authority": False,
            },
            "held_out_1000_1019": assessment,
            "paired_shadow": {"status": "not_run", "passed": False},
            "g1_assist_authority": {
                "status": "fail_closed",
                "passed": False,
                "g1_assist_eligible": False,
                "assist_enabled": False,
                "authority_enabled": False,
                "blockers": authority_blockers,
            },
        },
        "implementation_sha256": _implementation_hashes(),
    }
    report["content_sha256"] = _sha256_json(report)
    temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir(parents=True)
    try:
        _write_json_atomic(temporary / HELDOUT_EVALUATION_FILENAME, report)
        _write_text_atomic(
            temporary / HELDOUT_REPORT_FILENAME,
            render_heldout_evaluation_markdown(report),
        )
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return MappingProxyType(report)


def render_heldout_evaluation_markdown(report: Mapping[str, Any]) -> str:
    """Render the held-out evidence as a concise Chinese technical report."""

    corpus = report["heldout_corpus"]
    assessment = report["heldout_assessment"]
    overall = report["overall"]
    model = report["development_model"]
    lines = [
        "# D5 保留种子跨视角图评估",
        "",
        "## 结论",
        "",
        f"保留集评估状态为 `{assessment['status']}`。本次只评估 development bundle，"
        "未调温度、未选阈值、未更新权重。",
        "paired shadow 尚未执行。无论保留集是否通过，G1、辅助模式和控制权限均保持关闭。",
        "",
        "## 数据与模型",
        "",
        f"- 图帧：`{corpus['episode_count']}`；seed：`{corpus['seed_values']}`。",
        f"- 场景规模单元：`{corpus['scenario_scale_cell_count']}`。",
        f"- held-out manifest SHA-256：`{corpus['manifest_sha256']}`。",
        f"- 模型：`{model['model_id']}`；权重 SHA-256：`{model['weights_sha256']}`。",
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
    ]
    for name in (
        "precision",
        "recall",
        "f1",
        "false_merge_rate",
        "candidate_recall",
        "ece",
        "p95_inference_latency_ms",
    ):
        metric = overall["metrics"][name]
        value = metric["value"] if metric["available"] else f"不可用：{metric['reason']}"
        lines.append(f"| `{name}` | `{value}` |")
    lines.extend(
        [
            "",
            "## 场景规模单元",
            "",
            "| 单元 | 边样本 | 精确率 | 召回率 | F1 | 错误合并率 | 候选召回率 | 校准误差 | P95 毫秒 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for cell in report["cell_metrics"]:
        values = [
            _metric_text(cell["metrics"][name])
            for name in (
                "precision",
                "recall",
                "f1",
                "false_merge_rate",
                "candidate_recall",
                "ece",
                "p95_inference_latency_ms",
            )
        ]
        lines.append(
            f"| `{cell['cell_id']}` | {cell['labeled_candidate_edge_count']} | "
            + " | ".join(values)
            + " |"
        )
    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            "在线图不含 evaluator truth。真值只用于离线标签和 lineage 核验。候选边保持默认时间、"
            "极线、射线、重投影和协方差门，同相机边为零。D5 未创建、改写或换绑 `global_track_id`。",
            "模型包、权重和 held-out corpus 在评估前后哈希一致。",
            "",
        ]
    )
    return "\n".join(lines)


def _run_frozen_inference(
    episodes: Sequence[LoadedHeldoutEpisode],
    model: torch.nn.Module,
    *,
    temperature: float,
    device: torch.device,
    latency_repeats: int,
) -> tuple[dict[str, np.ndarray], dict[str, tuple[float, ...]]]:
    probabilities: dict[str, np.ndarray] = {}
    latencies: dict[str, tuple[float, ...]] = {}
    model.to(device)
    model.eval()
    with torch.no_grad():
        for episode in episodes:
            graph = episode.graph
            tensors = (
                torch.as_tensor(np.array(graph.node_features, copy=True), dtype=torch.float32, device=device),
                torch.as_tensor(np.array(graph.edge_index, copy=True), dtype=torch.long, device=device),
                torch.as_tensor(np.array(graph.edge_features, copy=True), dtype=torch.float32, device=device),
            )
            logits = model.edge_logits(*tensors)
            values = torch.sigmoid(logits / float(temperature)).detach().cpu().numpy().astype(np.float64)
            if values.shape != (graph.edge_count,) or not np.all(np.isfinite(values)):
                _fail("heldout_model_output_invalid", graph.episode_uid)
            probabilities[graph.episode_uid] = values
            measured: list[float] = []
            for _ in range(latency_repeats):
                if device.type == "cuda":
                    torch.cuda.synchronize(device)
                started = time.perf_counter()
                timed_logits = model.edge_logits(*tensors)
                timed_values = torch.sigmoid(timed_logits / float(temperature))
                if device.type == "cuda":
                    torch.cuda.synchronize(device)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if not bool(torch.all(torch.isfinite(timed_values))):
                    _fail("heldout_model_output_invalid", graph.episode_uid)
                measured.append(elapsed_ms)
            latencies[graph.episode_uid] = tuple(measured)
    return probabilities, latencies


def _evaluate_episode_group(
    episodes: Sequence[LoadedHeldoutEpisode],
    probabilities_by_episode: Mapping[str, np.ndarray],
    latency_by_episode: Mapping[str, Sequence[float]],
    *,
    threshold: float,
    temperature: float,
    ece_bins: int,
    device: str,
) -> dict[str, Any]:
    probabilities: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    latency_values: list[float] = []
    for episode in episodes:
        target, eligible = edge_targets(episode)  # type: ignore[arg-type]
        if not bool(np.all(eligible)):
            _fail("heldout_unlabeled_candidate_edge", episode.graph.episode_uid)
        values = np.asarray(probabilities_by_episode[episode.graph.episode_uid], dtype=np.float64)
        probabilities.append(values)
        targets.append(np.asarray(target, dtype=np.float64))
        latency_values.extend(float(value) for value in latency_by_episode[episode.graph.episode_uid])
    probability_array = np.concatenate(probabilities)
    target_array = np.concatenate(targets)
    metrics = _edge_and_cluster_metrics(  # type: ignore[arg-type]
        episodes,
        probability_array,
        target_array,
        threshold=float(threshold),
        ece_bins=ece_bins,
    )
    latency_array = np.asarray(latency_values, dtype=np.float64)
    latency = {
        "device": str(device),
        "sample_count": int(latency_array.size),
        "p50_ms": float(np.percentile(latency_array, 50)),
        "p95_ms": float(np.percentile(latency_array, 95)),
        "max_ms": float(np.max(latency_array)),
    }
    metrics["p50_inference_latency_ms"] = _available(latency["p50_ms"])
    metrics["p95_inference_latency_ms"] = _available(latency["p95_ms"])
    return {
        "episode_count": len(episodes),
        "complete_truth": True,
        "truth_scope": "complete_graph_truth_evaluator_only",
        "labeled_candidate_edge_count": int(target_array.size),
        "decision_threshold": float(threshold),
        "temperature": float(temperature),
        "metrics": metrics,
        "latency": latency,
    }


def _assess_heldout_metrics(
    overall: Mapping[str, Any],
    cell_metrics: Sequence[Mapping[str, Any]],
    *,
    expected_cell_count: int,
) -> dict[str, Any]:
    criteria = TrackletReadinessCriteria()
    limits = (
        ("precision", ">=", criteria.minimum_test_precision),
        ("recall", ">=", criteria.minimum_test_recall),
        ("f1", ">=", criteria.minimum_test_f1),
        ("false_merge_rate", "<=", criteria.maximum_test_false_merge_rate),
        ("candidate_recall", ">=", criteria.minimum_test_candidate_recall),
        ("ece", "<=", criteria.maximum_test_ece),
        ("p95_inference_latency_ms", "<=", criteria.maximum_p95_inference_latency_ms),
    )
    overall_gates = _metric_gates(overall["metrics"], limits)
    cell_assessments = [
        {
            "cell_id": str(cell["cell_id"]),
            "gates": _metric_gates(cell["metrics"], limits),
        }
        for cell in cell_metrics
    ]
    for item in cell_assessments:
        item["passed"] = all(gate["passed"] for gate in item["gates"])
    catalog_passed = len(cell_metrics) == expected_cell_count
    passed = (
        all(gate["passed"] for gate in overall_gates)
        and catalog_passed
        and all(item["passed"] for item in cell_assessments)
    )
    reasons = [f"overall:{gate['name']}" for gate in overall_gates if not gate["passed"]]
    reasons.extend(
        f"cell:{item['cell_id']}"
        for item in cell_assessments
        if not item["passed"]
    )
    if not catalog_passed:
        reasons.append("scenario_scale_cell_catalog")
    return {
        "status": "pass" if passed else "fail_closed",
        "passed": passed,
        "overall_gates": overall_gates,
        "cell_catalog_gate": {
            "actual": len(cell_metrics),
            "expected": expected_cell_count,
            "passed": catalog_passed,
        },
        "cell_assessments": cell_assessments,
        "failure_reasons": reasons,
        "paired_shadow_satisfied": False,
        "g1_assist_eligible": False,
        "authority_enabled": False,
    }


def _metric_gates(
    metrics: Mapping[str, Any],
    limits: Sequence[tuple[str, str, float]],
) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for name, operator, threshold in limits:
        metric = metrics.get(name)
        available = isinstance(metric, Mapping) and metric.get("available") is True
        value = metric.get("value") if available else None
        passed = bool(
            available
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and (float(value) >= threshold if operator == ">=" else float(value) <= threshold)
        )
        gates.append(
            {
                "name": name,
                "available": available,
                "value": value,
                "operator": operator,
                "threshold": threshold,
                "passed": passed,
            }
        )
    return gates


def _build_manifest(
    *,
    descriptors: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]],
    config: HeldoutGenerationConfig,
    generation_config: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    source_git_commit: str,
    source_repository_dirty: bool,
    created_at_utc: str,
    lineage_path: Path,
    lineage_record_count: int,
    class_counts: Mapping[str, int],
    gate_counts: Mapping[str, int],
    factor_counts: Mapping[str, int],
) -> dict[str, Any]:
    config_path = Path("heldout_dataset") / HELDOUT_CONFIG_FILENAME
    config_item = next(item for item in artifacts if item["path"] == config_path.as_posix())
    lineage_item = next(item for item in artifacts if item["path"] == lineage_path.as_posix())
    manifest: dict[str, Any] = {
        "schema_version": HELDOUT_CORPUS_SCHEMA_VERSION,
        "evaluation_role": HELDOUT_ROLE,
        "created_at_utc": created_at_utc,
        "profile": config.to_payload(),
        "training_split_registry_used": False,
        "source": {
            "git_commit": source_git_commit,
            "repository_dirty": source_repository_dirty,
            "implementation_sha256": _implementation_hashes(),
        },
        "read_only_training_sources": dict(source_binding),
        "config": {
            "file": config_path.as_posix(),
            "sha256": config_item["sha256"],
            "generation_config_sha256": _sha256_json(generation_config),
        },
        "candidate_gate": {
            "policy": "unchanged_sparse_tracklet_default",
            "config": asdict(SparseTrackletGraphConfig()),
            "config_sha256": generation_config["candidate_gate_config_sha256"],
            "aggregate_counts": {key: int(value) for key, value in sorted(gate_counts.items())},
        },
        "evaluator_lineage": {
            "file": lineage_path.as_posix(),
            "sha256": lineage_item["sha256"],
            "record_count": int(lineage_record_count),
            "physically_separate_from_online_graph": True,
        },
        "episodes": sorted((dict(item) for item in descriptors), key=lambda item: item["episode_uid"]),
        "counts": {
            "episode_count": len(descriptors),
            "seed_count": len(config.seeds),
            "scenario_scale_cell_count": len(config.scenario_cells),
            "node_count": sum(int(item["node_count"]) for item in descriptors),
            "candidate_edge_count": sum(int(item["edge_count"]) for item in descriptors),
            "class_balance": {key: int(value) for key, value in sorted(class_counts.items())},
            "factor_counts": {key: int(value) for key, value in sorted(factor_counts.items())},
        },
        "identity_and_truth_safety": {
            "anonymous_online_tracklets": True,
            "online_truth_feature_count": 0,
            "same_camera_candidate_edge_count": 0,
            "global_track_id_created_or_rebound": False,
            "all_episodes_held_out_evaluation": True,
            "train_validation_test_assignment_count": 0,
        },
        "artifact_inventory": list(artifacts),
        "artifact_inventory_sha256": _sha256_json({"artifacts": list(artifacts)}),
    }
    manifest["content_sha256"] = _sha256_json(manifest)
    return manifest


def _validate_manifest_counts(corpus: LoadedHeldoutCorpus) -> None:
    counts = corpus.manifest.get("counts")
    if not isinstance(counts, Mapping):
        _fail("heldout_counts_missing", "manifest counts are missing")
    class_counts: Counter[str] = Counter()
    for episode in corpus.episodes:
        class_counts.update(episode.class_balance)
    expected = {
        "episode_count": len(corpus.episodes),
        "seed_count": len({episode.graph.seed for episode in corpus.episodes}),
        "scenario_scale_cell_count": len({(episode.scenario, episode.scale) for episode in corpus.episodes}),
        "node_count": sum(episode.graph.node_count for episode in corpus.episodes),
        "candidate_edge_count": sum(episode.graph.edge_count for episode in corpus.episodes),
        "class_balance": {key: int(value) for key, value in sorted(class_counts.items())},
    }
    for name, value in expected.items():
        if counts.get(name) != value:
            _fail("heldout_count_mismatch", f"{name}:actual={counts.get(name)};expected={value}")


def _validate_heldout_descriptor(
    descriptor: Mapping[str, Any],
    profile: HeldoutGenerationConfig,
) -> None:
    if set(descriptor) != _HELDOUT_DESCRIPTOR_FIELDS:
        _fail("heldout_descriptor_fields_mismatch", str(sorted(set(descriptor) ^ _HELDOUT_DESCRIPTOR_FIELDS)))
    if descriptor.get("schema_version") != HELDOUT_EPISODE_SCHEMA_VERSION:
        _fail("heldout_descriptor_schema_mismatch", str(descriptor.get("schema_version")))
    if descriptor.get("evaluation_role") != HELDOUT_ROLE or descriptor.get("split") != HELDOUT_ROLE:
        _fail("heldout_episode_training_split_forbidden", str(descriptor.get("split")))
    seed = int(descriptor["seed"])
    scenario = str(descriptor["scenario"])
    scale = int(descriptor["scale"])
    if seed not in profile.seeds:
        _fail("heldout_seed_catalog_mismatch", str(seed))
    if (scenario, scale) not in profile.scenario_cells:
        _fail("scenario_cell_catalog_mismatch", f"{scenario}:{scale}")
    if descriptor["scenario_version"] != _SCENARIO_VERSION_BY_CELL[(scenario, scale)]:
        _fail("heldout_scenario_version_mismatch", str(descriptor["scenario_version"]))
    if not str(descriptor["episode_id"]).startswith("d5-heldout-"):
        _fail("heldout_episode_id_invalid", str(descriptor["episode_id"]))
    if descriptor.get("labels_complete") is not True or descriptor.get("candidate_recall_available") is not True:
        _fail("heldout_labels_incomplete", str(descriptor["episode_uid"]))


def _write_lineage(
    path: Path,
    records: Sequence[Mapping[str, Any]],
    *,
    candidate_gate_config_sha256: str,
) -> None:
    payload = {
        "schema_version": HELDOUT_LINEAGE_SCHEMA_VERSION,
        "evaluation_role": HELDOUT_ROLE,
        "candidate_gate_config_sha256": candidate_gate_config_sha256,
        "record_count": len(records),
        "records": sorted(
            (dict(item) for item in records),
            key=lambda item: (item["episode_uid"], item["tracklet_key"], item["measurement_timestamp"]),
        ),
    }
    raw = _canonical_json_bytes(payload)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as stream:
        stream.write(raw)
    path.write_bytes(buffer.getvalue())


def _load_lineage(path: Path) -> Mapping[str, Any]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("heldout_lineage_invalid", str(exc))
    if not isinstance(value, Mapping) or value.get("schema_version") != HELDOUT_LINEAGE_SCHEMA_VERSION:
        _fail("heldout_lineage_schema_mismatch", str(path))
    if value.get("evaluation_role") != HELDOUT_ROLE:
        _fail("heldout_lineage_role_mismatch", str(path))
    records = value.get("records")
    if not isinstance(records, list) or value.get("record_count") != len(records):
        _fail("heldout_lineage_count_mismatch", str(path))
    return value


def _validate_lineage(corpus: LoadedHeldoutCorpus, lineage: Mapping[str, Any]) -> None:
    index: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    required = {
        "episode_uid",
        "scenario_version",
        "seed",
        "evaluation_role",
        "tracklet_key",
        "camera_key",
        "measurement_timestamp",
        "source_observation_id",
        "truth_entity_id",
        "observation_kind",
        "entity_slot",
        "world_point_ned",
        "evidence_kind",
    }
    for raw in lineage["records"]:
        if not isinstance(raw, Mapping) or set(raw) != required:
            _fail("heldout_lineage_record_fields_mismatch", str(raw))
        item = dict(raw)
        if item["evaluation_role"] != HELDOUT_ROLE:
            _fail("heldout_lineage_role_mismatch", str(item["episode_uid"]))
        if item["evidence_kind"] != "offline_observation_truth_lineage":
            _fail("heldout_lineage_evidence_invalid", str(item["episode_uid"]))
        if item["observation_kind"] not in {"physical_target", "camera_local_false_alarm"}:
            _fail("heldout_lineage_observation_kind_invalid", str(item["observation_kind"]))
        point = np.asarray(item["world_point_ned"], dtype=float)
        if point.shape != (3,) or not np.all(np.isfinite(point)):
            _fail("heldout_lineage_world_point_invalid", str(item["episode_uid"]))
        seed = int(item["seed"])
        slot = int(item["entity_slot"])
        expected_truth = (
            _truth_entity_id(seed, slot)
            if item["observation_kind"] == "physical_target"
            else _clutter_truth_id_from_record(item)
        )
        if item["truth_entity_id"] != expected_truth:
            _fail("heldout_truth_lineage_forgery", str(item["episode_uid"]))
        key = (
            str(item["episode_uid"]),
            str(item["tracklet_key"]),
            _time_key(float(item["measurement_timestamp"])),
        )
        if key in index:
            _fail("heldout_lineage_duplicate", str(key))
        index[key] = item

    matched = 0
    for episode in corpus.episodes:
        labels = episode.evaluator_labels.by_tracklet_key
        for index_number, tracklet_key in enumerate(episode.graph.tracklet_keys):
            key = (
                episode.graph.episode_uid,
                tracklet_key,
                _time_key(float(episode.graph.measurement_timestamps[index_number])),
            )
            item = index.get(key)
            if item is None:
                _fail("heldout_lineage_missing", str(key))
            label = labels.get(tracklet_key)
            if label is None or label.truth_entity_id != item["truth_entity_id"]:
                _fail("heldout_truth_lineage_forgery", str(key))
            if item["camera_key"] != episode.graph.camera_keys[index_number]:
                _fail("heldout_lineage_camera_mismatch", str(key))
            if int(item["seed"]) != episode.graph.seed:
                _fail("heldout_lineage_seed_mismatch", str(key))
            matched += 1
    if len(index) != matched:
        _fail("heldout_lineage_orphan", f"lineage={len(index)};matched={matched}")
    if corpus.manifest["evaluator_lineage"]["record_count"] != matched:
        _fail("heldout_lineage_count_mismatch", str(matched))


def _profile_from_payload(value: Any, require_full_profile: bool) -> HeldoutGenerationConfig:
    if not isinstance(value, Mapping):
        _fail("heldout_profile_missing", "held-out profile is missing")
    raw_cells = value.get("scenario_cells")
    if not isinstance(raw_cells, list):
        _fail("scenario_cell_catalog_invalid", "scenario cells must be a list")
    try:
        cells = tuple((str(item["scenario"]), int(item["scale"])) for item in raw_cells)
        seeds = tuple(int(seed) for seed in value["seeds"])
        profile = HeldoutGenerationConfig(
            profile_version=str(value["profile_version"]),
            seeds=seeds,
            scenario_cells=cells,
            frames_per_seed_cell=int(value["frames_per_seed_cell"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TrackletHeldoutEvaluationError):
            raise
        _fail("heldout_profile_invalid", str(exc))
    if value != profile.to_payload():
        _fail("heldout_profile_fields_mismatch", str(value))
    if require_full_profile and profile.profile_version != HELDOUT_FULL_PROFILE_VERSION:
        _fail("heldout_full_profile_required", profile.profile_version)
    return profile


def _training_source_binding(formal_root: Path, supplemental_root: Path) -> dict[str, Any]:
    formal_manifest = formal_root / "manifest.json"
    supplemental_manifest = supplemental_root / "supplemental_manifest.json"
    for path, code in (
        (formal_manifest, "formal_manifest_missing"),
        (supplemental_manifest, "supplemental_manifest_missing"),
    ):
        if not path.is_file():
            _fail(code, str(path))
        _read_json(path)
    return {
        "formal": {
            "manifest_file": "manifest.json",
            "manifest_sha256": sha256_file(formal_manifest),
            "modified": False,
        },
        "supplemental": {
            "manifest_file": "supplemental_manifest.json",
            "manifest_sha256": sha256_file(supplemental_manifest),
            "modified": False,
        },
        "samples_copied_or_rewritten": False,
    }


def _source_hash_snapshot(formal_root: Path, supplemental_root: Path) -> dict[str, str]:
    return {
        "formal": sha256_file(formal_root / "manifest.json"),
        "supplemental": sha256_file(supplemental_root / "supplemental_manifest.json"),
    }


def _artifact_inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def _validate_inventory(root: Path, value: Any) -> None:
    if not isinstance(value, list) or not value:
        _fail("heldout_artifact_inventory_missing", str(root))
    paths: set[str] = set()
    canonical: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != {"path", "sha256", "size_bytes"}:
            _fail("heldout_artifact_inventory_invalid", str(raw))
        relative = str(raw["path"])
        if relative in paths:
            _fail("heldout_artifact_inventory_duplicate", relative)
        paths.add(relative)
        path = _safe_artifact(root, relative)
        if path.stat().st_size != int(raw["size_bytes"]):
            _fail("heldout_artifact_size_mismatch", relative)
        if sha256_file(path) != raw["sha256"]:
            _fail("heldout_artifact_hash_mismatch", relative)
        canonical.append(dict(raw))
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != HELDOUT_MANIFEST_FILENAME
    }
    if actual != paths:
        _fail("heldout_artifact_inventory_set_mismatch", f"missing={sorted(paths-actual)};extra={sorted(actual-paths)}")
    manifest = _read_json(root / HELDOUT_MANIFEST_FILENAME)
    if manifest.get("artifact_inventory_sha256") != _sha256_json({"artifacts": canonical}):
        _fail("heldout_artifact_inventory_hash_mismatch", str(root))


def _validate_destination(destination: Path, sources: Sequence[Path]) -> None:
    for source in sources:
        if destination == source or destination in source.parents or source in destination.parents:
            _fail("output_source_overlap", f"output={destination};source={source}")


def _safe_artifact(root: Path, raw_relative: Any) -> Path:
    relative = Path(str(raw_relative))
    if relative.is_absolute() or not str(relative) or ".." in relative.parts:
        _fail("heldout_artifact_path_invalid", str(raw_relative))
    path = (root / relative).resolve()
    if root != path and root not in path.parents:
        _fail("heldout_artifact_path_escape", str(raw_relative))
    if not path.is_file():
        _fail("heldout_artifact_missing", str(raw_relative))
    return path


def _implementation_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {
        name: sha256_file(root / name)
        for name in _IMPLEMENTATION_FILES
    }


def _validate_commit(value: str) -> str:
    commit = str(value).strip().lower()
    if _COMMIT_PATTERN.fullmatch(commit) is None:
        _fail("source_git_commit_invalid", commit)
    return commit


def _verify_content_hash(value: Mapping[str, Any], code: str) -> None:
    expected = value.get("content_sha256")
    unhashed = dict(value)
    unhashed.pop("content_sha256", None)
    if expected != _sha256_json(unhashed):
        _fail(code, str(expected))


def _metric_text(metric: Mapping[str, Any]) -> str:
    return str(metric["value"]) if metric.get("available") else "不可用"


def _available(value: float | int) -> dict[str, Any]:
    return {"available": True, "value": value}


def _time_key(value: float) -> str:
    return f"{float(value):.9f}"


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _fail("heldout_json_invalid", f"{path}:{exc}")
    if not isinstance(value, dict):
        _fail("heldout_json_object_required", str(path))
    return value


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(value))


def _write_text_atomic(path: Path, value: str) -> None:
    _write_bytes_atomic(path, (value.rstrip() + "\n").encode("utf-8"))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _git_provenance() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[4]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def _fail(code: str, message: str) -> None:
    raise TrackletHeldoutEvaluationError(code, message)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Produce or evaluate the D5 reserved-seed corpus")
    commands = parser.add_subparsers(dest="command", required=True)
    produce = commands.add_parser("produce", help="generate the complete 1000-1019 held-out corpus")
    produce.add_argument("--formal-dataset", required=True)
    produce.add_argument("--supplemental-root", required=True)
    produce.add_argument("--output-dir", required=True)
    produce.add_argument("--created-at-utc", required=True)
    validate = commands.add_parser("validate", help="strictly reload the complete held-out corpus")
    validate.add_argument("--heldout-corpus", required=True)
    evaluate = commands.add_parser("evaluate", help="evaluate one development-only model bundle")
    evaluate.add_argument("--heldout-corpus", required=True)
    evaluate.add_argument("--bundle-dir", required=True)
    evaluate.add_argument("--output-dir", required=True)
    evaluate.add_argument("--evaluated-at-utc", required=True)
    evaluate.add_argument("--device", default="cpu")
    evaluate.add_argument("--ece-bins", type=int, default=10)
    evaluate.add_argument("--latency-repeats", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "produce":
        commit, dirty = _git_provenance()
        corpus = generate_tracklet_heldout_corpus(
            args.output_dir,
            formal_dataset_dir=args.formal_dataset,
            supplemental_root=args.supplemental_root,
            created_at_utc=args.created_at_utc,
            source_git_commit=commit,
            source_repository_dirty=dirty,
        )
        payload = {
            "manifest_sha256": corpus.manifest_sha256,
            "episode_count": len(corpus.episodes),
            "seed_values": sorted({episode.graph.seed for episode in corpus.episodes}),
            "evaluation_role": HELDOUT_ROLE,
        }
    elif args.command == "validate":
        corpus = load_tracklet_heldout_corpus(args.heldout_corpus)
        payload = {
            "manifest_sha256": corpus.manifest_sha256,
            "episode_count": len(corpus.episodes),
            "seed_values": sorted({episode.graph.seed for episode in corpus.episodes}),
            "evaluation_role": HELDOUT_ROLE,
        }
    else:
        report = evaluate_heldout_development_bundle(
            args.heldout_corpus,
            args.bundle_dir,
            args.output_dir,
            evaluated_at_utc=args.evaluated_at_utc,
            policy=HeldoutEvaluationPolicy(
                device=args.device,
                ece_bins=args.ece_bins,
                latency_repeats=args.latency_repeats,
            ),
        )
        payload = {
            "content_sha256": report["content_sha256"],
            "heldout_status": report["heldout_assessment"]["status"],
            "paired_shadow": "not_run",
            "g1_assist_authority": False,
        }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "HELDOUT_EXPECTED_FRAME_COUNT",
    "HELDOUT_RESERVED_SEEDS",
    "HeldoutEvaluationPolicy",
    "HeldoutGenerationConfig",
    "LoadedHeldoutCorpus",
    "LoadedHeldoutEpisode",
    "TrackletHeldoutEvaluationError",
    "evaluate_heldout_development_bundle",
    "generate_tracklet_heldout_corpus",
    "load_tracklet_heldout_corpus",
    "main",
    "render_heldout_evaluation_markdown",
]
