"""Strict internal-development training adapter for the detached D5 corpus."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import uuid

import torch

from .canonical_seed_view import _load_registry_binding
from .sparse_tracklet_graph import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    SparseTrackletGraphConfig,
)
from .tracklet_dataset import (
    LoadedTrackletDataset,
    LoadedTrackletEpisode,
    sha256_file,
)
from .tracklet_model_bundle import (
    MANIFEST_FILENAME,
    WEIGHTS_FILENAME,
    load_tracklet_model_bundle,
)
from .tracklet_supplemental_admission import (
    LoadedTrackletCompositeAdmission,
    load_tracklet_composite_admission_view,
)
from .tracklet_supplemental_curriculum import FORMAL_SCENARIO_CELLS
from .tracklet_training import (
    ROBUST_TRAINING_PROFILE_VERSION,
    ROBUST_TRAINING_VIEW_IDS,
    TRAINING_REPORT_SCHEMA_VERSION,
    TrackletTrainingConfig,
    evaluate_tracklet_edge_model,
    run_loaded_tracklet_training_pipeline,
)
from .tracklet_training_audit import (
    TrackletReadinessCriteria,
    assess_tracklet_model_promotion,
    audit_tracklet_training_readiness,
)


COMPOSITE_TRAINING_PREFLIGHT_SCHEMA_VERSION = (
    "d5.tracklet-composite-training-preflight.v1"
)
COMPOSITE_INTERNAL_TRAINING_SCHEMA_VERSION = (
    "d5.tracklet-composite-internal-training.v1"
)
COMPOSITE_INTERNAL_TRAINING_PROFILE_VERSION = (
    "d5-tracklet-native-pytorch-internal-development-v1"
)
COMPOSITE_SMOKE_TRAINING_PROFILE_VERSION = (
    "d5-tracklet-native-pytorch-dirty-smoke-v1"
)
COMPOSITE_ROBUST_TRAINING_PROFILE_VERSION = (
    "d5-tracklet-native-pytorch-robust-development-v2"
)
D6_MODEL_EVALUATION_SCHEMA_VERSION = "d5.tracklet-graph-model-evaluation.v1"
D6_MODEL_EVALUATION_DATE = "2026-07-21"
D6_MODEL_EVALUATION_FILENAME = "d6_model_evaluation.json"
RESERVED_EVALUATION_SEEDS = tuple(range(1000, 1020))
EXPECTED_SEED_COUNTS = MappingProxyType(
    {"train": 60, "validation": 20, "test": 20}
)
FROZEN_CANDIDATE_GATE_CONFIG = MappingProxyType(
    asdict(SparseTrackletGraphConfig())
)
_SPLITS = ("train", "validation", "test")
_SCENARIO_SCALE_PATTERN = re.compile(
    r"^(?P<scenario>.+)-(?P<resources>\d+)v(?P<targets>\d+)-v(?P<version>\d+)$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_IMPLEMENTATION_FILES = (
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
    "tracklet_supplemental_admission.py",
    "tracklet_composite_training.py",
)


class CompositeInternalTrainingError(ValueError):
    """Stable fail-closed error at the composite training boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class CompositeInternalTrainingProfile:
    """Frozen model, optimizer, feature, thread, and gate profile."""

    profile_version: str = COMPOSITE_INTERNAL_TRAINING_PROFILE_VERSION
    torch_num_threads: int = 1
    candidate_gate_config: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType(dict(FROZEN_CANDIDATE_GATE_CONFIG))
    )
    training: TrackletTrainingConfig = field(
        default_factory=lambda: TrackletTrainingConfig(
            seed=20260721,
            epochs=30,
            learning_rate=1.0e-3,
            weight_decay=1.0e-5,
            hidden_dim=32,
            message_passing_steps=2,
            dropout=0.0,
            graphs_per_optimizer_step=16,
            hard_negative_ratio=3.0,
            max_hard_negatives_without_positive=64,
            ece_bins=10,
            latency_repeats=3,
            device="cpu",
        )
    )

    def __post_init__(self) -> None:
        if self.torch_num_threads != 1:
            _fail("model_config_drift", "internal training requires one PyTorch CPU thread")
        if dict(self.candidate_gate_config) != dict(FROZEN_CANDIDATE_GATE_CONFIG):
            _fail(
                "candidate_gate_lowered_or_changed",
                "internal training requires the existing default geometry candidate gates",
            )

    def to_payload(self) -> dict[str, Any]:
        criteria = TrackletReadinessCriteria()
        return {
            "profile_version": self.profile_version,
            "framework": "native_pytorch_without_pytorch_geometric",
            "model_class": "NativeTrackletEdgeClassifier",
            "torch_num_threads": self.torch_num_threads,
            "training": asdict(self.training),
            "node_feature_names": list(NODE_FEATURE_NAMES),
            "edge_feature_names": list(EDGE_FEATURE_NAMES),
            "candidate_gate_config": dict(self.candidate_gate_config),
            "model_test_thresholds": {
                "minimum_test_precision": criteria.minimum_test_precision,
                "minimum_test_recall": criteria.minimum_test_recall,
                "minimum_test_f1": criteria.minimum_test_f1,
                "maximum_test_false_merge_rate": criteria.maximum_test_false_merge_rate,
                "minimum_test_candidate_recall": criteria.minimum_test_candidate_recall,
                "maximum_test_ece": criteria.maximum_test_ece,
                "maximum_p95_inference_latency_ms": (
                    criteria.maximum_p95_inference_latency_ms
                ),
            },
        }


PRODUCTION_TRAINING_PROFILE = CompositeInternalTrainingProfile()
SMOKE_TRAINING_PROFILE = CompositeInternalTrainingProfile(
    profile_version=COMPOSITE_SMOKE_TRAINING_PROFILE_VERSION,
    training=TrackletTrainingConfig(
        seed=20260721,
        epochs=2,
        learning_rate=1.0e-3,
        weight_decay=1.0e-5,
        hidden_dim=8,
        message_passing_steps=1,
        dropout=0.0,
        graphs_per_optimizer_step=4,
        hard_negative_ratio=3.0,
        max_hard_negatives_without_positive=16,
        ece_bins=5,
        latency_repeats=1,
        device="cpu",
    ),
)
ROBUST_TRAINING_PROFILE = CompositeInternalTrainingProfile(
    profile_version=COMPOSITE_ROBUST_TRAINING_PROFILE_VERSION,
    training=TrackletTrainingConfig(
        seed=20260726,
        epochs=12,
        learning_rate=5.0e-4,
        weight_decay=1.0e-4,
        hidden_dim=48,
        message_passing_steps=2,
        dropout=0.1,
        graphs_per_optimizer_step=32,
        hard_negative_ratio=4.0,
        max_hard_negatives_without_positive=64,
        ece_bins=10,
        latency_repeats=3,
        device="cpu",
        robust_training_profile_version=ROBUST_TRAINING_PROFILE_VERSION,
        robust_training_view_ids=ROBUST_TRAINING_VIEW_IDS,
    ),
)


@dataclass(frozen=True)
class LoadedCompositeTrainingCorpus:
    admission: LoadedTrackletCompositeAdmission
    formal_dataset_root: Path
    supplemental_root: Path
    admission_report_path: Path
    admission_report: Mapping[str, Any]
    admission_report_sha256: str
    corpus_audit: Mapping[str, Any]
    hash_bound_dirty_source_accepted: bool = False

    @property
    def dataset(self) -> LoadedTrackletDataset:
        return self.admission.dataset


def load_composite_training_corpus(
    *,
    formal_dataset_dir: str | Path,
    supplemental_root: str | Path,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    composite_view_manifest_path: str | Path,
    composite_admission_report_path: str | Path,
    allow_hash_bound_dirty_source: bool = False,
) -> LoadedCompositeTrainingCorpus:
    """Strictly load all bound sources without copying or rewriting samples."""

    formal_root = Path(formal_dataset_dir).resolve()
    supplemental_dir = Path(supplemental_root).resolve()
    admission = load_tracklet_composite_admission_view(
        formal_dataset_dir=formal_root,
        supplemental_root=supplemental_dir,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
        view_manifest_path=composite_view_manifest_path,
    )
    report_path = Path(composite_admission_report_path).resolve()
    report = _load_bound_admission_report(report_path, admission)
    assignment, _ = _load_registry_binding(
        Path(training_seed_registry_path).resolve(),
        Path(shared_seed_registry_path).resolve(),
    )
    corpus_audit = audit_composite_training_dataset(
        admission.dataset,
        expected_seed_assignment=assignment,
        expected_scenario_cells=FORMAL_SCENARIO_CELLS,
        reserved_evaluation_seeds=RESERVED_EVALUATION_SEEDS,
    )
    if admission.readiness["data_support_readiness"]["status"] != "pass":
        _fail("data_support_not_ready", "composite data-support admission is not pass")
    readiness = admission.readiness["training_readiness"]
    dirty_only = (
        readiness["status"] == "fail_closed"
        and readiness.get("failure_reasons")
        == ["supplemental_source_repository_dirty"]
        and admission.view_manifest["sources"].get(
            "supplemental_source_repository_dirty"
        )
        is True
    )
    if readiness["status"] != "pass" and not (
        allow_hash_bound_dirty_source and dirty_only
    ):
        _fail("training_data_not_ready", "composite training-data admission is not pass")
    return LoadedCompositeTrainingCorpus(
        admission=admission,
        formal_dataset_root=formal_root,
        supplemental_root=supplemental_dir,
        admission_report_path=report_path,
        admission_report=MappingProxyType(report),
        admission_report_sha256=sha256_file(report_path),
        corpus_audit=MappingProxyType(corpus_audit),
        hash_bound_dirty_source_accepted=bool(
            allow_hash_bound_dirty_source and dirty_only
        ),
    )


def audit_composite_training_dataset(
    dataset: LoadedTrackletDataset,
    *,
    expected_seed_assignment: Mapping[int, str],
    expected_scenario_cells: Sequence[tuple[str, int]],
    reserved_evaluation_seeds: Sequence[int],
) -> dict[str, Any]:
    """Audit complete seed splits, 45 cells, labels, and identity safety."""

    if not isinstance(dataset, LoadedTrackletDataset):
        raise TypeError("dataset must be a LoadedTrackletDataset")
    expected_assignment = {int(seed): str(split) for seed, split in expected_seed_assignment.items()}
    if not expected_assignment:
        _fail("seed_assignment_empty", "expected seed assignment must be non-empty")
    if set(expected_assignment.values()) != set(_SPLITS):
        _fail("seed_assignment_split_mismatch", "expected assignment must contain all splits")
    reserved = {int(seed) for seed in reserved_evaluation_seeds}
    seen_seed_splits: dict[int, set[str]] = {}
    split_class_counts = {split: Counter() for split in _SPLITS}
    cell_counts: dict[tuple[str, str, int], Counter[str]] = {}
    same_camera_edge_count = 0
    missing_label_count = 0
    unlabeled_edge_count = 0
    for episode in dataset.episodes:
        seed = int(episode.graph.seed)
        seen_seed_splits.setdefault(seed, set()).add(episode.split)
        if seed not in expected_assignment or expected_assignment[seed] != episode.split:
            _fail("seed_split_leakage", f"seed {seed} entered {episode.split}")
        split_class_counts[episode.split].update(episode.class_balance)
        if not episode.evaluator_labels.labels_complete:
            _fail("incomplete_evaluator_labels", episode.graph.episode_uid)
        if not episode.evaluator_labels.candidate_recall_available:
            _fail("candidate_recall_unavailable", episode.graph.episode_uid)
        label_keys = set(episode.evaluator_labels.by_tracklet_key)
        missing_label_count += len(set(episode.graph.tracklet_keys) - label_keys)
        unlabeled_edge_count += episode.class_balance["unlabeled_candidate_edges"]
        for source, target in episode.graph.edge_index.T:
            if episode.graph.camera_keys[int(source)] == episode.graph.camera_keys[int(target)]:
                same_camera_edge_count += 1
        scenario, scale = _scenario_scale(episode.graph.scenario_version)
        key = (episode.split, scenario, scale)
        counter = cell_counts.setdefault(key, Counter())
        counter["episode_count"] += 1
        counter["positive_candidate_edges"] += episode.class_balance[
            "positive_candidate_edges"
        ]
        counter["negative_candidate_edges"] += episode.class_balance[
            "negative_candidate_edges"
        ]

    observed_seeds = set(seen_seed_splits)
    if observed_seeds != set(expected_assignment):
        _fail(
            "seed_catalog_mismatch",
            f"missing={sorted(set(expected_assignment)-observed_seeds)};"
            f"extra={sorted(observed_seeds-set(expected_assignment))}",
        )
    if any(len(splits) != 1 for splits in seen_seed_splits.values()):
        _fail("seed_split_leakage", "one or more seeds entered multiple splits")
    overlap = sorted(observed_seeds & reserved)
    if overlap:
        _fail("reserved_seed_leakage", str(overlap))
    for split in _SPLITS:
        if split_class_counts[split]["positive_candidate_edges"] <= 0:
            _fail("empty_positive_class", split)
        if split_class_counts[split]["negative_candidate_edges"] <= 0:
            _fail("empty_negative_class", split)
    if missing_label_count or unlabeled_edge_count:
        _fail(
            "label_completeness_failure",
            f"missing_labels={missing_label_count};unlabeled_edges={unlabeled_edge_count}",
        )
    if same_camera_edge_count:
        _fail("same_camera_candidate_edge", str(same_camera_edge_count))

    expected_cells = {(str(scenario), int(scale)) for scenario, scale in expected_scenario_cells}
    cells_by_split: dict[str, set[tuple[str, int]]] = {split: set() for split in _SPLITS}
    cell_records: list[dict[str, Any]] = []
    for (split, scenario, scale), counts in sorted(cell_counts.items()):
        cells_by_split[split].add((scenario, scale))
        if counts["positive_candidate_edges"] <= 0 or counts["negative_candidate_edges"] <= 0:
            _fail("scenario_cell_missing_class", f"{split}:{scenario}:{scale}")
        cell_records.append(
            {
                "split": split,
                "scenario": scenario,
                "scale": scale,
                **dict(counts),
            }
        )
    for split in _SPLITS:
        if cells_by_split[split] != expected_cells:
            _fail(
                "scenario_cell_catalog_mismatch",
                f"{split}:missing={sorted(expected_cells-cells_by_split[split])};"
                f"extra={sorted(cells_by_split[split]-expected_cells)}",
            )
    seed_counts = Counter(expected_assignment.values())
    actual_seed_counts = {split: seed_counts[split] for split in _SPLITS}
    if actual_seed_counts != dict(EXPECTED_SEED_COUNTS):
        _fail(
            "seed_split_count_mismatch",
            f"actual={actual_seed_counts};expected={dict(EXPECTED_SEED_COUNTS)}",
        )
    return {
        "episode_count": len(dataset.episodes),
        "candidate_edge_count": sum(
            episode.graph.edge_count for episode in dataset.episodes
        ),
        "seed_count_by_split": actual_seed_counts,
        "whole_seed_atomic": True,
        "reserved_evaluation_seed_overlap": overlap,
        "scenario_scale_cell_count_by_split": {
            split: len(cells_by_split[split]) for split in _SPLITS
        },
        "scenario_scale_cells": cell_records,
        "class_balance_by_split": {
            split: {
                "positive_candidate_edges": split_class_counts[split][
                    "positive_candidate_edges"
                ],
                "negative_candidate_edges": split_class_counts[split][
                    "negative_candidate_edges"
                ],
                "unlabeled_candidate_edges": split_class_counts[split][
                    "unlabeled_candidate_edges"
                ],
            }
            for split in _SPLITS
        },
        "identity_safety": {
            "same_camera_candidate_edge_count": same_camera_edge_count,
            "same_camera_mutual_exclusion_preserved": same_camera_edge_count == 0,
            "missing_evaluator_label_count": missing_label_count,
            "global_track_id_created_or_rebound": False,
            "online_truth_feature_count": 0,
        },
    }


def build_composite_training_preflight(
    corpus: LoadedCompositeTrainingCorpus,
    *,
    implementation_git_commit: str,
    implementation_repository_dirty: bool,
    profile: CompositeInternalTrainingProfile = PRODUCTION_TRAINING_PROFILE,
) -> dict[str, Any]:
    """Build a no-weight, fail-closed training preflight report."""

    _validate_profile(profile, smoke=False)
    commit = _validate_commit(implementation_git_commit)
    if type(implementation_repository_dirty) is not bool:
        _fail("dirty_flag_invalid", "implementation_repository_dirty must be bool")
    profile_payload = profile.to_payload()
    report: dict[str, Any] = {
        "schema_version": COMPOSITE_TRAINING_PREFLIGHT_SCHEMA_VERSION,
        "status": "ready_for_clean_internal_training",
        "sources": _source_binding(corpus),
        "implementation_provenance": {
            "git_commit": commit,
            "repository_dirty": implementation_repository_dirty,
            "implementation_sha256": _implementation_hashes(),
        },
        "profile": {
            "config": profile_payload,
            "config_sha256": _sha256_json(profile_payload),
        },
        "corpus_audit": dict(corpus.corpus_audit),
        "estimated_resources": _estimated_resources(corpus, profile),
        "layers": _untrained_layers(),
        "model_artifacts": {
            "model_training_performed": False,
            "pt_generated": False,
            "weights_sha256": None,
        },
    }
    report["content_sha256"] = _sha256_json(report)
    return report


def write_composite_training_preflight(
    report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> tuple[str, str]:
    """Atomically write machine-readable and Chinese preflight evidence."""

    json_file = Path(json_path)
    markdown_file = Path(markdown_path)
    _write_json_atomic(json_file, dict(report))
    _write_text_atomic(markdown_file, render_composite_training_preflight_markdown(report))
    return sha256_file(json_file), sha256_file(markdown_file)


def run_composite_internal_development_training(
    corpus: LoadedCompositeTrainingCorpus,
    output_dir: str | Path,
    *,
    implementation_git_commit: str,
    implementation_repository_dirty: bool,
    smoke: bool = False,
    robust_v2: bool = False,
    allow_hash_bound_dirty_source: bool = False,
) -> Mapping[str, Any]:
    """Train a permanently development-only bundle from the read-only view."""

    if smoke and robust_v2:
        _fail("training_profile_conflict", "smoke and robust_v2 are mutually exclusive")
    profile = (
        SMOKE_TRAINING_PROFILE
        if smoke
        else ROBUST_TRAINING_PROFILE
        if robust_v2
        else PRODUCTION_TRAINING_PROFILE
    )
    _validate_profile(profile, smoke=smoke, robust_v2=robust_v2)
    commit = _validate_commit(implementation_git_commit)
    if type(implementation_repository_dirty) is not bool:
        _fail("dirty_flag_invalid", "implementation_repository_dirty must be bool")
    if (
        implementation_repository_dirty
        and not smoke
        and not allow_hash_bound_dirty_source
    ):
        _fail(
            "dirty_production_training_forbidden",
            "final internal weights require a detached clean worktree",
        )
    if allow_hash_bound_dirty_source and (smoke or not robust_v2):
        _fail(
            "hash_bound_dirty_mode_invalid",
            "dirty hash-bound training is restricted to the robust-v2 development profile",
        )
    if corpus.hash_bound_dirty_source_accepted and not (
        robust_v2 and allow_hash_bound_dirty_source
    ):
        _fail(
            "hash_bound_dirty_corpus_mode_required",
            "dirty supplemental provenance requires explicit robust-v2 hash-bound mode",
        )
    destination = Path(output_dir).resolve()
    _assert_training_output_detached(destination, corpus)
    if destination.exists():
        _fail("training_output_exists", str(destination))
    _configure_threads(profile)
    composite_training_view = _composite_training_view(corpus.dataset)
    training_dataset = (
        _smoke_training_view(composite_training_view)
        if smoke
        else composite_training_view
    )
    readiness = audit_tracklet_training_readiness(training_dataset)
    temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir(parents=True)
    try:
        bundle_dir = temporary / "model_bundle"
        raw_report_path = temporary / "raw_training_report.json"
        training_report = run_loaded_tracklet_training_pipeline(
            training_dataset,
            bundle_dir,
            raw_report_path,
            config=profile.training,
            development_only=True,
            readiness_audit_sha256=corpus.admission_report_sha256,
        )
        training_report["bundle"]["directory"] = "model_bundle"
        _write_json_atomic(raw_report_path, training_report)
        promotion = assess_tracklet_model_promotion(readiness, training_report)
        cell_evaluation = (
            []
            if smoke
            else _evaluate_test_scenario_cells(
                training_dataset,
                bundle_dir=bundle_dir,
                config=profile.training,
            )
        )
        internal = assess_internal_model_test(
            training_report["test"]["metrics"],
            same_camera_mutual_exclusion_preserved=bool(
                corpus.corpus_audit["identity_safety"][
                    "same_camera_mutual_exclusion_preserved"
                ]
            ),
            audited_scenario_cell_count=(
                len(FORMAL_SCENARIO_CELLS) if not smoke else 0
            ),
            smoke=smoke,
        )
        if smoke:
            d6_export = {
                "status": "not_written_dirty_smoke",
                "internal_model_test_evidence_only": True,
                "held_out_evaluation_included": False,
                "paired_shadow_included": False,
                "g1_assist_authority_enabled": False,
            }
        else:
            d6_report = build_d6_model_evaluation_report(
                training_report,
                cell_evaluation,
                bundle_dir=bundle_dir,
            )
            d6_report_path = temporary / D6_MODEL_EVALUATION_FILENAME
            _write_json_atomic(d6_report_path, d6_report)
            d6_export = {
                "status": "written_internal_model_test_only",
                "model_report_file": D6_MODEL_EVALUATION_FILENAME,
                "model_report_sha256": sha256_file(d6_report_path),
                "model_weights_file": f"model_bundle/{WEIGHTS_FILENAME}",
                "model_weights_sha256": d6_report["weights_sha256"],
                "model_config_file": f"model_bundle/{MANIFEST_FILENAME}",
                "model_config_sha256": d6_report["config_sha256"],
                "internal_model_test_evidence_only": True,
                "held_out_evaluation_included": False,
                "paired_shadow_included": False,
                "g1_assist_authority_enabled": False,
            }
        final_report: dict[str, Any] = {
            "schema_version": COMPOSITE_INTERNAL_TRAINING_SCHEMA_VERSION,
            "status": (
                "dirty_smoke_only"
                if smoke
                else "hash_bound_dirty_internal_development_complete"
                if implementation_repository_dirty
                else "internal_development_complete"
            ),
            "sources": _source_binding(corpus),
            "implementation_provenance": {
                "git_commit": commit,
                "repository_dirty": implementation_repository_dirty,
                "implementation_sha256": _implementation_hashes(),
                "source_binding_mode": (
                    "exact_source_hashes_dirty_development"
                    if implementation_repository_dirty
                    else "clean_git_commit_and_exact_source_hashes"
                ),
                "clean_source_claimed": not implementation_repository_dirty,
            },
            "profile": {
                "config": profile.to_payload(),
                "config_sha256": _sha256_json(profile.to_payload()),
            },
            "training_report": training_report,
            "promotion_threshold_assessment": promotion,
            "scenario_scale_test_audit": cell_evaluation,
            "d6_model_evaluation_export": d6_export,
            "layers": _trained_layers(internal, smoke=smoke),
            "identity_safety": dict(corpus.corpus_audit["identity_safety"]),
        }
        final_report["content_sha256"] = _sha256_json(final_report)
        _write_json_atomic(temporary / "internal_training_admission.json", final_report)
        _write_text_atomic(
            temporary / "INTERNAL_TRAINING_REPORT_CN.md",
            render_internal_training_markdown(final_report),
        )
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return MappingProxyType(final_report)


def assess_internal_model_test(
    metrics: Mapping[str, Any],
    *,
    same_camera_mutual_exclusion_preserved: bool,
    audited_scenario_cell_count: int,
    smoke: bool = False,
) -> dict[str, Any]:
    """Apply immutable model gates without granting G1 or assist."""

    criteria = TrackletReadinessCriteria()
    checks = (
        ("precision", ">=", criteria.minimum_test_precision),
        ("recall", ">=", criteria.minimum_test_recall),
        ("f1", ">=", criteria.minimum_test_f1),
        ("false_merge_rate", "<=", criteria.maximum_test_false_merge_rate),
        ("candidate_recall", ">=", criteria.minimum_test_candidate_recall),
        ("ece", "<=", criteria.maximum_test_ece),
        (
            "p95_inference_latency_ms",
            "<=",
            criteria.maximum_p95_inference_latency_ms,
        ),
    )
    gates: list[dict[str, Any]] = []
    for name, operator, threshold in checks:
        metric = metrics.get(name)
        available = isinstance(metric, Mapping) and bool(metric.get("available"))
        value = metric.get("value") if available else None
        passed = available and (
            float(value) >= threshold if operator == ">=" else float(value) <= threshold
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
    identity_gate = {
        "name": "same_camera_mutual_exclusion",
        "available": True,
        "value": bool(same_camera_mutual_exclusion_preserved),
        "operator": "==",
        "threshold": True,
        "passed": bool(same_camera_mutual_exclusion_preserved),
    }
    cell_gate = {
        "name": "all_scenario_scale_cells_audited",
        "available": True,
        "value": int(audited_scenario_cell_count),
        "operator": "==",
        "threshold": len(FORMAL_SCENARIO_CELLS),
        "passed": int(audited_scenario_cell_count) == len(FORMAL_SCENARIO_CELLS),
    }
    gates.extend((identity_gate, cell_gate))
    passed = all(gate["passed"] for gate in gates) and not smoke
    return {
        "status": "dirty_smoke_only" if smoke else "pass" if passed else "fail_closed",
        "passed": passed,
        "g1_assist_eligible": False,
        "gates": gates,
        "failure_reasons": [gate["name"] for gate in gates if not gate["passed"]],
    }


def build_d6_model_evaluation_report(
    training_report: Mapping[str, Any],
    cell_evaluations: Sequence[Mapping[str, Any]],
    *,
    bundle_dir: str | Path,
    evaluation_date: str = D6_MODEL_EVALUATION_DATE,
) -> dict[str, Any]:
    """Build D6's exact internal-test evidence from measured D5 artifacts."""

    if training_report.get("schema_version") != TRAINING_REPORT_SCHEMA_VERSION:
        _fail("training_report_schema_mismatch", "unsupported D5 training report")
    root = Path(bundle_dir).resolve()
    weights_path = root / WEIGHTS_FILENAME
    config_path = root / MANIFEST_FILENAME
    if not weights_path.is_file() or not config_path.is_file():
        _fail("model_bundle_artifact_missing", str(root))
    weights_sha256 = sha256_file(weights_path)
    config_sha256 = sha256_file(config_path)
    bundle = _require_mapping(training_report.get("bundle"), "training bundle")
    if bundle.get("weights_sha256") != weights_sha256:
        _fail("model_weight_hash_mismatch", str(weights_path))
    if bundle.get("manifest_sha256") != config_sha256:
        _fail("model_config_hash_mismatch", str(config_path))

    dataset = _require_mapping(training_report.get("dataset"), "training dataset")
    training_source_sha256 = _require_sha256(
        dataset.get("training_set_sha256"), "training_source_sha256"
    )
    raw_test_seeds = dataset.get("test_seed_values")
    if not isinstance(raw_test_seeds, Sequence) or isinstance(raw_test_seeds, (str, bytes)):
        _fail("test_seed_values_missing", "training report lacks test seed values")
    test_seed_values = [int(value) for value in raw_test_seeds]
    if (
        len(test_seed_values) != EXPECTED_SEED_COUNTS["test"]
        or len(set(test_seed_values)) != len(test_seed_values)
        or set(test_seed_values) & set(RESERVED_EVALUATION_SEEDS)
    ):
        _fail("test_seed_partition_invalid", str(test_seed_values))

    test = _require_mapping(training_report.get("test"), "test evaluation")
    if test.get("complete_truth") is not True or test.get("truth_scope") != "complete_graph_truth":
        _fail("test_truth_incomplete", "D6 export requires complete internal test truth")
    test_metrics = _d6_metric_set(test.get("metrics"), "test metrics")
    latency = _d6_latency(test.get("latency"))

    expected_cells = tuple(FORMAL_SCENARIO_CELLS)
    observed_cells = tuple(
        (str(item.get("scenario")), int(item.get("scale", -1)))
        for item in cell_evaluations
    )
    if observed_cells != expected_cells:
        _fail(
            "model_cell_catalog_mismatch",
            f"observed={observed_cells};expected={expected_cells}",
        )
    cell_metrics: list[dict[str, Any]] = []
    for item in cell_evaluations:
        scenario = str(item["scenario"])
        scale = int(item["scale"])
        if item.get("complete_truth") is not True:
            _fail("cell_truth_incomplete", f"{scenario}:{scale}")
        sample_count = item.get("labeled_candidate_edge_count")
        if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
            _fail("cell_sample_count_invalid", f"{scenario}:{scale}")
        cell_metrics.append(
            {
                "cell_id": f"{scenario}-{scale}v{scale}",
                "scenario": scenario,
                "scale": scale,
                "sample_count": sample_count,
                **_d6_metric_set(item.get("metrics"), f"{scenario}:{scale} metrics"),
            }
        )

    date = str(evaluation_date).strip()
    if not date:
        _fail("evaluation_date_missing", "evaluation date must be non-empty")
    report: dict[str, Any] = {
        "schema_version": D6_MODEL_EVALUATION_SCHEMA_VERSION,
        "evaluation_date": date,
        "model_id": f"d5-tracklet-internal-{weights_sha256[:16]}",
        "weights_sha256": weights_sha256,
        "config_sha256": config_sha256,
        "training_source_sha256": training_source_sha256,
        "test_seed_values": test_seed_values,
        "test_metrics": test_metrics,
        "cell_metrics": cell_metrics,
        "latency": latency,
    }
    report["content_sha256"] = _sha256_json(report)
    return report


def _d6_metric_set(value: Any, context: str) -> dict[str, float]:
    source = _require_mapping(value, context)
    names = (
        "precision",
        "recall",
        "f1",
        "candidate_recall",
        "false_merge_rate",
        "ece",
    )
    result: dict[str, float] = {}
    for name in names:
        metric = _require_mapping(source.get(name), f"{context} {name}")
        raw = metric.get("value")
        if metric.get("available") is not True or isinstance(raw, bool):
            _fail("model_metric_unavailable", f"{context}:{name}")
        try:
            number = float(raw)
        except (TypeError, ValueError):
            _fail("model_metric_invalid", f"{context}:{name}")
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            _fail("model_metric_invalid", f"{context}:{name}")
        result[name] = number
    return result


def _d6_latency(value: Any) -> dict[str, Any]:
    source = _require_mapping(value, "test latency")
    device = str(source.get("device", "")).strip()
    sample_count = source.get("sample_count")
    if not device:
        _fail("latency_device_missing", "test latency device is missing")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
        _fail("latency_sample_count_invalid", str(sample_count))
    values: list[float] = []
    for name in ("p50_ms", "p95_ms", "max_ms"):
        raw = source.get(name)
        if isinstance(raw, bool):
            _fail("latency_value_invalid", name)
        try:
            number = float(raw)
        except (TypeError, ValueError):
            _fail("latency_value_invalid", name)
        if not math.isfinite(number) or number < 0.0:
            _fail("latency_value_invalid", name)
        values.append(number)
    if not values[0] <= values[1] <= values[2]:
        _fail("latency_order_invalid", str(values))
    return {
        "device": device,
        "sample_count": sample_count,
        "p50_ms": values[0],
        "p95_ms": values[1],
        "max_ms": values[2],
    }


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", context)
    return value


def _require_sha256(value: Any, context: str) -> str:
    digest = str(value).strip().lower()
    if _SHA256_PATTERN.fullmatch(digest) is None:
        _fail("sha256_invalid", context)
    return digest


def render_composite_training_preflight_markdown(report: Mapping[str, Any]) -> str:
    source = report["sources"]
    audit = report["corpus_audit"]
    estimate = report["estimated_resources"]
    return "\n".join(
        [
            "# D5 Composite Tracklet 内部训练预检",
            "",
            "## 结论",
            "",
            "clean composite 数据来源、完整 seed 切分、45 个场景规模单元、标签和同相机互斥审计通过。",
            "本报告没有训练模型，没有生成 `.pt`。内部模型测试、保留 seed 评估和 paired shadow 均未运行，G1/assist 保持关闭。",
            "",
            "## 绑定",
            "",
            f"- composite view SHA-256：`{source['composite_view_sha256']}`",
            f"- admission report SHA-256：`{source['composite_admission_report_sha256']}`",
            f"- formal manifest SHA-256：`{source['formal_manifest_sha256']}`",
            f"- supplemental manifest SHA-256：`{source['supplemental_manifest_sha256']}`",
            f"- profile SHA-256：`{report['profile']['config_sha256']}`",
            "",
            "## 数据",
            "",
            f"- 图帧/候选边：`{audit['episode_count']}` / `{audit['candidate_edge_count']}`",
            f"- seed：`{audit['seed_count_by_split']}`，保留 seed 重叠 `{audit['reserved_evaluation_seed_overlap']}`",
            f"- 每个 split 场景规模 cell：`{audit['scenario_scale_cell_count_by_split']}`",
            f"- 同相机候选边：`{audit['identity_safety']['same_camera_candidate_edge_count']}`",
            "",
            "## 资源估算",
            "",
            f"- 训练图呈现次数：`{estimate['training_graph_presentations']}`",
            f"- CPU 预计耗时：`{estimate['estimated_cpu_wall_time']}`",
            f"- 峰值内存建议：`{estimate['recommended_memory']}`",
            f"- 新增 bundle/report：`{estimate['estimated_output_storage']}`",
            "",
            "## 后续门",
            "",
            "clean detached worktree 执行内部训练后，仍须通过固定 test 指标门。保留 seed `1000-1019` 与 paired shadow 完成前，任何内部测试结果都不得开放 G1、assist 或相机控制权限。",
            "",
        ]
    )


def render_internal_training_markdown(report: Mapping[str, Any]) -> str:
    layers = report["layers"]
    internal = layers["internal_model_test"]
    return "\n".join(
        [
            "# D5 Composite Tracklet 内部开发训练",
            "",
            "## 状态",
            "",
            f"内部模型测试状态为 `{internal['status']}`。bundle 永久标记为 development/shadow-only。",
            "保留 seed 和 paired shadow 未完成，G1、assist 与在线/相机控制权限均关闭。",
            "",
            "## 分层准入",
            "",
            f"- data_support：`{layers['data_support']['status']}`",
            f"- internal_model_test：`{internal['status']}`",
            f"- held_out_1000_1019：`{layers['held_out_1000_1019']['status']}`",
            f"- paired_shadow：`{layers['paired_shadow']['status']}`",
            f"- G1/assist：`{layers['g1_assist']['status']}`",
            "",
        ]
    )


def _load_bound_admission_report(
    path: Path,
    admission: LoadedTrackletCompositeAdmission,
) -> dict[str, Any]:
    payload = _read_json(path)
    content_sha = payload.get("content_sha256")
    unhashed = dict(payload)
    unhashed.pop("content_sha256", None)
    if content_sha != _sha256_json(unhashed):
        _fail("admission_report_content_hash_mismatch", str(path))
    expected = dict(admission.readiness)
    expected["view_manifest_sha256"] = admission.view_manifest_sha256
    expected["view_content_sha256"] = admission.view_manifest["content_sha256"]
    expected["content_sha256"] = _sha256_json(expected)
    if payload != expected:
        _fail("admission_report_view_mismatch", str(path))
    return payload


def _source_binding(corpus: LoadedCompositeTrainingCorpus) -> dict[str, Any]:
    sources = corpus.admission.readiness["sources"]
    return {
        "composite_view_sha256": corpus.admission.view_manifest_sha256,
        "composite_view_content_sha256": corpus.admission.view_manifest["content_sha256"],
        "composite_admission_report_sha256": corpus.admission_report_sha256,
        "formal_manifest_sha256": sources["formal_manifest_sha256"],
        "supplemental_manifest_sha256": sources["supplemental_manifest_sha256"],
        "supplemental_source_repository_dirty": sources[
            "supplemental_source_repository_dirty"
        ],
        "hash_bound_dirty_source_accepted": (
            corpus.hash_bound_dirty_source_accepted
        ),
        "source_samples_copied_or_rewritten": False,
    }


def _untrained_layers() -> dict[str, Any]:
    return {
        "data_support": {"status": "pass", "passed": True},
        "internal_model_test": {
            "status": "not_run",
            "passed": False,
            "reason": "clean_internal_model_not_trained",
        },
        "held_out_1000_1019": {
            "status": "not_run",
            "passed": False,
        },
        "paired_shadow": {"status": "not_run", "passed": False},
        "g1_assist": {
            "status": "fail_closed",
            "passed": False,
            "eligible": False,
            "authority_enabled": False,
            "blockers": [
                "internal_model_test_not_run",
                "held_out_1000_1019_not_run",
                "paired_shadow_not_run",
            ],
        },
    }


def _trained_layers(internal: Mapping[str, Any], *, smoke: bool) -> dict[str, Any]:
    blockers = ["held_out_1000_1019_not_run", "paired_shadow_not_run"]
    if not internal["passed"]:
        blockers.insert(0, "internal_model_test_not_passed")
    if smoke:
        blockers.insert(0, "dirty_smoke_weights_forbidden")
    return {
        "data_support": {"status": "pass", "passed": True},
        "internal_model_test": dict(internal),
        "held_out_1000_1019": {"status": "not_run", "passed": False},
        "paired_shadow": {"status": "not_run", "passed": False},
        "g1_assist": {
            "status": "fail_closed",
            "passed": False,
            "eligible": False,
            "authority_enabled": False,
            "blockers": blockers,
        },
    }


def _evaluate_test_scenario_cells(
    dataset: LoadedTrackletDataset,
    *,
    bundle_dir: Path,
    config: TrackletTrainingConfig,
) -> list[dict[str, Any]]:
    scorer = load_tracklet_model_bundle(
        bundle_dir,
        device=config.device,
        expected_dataset_manifest_sha256=dataset.manifest_sha256,
        expected_split_sha256=str(dataset.manifest["split_sha256"]),
        expected_training_set_sha256=str(dataset.manifest["training_set_sha256"]),
    )
    groups: dict[tuple[str, int], list[LoadedTrackletEpisode]] = {}
    for episode in dataset.split("test"):
        groups.setdefault(_scenario_scale(episode.graph.scenario_version), []).append(episode)
    records: list[dict[str, Any]] = []
    for scenario, scale in FORMAL_SCENARIO_CELLS:
        episodes = tuple(groups[(scenario, scale)])
        view = LoadedTrackletDataset(
            root=dataset.root,
            manifest=dataset.manifest,
            manifest_sha256=dataset.manifest_sha256,
            episodes=episodes,
        )
        result = evaluate_tracklet_edge_model(
            view,
            scorer.model,
            split="test",
            temperature=scorer.temperature,
            decision_threshold=scorer.decision_threshold,
            device=config.device,
            ece_bins=config.ece_bins,
            latency_repeats=1,
            model_size_bytes=(bundle_dir / "weights.pt").stat().st_size,
        )
        records.append({"scenario": scenario, "scale": scale, **result})
    return records


def _smoke_training_view(dataset: LoadedTrackletDataset) -> LoadedTrackletDataset:
    selected: list[LoadedTrackletEpisode] = []
    for split in _SPLITS:
        positive = 0
        negative = 0
        for episode in dataset.split(split):
            if episode.graph.edge_count == 0:
                continue
            selected.append(episode)
            positive += episode.class_balance["positive_candidate_edges"]
            negative += episode.class_balance["negative_candidate_edges"]
            if positive > 0 and negative > 0 and sum(
                item.split == split for item in selected
            ) >= 4:
                break
        if positive <= 0 or negative <= 0:
            _fail("smoke_split_missing_class", split)
    payload = {
        "source_manifest_sha256": dataset.manifest_sha256,
        "profile": COMPOSITE_SMOKE_TRAINING_PROFILE_VERSION,
        "episodes": [item.graph.episode_uid for item in selected],
    }
    manifest = dict(dataset.manifest)
    manifest["config_sha256"] = _sha256_json(payload)
    manifest["split_sha256"] = _sha256_json(
        {"split": [(item.graph.episode_uid, item.split) for item in selected]}
    )
    manifest["training_set_sha256"] = _sha256_json(
        {
            "train": [
                item.graph.episode_uid for item in selected if item.split == "train"
            ]
        }
    )
    return LoadedTrackletDataset(
        root=dataset.root,
        manifest=MappingProxyType(manifest),
        manifest_sha256=_sha256_json(manifest),
        episodes=tuple(selected),
    )


def _composite_training_view(
    dataset: LoadedTrackletDataset,
) -> LoadedTrackletDataset:
    """Add training-only provenance to an immutable in-memory manifest view."""

    manifest = dict(dataset.manifest)
    manifest["hard_negative_provenance"] = [
        {
            "source": "formal_complete_frames_after_existing_geometry_candidate_gate",
            "truth_use": "offline_evaluator_labels_only",
        },
        {
            "source": "supplemental_physical_projection_after_default_geometry_gates",
            "truth_use": "offline_exact_observation_lineage_only",
        },
    ]
    manifest["composite_training_adapter"] = {
        "profile_version": COMPOSITE_INTERNAL_TRAINING_PROFILE_VERSION,
        "source_manifest_sha256": dataset.manifest_sha256,
        "source_samples_copied_or_rewritten": False,
    }
    return LoadedTrackletDataset(
        root=dataset.root,
        manifest=MappingProxyType(manifest),
        manifest_sha256=_sha256_json(manifest),
        episodes=dataset.episodes,
    )


def _estimated_resources(
    corpus: LoadedCompositeTrainingCorpus,
    profile: CompositeInternalTrainingProfile,
) -> dict[str, Any]:
    train_graphs = sum(
        episode.split == "train" for episode in corpus.dataset.episodes
    )
    return {
        "training_graph_count": train_graphs,
        "epochs": profile.training.epochs,
        "training_graph_presentations": train_graphs * profile.training.epochs,
        "estimated_cpu_wall_time": "20-45 min on the current 30 GiB workstation; verify in clean run",
        "recommended_memory": ">=4 GiB available; strict composite load observed below 1 GiB RSS",
        "estimated_output_storage": "<2 MiB for weights, manifests, and reports; source corpus is not copied",
    }


def _validate_profile(
    profile: CompositeInternalTrainingProfile,
    *,
    smoke: bool,
    robust_v2: bool = False,
) -> None:
    expected = (
        SMOKE_TRAINING_PROFILE
        if smoke
        else ROBUST_TRAINING_PROFILE
        if robust_v2
        else PRODUCTION_TRAINING_PROFILE
    )
    if profile.to_payload() != expected.to_payload():
        _fail("model_config_drift", "model, feature, gate, seed, or thread profile changed")


def _configure_threads(profile: CompositeInternalTrainingProfile) -> None:
    os.environ["OMP_NUM_THREADS"] = str(profile.torch_num_threads)
    os.environ["MKL_NUM_THREADS"] = str(profile.torch_num_threads)
    torch.set_num_threads(profile.torch_num_threads)
    if torch.get_num_threads() != profile.torch_num_threads:
        _fail("thread_configuration_failed", str(torch.get_num_threads()))


def _scenario_scale(value: str) -> tuple[str, int]:
    match = _SCENARIO_SCALE_PATTERN.fullmatch(str(value))
    if match is None:
        _fail("scenario_version_invalid", str(value))
    resources = int(match.group("resources"))
    targets = int(match.group("targets"))
    if resources != targets:
        _fail("scenario_scale_not_square", str(value))
    return match.group("scenario"), resources


def _implementation_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {name: sha256_file(root / name) for name in _IMPLEMENTATION_FILES}


def _assert_training_output_detached(
    output: Path,
    corpus: LoadedCompositeTrainingCorpus,
) -> None:
    roots = (
        corpus.formal_dataset_root.resolve(),
        corpus.supplemental_root.resolve(),
        corpus.admission.view_manifest_path.resolve(),
        corpus.admission_report_path.resolve(),
    )
    for root in roots:
        if output == root or root in output.parents or output in root.parents:
            _fail("training_output_overlaps_source", f"{output} vs {root}")


def _validate_commit(value: str) -> str:
    commit = str(value).strip().lower()
    if _COMMIT_PATTERN.fullmatch(commit) is None:
        _fail("git_commit_invalid", str(value))
    return commit


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


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _fail("json_read_failed", f"{path}: {error}")
    if not isinstance(value, dict):
        _fail("json_object_required", str(path))
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    text = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    _write_text_atomic(path, text)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fail(code: str, message: str) -> None:
    raise CompositeInternalTrainingError(code, message)


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--formal-dataset", required=True)
    parser.add_argument("--supplemental-root", required=True)
    parser.add_argument("--training-seed-registry", required=True)
    parser.add_argument("--shared-seed-registry", required=True)
    parser.add_argument("--composite-view", required=True)
    parser.add_argument("--composite-admission-report", required=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit or train the D5 clean composite tracklet corpus"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    _add_source_arguments(preflight)
    preflight.add_argument("--output-json", required=True)
    preflight.add_argument("--output-markdown", required=True)
    train = subparsers.add_parser("train")
    _add_source_arguments(train)
    train.add_argument("--output-dir", required=True)
    train.add_argument("--smoke", action="store_true")
    train.add_argument("--robust-v2", action="store_true")
    train.add_argument(
        "--allow-hash-bound-dirty-source",
        action="store_true",
        help=(
            "allow only robust-v2 development training from an exact-hash-bound "
            "dirty source tree; no clean-source claim is emitted"
        ),
    )
    args = parser.parse_args(argv)
    corpus = load_composite_training_corpus(
        formal_dataset_dir=args.formal_dataset,
        supplemental_root=args.supplemental_root,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        composite_view_manifest_path=args.composite_view,
        composite_admission_report_path=args.composite_admission_report,
        allow_hash_bound_dirty_source=bool(
            args.command == "train"
            and getattr(args, "allow_hash_bound_dirty_source", False)
        ),
    )
    commit, dirty = _git_provenance()
    if args.command == "preflight":
        report = build_composite_training_preflight(
            corpus,
            implementation_git_commit=commit,
            implementation_repository_dirty=dirty,
        )
        hashes = write_composite_training_preflight(
            report,
            json_path=args.output_json,
            markdown_path=args.output_markdown,
        )
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "json_sha256": hashes[0],
                    "markdown_sha256": hashes[1],
                    "g1_assist_eligible": False,
                },
                sort_keys=True,
            )
        )
        return 0
    report = run_composite_internal_development_training(
        corpus,
        args.output_dir,
        implementation_git_commit=commit,
        implementation_repository_dirty=dirty,
        smoke=args.smoke,
        robust_v2=args.robust_v2,
        allow_hash_bound_dirty_source=args.allow_hash_bound_dirty_source,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "internal_model_test": report["layers"]["internal_model_test"][
                    "status"
                ],
                "g1_assist_eligible": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "COMPOSITE_INTERNAL_TRAINING_PROFILE_VERSION",
    "COMPOSITE_ROBUST_TRAINING_PROFILE_VERSION",
    "COMPOSITE_INTERNAL_TRAINING_SCHEMA_VERSION",
    "COMPOSITE_TRAINING_PREFLIGHT_SCHEMA_VERSION",
    "D6_MODEL_EVALUATION_DATE",
    "D6_MODEL_EVALUATION_FILENAME",
    "D6_MODEL_EVALUATION_SCHEMA_VERSION",
    "CompositeInternalTrainingError",
    "CompositeInternalTrainingProfile",
    "LoadedCompositeTrainingCorpus",
    "PRODUCTION_TRAINING_PROFILE",
    "ROBUST_TRAINING_PROFILE",
    "SMOKE_TRAINING_PROFILE",
    "assess_internal_model_test",
    "audit_composite_training_dataset",
    "build_d6_model_evaluation_report",
    "build_composite_training_preflight",
    "load_composite_training_corpus",
    "run_composite_internal_development_training",
    "write_composite_training_preflight",
]
