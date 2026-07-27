"""Evaluator-only paired shadow for deterministic and frozen GNN edge scoring.

The evaluator loads each held-out graph once, builds one immutable graph view,
and sends that same view to the current deterministic geometry rule and a
strictly loaded frozen model bundle.  Both arms use the existing constrained
clustering implementation.  Evaluator truth is used only after inference to
score edges and clusters; it never enters either arm's feature path.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import time
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import uuid

import numpy as np
import torch

from .scalable_3d_adapter import (
    Scalable3DAdapterConfig,
    _deterministic_edge_probabilities,
    _score_graph_edges,
)
from .sparse_tracklet_graph import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    SparseTrackletGraph,
    constrained_tracklet_clusters,
)
from .tracklet_dataset import sha256_file
from .tracklet_heldout_evaluation import (
    HELDOUT_CONFIG_FILENAME,
    HELDOUT_MANIFEST_FILENAME,
    HELDOUT_RESERVED_SEEDS,
    LoadedHeldoutEpisode,
    TrackletHeldoutEvaluationError,
    load_tracklet_heldout_corpus,
)
from .tracklet_model_bundle import (
    CHECKSUMS_FILENAME,
    MANIFEST_FILENAME,
    WEIGHTS_FILENAME,
    ModelBundleValidationError,
    load_tracklet_model_bundle,
)
from .tracklet_supplemental_curriculum import FORMAL_SCENARIO_CELLS


PAIRED_SHADOW_SCHEMA_VERSION = "d5.tracklet-paired-shadow.v2"
PAIRED_SHADOW_INPUT_SPEC_SCHEMA_VERSION = "d5.tracklet-paired-shadow-input.v1"
PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION = "d5.tracklet-paired-shadow-lineage.v1"
PAIRED_SHADOW_REPORT_FILENAME = "paired_shadow_report.json"
PAIRED_SHADOW_MARKDOWN_FILENAME = "PAIRED_SHADOW_REPORT_CN.md"
PAIRED_SHADOW_LINEAGE_FILENAME = "paired_episode_lineage.jsonl"
FLOAT_COMPARISON_TOLERANCE = 1.0e-12
MINIMUM_CANDIDATE_RECALL = 0.95
MAXIMUM_FALSE_MERGE_RATE = 0.01
MAXIMUM_MODEL_P95_MS = 100.0
NEAR_DETERMINISTIC_UNIVARIATE_AUC = 0.995
RULE_IMPLEMENTATION = "scalable_3d_adapter._deterministic_edge_probabilities"
CLUSTER_IMPLEMENTATION = "sparse_tracklet_graph.constrained_tracklet_clusters"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SHARED_GLOBAL_TRACK_COUNT_INDEX = EDGE_FEATURE_NAMES.index(
    "shared_global_track_count"
)
_EDGE_FEATURE_INDEX = {
    name: EDGE_FEATURE_NAMES.index(name) for name in EDGE_FEATURE_NAMES
}
_NODE_FEATURE_INDEX = {
    name: NODE_FEATURE_NAMES.index(name) for name in NODE_FEATURE_NAMES
}
ROBUSTNESS_PROFILE_DEFINITIONS: tuple[Mapping[str, Any], ...] = (
    MappingProxyType(
        {
            "profile_id": "asynchronous_timestamp_jitter",
            "purpose": "increase anonymous cross-camera timestamp separation",
            "truth_dependent": False,
            "candidate_graph_rebuilt": False,
        }
    ),
    MappingProxyType(
        {
            "profile_id": "extrinsics_drift",
            "purpose": "increase extrinsics uncertainty and projection residuals",
            "truth_dependent": False,
            "candidate_graph_rebuilt": False,
        }
    ),
    MappingProxyType(
        {
            "profile_id": "occlusion_reappearance_proxy",
            "purpose": "lower anonymous tracklet confidence and increase age after a visibility gap",
            "truth_dependent": False,
            "candidate_graph_rebuilt": False,
        }
    ),
    MappingProxyType(
        {
            "profile_id": "similar_motion_confusers",
            "purpose": "remove most motion and scale-rate separation from every candidate edge",
            "truth_dependent": False,
            "candidate_graph_rebuilt": False,
        }
    ),
    MappingProxyType(
        {
            "profile_id": "independent_bbox_scale_jitter",
            "purpose": "replace exact scale coincidences with label-independent bbox perturbations",
            "truth_dependent": False,
            "candidate_graph_rebuilt": False,
        }
    ),
)
_IMPLEMENTATION_FILES = (
    "scalable_3d_adapter.py",
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_g1_evidence_assembler.py",
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_heldout_evaluation.py",
    "tracklet_paired_shadow.py",
)


class TrackletPairedShadowError(ValueError):
    """Stable fail-closed paired-shadow error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class PairedShadowInputSpec:
    """Explicit paths and out-of-band hashes; no adjacent artifact discovery."""

    heldout_corpus_dir: str | Path
    bundle_dir: str | Path
    heldout_report_path: str | Path
    output_dir: str | Path
    expected_corpus_manifest_sha256: str
    expected_corpus_content_sha256: str
    expected_corpus_config_sha256: str
    expected_bundle_manifest_sha256: str
    expected_bundle_weights_sha256: str
    expected_bundle_checksums_sha256: str
    expected_heldout_report_sha256: str
    expected_heldout_report_content_sha256: str
    evaluated_at_utc: str
    superseded_output_dir: str | Path | None = None
    expected_superseded_report_sha256: str | None = None
    expected_superseded_lineage_sha256: str | None = None
    device: str = "cpu"
    require_full_profile: bool = True

    def __post_init__(self) -> None:
        for name in (
            "heldout_corpus_dir",
            "bundle_dir",
            "heldout_report_path",
            "output_dir",
        ):
            object.__setattr__(self, name, Path(getattr(self, name)).resolve())
        for name in (
            "expected_corpus_manifest_sha256",
            "expected_corpus_content_sha256",
            "expected_corpus_config_sha256",
            "expected_bundle_manifest_sha256",
            "expected_bundle_weights_sha256",
            "expected_bundle_checksums_sha256",
            "expected_heldout_report_sha256",
            "expected_heldout_report_content_sha256",
        ):
            value = str(getattr(self, name)).strip().lower()
            if not _SHA256_PATTERN.fullmatch(value):
                raise TrackletPairedShadowError(
                    "input_sha256_invalid", f"{name} must be a lowercase SHA-256"
                )
            object.__setattr__(self, name, value)
        superseded_values = (
            self.superseded_output_dir,
            self.expected_superseded_report_sha256,
            self.expected_superseded_lineage_sha256,
        )
        if any(value is not None for value in superseded_values) and not all(
            value is not None for value in superseded_values
        ):
            raise TrackletPairedShadowError(
                "superseded_evidence_spec_incomplete",
                "superseded output path and both expected hashes are required together",
            )
        if self.superseded_output_dir is not None:
            object.__setattr__(
                self,
                "superseded_output_dir",
                Path(self.superseded_output_dir).resolve(),
            )
            for name in (
                "expected_superseded_report_sha256",
                "expected_superseded_lineage_sha256",
            ):
                value = str(getattr(self, name)).strip().lower()
                if not _SHA256_PATTERN.fullmatch(value):
                    raise TrackletPairedShadowError(
                        "input_sha256_invalid", f"{name} must be a lowercase SHA-256"
                    )
                object.__setattr__(self, name, value)
        timestamp = str(self.evaluated_at_utc).strip()
        if not timestamp:
            raise TrackletPairedShadowError(
                "evaluated_at_missing", "evaluated_at_utc must be non-empty"
            )
        object.__setattr__(self, "evaluated_at_utc", timestamp)
        torch.device(self.device)

    def to_payload(self) -> dict[str, Any]:
        expected_hashes = {
            "corpus_manifest_sha256": self.expected_corpus_manifest_sha256,
            "corpus_content_sha256": self.expected_corpus_content_sha256,
            "corpus_config_sha256": self.expected_corpus_config_sha256,
            "bundle_manifest_sha256": self.expected_bundle_manifest_sha256,
            "bundle_weights_sha256": self.expected_bundle_weights_sha256,
            "bundle_checksums_sha256": self.expected_bundle_checksums_sha256,
            "heldout_report_sha256": self.expected_heldout_report_sha256,
            "heldout_report_content_sha256": self.expected_heldout_report_content_sha256,
        }
        superseded_evidence = None
        if self.superseded_output_dir is not None:
            expected_hashes.update(
                {
                    "superseded_report_sha256": self.expected_superseded_report_sha256,
                    "superseded_lineage_sha256": self.expected_superseded_lineage_sha256,
                }
            )
            superseded_evidence = {
                "directory": str(self.superseded_output_dir),
                "expected_report_sha256": self.expected_superseded_report_sha256,
                "expected_lineage_sha256": self.expected_superseded_lineage_sha256,
            }
        return {
            "schema_version": PAIRED_SHADOW_INPUT_SPEC_SCHEMA_VERSION,
            "heldout_corpus_dir": str(self.heldout_corpus_dir),
            "bundle_dir": str(self.bundle_dir),
            "heldout_report_path": str(self.heldout_report_path),
            "output_dir": str(self.output_dir),
            "expected_hashes": expected_hashes,
            "superseded_evidence": superseded_evidence,
            "evaluated_at_utc": self.evaluated_at_utc,
            "device": str(self.device),
            "require_full_profile": bool(self.require_full_profile),
        }


@dataclass(frozen=True)
class _ShadowNode:
    tracklet_key: str
    camera_key: str


@dataclass(frozen=True)
class _ShadowEdge:
    source_index: int
    target_index: int
    source_tracklet_key: str
    target_tracklet_key: str
    shared_global_track_ids: tuple[str, ...]
    gate_score: float


def run_tracklet_paired_shadow(spec: PairedShadowInputSpec) -> Mapping[str, Any]:
    """Run the paired evaluator and atomically publish pass or fail-closed evidence."""

    destination = Path(spec.output_dir)
    _validate_destination(spec)
    if destination.exists():
        _fail("paired_shadow_destination_exists", str(destination))
    started = time.perf_counter()
    try:
        report, lineage = _evaluate(spec, started)
    except Exception as exc:  # The evaluator must preserve a stable fail-closed artifact.
        code = _exception_code(exc)
        report = _failure_report(spec, started, code, str(exc))
        lineage = ()
    _publish(destination, report, lineage)
    return MappingProxyType(report)


def _evaluate(
    spec: PairedShadowInputSpec,
    started: float,
) -> tuple[dict[str, Any], tuple[Mapping[str, Any], ...]]:
    actual_before = _validate_explicit_inputs(spec)
    corpus = load_tracklet_heldout_corpus(
        spec.heldout_corpus_dir,
        require_full_profile=spec.require_full_profile,
    )
    scorer = load_tracklet_model_bundle(spec.bundle_dir, device=spec.device)
    admission = scorer.manifest.get("admission", {})
    if admission.get("status") != "development_only_fail_closed":
        _fail("development_bundle_required", str(admission.get("status")))
    if admission.get("default_model") is not False or admission.get(
        "g1_assist_eligible"
    ) is not False:
        _fail("development_bundle_authority_invalid", str(admission))

    rule_config = Scalable3DAdapterConfig()
    if not corpus.episodes:
        _fail("heldout_corpus_empty", str(spec.heldout_corpus_dir))
    runtime_fallback = _runtime_fallback_probe(
        _shared_graph_view(corpus.episodes[0]),
        rule_config,
    )
    records: list[Mapping[str, Any]] = []
    for episode in corpus.episodes:
        records.append(
            _evaluate_episode(
                episode,
                scorer=scorer,
                rule_config=rule_config,
            )
        )

    feature_label_diagnostics = _feature_label_diagnostics(corpus.episodes)
    actual_after = _actual_input_hashes(spec)
    immutable_inputs = actual_after == actual_before
    by_seed = [
        _aggregate_group(
            [record for record in records if int(record["seed"]) == seed],
            group_id=f"seed-{seed}",
        )
        for seed in sorted({int(record["seed"]) for record in records})
    ]
    by_cell = [
        _aggregate_group(
            [
                record
                for record in records
                if record["scenario"] == scenario and int(record["scale"]) == scale
            ],
            group_id=f"{scenario}-{scale}v{scale}",
            scenario=scenario,
            scale=scale,
        )
        for scenario, scale in FORMAL_SCENARIO_CELLS
        if any(
            record["scenario"] == scenario and int(record["scale"]) == scale
            for record in records
        )
    ]
    overall = _aggregate_group(records, group_id="overall")
    robustness_profiles = _aggregate_robustness_profiles(records)
    safety = _safety_summary(records, corpus.manifest)
    identity = _identity_summary(records)
    catalog = _catalog_summary(records, corpus.manifest["profile"])
    expected_episode_count = (
        len(HELDOUT_RESERVED_SEEDS) * len(FORMAL_SCENARIO_CELLS)
        if spec.require_full_profile
        else int(corpus.manifest["profile"]["expected_frame_count"])
    )
    expected_seed_count = (
        len(HELDOUT_RESERVED_SEEDS)
        if spec.require_full_profile
        else len(corpus.manifest["profile"]["seeds"])
    )
    expected_cell_count = (
        len(FORMAL_SCENARIO_CELLS)
        if spec.require_full_profile
        else len(corpus.manifest["profile"]["scenario_cells"])
    )
    assessment = _assessment(
        overall=overall,
        cell_metrics=by_cell,
        identity=identity,
        safety=safety,
        immutable_inputs=immutable_inputs,
        actual_episode_count=len(records),
        expected_episode_count=expected_episode_count,
        actual_seed_count=len(by_seed),
        expected_seed_count=expected_seed_count,
        actual_cell_count=len(by_cell),
        expected_cell_count=expected_cell_count,
        catalog=catalog,
        robustness_profiles=robustness_profiles,
        runtime_fallback=runtime_fallback,
    )
    wall_seconds = time.perf_counter() - started
    report: dict[str, Any] = {
        "schema_version": PAIRED_SHADOW_SCHEMA_VERSION,
        "evaluated_at_utc": spec.evaluated_at_utc,
        "status": assessment["status"],
        "execution_completed": True,
        "evaluation_role": "evaluator_only_paired_shadow",
        "input_spec": spec.to_payload(),
        "input_spec_sha256": _sha256_json(spec.to_payload()),
        "input_hashes_before": actual_before,
        "input_hashes_after": actual_after,
        "input_artifacts_unchanged": immutable_inputs,
        "evidence_status": _evidence_status(
            spec,
            passed=True,
            actual_hashes=actual_after,
        ),
        "heldout_lineage_binding": {
            "report_used_for_predictions": False,
            "report_used_for_lineage_only": True,
            "corpus_manifest_sha256": corpus.manifest_sha256,
            "corpus_content_sha256": corpus.manifest["content_sha256"],
            "bundle_manifest_sha256": scorer.bundle_manifest_sha256,
            "bundle_weights_sha256": scorer.bundle_weights_sha256,
        },
        "frozen_decision": {
            "rule_implementation": RULE_IMPLEMENTATION,
            "rule_probability_temperature": rule_config.rule_probability_temperature,
            "rule_single_projection_probability_floor": (
                rule_config.rule_single_projection_probability_floor
            ),
            "rule_decision_threshold": rule_config.edge_probability_threshold,
            "model_temperature": scorer.temperature,
            "model_decision_threshold": scorer.decision_threshold,
            "temperature_reestimated": False,
            "threshold_reselected": False,
            "weights_updated": False,
            "candidate_gate_changed": False,
            "cluster_implementation": CLUSTER_IMPLEMENTATION,
        },
        "totals": {
            "episode_count": len(records),
            "seed_count": len(by_seed),
            "scenario_scale_cell_count": len(by_cell),
            "node_count": sum(int(record["node_count"]) for record in records),
            "candidate_edge_count": sum(
                int(record["candidate_edge_count"]) for record in records
            ),
            "labeled_candidate_edge_count": sum(
                int(record["labeled_candidate_edge_count"]) for record in records
            ),
        },
        "graph_identity": identity,
        "catalog_integrity": catalog,
        "feature_label_diagnostics": feature_label_diagnostics,
        "robustness_profiles": robustness_profiles,
        "runtime_fallback_probe": runtime_fallback,
        "overall": overall,
        "seed_metrics": by_seed,
        "cell_metrics": by_cell,
        "identity_and_truth_safety": safety,
        "paired_shadow_assessment": assessment,
        "runtime": {
            "wall_seconds": wall_seconds,
            "max_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "max_rss_mib": float(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
            ),
            "device": str(scorer.device),
            "cuda_available": bool(torch.cuda.is_available()),
            "cpu_count": os.cpu_count(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
        },
        "implementation_sha256": _implementation_hashes(),
        "authority": {
            "status": "pending_d6_external_audit",
            "paired_shadow_passed": assessment["passed"],
            "g1": False,
            "assist": False,
            "authority": False,
            "rule_fallback": True,
            "runtime_default_changed": False,
        },
    }
    return report, tuple(records)


def _evaluate_episode(
    episode: LoadedHeldoutEpisode,
    *,
    scorer: Any,
    rule_config: Scalable3DAdapterConfig,
) -> Mapping[str, Any]:
    loaded = episode.graph
    graph = _shared_graph_view(episode)
    graph_arrays_sha256 = _graph_arrays_sha256(graph)
    loaded_arrays_sha256 = _loaded_graph_arrays_sha256(loaded)
    candidate_edge_sha256 = _candidate_edges_sha256(graph)

    control_started = time.perf_counter()
    control_probabilities = _deterministic_edge_probabilities(graph, rule_config)
    control_scoring_ms = (time.perf_counter() - control_started) * 1000.0
    graph_after_control_sha256 = _graph_arrays_sha256(graph)
    candidates_after_control_sha256 = _candidate_edges_sha256(graph)

    model_started = time.perf_counter()
    model_probabilities_tensor = scorer.forward_graph(graph)
    if scorer.device.type == "cuda":
        torch.cuda.synchronize(scorer.device)
    model_scoring_ms = (time.perf_counter() - model_started) * 1000.0
    graph_after_model_sha256 = _graph_arrays_sha256(graph)
    candidates_after_model_sha256 = _candidate_edges_sha256(graph)
    model_probabilities = (
        model_probabilities_tensor.detach().cpu().numpy().astype(np.float64, copy=False)
    )
    if control_probabilities.shape != (graph.edge_count,) or model_probabilities.shape != (
        graph.edge_count,
    ):
        _fail("paired_probability_shape_mismatch", loaded.episode_uid)
    if not np.all(np.isfinite(control_probabilities)) or not np.all(
        np.isfinite(model_probabilities)
    ):
        _fail("paired_probability_non_finite", loaded.episode_uid)

    control_cluster_started = time.perf_counter()
    control_clusters = constrained_tracklet_clusters(
        graph,
        control_probabilities,
        probability_threshold=rule_config.edge_probability_threshold,
    )
    control_cluster_ms = (time.perf_counter() - control_cluster_started) * 1000.0
    model_cluster_started = time.perf_counter()
    model_clusters = constrained_tracklet_clusters(
        graph,
        model_probabilities,
        probability_threshold=scorer.decision_threshold,
    )
    model_cluster_ms = (time.perf_counter() - model_cluster_started) * 1000.0
    robustness_runs = _run_robustness_profiles(
        graph,
        episode_uid=loaded.episode_uid,
        scorer=scorer,
        rule_config=rule_config,
    )
    graph_after_clustering_sha256 = _graph_arrays_sha256(graph)
    candidates_after_clustering_sha256 = _candidate_edges_sha256(graph)

    graph_checkpoints = (
        loaded_arrays_sha256,
        graph_arrays_sha256,
        graph_after_control_sha256,
        graph_after_model_sha256,
        graph_after_clustering_sha256,
    )
    if len(set(graph_checkpoints)) != 1:
        _fail("paired_graph_identity_mismatch", loaded.episode_uid)
    candidate_checkpoints = (
        candidate_edge_sha256,
        candidates_after_control_sha256,
        candidates_after_model_sha256,
        candidates_after_clustering_sha256,
    )
    if len(set(candidate_checkpoints)) != 1:
        _fail("paired_candidate_identity_mismatch", loaded.episode_uid)

    # Evaluator truth is first accessed for scoring only after both arms have
    # completed probability inference and constrained clustering.
    labels = episode.evaluator_labels.by_tracklet_key
    labels_before_sha256 = _evaluator_labels_sha256(labels)
    targets, unlabeled_count = _targets(graph, labels)
    candidate_numerator, candidate_denominator = _candidate_recall_counts(graph, labels)

    control = _arm_episode_metrics(
        graph,
        labels,
        targets,
        control_probabilities,
        control_clusters,
        threshold=rule_config.edge_probability_threshold,
        scoring_latency_ms=control_scoring_ms,
        clustering_latency_ms=control_cluster_ms,
    )
    model = _arm_episode_metrics(
        graph,
        labels,
        targets,
        model_probabilities,
        model_clusters,
        threshold=scorer.decision_threshold,
        scoring_latency_ms=model_scoring_ms,
        clustering_latency_ms=model_cluster_ms,
    )
    robustness_profiles: dict[str, Any] = {}
    for profile_id, run in robustness_runs.items():
        profile_graph = run["graph"]
        robustness_profiles[profile_id] = {
            "profile": dict(run["profile"]),
            "transform": dict(run["transform"]),
            "graph_sha256": run["graph_sha256"],
            "graph_identity_match": bool(run["graph_identity_match"]),
            "candidate_identity_match": bool(run["candidate_identity_match"]),
            "truth_used_for_transform": False,
            "control": _arm_episode_metrics(
                profile_graph,
                labels,
                targets,
                run["control_probabilities"],
                run["control_clusters"],
                threshold=rule_config.edge_probability_threshold,
                scoring_latency_ms=run["control_scoring_ms"],
                clustering_latency_ms=run["control_cluster_ms"],
            ),
            "model": _arm_episode_metrics(
                profile_graph,
                labels,
                targets,
                run["model_probabilities"],
                run["model_clusters"],
                threshold=scorer.decision_threshold,
                scoring_latency_ms=run["model_scoring_ms"],
                clustering_latency_ms=run["model_cluster_ms"],
            ),
        }
    labels_after_sha256 = _evaluator_labels_sha256(labels)
    control["probabilities_sha256"] = _array_sha256(control_probabilities)
    model["probabilities_sha256"] = _array_sha256(model_probabilities)
    return MappingProxyType(
        {
            "schema_version": PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
            "episode_uid": loaded.episode_uid,
            "seed": loaded.seed,
            "scenario": episode.scenario,
            "scale": episode.scale,
            "graph_sha256": episode.graph_sha256,
            "labels_sha256": episode.labels_sha256,
            "loaded_graph_instance_count": 1,
            "node_count": graph.node_count,
            "candidate_edge_count": graph.edge_count,
            "labeled_candidate_edge_count": graph.edge_count - unlabeled_count,
            "unlabeled_candidate_edge_count": unlabeled_count,
            "candidate_recall_numerator": candidate_numerator,
            "candidate_recall_denominator": candidate_denominator,
            "candidate_recall": _ratio(candidate_numerator, candidate_denominator),
            "source_arrays_sha256": loaded_arrays_sha256,
            "shared_arrays_sha256": graph_arrays_sha256,
            "graph_after_control_sha256": graph_after_control_sha256,
            "graph_after_model_sha256": graph_after_model_sha256,
            "graph_after_clustering_sha256": graph_after_clustering_sha256,
            "control_graph_sha256": episode.graph_sha256,
            "model_graph_sha256": episode.graph_sha256,
            "control_candidate_edge_sha256": candidate_edge_sha256,
            "model_candidate_edge_sha256": candidate_edge_sha256,
            "control_labels_sha256": episode.labels_sha256,
            "model_labels_sha256": episode.labels_sha256,
            "evaluator_labels_before_sha256": labels_before_sha256,
            "evaluator_labels_after_sha256": labels_after_sha256,
            "graph_identity_match": len(set(graph_checkpoints)) == 1,
            "candidate_identity_match": len(set(candidate_checkpoints)) == 1,
            "label_identity_match": labels_before_sha256 == labels_after_sha256,
            "truth_scoring_started_after_both_arm_predictions": True,
            "same_camera_candidate_edge_count": _same_camera_candidate_edge_count(
                graph
            ),
            "control": control,
            "model": model,
            "robustness_profiles": robustness_profiles,
        }
    )


def _run_robustness_profiles(
    graph: SparseTrackletGraph,
    *,
    episode_uid: str,
    scorer: Any,
    rule_config: Scalable3DAdapterConfig,
) -> dict[str, dict[str, Any]]:
    """Run label-independent counterfactual graphs through both frozen arms."""

    results: dict[str, dict[str, Any]] = {}
    for profile in ROBUSTNESS_PROFILE_DEFINITIONS:
        profile_id = str(profile["profile_id"])
        profile_graph, transform = _counterfactual_graph(
            graph,
            profile_id=profile_id,
            episode_uid=episode_uid,
        )
        graph_before = _graph_arrays_sha256(profile_graph)
        candidates_before = _candidate_edges_sha256(profile_graph)

        control_started = time.perf_counter()
        control_probabilities = _deterministic_edge_probabilities(
            profile_graph, rule_config
        )
        control_scoring_ms = (time.perf_counter() - control_started) * 1000.0
        control_cluster_started = time.perf_counter()
        control_clusters = constrained_tracklet_clusters(
            profile_graph,
            control_probabilities,
            probability_threshold=rule_config.edge_probability_threshold,
        )
        control_cluster_ms = (
            time.perf_counter() - control_cluster_started
        ) * 1000.0

        model_started = time.perf_counter()
        model_tensor = scorer.forward_graph(profile_graph)
        if scorer.device.type == "cuda":
            torch.cuda.synchronize(scorer.device)
        model_scoring_ms = (time.perf_counter() - model_started) * 1000.0
        model_probabilities = (
            model_tensor.detach().cpu().numpy().astype(np.float64, copy=False)
        )
        if model_probabilities.shape != (profile_graph.edge_count,):
            _fail(
                "robustness_probability_shape_mismatch",
                f"{episode_uid}:{profile_id}",
            )
        if not np.all(np.isfinite(model_probabilities)):
            _fail(
                "robustness_probability_non_finite",
                f"{episode_uid}:{profile_id}",
            )
        model_cluster_started = time.perf_counter()
        model_clusters = constrained_tracklet_clusters(
            profile_graph,
            model_probabilities,
            probability_threshold=scorer.decision_threshold,
        )
        model_cluster_ms = (
            time.perf_counter() - model_cluster_started
        ) * 1000.0

        graph_after = _graph_arrays_sha256(profile_graph)
        candidates_after = _candidate_edges_sha256(profile_graph)
        results[profile_id] = {
            "profile": profile,
            "transform": transform,
            "graph": profile_graph,
            "graph_sha256": graph_before,
            "graph_identity_match": graph_before == graph_after,
            "candidate_identity_match": candidates_before == candidates_after,
            "control_probabilities": control_probabilities,
            "control_clusters": control_clusters,
            "control_scoring_ms": control_scoring_ms,
            "control_cluster_ms": control_cluster_ms,
            "model_probabilities": model_probabilities,
            "model_clusters": model_clusters,
            "model_scoring_ms": model_scoring_ms,
            "model_cluster_ms": model_cluster_ms,
        }
    return results


def _counterfactual_graph(
    graph: SparseTrackletGraph,
    *,
    profile_id: str,
    episode_uid: str,
) -> tuple[SparseTrackletGraph, Mapping[str, Any]]:
    """Create one anonymous, deterministic post-gate stress view.

    The candidate topology and gate scores remain fixed.  These views are
    diagnostic counterfactuals, not claims that the original physical
    projection pipeline generated the perturbed measurements.
    """

    node_features = np.array(graph.node_features, dtype=np.float32, copy=True)
    edge_features = np.array(graph.edge_features, dtype=np.float32, copy=True)
    seed_material = hashlib.sha256(
        f"{episode_uid}:{profile_id}:d5-robustness-v1".encode("utf-8")
    ).digest()
    seed = int.from_bytes(seed_material[:8], "big", signed=False)
    rng = np.random.default_rng(seed)
    changed_node_features: tuple[str, ...] = ()
    changed_edge_features: tuple[str, ...] = ()
    modified_node_count = 0
    modified_edge_count = graph.edge_count

    if profile_id == "asynchronous_timestamp_jitter":
        index = _EDGE_FEATURE_INDEX["time_delta_s"]
        edge_features[:, index] = np.clip(
            edge_features[:, index]
            + rng.uniform(0.075, 0.175, size=graph.edge_count),
            0.0,
            0.35,
        )
        changed_edge_features = ("time_delta_s",)
    elif profile_id == "extrinsics_drift":
        covariance = _EDGE_FEATURE_INDEX["extrinsics_covariance_trace"]
        reprojection = _EDGE_FEATURE_INDEX["reprojection_error_px"]
        epipolar = _EDGE_FEATURE_INDEX["epipolar_error_px"]
        global_projection = _EDGE_FEATURE_INDEX["global_projection_mahalanobis"]
        edge_features[:, covariance] = np.clip(
            edge_features[:, covariance] * 4.0 + 0.05,
            0.0,
            1000.0,
        )
        edge_features[:, reprojection] *= 1.75
        edge_features[:, epipolar] *= 1.75
        edge_features[:, global_projection] *= 1.5
        changed_edge_features = (
            "extrinsics_covariance_trace",
            "reprojection_error_px",
            "epipolar_error_px",
            "global_projection_mahalanobis",
        )
    elif profile_id == "occlusion_reappearance_proxy":
        confidence = _NODE_FEATURE_INDEX["confidence"]
        age = _NODE_FEATURE_INDEX["tracklet_age_s"]
        edge_confidence = _EDGE_FEATURE_INDEX["confidence_product"]
        time_delta = _EDGE_FEATURE_INDEX["time_delta_s"]
        node_mask = rng.random(graph.node_count) < 0.35
        if graph.node_count and not bool(np.any(node_mask)):
            node_mask[int(seed % graph.node_count)] = True
        node_features[node_mask, confidence] *= 0.4
        node_features[node_mask, age] += 0.75
        modified_node_count = int(np.sum(node_mask))
        edge_mask = (
            node_mask[graph.edge_index[0]] | node_mask[graph.edge_index[1]]
            if graph.edge_count
            else np.zeros(0, dtype=bool)
        )
        edge_features[edge_mask, edge_confidence] *= 0.4
        edge_features[edge_mask, time_delta] = np.clip(
            edge_features[edge_mask, time_delta] + 0.1,
            0.0,
            0.35,
        )
        modified_edge_count = int(np.sum(edge_mask))
        changed_node_features = ("confidence", "tracklet_age_s")
        changed_edge_features = ("confidence_product", "time_delta_s")
    elif profile_id == "similar_motion_confusers":
        edge_names = (
            "bbox_log_scale_delta",
            "bbox_scale_rate_delta_s",
            "angular_velocity_delta_rad_s",
        )
        node_names = (
            "angular_velocity_x_rad_s",
            "angular_velocity_y_rad_s",
            "bbox_scale_rate_s",
        )
        for name in edge_names:
            edge_features[:, _EDGE_FEATURE_INDEX[name]] = 0.0
        for name in node_names:
            node_features[:, _NODE_FEATURE_INDEX[name]] = 0.0
        modified_node_count = graph.node_count
        changed_node_features = node_names
        changed_edge_features = edge_names
    elif profile_id == "independent_bbox_scale_jitter":
        log_scale = _EDGE_FEATURE_INDEX["bbox_log_scale_delta"]
        scale_rate = _EDGE_FEATURE_INDEX["bbox_scale_rate_delta_s"]
        node_log_area = _NODE_FEATURE_INDEX["log_bbox_area_ratio"]
        node_scale_rate = _NODE_FEATURE_INDEX["bbox_scale_rate_s"]
        edge_features[:, log_scale] = np.abs(
            rng.normal(0.0, 0.08, size=graph.edge_count)
        )
        edge_features[:, scale_rate] = np.abs(
            rng.normal(0.0, 0.0015, size=graph.edge_count)
        )
        node_features[:, node_log_area] += rng.normal(
            0.0, 0.08, size=graph.node_count
        )
        node_features[:, node_scale_rate] += rng.normal(
            0.0, 0.0015, size=graph.node_count
        )
        modified_node_count = graph.node_count
        changed_node_features = ("log_bbox_area_ratio", "bbox_scale_rate_s")
        changed_edge_features = (
            "bbox_log_scale_delta",
            "bbox_scale_rate_delta_s",
        )
    else:
        _fail("robustness_profile_unknown", profile_id)

    transformed = SparseTrackletGraph(
        nodes=graph.nodes,  # type: ignore[arg-type]
        node_features=node_features,
        edge_index=graph.edge_index,
        edge_features=edge_features,
        edges=graph.edges,  # type: ignore[arg-type]
        candidate_counts=graph.candidate_counts,
    )
    return transformed, MappingProxyType(
        {
            "schema_version": "d5.tracklet-counterfactual-transform.v1",
            "profile_id": profile_id,
            "deterministic_seed": seed,
            "label_accessed": False,
            "candidate_topology_changed": False,
            "gate_score_changed": False,
            "changed_node_features": list(changed_node_features),
            "changed_edge_features": list(changed_edge_features),
            "modified_node_count": modified_node_count,
            "modified_edge_count": modified_edge_count,
        }
    )


def _runtime_fallback_probe(
    graph: SparseTrackletGraph,
    config: Scalable3DAdapterConfig,
) -> Mapping[str, Any]:
    """Exercise the online scorer boundary with anonymous model failures."""

    class _Unavailable:
        available = False
        failure_reason = "bundle_probe_unavailable"

    class _OutputModel:
        available = True
        decision_threshold = 0.5

        def __init__(self, kind: str) -> None:
            self.kind = kind

        def forward_graph(self, value: SparseTrackletGraph) -> np.ndarray:
            if self.kind == "shape":
                return np.zeros(value.edge_count + 1, dtype=float)
            if self.kind == "non_finite":
                result = np.zeros(value.edge_count, dtype=float)
                if result.size:
                    result[0] = np.nan
                return result
            if self.kind == "out_of_range":
                return np.full(value.edge_count, 1.1, dtype=float)
            if self.kind == "error":
                raise RuntimeError("injected scoring failure")
            if self.kind == "low_confidence":
                return np.full(value.edge_count, 0.5, dtype=float)
            if self.kind == "timeout":
                time.sleep(0.002)
                return np.zeros(value.edge_count, dtype=float)
            return np.zeros(value.edge_count, dtype=float)

    invalid_threshold = _OutputModel("valid")
    invalid_threshold.decision_threshold = math.nan
    cases: tuple[tuple[str, Any, Scalable3DAdapterConfig], ...] = (
        ("model_missing", None, config),
        ("bundle_unavailable", _Unavailable(), config),
        ("shape_mismatch", _OutputModel("shape"), config),
        ("non_finite_output", _OutputModel("non_finite"), config),
        ("out_of_range_output", _OutputModel("out_of_range"), config),
        ("model_exception", _OutputModel("error"), config),
        ("low_confidence", _OutputModel("low_confidence"), config),
        ("invalid_threshold", invalid_threshold, config),
        (
            "inference_timeout",
            _OutputModel("timeout"),
            replace(config, model_inference_timeout_ms=0.01),
        ),
    )
    rule_probabilities = _deterministic_edge_probabilities(graph, config)
    records: list[dict[str, Any]] = []
    for case_id, edge_model, case_config in cases:
        probabilities, status, source, reason, threshold, latency = _score_graph_edges(
            graph,
            case_config,
            edge_model,
        )
        records.append(
            {
                "case_id": case_id,
                "scoring_status": status,
                "probability_source": source,
                "fallback_reason": reason,
                "decision_threshold": threshold,
                "latency_ms": latency,
                "rule_probability_match": bool(
                    np.array_equal(probabilities, rule_probabilities)
                ),
                "fallback_applied": status.startswith("rule_fallback_"),
            }
        )
    passed = sum(
        bool(item["fallback_applied"]) and bool(item["rule_probability_match"])
        for item in records
    )
    return {
        "schema_version": "d5.tracklet-runtime-fallback-probe.v1",
        "anonymous_graph": True,
        "online_truth_feature_count": 0,
        "case_count": len(records),
        "passed_case_count": passed,
        "fallback_rate": _ratio(passed, len(records), zero=0.0),
        "all_failures_return_exact_rule_probabilities": passed == len(records),
        "cases": records,
    }


def _shared_graph_view(episode: LoadedHeldoutEpisode) -> SparseTrackletGraph:
    loaded = episode.graph
    nodes = tuple(
        _ShadowNode(tracklet_key=tracklet_key, camera_key=camera_key)
        for tracklet_key, camera_key in zip(
            loaded.tracklet_keys, loaded.camera_keys, strict=True
        )
    )
    edges: list[_ShadowEdge] = []
    for edge_number, (source, target) in enumerate(loaded.edge_index.T):
        count_value = float(
            loaded.edge_features[edge_number, _SHARED_GLOBAL_TRACK_COUNT_INDEX]
        )
        count = int(round(count_value))
        if count < 0 or abs(count_value - count) > FLOAT_COMPARISON_TOLERANCE:
            _fail(
                "shared_projection_count_invalid",
                f"{loaded.episode_uid}:{edge_number}:{count_value}",
            )
        edges.append(
            _ShadowEdge(
                source_index=int(source),
                target_index=int(target),
                source_tracklet_key=loaded.tracklet_keys[int(source)],
                target_tracklet_key=loaded.tracklet_keys[int(target)],
                shared_global_track_ids=tuple(
                    f"anonymous-projection-{index}" for index in range(count)
                ),
                gate_score=float(loaded.gate_scores[edge_number]),
            )
        )
    return SparseTrackletGraph(
        nodes=nodes,  # type: ignore[arg-type]
        node_features=loaded.node_features,
        edge_index=loaded.edge_index,
        edge_features=loaded.edge_features,
        edges=tuple(edges),  # type: ignore[arg-type]
        candidate_counts=loaded.candidate_counts,
    )


def _targets(
    graph: SparseTrackletGraph,
    labels: Mapping[str, Any],
) -> tuple[np.ndarray, int]:
    targets = np.zeros(graph.edge_count, dtype=bool)
    unlabeled = 0
    for edge_number, edge in enumerate(graph.edges):
        left = labels.get(edge.source_tracklet_key)
        right = labels.get(edge.target_tracklet_key)
        if left is None or right is None:
            unlabeled += 1
            continue
        targets[edge_number] = left.truth_entity_id == right.truth_entity_id
    targets.setflags(write=False)
    return targets, unlabeled


def _candidate_recall_counts(
    graph: SparseTrackletGraph,
    labels: Mapping[str, Any],
) -> tuple[int, int]:
    groups: dict[str, dict[str, int]] = {}
    for node in graph.nodes:
        label = labels.get(node.tracklet_key)
        if label is None:
            continue
        camera_counts = groups.setdefault(label.truth_entity_id, {})
        camera_counts[node.camera_key] = camera_counts.get(node.camera_key, 0) + 1
    denominator = 0
    for camera_counts in groups.values():
        total = sum(camera_counts.values())
        denominator += total * (total - 1) // 2
        denominator -= sum(count * (count - 1) // 2 for count in camera_counts.values())
    numerator = sum(
        int(
            labels[edge.source_tracklet_key].truth_entity_id
            == labels[edge.target_tracklet_key].truth_entity_id
        )
        for edge in graph.edges
        if edge.source_tracklet_key in labels and edge.target_tracklet_key in labels
    )
    return numerator, denominator


def _arm_episode_metrics(
    graph: SparseTrackletGraph,
    labels: Mapping[str, Any],
    targets: np.ndarray,
    probabilities: np.ndarray,
    clusters: Sequence[Any],
    *,
    threshold: float,
    scoring_latency_ms: float,
    clustering_latency_ms: float,
) -> dict[str, Any]:
    predicted_edges = probabilities >= threshold
    edge_counts = _binary_counts(predicted_edges, targets)
    cluster_counts, same_camera_violations = _cluster_pair_counts(
        graph, labels, clusters
    )
    return {
        "decision_threshold": float(threshold),
        "edge": _metrics_from_counts(edge_counts),
        "cluster_pairwise": {
            **_metrics_from_counts(cluster_counts),
            "erroneous_merge_pair_count": cluster_counts["false_positive"],
            "same_target_split_pair_count": cluster_counts["false_negative"],
        },
        "cluster_count": len(clusters),
        "same_camera_mutual_exclusion_violation_count": same_camera_violations,
        "edge_by_shared_global_track_count": _stratified_edge_metrics(
            graph,
            predicted_edges,
            targets,
        ),
        "scoring_latency_ms": float(scoring_latency_ms),
        "clustering_latency_ms": float(clustering_latency_ms),
        "total_latency_ms": float(scoring_latency_ms + clustering_latency_ms),
        "clusters_sha256": _sha256_json(
            [list(cluster.tracklet_keys) for cluster in clusters]
        ),
    }


def _binary_counts(predicted: np.ndarray, expected: np.ndarray) -> dict[str, int]:
    return {
        "true_positive": int(np.sum(predicted & expected)),
        "false_positive": int(np.sum(predicted & ~expected)),
        "false_negative": int(np.sum(~predicted & expected)),
        "true_negative": int(np.sum(~predicted & ~expected)),
    }


def _stratified_edge_metrics(
    graph: SparseTrackletGraph,
    predicted: np.ndarray,
    expected: np.ndarray,
) -> dict[str, Any]:
    values = np.asarray(
        graph.edge_features[:, _SHARED_GLOBAL_TRACK_COUNT_INDEX], dtype=float
    )
    masks = {
        "0": np.isclose(values, 0.0, atol=FLOAT_COMPARISON_TOLERANCE),
        "1": np.isclose(values, 1.0, atol=FLOAT_COMPARISON_TOLERANCE),
    }
    masks["other"] = ~(masks["0"] | masks["1"])
    result: dict[str, Any] = {}
    for name, mask in masks.items():
        counts = _binary_counts(predicted[mask], expected[mask])
        edge_count = int(np.sum(mask))
        result[name] = {
            "available": edge_count > 0,
            "reason": None if edge_count else "no_candidate_edges_in_stratum",
            "edge_count": edge_count,
            **_metrics_from_counts(counts),
        }
    return result


def _cluster_pair_counts(
    graph: SparseTrackletGraph,
    labels: Mapping[str, Any],
    clusters: Sequence[Any],
) -> tuple[dict[str, int], int]:
    cluster_by_node: dict[int, int] = {}
    same_camera_violations = 0
    for cluster_number, cluster in enumerate(clusters):
        cameras = [graph.nodes[index].camera_key for index in cluster.node_indices]
        same_camera_violations += len(cameras) - len(set(cameras))
        for node_index in cluster.node_indices:
            cluster_by_node[int(node_index)] = cluster_number
    predicted: list[bool] = []
    expected: list[bool] = []
    for left in range(graph.node_count):
        for right in range(left + 1, graph.node_count):
            if graph.nodes[left].camera_key == graph.nodes[right].camera_key:
                continue
            left_label = labels.get(graph.nodes[left].tracklet_key)
            right_label = labels.get(graph.nodes[right].tracklet_key)
            if left_label is None or right_label is None:
                continue
            predicted.append(cluster_by_node[left] == cluster_by_node[right])
            expected.append(left_label.truth_entity_id == right_label.truth_entity_id)
    return (
        _binary_counts(np.asarray(predicted, dtype=bool), np.asarray(expected, dtype=bool)),
        same_camera_violations,
    )


def _metrics_from_counts(counts: Mapping[str, int]) -> dict[str, Any]:
    true_positive = int(counts["true_positive"])
    false_positive = int(counts["false_positive"])
    false_negative = int(counts["false_negative"])
    predicted_positive = true_positive + false_positive
    actual_positive = true_positive + false_negative
    precision = _ratio(true_positive, predicted_positive)
    recall = _ratio(true_positive, actual_positive)
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else 0.0
        if precision is not None and recall is not None
        else None
    )
    return {
        **{key: int(value) for key, value in counts.items()},
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_merge_rate": _ratio(false_positive, predicted_positive, zero=0.0),
    }


def _aggregate_group(
    records: Sequence[Mapping[str, Any]],
    *,
    group_id: str,
    scenario: str | None = None,
    scale: int | None = None,
) -> dict[str, Any]:
    if not records:
        _fail("paired_shadow_group_empty", group_id)
    candidate_numerator = sum(int(item["candidate_recall_numerator"]) for item in records)
    candidate_denominator = sum(
        int(item["candidate_recall_denominator"]) for item in records
    )
    result: dict[str, Any] = {
        "group_id": group_id,
        "episode_count": len(records),
        "seed_count": len({int(item["seed"]) for item in records}),
        "node_count": sum(int(item["node_count"]) for item in records),
        "candidate_edge_count": sum(int(item["candidate_edge_count"]) for item in records),
        "candidate_recall_numerator": candidate_numerator,
        "candidate_recall_denominator": candidate_denominator,
        "candidate_recall": _ratio(candidate_numerator, candidate_denominator),
        "control": _aggregate_arm(records, "control"),
        "model": _aggregate_arm(records, "model"),
    }
    candidate_coverage = {
        "candidate_edge_count": result["candidate_edge_count"],
        "same_target_candidate_count": candidate_numerator,
        "same_target_cross_camera_pair_count": candidate_denominator,
        "candidate_recall": result["candidate_recall"],
    }
    result["control"]["candidate_coverage"] = dict(candidate_coverage)
    result["model"]["candidate_coverage"] = dict(candidate_coverage)
    if scenario is not None:
        result["scenario"] = scenario
    if scale is not None:
        result["scale"] = int(scale)
    result["delta_model_minus_rule"] = _metric_deltas(result["control"], result["model"])
    result["quality_gates"] = _quality_gates(result)
    result["quality_not_degraded"] = all(
        bool(gate["passed"]) for gate in result["quality_gates"]
    )
    return result


def _aggregate_robustness_profiles(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate diagnostic stress profiles without changing admission gates."""

    definitions = {
        str(item["profile_id"]): dict(item)
        for item in ROBUSTNESS_PROFILE_DEFINITIONS
    }
    results: list[dict[str, Any]] = []
    for profile_id in definitions:
        profile_records = [
            {
                "control": item["robustness_profiles"][profile_id]["control"],
                "model": item["robustness_profiles"][profile_id]["model"],
            }
            for item in records
        ]
        control = _aggregate_arm(profile_records, "control")
        model = _aggregate_arm(profile_records, "model")
        candidate_numerator = sum(
            int(item["candidate_recall_numerator"]) for item in records
        )
        candidate_denominator = sum(
            int(item["candidate_recall_denominator"]) for item in records
        )
        candidate_recall = _ratio(candidate_numerator, candidate_denominator)
        graph_matches = sum(
            bool(item["robustness_profiles"][profile_id]["graph_identity_match"])
            for item in records
        )
        candidate_matches = sum(
            bool(item["robustness_profiles"][profile_id]["candidate_identity_match"])
            for item in records
        )
        results.append(
            {
                "profile": definitions[profile_id],
                "episode_count": len(records),
                "candidate_edge_count": sum(
                    int(item["candidate_edge_count"]) for item in records
                ),
                "candidate_recall": candidate_recall,
                "control": control,
                "model": model,
                "delta_model_minus_rule": _metric_deltas(control, model),
                "graph_identity_ratio": _ratio(
                    graph_matches, len(records), zero=0.0
                ),
                "candidate_identity_ratio": _ratio(
                    candidate_matches, len(records), zero=0.0
                ),
                "truth_used_for_transform": False,
                "interpretation": (
                    "diagnostic_post_gate_counterfactual_not_physical_generalization"
                ),
                "authority_effect": "none",
            }
        )
    return results


def _aggregate_arm(records: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    edge_counts = _sum_counts(records, arm, "edge")
    cluster_counts = _sum_counts(records, arm, "cluster_pairwise")
    scoring = np.asarray(
        [float(item[arm]["scoring_latency_ms"]) for item in records], dtype=float
    )
    clustering = np.asarray(
        [float(item[arm]["clustering_latency_ms"]) for item in records], dtype=float
    )
    total = scoring + clustering
    return {
        "edge": _metrics_from_counts(edge_counts),
        "cluster_pairwise": {
            **_metrics_from_counts(cluster_counts),
            "erroneous_merge_pair_count": cluster_counts["false_positive"],
            "same_target_split_pair_count": cluster_counts["false_negative"],
        },
        "same_camera_mutual_exclusion_violation_count": sum(
            int(item[arm]["same_camera_mutual_exclusion_violation_count"])
            for item in records
        ),
        "edge_by_shared_global_track_count": _aggregate_stratified_edge_metrics(
            records, arm
        ),
        "latency_ms": {
            "sample_count": len(records),
            "scoring_p50": float(np.percentile(scoring, 50)),
            "scoring_p95": float(np.percentile(scoring, 95)),
            "scoring_max": float(np.max(scoring)),
            "clustering_p50": float(np.percentile(clustering, 50)),
            "clustering_p95": float(np.percentile(clustering, 95)),
            "total_p50": float(np.percentile(total, 50)),
            "total_p95": float(np.percentile(total, 95)),
        },
    }


def _aggregate_stratified_edge_metrics(
    records: Sequence[Mapping[str, Any]], arm: str
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for stratum in ("0", "1", "other"):
        items = [item[arm]["edge_by_shared_global_track_count"][stratum] for item in records]
        counts = {
            name: sum(int(item[name]) for item in items)
            for name in (
                "true_positive",
                "false_positive",
                "false_negative",
                "true_negative",
            )
        }
        edge_count = sum(int(item["edge_count"]) for item in items)
        result[stratum] = {
            "available": edge_count > 0,
            "reason": None if edge_count else "no_candidate_edges_in_stratum",
            "edge_count": edge_count,
            **_metrics_from_counts(counts),
        }
    result["cluster_metrics"] = {
        "available": False,
        "reason": "constrained_clusters_span_edges_and_are_not_recomputed_per_stratum",
    }
    return result


def _sum_counts(
    records: Sequence[Mapping[str, Any]], arm: str, layer: str
) -> dict[str, int]:
    names = ("true_positive", "false_positive", "false_negative", "true_negative")
    return {
        name: sum(int(item[arm][layer][name]) for item in records) for name in names
    }


def _metric_deltas(control: Mapping[str, Any], model: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "edge": {
            name: _subtract(model["edge"][name], control["edge"][name])
            for name in ("precision", "recall", "f1", "false_merge_rate")
        },
        "cluster_pairwise": {
            name: _subtract(
                model["cluster_pairwise"][name], control["cluster_pairwise"][name]
            )
            for name in ("precision", "recall", "f1", "false_merge_rate")
        },
        "erroneous_merge_pair_count": (
            model["cluster_pairwise"]["erroneous_merge_pair_count"]
            - control["cluster_pairwise"]["erroneous_merge_pair_count"]
        ),
        "same_target_split_pair_count": (
            model["cluster_pairwise"]["same_target_split_pair_count"]
            - control["cluster_pairwise"]["same_target_split_pair_count"]
        ),
        "scoring_p95_ms": (
            model["latency_ms"]["scoring_p95"]
            - control["latency_ms"]["scoring_p95"]
        ),
    }


def _quality_gates(group: Mapping[str, Any]) -> list[dict[str, Any]]:
    control = group["control"]
    model = group["model"]
    gates = [
        _comparison_gate(
            "candidate_recall_equal",
            model["candidate_coverage"]["candidate_recall"],
            "==",
            control["candidate_coverage"]["candidate_recall"],
        ),
        _comparison_gate(
            "candidate_edge_count_equal",
            model["candidate_coverage"]["candidate_edge_count"],
            "==",
            control["candidate_coverage"]["candidate_edge_count"],
        ),
        _comparison_gate(
            "candidate_recall_minimum",
            model["candidate_coverage"]["candidate_recall"],
            ">=",
            MINIMUM_CANDIDATE_RECALL,
        ),
    ]
    for name in ("precision", "recall", "f1"):
        gates.append(
            _comparison_gate(
                f"edge_{name}_not_lower",
                model["edge"][name],
                ">=",
                control["edge"][name],
            )
        )
    gates.extend(
        [
            _comparison_gate(
                "edge_false_merge_not_higher",
                model["edge"]["false_merge_rate"],
                "<=",
                control["edge"]["false_merge_rate"],
            ),
            _comparison_gate(
                "edge_false_merge_absolute_limit",
                model["edge"]["false_merge_rate"],
                "<=",
                MAXIMUM_FALSE_MERGE_RATE,
            ),
        ]
    )
    for name in ("precision", "recall", "f1"):
        gates.append(
            _comparison_gate(
                f"cluster_{name}_not_lower",
                model["cluster_pairwise"][name],
                ">=",
                control["cluster_pairwise"][name],
            )
        )
    gates.extend(
        [
            _comparison_gate(
                "cluster_erroneous_merge_not_increased",
                model["cluster_pairwise"]["erroneous_merge_pair_count"],
                "<=",
                control["cluster_pairwise"]["erroneous_merge_pair_count"],
            ),
            _comparison_gate(
                "cluster_same_target_split_not_increased",
                model["cluster_pairwise"]["same_target_split_pair_count"],
                "<=",
                control["cluster_pairwise"]["same_target_split_pair_count"],
            ),
        ]
    )
    return gates


def _comparison_gate(
    name: str,
    actual: float | int | None,
    operator: str,
    reference: float | int | None,
) -> dict[str, Any]:
    available = actual is not None and reference is not None
    passed = False
    if available:
        left = float(actual)
        right = float(reference)
        if math.isfinite(left) and math.isfinite(right):
            if operator == ">=":
                passed = left + FLOAT_COMPARISON_TOLERANCE >= right
            elif operator == "<=":
                passed = left <= right + FLOAT_COMPARISON_TOLERANCE
            elif operator == "==":
                passed = abs(left - right) <= FLOAT_COMPARISON_TOLERANCE
            else:
                raise ValueError(f"unknown comparison operator: {operator}")
    return {
        "name": name,
        "actual": actual,
        "operator": operator,
        "reference": reference,
        "tolerance": FLOAT_COMPARISON_TOLERANCE,
        "available": available,
        "passed": bool(passed),
    }


def _assessment(
    *,
    overall: Mapping[str, Any],
    cell_metrics: Sequence[Mapping[str, Any]],
    identity: Mapping[str, Any],
    safety: Mapping[str, Any],
    immutable_inputs: bool,
    actual_episode_count: int,
    expected_episode_count: int,
    actual_seed_count: int,
    expected_seed_count: int,
    actual_cell_count: int,
    expected_cell_count: int,
    catalog: Mapping[str, Any],
    robustness_profiles: Sequence[Mapping[str, Any]],
    runtime_fallback: Mapping[str, Any],
) -> dict[str, Any]:
    gates = list(overall["quality_gates"])
    gates.extend(
        [
            _comparison_gate(
                "episode_catalog", actual_episode_count, "==", expected_episode_count
            ),
            _comparison_gate("seed_catalog", actual_seed_count, "==", expected_seed_count),
            _comparison_gate("cell_catalog", actual_cell_count, "==", expected_cell_count),
            _comparison_gate(
                "graph_identity_ratio",
                identity["graph_identity_ratio"],
                "==",
                1.0,
            ),
            _comparison_gate(
                "candidate_identity_ratio",
                identity["candidate_identity_ratio"],
                "==",
                1.0,
            ),
            _comparison_gate(
                "label_identity_ratio",
                identity["label_identity_ratio"],
                "==",
                1.0,
            ),
            _comparison_gate(
                "model_p95_latency_ms",
                overall["model"]["latency_ms"]["scoring_p95"],
                "<=",
                MAXIMUM_MODEL_P95_MS,
            ),
            _comparison_gate(
                "same_camera_candidate_edges",
                safety["same_camera_candidate_edge_count"],
                "==",
                0,
            ),
            _comparison_gate(
                "same_camera_mutual_exclusion",
                safety["same_camera_mutual_exclusion_violation_count"],
                "==",
                0,
            ),
            _comparison_gate(
                "truth_scoring_after_both_arm_predictions",
                safety["truth_scoring_after_both_arm_predictions_count"],
                "==",
                actual_episode_count,
            ),
            _comparison_gate(
                "online_truth_feature_count",
                safety["online_truth_feature_count"],
                "==",
                0,
            ),
            _comparison_gate(
                "unlabeled_candidate_edge_count",
                safety["unlabeled_candidate_edge_count"],
                "==",
                0,
            ),
            _comparison_gate(
                "global_track_id_rewrite_count",
                safety["global_track_id_rewrite_count"],
                "==",
                0,
            ),
            {
                "name": "complete_seed_cell_catalog",
                "actual": catalog["complete"],
                "operator": "is",
                "reference": True,
                "tolerance": 0.0,
                "available": True,
                "passed": bool(catalog["complete"]),
            },
            {
                "name": "input_artifacts_unchanged",
                "actual": immutable_inputs,
                "operator": "is",
                "reference": True,
                "tolerance": 0.0,
                "available": True,
                "passed": bool(immutable_inputs),
            },
            _comparison_gate(
                "runtime_model_failure_fallback_rate",
                runtime_fallback["fallback_rate"],
                "==",
                1.0,
            ),
            {
                "name": "robustness_profiles_truth_independent",
                "actual": all(
                    item["truth_used_for_transform"] is False
                    for item in robustness_profiles
                ),
                "operator": "is",
                "reference": True,
                "tolerance": 0.0,
                "available": True,
                "passed": all(
                    item["truth_used_for_transform"] is False
                    for item in robustness_profiles
                ),
            },
            {
                "name": "robustness_profiles_graph_identity",
                "actual": sum(
                    item["graph_identity_ratio"] == 1.0
                    and item["candidate_identity_ratio"] == 1.0
                    for item in robustness_profiles
                ),
                "operator": "==",
                "reference": len(ROBUSTNESS_PROFILE_DEFINITIONS),
                "tolerance": 0.0,
                "available": True,
                "passed": len(robustness_profiles)
                == len(ROBUSTNESS_PROFILE_DEFINITIONS)
                and all(
                    item["graph_identity_ratio"] == 1.0
                    and item["candidate_identity_ratio"] == 1.0
                    for item in robustness_profiles
                ),
            },
        ]
    )
    cell_assessments = [
        {
            "cell_id": cell["group_id"],
            "passed": bool(cell["quality_not_degraded"]),
            "failed_gates": [
                gate["name"] for gate in cell["quality_gates"] if not gate["passed"]
            ],
        }
        for cell in cell_metrics
    ]
    cell_quality_passed = len(cell_metrics) == expected_cell_count and all(
        item["passed"] for item in cell_assessments
    )
    gates.append(
        {
            "name": "all_cells_no_quality_degradation",
            "actual": sum(item["passed"] for item in cell_assessments),
            "operator": "==",
            "reference": expected_cell_count,
            "tolerance": 0.0,
            "available": True,
            "passed": cell_quality_passed,
        }
    )
    passed = all(bool(gate["passed"]) for gate in gates)
    failures = [str(gate["name"]) for gate in gates if not gate["passed"]]
    failures.extend(
        f"cell:{item['cell_id']}:{','.join(item['failed_gates'])}"
        for item in cell_assessments
        if not item["passed"]
    )
    return {
        "status": "pass" if passed else "fail_closed",
        "passed": passed,
        "gates": gates,
        "cell_assessments": cell_assessments,
        "failure_reasons": failures,
        "d6_external_audit_required": True,
        "g1": False,
        "assist": False,
        "authority": False,
        "rule_fallback": True,
    }


def _identity_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(records)
    graph_matches = sum(bool(item["graph_identity_match"]) for item in records)
    candidate_matches = sum(bool(item["candidate_identity_match"]) for item in records)
    label_matches = sum(bool(item["label_identity_match"]) for item in records)
    return {
        "episode_count": count,
        "same_loaded_graph_sent_to_both_arms_count": count,
        "graph_identity_match_count": graph_matches,
        "candidate_identity_match_count": candidate_matches,
        "label_identity_match_count": label_matches,
        "graph_identity_ratio": _ratio(graph_matches, count),
        "candidate_identity_ratio": _ratio(candidate_matches, count),
        "label_identity_ratio": _ratio(label_matches, count),
        "model_candidate_edges_added_or_removed": 0,
    }


def _feature_label_diagnostics(
    episodes: Sequence[LoadedHeldoutEpisode],
) -> dict[str, Any]:
    feature_batches: list[np.ndarray] = []
    target_batches: list[np.ndarray] = []
    for episode in episodes:
        graph = episode.graph
        labels = episode.evaluator_labels.by_tracklet_key
        targets = np.asarray(
            [
                labels[graph.tracklet_keys[int(source)]].truth_entity_id
                == labels[graph.tracklet_keys[int(target)]].truth_entity_id
                for source, target in graph.edge_index.T
            ],
            dtype=bool,
        )
        feature_batches.append(np.asarray(graph.edge_features, dtype=np.float64))
        target_batches.append(targets)
    features = np.concatenate(feature_batches, axis=0)
    targets = np.concatenate(target_batches, axis=0)
    diagnostics: list[dict[str, Any]] = []
    for index, name in enumerate(EDGE_FEATURE_NAMES):
        values = features[:, index]
        positive = values[targets]
        negative = values[~targets]
        auc = _univariate_auc(values, targets)
        correlation = _point_biserial_correlation(values, targets)
        diagnostics.append(
            {
                "feature": name,
                "sample_count": int(values.size),
                "unique_value_count": int(np.unique(values).size),
                "positive": _numeric_distribution(positive),
                "negative": _numeric_distribution(negative),
                "point_biserial_correlation": correlation,
                "univariate_auc": auc,
                "near_deterministic_univariate": bool(
                    auc["available"]
                    and float(auc["best_direction_auc"])
                    >= NEAR_DETERMINISTIC_UNIVARIATE_AUC
                ),
                "range_separated": bool(
                    positive.size
                    and negative.size
                    and (
                        float(np.max(positive)) < float(np.min(negative))
                        or float(np.max(negative)) < float(np.min(positive))
                    )
                ),
            }
        )
    shared = features[:, _SHARED_GLOBAL_TRACK_COUNT_INDEX]
    shared_strata = {
        str(value): _label_distribution(targets[np.isclose(shared, float(value))])
        for value in (0, 1)
    }
    shared_other_mask = ~(
        np.isclose(shared, 0.0, atol=FLOAT_COMPARISON_TOLERANCE)
        | np.isclose(shared, 1.0, atol=FLOAT_COMPARISON_TOLERANCE)
    )
    shared_strata["other"] = _label_distribution(targets[shared_other_mask])
    near_deterministic = [
        item["feature"] for item in diagnostics if item["near_deterministic_univariate"]
    ]
    available_auc = [
        (
            str(item["feature"]),
            float(item["univariate_auc"]["best_direction_auc"]),
        )
        for item in diagnostics
        if item["univariate_auc"]["available"]
    ]
    maximum_single_feature_auc = (
        {
            "available": True,
            "feature": max(available_auc, key=lambda item: item[1])[0],
            "best_direction_auc": max(available_auc, key=lambda item: item[1])[1],
        }
        if available_auc
        else {
            "available": False,
            "feature": None,
            "best_direction_auc": None,
            "reason": "no_feature_with_both_label_classes",
        }
    )
    limitation_flags: list[str] = ["perfect_score_not_online_generalization_evidence"]
    if not shared_strata["1"]["available"]:
        limitation_flags.append("shared_global_track_count_one_stratum_absent")
    if near_deterministic:
        limitation_flags.append("near_deterministic_synthetic_feature_separability")
    return {
        "scope": "post_prediction_evaluator_only",
        "interpretation_scope": "dataset_separability_not_model_feature_attribution",
        "candidate_edge_count": int(targets.size),
        "positive_candidate_edge_count": int(np.sum(targets)),
        "negative_candidate_edge_count": int(np.sum(~targets)),
        "near_deterministic_auc_threshold": NEAR_DETERMINISTIC_UNIVARIATE_AUC,
        "near_deterministic_feature_names": near_deterministic,
        "maximum_single_feature_auc": maximum_single_feature_auc,
        "features": diagnostics,
        "shared_global_track_count": {
            "strata": shared_strata,
            "mutual_information_bits": _discrete_mutual_information(shared, targets),
            "near_deterministic": False,
        },
        "limitation_flags": limitation_flags,
        "changes_to_frozen_evaluation": {
            "candidate_gate_changed": False,
            "threshold_reselected": False,
            "temperature_reestimated": False,
            "weights_updated": False,
            "predictions_recomputed_for_diagnostics": False,
        },
    }


def _numeric_distribution(values: np.ndarray) -> dict[str, Any]:
    if not values.size:
        return {"available": False, "count": 0, "reason": "empty_class"}
    return {
        "available": True,
        "count": int(values.size),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "mean": float(np.mean(values)),
        "standard_deviation": float(np.std(values)),
        "exact_zero_fraction": float(np.mean(values == 0.0)),
    }


def _label_distribution(targets: np.ndarray) -> dict[str, Any]:
    count = int(targets.size)
    positives = int(np.sum(targets))
    return {
        "available": count > 0,
        "reason": None if count else "no_candidate_edges_in_stratum",
        "edge_count": count,
        "positive_count": positives,
        "negative_count": count - positives,
        "positive_rate": _ratio(positives, count),
    }


def _point_biserial_correlation(
    values: np.ndarray, targets: np.ndarray
) -> dict[str, Any]:
    if values.size == 0 or not np.any(targets) or not np.any(~targets):
        return {"available": False, "value": None, "reason": "class_missing"}
    if float(np.std(values)) <= FLOAT_COMPARISON_TOLERANCE:
        return {"available": False, "value": None, "reason": "feature_constant"}
    value = float(np.corrcoef(values, targets.astype(np.float64))[0, 1])
    return {"available": True, "value": value, "reason": None}


def _univariate_auc(values: np.ndarray, targets: np.ndarray) -> dict[str, Any]:
    positive_count = int(np.sum(targets))
    negative_count = int(np.sum(~targets))
    if positive_count == 0 or negative_count == 0:
        return {
            "available": False,
            "auc": None,
            "best_direction_auc": None,
            "direction": None,
            "reason": "class_missing",
        }
    unique, inverse, counts = np.unique(
        values, return_inverse=True, return_counts=True
    )
    if unique.size <= 1:
        return {
            "available": False,
            "auc": None,
            "best_direction_auc": None,
            "direction": None,
            "reason": "feature_constant",
        }
    cumulative = np.cumsum(counts, dtype=np.float64)
    average_ranks = cumulative - (counts.astype(np.float64) - 1.0) / 2.0
    ranks = average_ranks[inverse]
    auc = float(
        (
            np.sum(ranks[targets])
            - positive_count * (positive_count + 1.0) / 2.0
        )
        / (positive_count * negative_count)
    )
    return {
        "available": True,
        "auc": auc,
        "best_direction_auc": max(auc, 1.0 - auc),
        "direction": "higher_for_positive" if auc >= 0.5 else "lower_for_positive",
        "reason": None,
    }


def _discrete_mutual_information(values: np.ndarray, targets: np.ndarray) -> float:
    joint = Counter(zip(values.tolist(), targets.astype(int).tolist(), strict=True))
    value_counts = Counter(values.tolist())
    target_counts = Counter(targets.astype(int).tolist())
    count = int(values.size)
    result = 0.0
    for (value, target), joint_count in joint.items():
        probability = joint_count / count
        independent = (value_counts[value] / count) * (target_counts[target] / count)
        result += probability * math.log2(probability / independent)
    return float(result)


def _catalog_summary(
    records: Sequence[Mapping[str, Any]], profile: Mapping[str, Any]
) -> dict[str, Any]:
    expected_seeds = tuple(int(value) for value in profile["seeds"])
    expected_cells = tuple(
        (str(item["scenario"]), int(item["scale"]))
        for item in profile["scenario_cells"]
    )
    expected_keys = {
        (seed, scenario, scale)
        for seed in expected_seeds
        for scenario, scale in expected_cells
    }
    counts = Counter(
        (int(item["seed"]), str(item["scenario"]), int(item["scale"]))
        for item in records
    )
    actual_keys = set(counts)
    duplicate_record_count = sum(max(0, count - 1) for count in counts.values())
    seed_frame_counts = {
        str(seed): sum(count for key, count in counts.items() if key[0] == seed)
        for seed in expected_seeds
    }
    cell_frame_counts = {
        f"{scenario}-{scale}v{scale}": sum(
            count
            for key, count in counts.items()
            if key[1] == scenario and key[2] == scale
        )
        for scenario, scale in expected_cells
    }
    missing = sorted(expected_keys - actual_keys)
    extra = sorted(actual_keys - expected_keys)
    complete = (
        not missing
        and not extra
        and duplicate_record_count == 0
        and all(value == len(expected_cells) for value in seed_frame_counts.values())
        and all(value == len(expected_seeds) for value in cell_frame_counts.values())
    )
    return {
        "complete": bool(complete),
        "expected_frame_count": len(expected_keys),
        "actual_frame_count": len(records),
        "expected_seed_count": len(expected_seeds),
        "expected_cell_count": len(expected_cells),
        "missing_seed_cell_count": len(missing),
        "extra_seed_cell_count": len(extra),
        "duplicate_record_count": duplicate_record_count,
        "seed_frame_counts": seed_frame_counts,
        "cell_frame_counts": cell_frame_counts,
    }


def _safety_summary(
    records: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    manifest_safety = manifest.get("identity_and_truth_safety", {})
    actual_same_camera_edges = sum(
        int(item["same_camera_candidate_edge_count"]) for item in records
    )
    return {
        "same_camera_candidate_edge_count": actual_same_camera_edges,
        "manifest_same_camera_candidate_edge_count": int(
            manifest_safety.get("same_camera_candidate_edge_count", -1)
        ),
        "same_camera_mutual_exclusion_violation_count": sum(
            int(item[arm]["same_camera_mutual_exclusion_violation_count"])
            for item in records
            for arm in ("control", "model")
        ),
        "online_truth_feature_count": int(
            manifest_safety.get("online_truth_feature_count", 0)
        ),
        "unlabeled_candidate_edge_count": sum(
            int(item["unlabeled_candidate_edge_count"]) for item in records
        ),
        "truth_scoring_after_both_arm_predictions_count": sum(
            bool(item["truth_scoring_started_after_both_arm_predictions"])
            for item in records
        ),
        "global_track_id_rewrite_count": 0,
        "global_track_id_created_or_rebound": False,
        "truth_scope": "evaluator_only_after_both_arm_predictions",
        "g1": False,
        "assist": False,
        "authority": False,
        "rule_fallback": True,
    }


def _validate_explicit_inputs(spec: PairedShadowInputSpec) -> dict[str, str]:
    actual = _actual_input_hashes(spec)
    expected = spec.to_payload()["expected_hashes"]
    for name, expected_value in expected.items():
        actual_value = actual.get(name)
        if actual_value != expected_value:
            _fail(
                f"{name}_mismatch",
                f"actual={actual_value};expected={expected_value}",
            )
    corpus_manifest = _read_json(Path(spec.heldout_corpus_dir) / HELDOUT_MANIFEST_FILENAME)
    _verify_content_hash(
        corpus_manifest,
        spec.expected_corpus_content_sha256,
        "corpus_content_sha256_mismatch",
    )
    if corpus_manifest.get("config", {}).get("sha256") != spec.expected_corpus_config_sha256:
        _fail("corpus_config_lineage_mismatch", str(corpus_manifest.get("config")))
    heldout_report = _read_json(Path(spec.heldout_report_path))
    _verify_content_hash(
        heldout_report,
        spec.expected_heldout_report_content_sha256,
        "heldout_report_content_sha256_mismatch",
    )
    report_corpus = heldout_report.get("heldout_corpus", {})
    report_model = heldout_report.get("development_model", {})
    if (
        report_corpus.get("manifest_sha256") != spec.expected_corpus_manifest_sha256
        or report_corpus.get("manifest_content_sha256")
        != spec.expected_corpus_content_sha256
    ):
        _fail("heldout_report_corpus_lineage_mismatch", str(report_corpus))
    if (
        report_model.get("bundle_manifest_sha256")
        != spec.expected_bundle_manifest_sha256
        or report_model.get("weights_sha256") != spec.expected_bundle_weights_sha256
    ):
        _fail("heldout_report_model_lineage_mismatch", str(report_model))
    return actual


def _actual_input_hashes(spec: PairedShadowInputSpec) -> dict[str, str]:
    corpus_root = Path(spec.heldout_corpus_dir)
    bundle_root = Path(spec.bundle_dir)
    paths = {
        "corpus_manifest_sha256": corpus_root / HELDOUT_MANIFEST_FILENAME,
        "corpus_config_sha256": corpus_root / "heldout_dataset" / HELDOUT_CONFIG_FILENAME,
        "bundle_manifest_sha256": bundle_root / MANIFEST_FILENAME,
        "bundle_weights_sha256": bundle_root / WEIGHTS_FILENAME,
        "bundle_checksums_sha256": bundle_root / CHECKSUMS_FILENAME,
        "heldout_report_sha256": Path(spec.heldout_report_path),
    }
    if spec.superseded_output_dir is not None:
        paths.update(
            {
                "superseded_report_sha256": Path(spec.superseded_output_dir)
                / PAIRED_SHADOW_REPORT_FILENAME,
                "superseded_lineage_sha256": Path(spec.superseded_output_dir)
                / PAIRED_SHADOW_LINEAGE_FILENAME,
            }
        )
    values: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            _fail("explicit_input_missing", f"{name}:{path}")
        values[name] = sha256_file(path)
    corpus_manifest = _read_json(paths["corpus_manifest_sha256"])
    heldout_report = _read_json(paths["heldout_report_sha256"])
    values["corpus_content_sha256"] = str(corpus_manifest.get("content_sha256", ""))
    values["heldout_report_content_sha256"] = str(
        heldout_report.get("content_sha256", "")
    )
    return values


def _validate_destination(spec: PairedShadowInputSpec) -> None:
    destination = Path(spec.output_dir)
    sources = (
        Path(spec.heldout_corpus_dir),
        Path(spec.bundle_dir),
        Path(spec.heldout_report_path),
        *(
            (Path(spec.superseded_output_dir),)
            if spec.superseded_output_dir is not None
            else ()
        ),
    )
    for source in sources:
        source_root = source if source.is_dir() else source.parent
        if _is_relative_to(destination, source_root) or _is_relative_to(
            source_root, destination
        ):
            _fail("output_source_overlap", f"output={destination};source={source}")


def _evidence_status(
    spec: PairedShadowInputSpec,
    *,
    passed: bool,
    actual_hashes: Mapping[str, str],
) -> dict[str, Any]:
    superseded: list[dict[str, Any]] = []
    if spec.superseded_output_dir is not None:
        superseded.append(
            {
                "directory": str(spec.superseded_output_dir),
                "status": (
                    "superseded_preserved" if passed else "preserved_not_superseded"
                ),
                "report_sha256": actual_hashes.get("superseded_report_sha256"),
                "lineage_sha256": actual_hashes.get("superseded_lineage_sha256"),
                "files_modified": False,
                "files_deleted": False,
            }
        )
    return {
        "status": "authoritative" if passed else "not_authoritative_fail_closed",
        "scope": "d5_heldout_paired_shadow_for_bound_input_spec",
        "supersedes": superseded,
    }


def _publish(
    destination: Path,
    report: dict[str, Any],
    lineage: Sequence[Mapping[str, Any]],
) -> None:
    if destination.exists():
        _fail("paired_shadow_destination_exists", str(destination))
    lineage_bytes = b"".join(_canonical_json_bytes(dict(item)) for item in lineage)
    report["paired_lineage"] = {
        "schema_version": PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
        "filename": PAIRED_SHADOW_LINEAGE_FILENAME,
        "record_count": len(lineage),
        "sha256": hashlib.sha256(lineage_bytes).hexdigest(),
    }
    report["content_sha256"] = _sha256_json(report)
    temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        (temporary / PAIRED_SHADOW_LINEAGE_FILENAME).write_bytes(lineage_bytes)
        (temporary / PAIRED_SHADOW_REPORT_FILENAME).write_bytes(
            _canonical_json_bytes(report)
        )
        (temporary / PAIRED_SHADOW_MARKDOWN_FILENAME).write_text(
            render_paired_shadow_markdown(report).rstrip() + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def render_paired_shadow_markdown(report: Mapping[str, Any]) -> str:
    """Render concise Chinese evidence without claiming online capability."""

    if not report.get("execution_completed"):
        reasons = report.get("paired_shadow_assessment", {}).get("failure_reasons", [])
        return "\n".join(
            [
                "# D5 同种子配对影子评估",
                "",
                "## 结论",
                "",
                "评估在输入或执行阶段关闭，未形成模型准入结论。",
                f"稳定失败原因：`{', '.join(str(item) for item in reasons)}`。",
                "G1、辅助模式和控制权限保持关闭，在线规则回退保持启用。",
                "",
            ]
        )
    totals = report["totals"]
    overall = report["overall"]
    control = overall["control"]
    model = overall["model"]
    assessment = report["paired_shadow_assessment"]
    identity = report["graph_identity"]
    diagnostics = report["feature_label_diagnostics"]
    feature_by_name = {
        item["feature"]: item for item in diagnostics["features"]
    }
    evidence_lines = [
        f"证据状态为 `{report['evidence_status']['status']}`。"
    ]
    if report["evidence_status"]["supersedes"]:
        evidence_lines.append(
            "旧版输出按 `superseded_preserved` 保留，未覆盖或删除。"
        )
    lines = [
        "# D5 同种子配对影子评估",
        "",
        "## 结论",
        "",
        f"正式评估状态为 `{assessment['status']}`。本次比较覆盖 "
        f"{totals['episode_count']} 帧、{totals['seed_count']} 个种子和 "
        f"{totals['scenario_scale_cell_count']} 个场景规模单元。",
        "评估只比较确定性几何规则和冻结图神经网络，不重估温度、不重选阈值、"
        "不更新权重，也不改变候选边。结果不能直接解释为在线能力。",
        *evidence_lines,
        "",
        "## 同图约束",
        "",
        f"- 图 identity：`{identity['graph_identity_match_count']}/"
        f"{identity['episode_count']}`。",
        f"- 候选边 identity：`{identity['candidate_identity_match_count']}/"
        f"{identity['episode_count']}`。",
        f"- evaluator 标签 identity：`{identity['label_identity_match_count']}/"
        f"{identity['episode_count']}`。",
        "- 模型新增或删除候选边：`0`。",
        "",
        "## 总体指标",
        "",
        "| 指标 | 几何规则 | 冻结模型 | 模型减规则 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for layer, label in (("edge", "边"), ("cluster_pairwise", "簇对")):
        for metric in ("precision", "recall", "f1", "false_merge_rate"):
            left = control[layer][metric]
            right = model[layer][metric]
            delta = _subtract(right, left)
            lines.append(
                f"| {label}{metric} | {_format_metric(left)} | "
                f"{_format_metric(right)} | {_format_metric(delta)} |"
            )
    lines.extend(
        [
            f"| 候选召回率 | {_format_metric(overall['candidate_recall'])} | "
            f"{_format_metric(overall['candidate_recall'])} | 0.000000 |",
            f"| 推理 P50 毫秒 | {control['latency_ms']['scoring_p50']:.6f} | "
            f"{model['latency_ms']['scoring_p50']:.6f} | "
            f"{model['latency_ms']['scoring_p50'] - control['latency_ms']['scoring_p50']:.6f} |",
            f"| 推理 P95 毫秒 | {control['latency_ms']['scoring_p95']:.6f} | "
            f"{model['latency_ms']['scoring_p95']:.6f} | "
            f"{model['latency_ms']['scoring_p95'] - control['latency_ms']['scoring_p95']:.6f} |",
            "",
            "## 困难扰动",
            "",
            "五类扰动由 episode 编号确定随机种子，对标签不可见。每个扰动视图保持"
            "候选边和门控分数不变，并把同一匿名图送入规则和模型。该结果用于检查"
            "特征捷径，不代表候选门在真实扰动下仍能保持相同召回率。",
            "",
            "| 扰动 | 候选召回 | 规则边 F1 | 模型边 F1 | 规则簇 F1 | 模型簇 F1 | 模型错误合并率 | 模型 P95 毫秒 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for profile in report["robustness_profiles"]:
        profile_id = profile["profile"]["profile_id"]
        lines.append(
            f"| `{profile_id}` | {_format_metric(profile['candidate_recall'])} | "
            f"{_format_metric(profile['control']['edge']['f1'])} | "
            f"{_format_metric(profile['model']['edge']['f1'])} | "
            f"{_format_metric(profile['control']['cluster_pairwise']['f1'])} | "
            f"{_format_metric(profile['model']['cluster_pairwise']['f1'])} | "
            f"{_format_metric(profile['model']['cluster_pairwise']['false_merge_rate'])} | "
            f"{profile['model']['latency_ms']['scoring_p95']:.6f} |"
        )
    fallback = report["runtime_fallback_probe"]
    lines.extend(
        [
            "",
            "## 异常回退",
            "",
            f"在线评分边界注入 `{fallback['case_count']}` 类模型异常，"
            f"`{fallback['passed_case_count']}` 类返回与几何规则逐值一致的概率，"
            f"回退率为 `{fallback['fallback_rate']:.6f}`。",
            "",
            "| 异常 | 状态 | 原因 | 与规则概率一致 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in fallback["cases"]:
        lines.append(
            f"| `{item['case_id']}` | `{item['scoring_status']}` | "
            f"`{item['fallback_reason']}` | "
            f"{'是' if item['rule_probability_match'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "## 特征与标签审查",
            "",
            "本节只检查冻结合成保留集的单特征可分性，不是模型归因分析。统计在两臂"
            "预测完成后使用 evaluator 标签生成，未改变候选图、权重、温度或阈值。",
            f"`shared_global_track_count` 与标签的互信息为 "
            f"`{diagnostics['shared_global_track_count']['mutual_information_bits']:.6f}` bit。"
            "本保留集该特征取值 1 的样本为空，不能验证模型在共享中心投影线索存在时的表现。",
            "",
            "| shared_global_track_count | 候选边 | 正样本率 | 规则边 F1 | 模型边 F1 |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    shared_label_strata = diagnostics["shared_global_track_count"]["strata"]
    for stratum in ("0", "1", "other"):
        label_stats = shared_label_strata[stratum]
        rule_stats = control["edge_by_shared_global_track_count"][stratum]
        model_stats = model["edge_by_shared_global_track_count"][stratum]
        lines.append(
            f"| {stratum} | {label_stats['edge_count']} | "
            f"{_format_metric(label_stats['positive_rate'])} | "
            f"{_format_metric(rule_stats['f1'])} | "
            f"{_format_metric(model_stats['f1'])} |"
        )
    lines.extend(
        [
            "",
            "单特征最佳方向受试者工作特征曲线下面积不低于 "
            f"`{diagnostics['near_deterministic_auc_threshold']:.3f}` 的项目如下。"
            "这些统计反映数据可分性，不证明冻结模型实际依赖对应特征。",
            f"最高单特征 AUC 为 "
            f"`{_format_metric(diagnostics['maximum_single_feature_auc']['best_direction_auc'])}`"
            f"，对应 `{diagnostics['maximum_single_feature_auc']['feature']}`。",
            "",
            "| 特征 | 最佳方向 AUC | 相关系数 | 正样本零值比例 | 负样本零值比例 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for name in diagnostics["near_deterministic_feature_names"]:
        item = feature_by_name[name]
        lines.append(
            f"| `{name}` | {item['univariate_auc']['best_direction_auc']:.6f} | "
            f"{_format_metric(item['point_biserial_correlation']['value'])} | "
            f"{item['positive']['exact_zero_fraction']:.6f} | "
            f"{item['negative']['exact_zero_fraction']:.6f} |"
        )
    if not diagnostics["near_deterministic_feature_names"]:
        lines.append("| 无 | 不适用 | 不适用 | 不适用 | 不适用 |")
    lines.extend(
        [
            "",
            "冻结模型取得满分的主要局限是合成保留集仍存在接近确定性的运动尺度线索。"
            "当前结果不能表述为真实跨视角泛化，也不能作为线上准入依据。后续应增加独立"
            "生成机制、相机异步、尺度噪声、姿态扰动和困难同运动负样本，再进行同种子影子对照。",
            "",
            "## 场景规模单元",
            "",
            "| 单元 | 帧数 | 候选召回 | 规则边 F1 | 模型边 F1 | 规则簇 F1 | 模型簇 F1 | 通过 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for cell in report["cell_metrics"]:
        lines.append(
            f"| {cell['group_id']} | {cell['episode_count']} | "
            f"{_format_metric(cell['candidate_recall'])} | "
            f"{_format_metric(cell['control']['edge']['f1'])} | "
            f"{_format_metric(cell['model']['edge']['f1'])} | "
            f"{_format_metric(cell['control']['cluster_pairwise']['f1'])} | "
            f"{_format_metric(cell['model']['cluster_pairwise']['f1'])} | "
            f"{'是' if cell['quality_not_degraded'] else '否'} |"
        )
    failures = assessment["failure_reasons"] or ["无"]
    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            f"准入失败原因：`{'; '.join(failures)}`。",
            "同相机互斥违规、在线真值特征、未标注候选边和全局航迹编号改写均按"
            "零值门控。无论本次 paired shadow 是否通过，G1、辅助模式和控制权限均"
            "保持关闭，确定性规则仍是在线回退路径，后续等待 D6 独立审计。",
            "",
            "## 运行信息",
            "",
            f"- 总耗时：`{report['runtime']['wall_seconds']:.3f}` 秒。",
            f"- 最大常驻内存：`{report['runtime']['max_rss_kib']}` KiB。",
            f"- 设备：`{report['runtime']['device']}`。",
            f"- 报告内容 SHA-256：`{report.get('content_sha256', '发布时计算')}`。",
            "",
        ]
    )
    return "\n".join(lines)


def _failure_report(
    spec: PairedShadowInputSpec,
    started: float,
    code: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "schema_version": PAIRED_SHADOW_SCHEMA_VERSION,
        "evaluated_at_utc": spec.evaluated_at_utc,
        "status": "fail_closed",
        "execution_completed": False,
        "evaluation_role": "evaluator_only_paired_shadow",
        "input_spec": spec.to_payload(),
        "input_spec_sha256": _sha256_json(spec.to_payload()),
        "evidence_status": _evidence_status(
            spec,
            passed=False,
            actual_hashes={},
        ),
        "paired_shadow_assessment": {
            "status": "fail_closed",
            "passed": False,
            "failure_reasons": [code],
            "failure_detail": detail,
            "d6_external_audit_required": True,
            "g1": False,
            "assist": False,
            "authority": False,
            "rule_fallback": True,
        },
        "runtime": {
            "wall_seconds": time.perf_counter() - started,
            "max_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "device": str(spec.device),
        },
        "authority": {
            "status": "fail_closed",
            "paired_shadow_passed": False,
            "g1": False,
            "assist": False,
            "authority": False,
            "rule_fallback": True,
            "runtime_default_changed": False,
        },
    }


def _graph_arrays_sha256(graph: SparseTrackletGraph) -> str:
    return _combined_array_sha256(
        graph.node_features,
        graph.edge_index,
        graph.edge_features,
        strings=[
            tuple(node.tracklet_key for node in graph.nodes),
            tuple(node.camera_key for node in graph.nodes),
        ],
    )


def _loaded_graph_arrays_sha256(graph: Any) -> str:
    return _combined_array_sha256(
        graph.node_features,
        graph.edge_index,
        graph.edge_features,
        strings=[graph.tracklet_keys, graph.camera_keys],
    )


def _candidate_edges_sha256(graph: SparseTrackletGraph) -> str:
    return _sha256_json(
        [
            {
                "source": edge.source_index,
                "target": edge.target_index,
                "gate_score": edge.gate_score,
                "shared_projection_count": len(edge.shared_global_track_ids),
            }
            for edge in graph.edges
        ]
    )


def _evaluator_labels_sha256(labels: Mapping[str, Any]) -> str:
    return _sha256_json(
        [
            {
                "tracklet_key": str(key),
                "truth_entity_id": str(label.truth_entity_id),
                "measurement_timestamp": float(label.measurement_timestamp),
            }
            for key, label in sorted(labels.items())
        ]
    )


def _same_camera_candidate_edge_count(graph: SparseTrackletGraph) -> int:
    return sum(
        graph.nodes[edge.source_index].camera_key
        == graph.nodes[edge.target_index].camera_key
        for edge in graph.edges
    )


def _combined_array_sha256(
    *arrays: np.ndarray,
    strings: Sequence[Sequence[str]],
) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(_canonical_json_bytes(list(contiguous.shape)))
        digest.update(contiguous.tobytes(order="C"))
    for values in strings:
        digest.update(_canonical_json_bytes(list(values)))
    return digest.hexdigest()


def _array_sha256(array: np.ndarray) -> str:
    return _combined_array_sha256(np.asarray(array), strings=[])


def _implementation_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {name: sha256_file(root / name) for name in _IMPLEMENTATION_FILES}


def _verify_content_hash(
    value: Mapping[str, Any], expected: str, code: str
) -> None:
    actual_field = value.get("content_sha256")
    unhashed = dict(value)
    unhashed.pop("content_sha256", None)
    calculated = _sha256_json(unhashed)
    if actual_field != expected or calculated != expected:
        _fail(code, f"field={actual_field};calculated={calculated};expected={expected}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _fail("paired_shadow_json_invalid", f"{path}:{exc}")
    if not isinstance(value, dict):
        _fail("paired_shadow_json_object_required", str(path))
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


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _ratio(numerator: int, denominator: int, *, zero: float | None = None) -> float | None:
    return numerator / denominator if denominator else zero


def _subtract(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    return float(left) - float(right)


def _format_metric(value: Any) -> str:
    return "不可用" if value is None else f"{float(value):.6f}"


def _exception_code(exc: Exception) -> str:
    if isinstance(
        exc,
        (
            TrackletPairedShadowError,
            TrackletHeldoutEvaluationError,
            ModelBundleValidationError,
        ),
    ):
        return str(exc.code)
    return f"paired_shadow_unexpected_{type(exc).__name__}"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _fail(code: str, message: str) -> None:
    raise TrackletPairedShadowError(code, message)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run D5 deterministic-rule versus frozen-GNN paired shadow."
    )
    parser.add_argument("--heldout-corpus", required=True)
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--heldout-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-corpus-manifest-sha256", required=True)
    parser.add_argument("--expected-corpus-content-sha256", required=True)
    parser.add_argument("--expected-corpus-config-sha256", required=True)
    parser.add_argument("--expected-bundle-manifest-sha256", required=True)
    parser.add_argument("--expected-bundle-weights-sha256", required=True)
    parser.add_argument("--expected-bundle-checksums-sha256", required=True)
    parser.add_argument("--expected-heldout-report-sha256", required=True)
    parser.add_argument("--expected-heldout-report-content-sha256", required=True)
    parser.add_argument("--superseded-output-dir")
    parser.add_argument("--expected-superseded-report-sha256")
    parser.add_argument("--expected-superseded-lineage-sha256")
    parser.add_argument("--evaluated-at-utc", required=True)
    parser.add_argument("--device", default="cpu")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    spec = PairedShadowInputSpec(
        heldout_corpus_dir=args.heldout_corpus,
        bundle_dir=args.bundle_dir,
        heldout_report_path=args.heldout_report,
        output_dir=args.output_dir,
        expected_corpus_manifest_sha256=args.expected_corpus_manifest_sha256,
        expected_corpus_content_sha256=args.expected_corpus_content_sha256,
        expected_corpus_config_sha256=args.expected_corpus_config_sha256,
        expected_bundle_manifest_sha256=args.expected_bundle_manifest_sha256,
        expected_bundle_weights_sha256=args.expected_bundle_weights_sha256,
        expected_bundle_checksums_sha256=args.expected_bundle_checksums_sha256,
        expected_heldout_report_sha256=args.expected_heldout_report_sha256,
        expected_heldout_report_content_sha256=args.expected_heldout_report_content_sha256,
        evaluated_at_utc=args.evaluated_at_utc,
        superseded_output_dir=args.superseded_output_dir,
        expected_superseded_report_sha256=args.expected_superseded_report_sha256,
        expected_superseded_lineage_sha256=args.expected_superseded_lineage_sha256,
        device=args.device,
    )
    report = run_tracklet_paired_shadow(spec)
    print(
        json.dumps(
            {
                "status": report["status"],
                "execution_completed": report["execution_completed"],
                "content_sha256": report["content_sha256"],
                "output_dir": str(spec.output_dir),
                "evidence_status": report["evidence_status"]["status"],
                "g1": False,
                "assist": False,
                "authority": False,
                "rule_fallback": True,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0 if report["execution_completed"] and report["status"] == "pass" else 2


__all__ = [
    "FLOAT_COMPARISON_TOLERANCE",
    "PAIRED_SHADOW_LINEAGE_FILENAME",
    "PAIRED_SHADOW_MARKDOWN_FILENAME",
    "PAIRED_SHADOW_REPORT_FILENAME",
    "PAIRED_SHADOW_SCHEMA_VERSION",
    "PairedShadowInputSpec",
    "TrackletPairedShadowError",
    "main",
    "render_paired_shadow_markdown",
    "run_tracklet_paired_shadow",
]


if __name__ == "__main__":
    raise SystemExit(main())
