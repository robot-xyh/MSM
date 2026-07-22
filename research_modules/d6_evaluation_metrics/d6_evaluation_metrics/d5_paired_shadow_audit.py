"""Independent, read-only audit of D5 paired-shadow graph evidence.

The producer report is treated as an authenticated claim, not as the source of
truth for aggregate metrics.  This module re-reads the paired lineage and the
held-out graph corpus, verifies every bound artifact, recomputes aggregate
counts, and keeps all learning authority disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


D5_PAIRED_SHADOW_AUDIT_SCHEMA_VERSION = "d6.d5-paired-shadow-audit.v1"
D5_PAIRED_SHADOW_AUDIT_MANIFEST_SCHEMA_VERSION = (
    "d6.d5-paired-shadow-audit-manifest.v1"
)
D5_PAIRED_SHADOW_INPUT_SCHEMA_VERSION = "d5.tracklet-paired-shadow-input.v1"
D5_PAIRED_SHADOW_REPORT_SCHEMA_VERSION = "d5.tracklet-paired-shadow.v1"
D5_PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION = (
    "d5.tracklet-paired-shadow-lineage.v1"
)
D5_HELDOUT_CORPUS_SCHEMA_VERSION = "d5.tracklet-heldout-corpus.v1"
D5_HELDOUT_EVALUATION_SCHEMA_VERSION = (
    "d5.tracklet-heldout-model-evaluation.v1"
)
D5_MODEL_BUNDLE_SCHEMA_VERSION = "d5.tracklet-model-bundle.v3"

D5_PAIRED_SHADOW_EXPECTED_SEEDS = tuple(range(1000, 1020))
D5_PAIRED_SHADOW_SCENARIOS = (
    "nominal",
    "dense_crossing",
    "formation_split",
    "evasive_multilevel",
    "delayed_noisy",
    "communication_degraded",
    "center_failure",
    "secondary_failure",
    "high_threat_m_to_n",
)
D5_PAIRED_SHADOW_SCALES = (5, 20, 50, 100, 200)
D5_PAIRED_SHADOW_EXPECTED_CELLS = tuple(
    (scenario, scale)
    for scenario in D5_PAIRED_SHADOW_SCENARIOS
    for scale in D5_PAIRED_SHADOW_SCALES
)
D5_PAIRED_SHADOW_EXPECTED_FRAME_COUNT = 900
D5_PAIRED_SHADOW_EXPECTED_LABELED_EDGE_COUNT = 74_024
D5_PAIRED_SHADOW_MAXIMUM_MODEL_P95_LATENCY_MS = 100.0
D5_PAIRED_SHADOW_MAXIMUM_FALSE_MERGE_RATE = 0.01
D5_PAIRED_SHADOW_MINIMUM_CANDIDATE_RECALL = 0.95

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COUNT_NAMES = ("true_positive", "false_positive", "false_negative", "true_negative")
_CENTER_BINDING_FEATURES = (
    "shared_global_track_count",
    "global_projection_mahalanobis",
)
_SYNTHETIC_SEPARABILITY_F1 = 0.98
_SYNTHETIC_SEPARABILITY_BALANCED_ACCURACY = 0.95


class D5PairedShadowAuditError(ValueError):
    """Raised when paired-shadow evidence fails a fail-closed audit gate."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class D5PairedShadowAuditInputs:
    """Explicit paths and out-of-band hashes for one independent audit."""

    paired_report_path: Path
    paired_lineage_path: Path
    heldout_corpus_dir: Path
    heldout_report_path: Path
    model_bundle_dir: Path
    d5_source_dir: Path
    superseded_report_path: Path
    superseded_lineage_path: Path
    output_dir: Path
    expected_paired_report_sha256: str
    expected_paired_report_content_sha256: str
    expected_paired_lineage_sha256: str
    expected_corpus_manifest_sha256: str
    expected_corpus_content_sha256: str
    expected_corpus_config_sha256: str
    expected_heldout_report_sha256: str
    expected_heldout_report_content_sha256: str
    expected_bundle_manifest_sha256: str
    expected_bundle_weights_sha256: str
    expected_bundle_checksums_sha256: str
    expected_superseded_report_sha256: str
    expected_superseded_lineage_sha256: str
    audited_at_utc: str

    def __post_init__(self) -> None:
        for name in (
            "paired_report_path",
            "paired_lineage_path",
            "heldout_corpus_dir",
            "heldout_report_path",
            "model_bundle_dir",
            "d5_source_dir",
            "superseded_report_path",
            "superseded_lineage_path",
            "output_dir",
        ):
            object.__setattr__(self, name, Path(getattr(self, name)).resolve())
        for name in (
            "expected_paired_report_sha256",
            "expected_paired_report_content_sha256",
            "expected_paired_lineage_sha256",
            "expected_corpus_manifest_sha256",
            "expected_corpus_content_sha256",
            "expected_corpus_config_sha256",
            "expected_heldout_report_sha256",
            "expected_heldout_report_content_sha256",
            "expected_bundle_manifest_sha256",
            "expected_bundle_weights_sha256",
            "expected_bundle_checksums_sha256",
            "expected_superseded_report_sha256",
            "expected_superseded_lineage_sha256",
        ):
            value = str(getattr(self, name)).strip().lower()
            if not _SHA256_RE.fullmatch(value):
                _fail("invalid_out_of_band_sha256", f"{name}={value!r}")
            object.__setattr__(self, name, value)
        if not str(self.audited_at_utc).strip():
            _fail("audit_timestamp_missing", "audited_at_utc is required")

    def expected_hashes(self) -> dict[str, str]:
        return {
            "paired_report_sha256": self.expected_paired_report_sha256,
            "paired_report_content_sha256": self.expected_paired_report_content_sha256,
            "paired_lineage_sha256": self.expected_paired_lineage_sha256,
            "corpus_manifest_sha256": self.expected_corpus_manifest_sha256,
            "corpus_content_sha256": self.expected_corpus_content_sha256,
            "corpus_config_sha256": self.expected_corpus_config_sha256,
            "heldout_report_sha256": self.expected_heldout_report_sha256,
            "heldout_report_content_sha256": self.expected_heldout_report_content_sha256,
            "bundle_manifest_sha256": self.expected_bundle_manifest_sha256,
            "bundle_weights_sha256": self.expected_bundle_weights_sha256,
            "bundle_checksums_sha256": self.expected_bundle_checksums_sha256,
            "superseded_report_sha256": self.expected_superseded_report_sha256,
            "superseded_lineage_sha256": self.expected_superseded_lineage_sha256,
        }


def audit_d5_paired_shadow_evidence(
    inputs: D5PairedShadowAuditInputs,
) -> dict[str, Any]:
    """Audit producer evidence without writing to or importing from D5."""

    _validate_input_locations(inputs)
    report = _load_json_object(inputs.paired_report_path, "paired report")
    corpus_manifest_path = inputs.heldout_corpus_dir / "heldout_manifest.json"
    heldout_report = _load_json_object(inputs.heldout_report_path, "held-out report")
    corpus_manifest = _load_json_object(corpus_manifest_path, "held-out manifest")
    bundle_manifest_path = inputs.model_bundle_dir / "manifest.json"
    bundle_weights_path = inputs.model_bundle_dir / "weights.pt"
    bundle_checksums_path = inputs.model_bundle_dir / "SHA256SUMS"
    bundle_manifest = _load_json_object(bundle_manifest_path, "model bundle manifest")

    critical_paths = {
        "paired_report": inputs.paired_report_path,
        "paired_lineage": inputs.paired_lineage_path,
        "corpus_manifest": corpus_manifest_path,
        "heldout_report": inputs.heldout_report_path,
        "bundle_manifest": bundle_manifest_path,
        "bundle_weights": bundle_weights_path,
        "bundle_checksums": bundle_checksums_path,
        "superseded_report": inputs.superseded_report_path,
        "superseded_lineage": inputs.superseded_lineage_path,
    }
    _verify_critical_hashes(inputs, critical_paths, report, corpus_manifest, heldout_report)
    inventory_paths = _validate_corpus_manifest_and_inventory(inputs, corpus_manifest)
    implementation_paths = _validate_implementation_bindings(inputs, report)
    all_snapshot_paths = {**critical_paths, **inventory_paths, **implementation_paths}
    snapshot_before = _snapshot(all_snapshot_paths)

    _validate_report_contract(inputs, report)
    _validate_heldout_and_bundle_bindings(
        inputs,
        report=report,
        corpus_manifest=corpus_manifest,
        heldout_report=heldout_report,
        bundle_manifest=bundle_manifest,
        bundle_checksums_path=bundle_checksums_path,
    )
    lineage_records = _load_jsonl(inputs.paired_lineage_path)
    lineage_summary = validate_paired_lineage_records(
        lineage_records,
        report=report,
        corpus_manifest=corpus_manifest,
    )
    aggregate_summary = _validate_recomputed_aggregates(lineage_records, report)
    separability = _audit_synthetic_separability(
        corpus_root=inputs.heldout_corpus_dir,
        corpus_manifest=corpus_manifest,
    )
    _validate_authoritative_v2_evidence(inputs, report, separability)
    _validate_independent_safety(report, corpus_manifest, separability)
    _validate_finite_numbers(report)

    snapshot_after = _snapshot(all_snapshot_paths)
    _expect_equal(
        snapshot_after,
        snapshot_before,
        "input_artifact_mutation_detected",
        "one or more paired-shadow inputs changed during audit",
    )
    snapshot_evidence = _snapshot_evidence(
        snapshot_before,
        snapshot_after,
        critical_paths,
        implementation_paths,
    )
    external_grade = separability["external_generalization_evidence_grade"]
    audit_status = (
        "pass_with_synthetic_separability_caveat"
        if separability["synthetic_single_feature_separability_risk"] == "high"
        else "pass"
    )
    result: dict[str, Any] = {
        "schema_version": D5_PAIRED_SHADOW_AUDIT_SCHEMA_VERSION,
        "audited_at_utc": str(inputs.audited_at_utc),
        "audit_role": "independent_read_only_consumer",
        "status": audit_status,
        "audit_passed": True,
        "explicit_input_binding": {
            "out_of_band_hashes": inputs.expected_hashes(),
            "all_required_hashes_matched": True,
            "producer_content_sha256_verified": True,
            "producer_file_sha256_verified": True,
            "producer_input_bindings_verified": True,
            "artifact_inventory_verified": True,
            "input_artifacts_unchanged": True,
            **snapshot_evidence,
        },
        "paired_shadow": {
            "layer_status": "complete",
            "research_shadow_status": "qualified_with_synthetic_separability_caveat"
            if external_grade != "supported"
            else "qualified",
            "seed_count": 20,
            "frame_count": D5_PAIRED_SHADOW_EXPECTED_FRAME_COUNT,
            "scenario_scale_cell_count": len(D5_PAIRED_SHADOW_EXPECTED_CELLS),
            "labeled_candidate_edge_count": (
                D5_PAIRED_SHADOW_EXPECTED_LABELED_EDGE_COUNT
            ),
            "lineage": lineage_summary,
            "recomputed_aggregates": aggregate_summary,
        },
        "synthetic_separability": separability,
        "evidence_layers": {
            "data_support": "complete",
            "training_source": "complete",
            "internal_model_test": "complete",
            "held_out_seed": "complete",
            "paired_shadow": "complete",
            "external_generalization": external_grade,
            "online_admission": "not_admitted",
        },
        "authority": {
            "g1": False,
            "ppo": False,
            "assist": False,
            "authority": False,
            "rule_fallback": True,
            "runtime_default_changed": False,
            "online_admission_changed": False,
        },
        "conclusion": {
            "paired_execution_and_accounting": "verified",
            "external_generalization": external_grade,
            "center_identity_cue_primary_driver": separability[
                "center_identity_cue_assessment"
            ]["primary_driver_supported"],
            "single_feature_explanation_available": separability[
                "single_feature_explanation_available"
            ],
            "online_permission": "denied",
            "required_next_evidence": [
                "remove_or_randomize_synthetically_separable motion/scale cues",
                "evaluate independently generated camera/target geometry",
                "repeat paired shadow without center binding features",
                "retain deterministic rule fallback during all follow-on studies",
            ],
        },
    }
    return _with_content_sha256(result)


def write_d5_paired_shadow_audit(
    inputs: D5PairedShadowAuditInputs,
) -> dict[str, Any]:
    """Write a self-contained D6 evidence package after a successful audit."""

    if inputs.output_dir.exists():
        _fail("output_directory_exists", str(inputs.output_dir))
    report = audit_d5_paired_shadow_evidence(inputs)
    markdown = render_d5_paired_shadow_audit_markdown(report)
    parent = inputs.output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{inputs.output_dir.name}.", dir=parent))
    try:
        report_path = temporary / "d5_paired_shadow_audit.json"
        markdown_path = temporary / "D5_PAIRED_SHADOW_AUDIT_CN.md"
        _write_json(report_path, report)
        markdown_path.write_text(markdown, encoding="utf-8")
        artifacts = [
            _artifact_record(report_path),
            _artifact_record(markdown_path),
        ]
        manifest = _with_content_sha256(
            {
                "schema_version": D5_PAIRED_SHADOW_AUDIT_MANIFEST_SCHEMA_VERSION,
                "audited_at_utc": report["audited_at_utc"],
                "status": report["status"],
                "audit_report_content_sha256": report["content_sha256"],
                "artifacts": artifacts,
                "input_artifact_set_sha256": report["explicit_input_binding"][
                    "input_artifact_set_sha256"
                ],
                "input_artifact_set_sha256_before": report[
                    "explicit_input_binding"
                ]["input_artifact_set_sha256_before"],
                "input_artifact_set_sha256_after": report[
                    "explicit_input_binding"
                ]["input_artifact_set_sha256_after"],
                "authority": dict(report["authority"]),
            }
        )
        manifest_path = temporary / "manifest.json"
        _write_json(manifest_path, manifest)
        checksum_records = artifacts + [_artifact_record(manifest_path)]
        (temporary / "SHA256SUMS").write_text(
            "".join(f"{item['sha256']}  {item['path']}\n" for item in checksum_records),
            encoding="ascii",
        )
        temporary.rename(inputs.output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return report


def validate_paired_lineage_records(
    records: Sequence[Mapping[str, Any]],
    *,
    report: Mapping[str, Any],
    corpus_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact one-to-one pairing and return independently counted evidence."""

    _expect_equal(
        len(records),
        D5_PAIRED_SHADOW_EXPECTED_FRAME_COUNT,
        "lineage_record_count_mismatch",
        "paired lineage must contain exactly 900 records",
    )
    descriptors = {
        str(item["episode_uid"]): item for item in _sequence(corpus_manifest, "episodes")
    }
    _expect_equal(
        len(descriptors),
        D5_PAIRED_SHADOW_EXPECTED_FRAME_COUNT,
        "corpus_episode_catalog_mismatch",
        "held-out manifest must contain 900 unique episode UIDs",
    )
    seen_uids: set[str] = set()
    seen_cells: set[tuple[int, str, int]] = set()
    graph_match = candidate_match = label_match = shared_instance = 0
    candidate_edges = labeled_edges = unlabeled_edges = 0
    node_count = 0
    for record in records:
        _expect_equal(
            record.get("schema_version"),
            D5_PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
            "lineage_schema_mismatch",
            "paired lineage schema changed",
        )
        uid = str(record.get("episode_uid", ""))
        _expect(uid in descriptors, "lineage_unknown_episode", uid)
        _expect(uid not in seen_uids, "lineage_duplicate_episode", uid)
        seen_uids.add(uid)
        descriptor = descriptors[uid]
        key = (
            _integer(record.get("seed"), "lineage seed"),
            str(record.get("scenario", "")),
            _integer(record.get("scale"), "lineage scale"),
        )
        _expect(key not in seen_cells, "lineage_duplicate_seed_cell", repr(key))
        seen_cells.add(key)
        _expect_equal(
            key,
            (
                int(descriptor["seed"]),
                str(descriptor["scenario"]),
                int(descriptor["scale"]),
            ),
            "lineage_descriptor_identity_mismatch",
            uid,
        )
        _expect_equal(
            _integer(record.get("loaded_graph_instance_count"), "loaded graph count"),
            1,
            "lineage_graph_loaded_more_than_once",
            uid,
        )
        graph_hashes = {
            str(record.get(name, ""))
            for name in (
                "graph_sha256",
                "control_graph_sha256",
                "model_graph_sha256",
            )
        }
        _expect_equal(
            graph_hashes,
            {str(descriptor["graph_sha256"])},
            "lineage_graph_identity_mismatch",
            uid,
        )
        label_hashes = {
            str(record.get(name, ""))
            for name in (
                "labels_sha256",
                "control_labels_sha256",
                "model_labels_sha256",
            )
        }
        _expect_equal(
            label_hashes,
            {str(descriptor["labels_sha256"])},
            "lineage_label_identity_mismatch",
            uid,
        )
        _expect_equal(
            record.get("control_candidate_edge_sha256"),
            record.get("model_candidate_edge_sha256"),
            "lineage_candidate_identity_mismatch",
            uid,
        )
        _expect_equal(
            record.get("source_arrays_sha256"),
            record.get("shared_arrays_sha256"),
            "lineage_loaded_array_identity_mismatch",
            uid,
        )
        source_arrays_sha256 = record.get("source_arrays_sha256")
        for name in (
            "graph_after_control_sha256",
            "graph_after_model_sha256",
            "graph_after_clustering_sha256",
        ):
            _expect_equal(
                record.get(name),
                source_arrays_sha256,
                "lineage_graph_mutation_detected",
                f"{uid}:{name}",
            )
        _expect_equal(
            record.get("evaluator_labels_after_sha256"),
            record.get("evaluator_labels_before_sha256"),
            "lineage_evaluator_label_mutation_detected",
            uid,
        )
        _expect(
            record.get("truth_scoring_started_after_both_arm_predictions") is True,
            "lineage_truth_scoring_order_invalid",
            uid,
        )
        _expect_equal(
            _integer(
                record.get("same_camera_candidate_edge_count"),
                "same camera candidate edge count",
            ),
            0,
            "lineage_same_camera_candidate_edge",
            uid,
        )
        for name in (
            "graph_identity_match",
            "candidate_identity_match",
            "label_identity_match",
        ):
            _expect(record.get(name) is True, f"lineage_{name}_false", uid)
        graph_match += int(bool(record["graph_identity_match"]))
        candidate_match += int(bool(record["candidate_identity_match"]))
        label_match += int(bool(record["label_identity_match"]))
        shared_instance += 1
        edge_count = _integer(record.get("candidate_edge_count"), "candidate edges")
        labeled_count = _integer(
            record.get("labeled_candidate_edge_count"), "labeled candidate edges"
        )
        unlabeled_count = _integer(
            record.get("unlabeled_candidate_edge_count"), "unlabeled candidate edges"
        )
        _expect_equal(
            edge_count,
            int(descriptor["edge_count"]),
            "lineage_edge_count_mismatch",
            uid,
        )
        _expect_equal(
            labeled_count + unlabeled_count,
            edge_count,
            "lineage_label_coverage_count_mismatch",
            uid,
        )
        _expect_equal(unlabeled_count, 0, "lineage_unlabeled_edge", uid)
        _validate_record_metrics(record, edge_count, uid)
        candidate_edges += edge_count
        labeled_edges += labeled_count
        unlabeled_edges += unlabeled_count
        node_count += _integer(record.get("node_count"), "node count")

    expected_keys = {
        (seed, scenario, scale)
        for seed in D5_PAIRED_SHADOW_EXPECTED_SEEDS
        for scenario, scale in D5_PAIRED_SHADOW_EXPECTED_CELLS
    }
    _expect_equal(
        seen_cells,
        expected_keys,
        "lineage_seed_cell_catalog_mismatch",
        "lineage has missing or extra seed/cell records",
    )
    _expect_equal(
        candidate_edges,
        D5_PAIRED_SHADOW_EXPECTED_LABELED_EDGE_COUNT,
        "lineage_candidate_edge_total_mismatch",
        str(candidate_edges),
    )
    _expect_equal(
        labeled_edges,
        D5_PAIRED_SHADOW_EXPECTED_LABELED_EDGE_COUNT,
        "lineage_labeled_edge_total_mismatch",
        str(labeled_edges),
    )
    graph_identity = _mapping(report, "graph_identity")
    expected_identity = {
        "episode_count": 900,
        "same_loaded_graph_sent_to_both_arms_count": shared_instance,
        "graph_identity_match_count": graph_match,
        "candidate_identity_match_count": candidate_match,
        "label_identity_match_count": label_match,
        "graph_identity_ratio": graph_match / len(records),
        "candidate_identity_ratio": candidate_match / len(records),
        "label_identity_ratio": label_match / len(records),
        "model_candidate_edges_added_or_removed": 0,
    }
    _expect_numeric_mapping_equal(
        graph_identity,
        expected_identity,
        "report_graph_identity_summary_mismatch",
    )
    return {
        "record_count": len(records),
        "unique_episode_uid_count": len(seen_uids),
        "unique_seed_cell_count": len(seen_cells),
        "missing_record_count": 0,
        "duplicate_record_count": 0,
        "loaded_graph_instance_equal_one_count": shared_instance,
        "control_model_graph_identity_ratio": graph_match / len(records),
        "control_model_candidate_identity_ratio": candidate_match / len(records),
        "control_model_label_identity_ratio": label_match / len(records),
        "candidate_edges_added_or_removed": 0,
        "candidate_edge_count": candidate_edges,
        "labeled_candidate_edge_count": labeled_edges,
        "unlabeled_candidate_edge_count": unlabeled_edges,
        "node_count": node_count,
    }


def screen_single_feature_separability(
    values: np.ndarray,
    labels: np.ndarray,
) -> dict[str, Any]:
    """Find the best one-dimensional threshold in either direction."""

    values = np.asarray(values, dtype=np.float64).reshape(-1)
    labels = np.asarray(labels, dtype=bool).reshape(-1)
    _expect_equal(
        values.shape,
        labels.shape,
        "separability_shape_mismatch",
        "feature and label arrays must have equal shape",
    )
    _expect(values.size > 0, "separability_empty", "no candidate edges")
    _expect(np.isfinite(values).all(), "separability_nonfinite", "feature values")
    positives = int(np.sum(labels))
    negatives = int(np.sum(~labels))
    _expect(positives > 0 and negatives > 0, "separability_single_class", "labels")
    order = np.argsort(values, kind="mergesort")
    ordered_values = values[order]
    ordered_labels = labels[order]
    unique_values = np.unique(ordered_values)
    boundaries = np.concatenate(
        (
            [np.nextafter(unique_values[0], -np.inf)],
            (unique_values[:-1] + unique_values[1:]) / 2.0,
            [np.nextafter(unique_values[-1], np.inf)],
        )
    )
    cumulative_positive = np.cumsum(ordered_labels, dtype=np.int64)
    cumulative_negative = np.cumsum(~ordered_labels, dtype=np.int64)
    indices = np.searchsorted(ordered_values, boundaries, side="right") - 1
    left_positive = np.where(
        indices >= 0, cumulative_positive[np.maximum(indices, 0)], 0
    )
    left_negative = np.where(
        indices >= 0, cumulative_negative[np.maximum(indices, 0)], 0
    )
    best: dict[str, Any] | None = None
    for direction in ("less_or_equal", "greater_than"):
        if direction == "less_or_equal":
            true_positive = left_positive
            false_positive = left_negative
        else:
            true_positive = positives - left_positive
            false_positive = negatives - left_negative
        false_negative = positives - true_positive
        true_negative = negatives - false_positive
        precision = np.divide(
            true_positive,
            true_positive + false_positive,
            out=np.zeros_like(true_positive, dtype=np.float64),
            where=(true_positive + false_positive) > 0,
        )
        recall = true_positive / positives
        f1 = np.divide(
            2.0 * precision * recall,
            precision + recall,
            out=np.zeros_like(precision),
            where=(precision + recall) > 0,
        )
        balanced_accuracy = (recall + true_negative / negatives) / 2.0
        index = max(
            range(len(boundaries)),
            key=lambda item: (
                float(f1[item]),
                float(balanced_accuracy[item]),
                -float(abs(boundaries[item])),
            ),
        )
        candidate = {
            "direction": direction,
            "threshold": float(boundaries[index]),
            "true_positive": int(true_positive[index]),
            "false_positive": int(false_positive[index]),
            "false_negative": int(false_negative[index]),
            "true_negative": int(true_negative[index]),
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "balanced_accuracy": float(balanced_accuracy[index]),
        }
        if best is None or (
            candidate["f1"], candidate["balanced_accuracy"]
        ) > (best["f1"], best["balanced_accuracy"]):
            best = candidate
    assert best is not None
    auc = _rank_auc(values, labels)
    return {
        "sample_count": int(values.size),
        "positive_count": positives,
        "negative_count": negatives,
        "unique_value_count": int(unique_values.size),
        "positive_distribution": _distribution(values[labels]),
        "negative_distribution": _distribution(values[~labels]),
        "univariate_auc": {
            "available": bool(unique_values.size > 1),
            "auc": auc if unique_values.size > 1 else None,
            "best_direction_auc": max(auc, 1.0 - auc)
            if unique_values.size > 1
            else None,
            "direction": (
                "higher_for_positive" if auc >= 0.5 else "lower_for_positive"
            )
            if unique_values.size > 1
            else None,
            "reason": None if unique_values.size > 1 else "feature_constant",
        },
        "best_threshold_rule": best,
        "near_perfect_separation": bool(
            best["f1"] >= _SYNTHETIC_SEPARABILITY_F1
            and best["balanced_accuracy"]
            >= _SYNTHETIC_SEPARABILITY_BALANCED_ACCURACY
        ),
    }


def _rank_auc(values: np.ndarray, labels: np.ndarray) -> float:
    order = np.argsort(values, kind="mergesort")
    ordered_values = values[order]
    ordered_labels = labels[order]
    ranks = np.empty(values.size, dtype=np.float64)
    start = 0
    while start < values.size:
        stop = start + 1
        while stop < values.size and ordered_values[stop] == ordered_values[start]:
            stop += 1
        ranks[start:stop] = (start + 1 + stop) / 2.0
        start = stop
    positive_count = int(np.sum(labels))
    negative_count = int(labels.size - positive_count)
    rank_sum = float(np.sum(ranks[ordered_labels]))
    return (
        rank_sum - positive_count * (positive_count + 1) / 2.0
    ) / (positive_count * negative_count)


def render_d5_paired_shadow_audit_markdown(report: Mapping[str, Any]) -> str:
    paired = report["paired_shadow"]
    aggregate = paired["recomputed_aggregates"]["overall"]
    separation = report["synthetic_separability"]
    center = separation["center_identity_cue_assessment"]
    top = separation["top_single_feature"]
    authority = report["authority"]
    lines = [
        "# D5 配对影子独立审计",
        "",
        "## 审计结论",
        "",
        "D6 对生产方报告、900 条逐帧谱系、held-out 图语料、模型包和源实现哈希进行了只读复核。"
        "配对执行、候选图同一性、逐单元质量和统计汇总通过，配对影子层标记为 complete。",
        "",
        "外部泛化证据没有随之开放。中心绑定计数在全部候选边上为零，中心投影马氏距离的"
        f"单特征 F1 为 `{center['global_projection_mahalanobis']['best_threshold_rule']['f1']:.6f}`，"
        "没有证据表明满分主要由中心身份线索直接驱动。与此同时，"
        f"`{top['feature_name']}` 单特征 F1 为 `{top['best_threshold_rule']['f1']:.6f}`，"
        f"平衡准确率为 `{top['best_threshold_rule']['balanced_accuracy']:.6f}`。"
        "该近乎完全可分现象说明当前 held-out 数据仍带有明显合成规律，因此本次结果只构成"
        "合成研究影子证据，不能证明真实跨相机泛化。",
        "",
        "## 输入与完整性",
        "",
        f"- 随机种子：`{paired['seed_count']}`。",
        f"- 帧数：`{paired['frame_count']}`。",
        f"- 场景规模单元：`{paired['scenario_scale_cell_count']}`。",
        f"- 已标注候选边：`{paired['labeled_candidate_edge_count']}`。",
        f"- 输入制品数：`{report['explicit_input_binding']['input_artifact_count']}`。",
        f"- 输入集合 SHA-256：`{report['explicit_input_binding']['input_artifact_set_sha256']}`。",
        "- 报告文件、报告内容、逐帧谱系、语料 manifest/content/config、held-out 评估和模型包"
        " manifest/weights/checksums 均与带外 SHA-256 一致。",
        "- 审计前后输入集合哈希一致，未写入 D5 冻结制品。",
        "",
        "## 配对一致性",
        "",
        "| 检查项 | 结果 |",
        "| --- | ---: |",
        f"| 唯一 episode | {paired['lineage']['unique_episode_uid_count']} |",
        f"| 单次加载图 | {paired['lineage']['loaded_graph_instance_equal_one_count']} |",
        f"| 图 identity | {paired['lineage']['control_model_graph_identity_ratio']:.6f} |",
        f"| 候选边 identity | {paired['lineage']['control_model_candidate_identity_ratio']:.6f} |",
        f"| 标签 identity | {paired['lineage']['control_model_label_identity_ratio']:.6f} |",
        f"| 模型增删候选边 | {paired['lineage']['candidate_edges_added_or_removed']} |",
        "",
        "## 汇总指标",
        "",
        "| 指标 | 规则臂 | 图网络臂 |",
        "| --- | ---: | ---: |",
        f"| 边精确率 | {aggregate['control']['edge']['precision']:.6f} | {aggregate['model']['edge']['precision']:.6f} |",
        f"| 边召回率 | {aggregate['control']['edge']['recall']:.6f} | {aggregate['model']['edge']['recall']:.6f} |",
        f"| 边 F1 | {aggregate['control']['edge']['f1']:.6f} | {aggregate['model']['edge']['f1']:.6f} |",
        f"| 簇精确率 | {aggregate['control']['cluster_pairwise']['precision']:.6f} | {aggregate['model']['cluster_pairwise']['precision']:.6f} |",
        f"| 簇召回率 | {aggregate['control']['cluster_pairwise']['recall']:.6f} | {aggregate['model']['cluster_pairwise']['recall']:.6f} |",
        f"| 簇 F1 | {aggregate['control']['cluster_pairwise']['f1']:.6f} | {aggregate['model']['cluster_pairwise']['f1']:.6f} |",
        f"| 打分 P95 延时（毫秒） | {aggregate['control']['latency_ms']['scoring_p95']:.6f} | {aggregate['model']['latency_ms']['scoring_p95']:.6f} |",
        "",
        "45 个场景规模单元均由 D6 从逐帧记录重新聚合，未发现模型臂相对规则臂的质量退化。"
        "同相机候选边、未标注候选边、在线真值特征和全局航迹编号改写均为零。",
        "",
        "## 合成可分性",
        "",
        "| 特征 | 单特征 F1 | 平衡准确率 | 近乎完全可分 |",
        "| --- | ---: | ---: | --- |",
    ]
    for item in separation["feature_screen"]:
        if item["feature_name"] in {
            "shared_global_track_count",
            "global_projection_mahalanobis",
            top["feature_name"],
        }:
            rule = item["best_threshold_rule"]
            lines.append(
                f"| {item['feature_name']} | {rule['f1']:.6f} | "
                f"{rule['balanced_accuracy']:.6f} | "
                f"{'是' if item['near_perfect_separation'] else '否'} |"
            )
    lines.extend(
        [
            "",
            f"近乎完全可分特征覆盖 `{separation['near_perfect_feature_count']}` 个。"
            f"最强单特征在 `{separation['top_feature_cell_coverage']['near_perfect_cell_count']}/45` "
            "个场景规模单元达到预设阈值。中心绑定线索不是本批满分的充分解释，但其他合成运动/尺度"
            "特征足以解释大部分分类结果。后续需要在不共享理想运动历史、加入外参偏差和独立相机噪声"
            "的数据上复验。",
            "",
            "## 权限边界",
            "",
            f"`G1={str(authority['g1']).lower()}`，`PPO={str(authority['ppo']).lower()}`，"
            f"`assist={str(authority['assist']).lower()}`，"
            f"`authority={str(authority['authority']).lower()}`，"
            f"`rule_fallback={str(authority['rule_fallback']).lower()}`。",
            "",
            "本审计没有改变线上准入、默认运行路径、图网络权重或 D5 冻结报告。",
            "",
            "## 哈希",
            "",
            f"- D6 审计内容 SHA-256：`{report['content_sha256']}`。",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_input_locations(inputs: D5PairedShadowAuditInputs) -> None:
    for name in (
        "paired_report_path",
        "paired_lineage_path",
        "heldout_report_path",
        "superseded_report_path",
        "superseded_lineage_path",
    ):
        path = Path(getattr(inputs, name))
        _expect(path.is_file(), "explicit_input_missing", f"{name}:{path}")
    for name in ("heldout_corpus_dir", "model_bundle_dir", "d5_source_dir"):
        path = Path(getattr(inputs, name))
        _expect(path.is_dir(), "explicit_input_missing", f"{name}:{path}")
    _expect(
        not inputs.output_dir.exists(),
        "output_directory_exists",
        str(inputs.output_dir),
    )
    for source in (
        inputs.heldout_corpus_dir,
        inputs.model_bundle_dir,
        inputs.d5_source_dir,
        inputs.paired_report_path,
        inputs.paired_lineage_path,
        inputs.heldout_report_path,
        inputs.superseded_report_path,
        inputs.superseded_lineage_path,
    ):
        _expect(
            inputs.output_dir != source and source not in inputs.output_dir.parents,
            "output_overlaps_input",
            f"output={inputs.output_dir}, input={source}",
        )


def _verify_critical_hashes(
    inputs: D5PairedShadowAuditInputs,
    paths: Mapping[str, Path],
    report: Mapping[str, Any],
    corpus_manifest: Mapping[str, Any],
    heldout_report: Mapping[str, Any],
) -> None:
    expected = inputs.expected_hashes()
    file_bindings = {
        "paired_report": "paired_report_sha256",
        "paired_lineage": "paired_lineage_sha256",
        "corpus_manifest": "corpus_manifest_sha256",
        "heldout_report": "heldout_report_sha256",
        "bundle_manifest": "bundle_manifest_sha256",
        "bundle_weights": "bundle_weights_sha256",
        "bundle_checksums": "bundle_checksums_sha256",
        "superseded_report": "superseded_report_sha256",
        "superseded_lineage": "superseded_lineage_sha256",
    }
    for name, key in file_bindings.items():
        _expect_equal(
            _sha256_file(paths[name]),
            expected[key],
            f"{name}_out_of_band_sha256_mismatch",
            str(paths[name]),
        )
    _validate_content_sha256(report, "paired report")
    _validate_content_sha256(corpus_manifest, "held-out manifest")
    _validate_content_sha256(heldout_report, "held-out report")
    _expect_equal(
        report.get("content_sha256"),
        expected["paired_report_content_sha256"],
        "paired_report_content_out_of_band_mismatch",
        "producer report content SHA differs from caller-provided SHA",
    )
    _expect_equal(
        corpus_manifest.get("content_sha256"),
        expected["corpus_content_sha256"],
        "corpus_content_out_of_band_mismatch",
        "held-out corpus content SHA differs from caller-provided SHA",
    )
    _expect_equal(
        heldout_report.get("content_sha256"),
        expected["heldout_report_content_sha256"],
        "heldout_report_content_out_of_band_mismatch",
        "held-out report content SHA differs from caller-provided SHA",
    )


def _validate_corpus_manifest_and_inventory(
    inputs: D5PairedShadowAuditInputs,
    manifest: Mapping[str, Any],
) -> dict[str, Path]:
    _expect_equal(
        manifest.get("schema_version"),
        D5_HELDOUT_CORPUS_SCHEMA_VERSION,
        "heldout_manifest_schema_mismatch",
        "held-out corpus schema changed",
    )
    profile = _mapping(manifest, "profile")
    _expect_equal(
        tuple(int(item) for item in _sequence(profile, "seeds")),
        D5_PAIRED_SHADOW_EXPECTED_SEEDS,
        "heldout_seed_catalog_mismatch",
        "held-out seeds must be 1000-1019",
    )
    cells = tuple(
        (str(item["scenario"]), int(item["scale"]))
        for item in _sequence(profile, "scenario_cells")
    )
    _expect_equal(
        cells,
        D5_PAIRED_SHADOW_EXPECTED_CELLS,
        "heldout_cell_catalog_mismatch",
        "held-out scenario/scale catalog changed",
    )
    counts = _mapping(manifest, "counts")
    for key, expected in (
        ("episode_count", 900),
        ("seed_count", 20),
        ("scenario_scale_cell_count", 45),
        ("candidate_edge_count", 74_024),
    ):
        _expect_equal(
            _integer(counts.get(key), key),
            expected,
            "heldout_manifest_count_mismatch",
            key,
        )
    class_balance = _mapping(counts, "class_balance")
    _expect_equal(
        _integer(class_balance.get("candidate_edges"), "candidate edges"),
        74_024,
        "heldout_manifest_edge_count_mismatch",
        "candidate edge count",
    )
    _expect_equal(
        _integer(class_balance.get("unlabeled_candidate_edges"), "unlabeled edges"),
        0,
        "heldout_manifest_unlabeled_edges",
        "all candidates must be labeled",
    )
    config = _mapping(manifest, "config")
    config_path = _safe_child(inputs.heldout_corpus_dir, str(config.get("file", "")))
    _expect_equal(
        _sha256_file(config_path),
        inputs.expected_corpus_config_sha256,
        "corpus_config_out_of_band_sha256_mismatch",
        str(config_path),
    )
    _expect_equal(
        config.get("sha256"),
        inputs.expected_corpus_config_sha256,
        "corpus_config_binding_mismatch",
        "manifest config binding",
    )
    inventory = list(_sequence(manifest, "artifact_inventory"))
    _expect_equal(
        _sha256_json({"artifacts": inventory}),
        manifest.get("artifact_inventory_sha256"),
        "corpus_inventory_content_sha256_mismatch",
        "held-out artifact inventory digest",
    )
    paths: dict[str, Path] = {}
    for item in inventory:
        record = _mapping_value(item, "artifact inventory record")
        relative = str(record.get("path", ""))
        path = _safe_child(inputs.heldout_corpus_dir, relative)
        _expect(path.is_file(), "corpus_inventory_artifact_missing", relative)
        _expect_equal(
            path.stat().st_size,
            _integer(record.get("size_bytes"), "artifact size"),
            "corpus_inventory_artifact_size_mismatch",
            relative,
        )
        _expect_equal(
            _sha256_file(path),
            str(record.get("sha256", "")),
            "corpus_inventory_artifact_sha256_mismatch",
            relative,
        )
        paths[f"corpus/{relative}"] = path
    _expect_equal(
        len(paths),
        len(inventory),
        "corpus_inventory_duplicate_path",
        "artifact inventory paths must be unique",
    )
    return paths


def _validate_implementation_bindings(
    inputs: D5PairedShadowAuditInputs,
    report: Mapping[str, Any],
) -> dict[str, Path]:
    bindings = _mapping(report, "implementation_sha256")
    paths: dict[str, Path] = {}
    for filename, expected in bindings.items():
        _expect(
            isinstance(filename, str) and filename.endswith(".py"),
            "implementation_binding_name_invalid",
            str(filename),
        )
        path = _safe_child(inputs.d5_source_dir, filename)
        _expect(path.is_file(), "implementation_source_missing", str(path))
        _expect_equal(
            _sha256_file(path),
            str(expected),
            "implementation_source_sha256_mismatch",
            filename,
        )
        paths[f"d5_source/{filename}"] = path
    _expect(
        "tracklet_paired_shadow.py" in bindings,
        "paired_shadow_implementation_unbound",
        "tracklet_paired_shadow.py is missing from implementation bindings",
    )
    return paths


def _validate_report_contract(
    inputs: D5PairedShadowAuditInputs,
    report: Mapping[str, Any],
) -> None:
    _expect_equal(
        report.get("schema_version"),
        D5_PAIRED_SHADOW_REPORT_SCHEMA_VERSION,
        "paired_report_schema_mismatch",
        "paired report schema changed",
    )
    _expect(report.get("execution_completed") is True, "paired_execution_incomplete", "")
    _expect_equal(report.get("status"), "pass", "producer_status_not_pass", "")
    _expect_equal(
        report.get("evaluation_role"),
        "evaluator_only_paired_shadow",
        "producer_role_mismatch",
        "producer must remain evaluator-only",
    )
    spec = _mapping(report, "input_spec")
    _expect_equal(
        spec.get("schema_version"),
        D5_PAIRED_SHADOW_INPUT_SCHEMA_VERSION,
        "paired_input_spec_schema_mismatch",
        "producer input spec schema changed",
    )
    _expect_equal(
        _sha256_json(spec),
        report.get("input_spec_sha256"),
        "paired_input_spec_sha256_mismatch",
        "producer input spec digest",
    )
    expected_paths = {
        "heldout_corpus_dir": inputs.heldout_corpus_dir,
        "heldout_report_path": inputs.heldout_report_path,
        "bundle_dir": inputs.model_bundle_dir,
    }
    for key, expected_path in expected_paths.items():
        _expect_equal(
            Path(str(spec.get(key, ""))).resolve(),
            expected_path,
            "paired_input_path_binding_mismatch",
            key,
        )
    superseded_spec = _mapping(spec, "superseded_evidence")
    _expect_equal(
        Path(str(superseded_spec.get("directory", ""))).resolve(),
        inputs.superseded_report_path.parent,
        "superseded_evidence_path_binding_mismatch",
        "superseded evidence directory",
    )
    _expect_equal(
        superseded_spec.get("expected_report_sha256"),
        inputs.expected_superseded_report_sha256,
        "superseded_report_binding_mismatch",
        "input spec",
    )
    _expect_equal(
        superseded_spec.get("expected_lineage_sha256"),
        inputs.expected_superseded_lineage_sha256,
        "superseded_lineage_binding_mismatch",
        "input spec",
    )
    producer_expected = _mapping(spec, "expected_hashes")
    for key in (
        "corpus_manifest_sha256",
        "corpus_content_sha256",
        "corpus_config_sha256",
        "bundle_manifest_sha256",
        "bundle_weights_sha256",
        "bundle_checksums_sha256",
        "heldout_report_sha256",
        "heldout_report_content_sha256",
        "superseded_report_sha256",
        "superseded_lineage_sha256",
    ):
        _expect_equal(
            producer_expected.get(key),
            inputs.expected_hashes()[key],
            "producer_expected_input_sha256_mismatch",
            key,
        )
    expected_input_hashes = {
        key: inputs.expected_hashes()[key]
        for key in (
            "corpus_manifest_sha256",
            "corpus_content_sha256",
            "corpus_config_sha256",
            "bundle_manifest_sha256",
            "bundle_weights_sha256",
            "bundle_checksums_sha256",
            "heldout_report_sha256",
            "heldout_report_content_sha256",
            "superseded_report_sha256",
            "superseded_lineage_sha256",
        )
    }
    _expect_equal(
        report.get("input_hashes_before"),
        expected_input_hashes,
        "producer_input_hashes_before_mismatch",
        "producer pre-run bindings",
    )
    _expect_equal(
        report.get("input_hashes_after"),
        expected_input_hashes,
        "producer_input_hashes_after_mismatch",
        "producer post-run bindings",
    )
    _expect(
        report.get("input_artifacts_unchanged") is True,
        "producer_reports_input_mutation",
        "input_artifacts_unchanged is not true",
    )
    totals = _mapping(report, "totals")
    expected_totals = {
        "episode_count": 900,
        "seed_count": 20,
        "scenario_scale_cell_count": 45,
        "candidate_edge_count": 74_024,
        "labeled_candidate_edge_count": 74_024,
    }
    for key, expected in expected_totals.items():
        _expect_equal(
            _integer(totals.get(key), key),
            expected,
            "producer_total_mismatch",
            key,
        )
    lineage = _mapping(report, "paired_lineage")
    _expect_equal(
        lineage.get("schema_version"),
        D5_PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
        "paired_lineage_binding_schema_mismatch",
        "lineage schema",
    )
    _expect_equal(
        _integer(lineage.get("record_count"), "lineage record count"),
        900,
        "paired_lineage_binding_count_mismatch",
        "lineage count",
    )
    _expect_equal(
        lineage.get("sha256"),
        inputs.expected_paired_lineage_sha256,
        "paired_lineage_binding_sha256_mismatch",
        "lineage file SHA",
    )
    _expect(lineage.get("same_seed_pairing") is True, "same_seed_pairing_false", "")
    _expect(
        lineage.get("predictions_reused_from_heldout_report") is False,
        "heldout_predictions_reused",
        "paired arms must be freshly scored",
    )
    frozen = _mapping(report, "frozen_decision")
    for name in (
        "temperature_reestimated",
        "threshold_reselected",
        "weights_updated",
        "candidate_gate_changed",
    ):
        _expect(frozen.get(name) is False, "paired_decision_not_frozen", name)
    assessment = _mapping(report, "paired_shadow_assessment")
    _expect(assessment.get("passed") is True, "producer_assessment_failed", "")
    _expect_equal(assessment.get("failure_reasons"), [], "producer_failure_reasons", "")
    _validate_authority_mapping(assessment, "paired_shadow_assessment")
    _validate_authority_mapping(_mapping(report, "authority"), "authority")


def _validate_heldout_and_bundle_bindings(
    inputs: D5PairedShadowAuditInputs,
    *,
    report: Mapping[str, Any],
    corpus_manifest: Mapping[str, Any],
    heldout_report: Mapping[str, Any],
    bundle_manifest: Mapping[str, Any],
    bundle_checksums_path: Path,
) -> None:
    _expect_equal(
        heldout_report.get("schema_version"),
        D5_HELDOUT_EVALUATION_SCHEMA_VERSION,
        "heldout_report_schema_mismatch",
        "held-out evaluation schema changed",
    )
    heldout_corpus = _mapping(heldout_report, "heldout_corpus")
    _expect_equal(
        heldout_corpus.get("manifest_sha256"),
        inputs.expected_corpus_manifest_sha256,
        "heldout_report_corpus_manifest_binding_mismatch",
        "held-out report corpus file binding",
    )
    _expect_equal(
        heldout_corpus.get("manifest_content_sha256"),
        inputs.expected_corpus_content_sha256,
        "heldout_report_corpus_content_binding_mismatch",
        "held-out report corpus content binding",
    )
    model = _mapping(heldout_report, "development_model")
    _expect_equal(
        model.get("bundle_manifest_sha256"),
        inputs.expected_bundle_manifest_sha256,
        "heldout_report_bundle_binding_mismatch",
        "held-out report model manifest binding",
    )
    _expect_equal(
        model.get("weights_sha256"),
        inputs.expected_bundle_weights_sha256,
        "heldout_report_weights_binding_mismatch",
        "held-out report model weights binding",
    )
    _expect_equal(
        model.get("admission_status"),
        "development_only_fail_closed",
        "heldout_model_admission_overstated",
        "held-out model must remain development-only",
    )
    _expect_equal(
        bundle_manifest.get("schema_version"),
        D5_MODEL_BUNDLE_SCHEMA_VERSION,
        "bundle_manifest_schema_mismatch",
        "model bundle schema changed",
    )
    admission = _mapping(bundle_manifest, "admission")
    _expect_equal(
        admission.get("status"),
        "development_only_fail_closed",
        "bundle_admission_overstated",
        "model bundle status",
    )
    _expect(admission.get("default_model") is False, "bundle_default_model_enabled", "")
    _expect(
        admission.get("g1_assist_eligible") is False,
        "bundle_g1_assist_enabled",
        "",
    )
    weights = _mapping(bundle_manifest, "weights")
    _expect_equal(
        weights.get("sha256"),
        inputs.expected_bundle_weights_sha256,
        "bundle_weights_internal_binding_mismatch",
        "bundle manifest weights binding",
    )
    checksum_entries = _parse_sha256sums(bundle_checksums_path)
    _expect_equal(
        checksum_entries,
        {
            "manifest.json": inputs.expected_bundle_manifest_sha256,
            "weights.pt": inputs.expected_bundle_weights_sha256,
        },
        "bundle_checksums_content_mismatch",
        "SHA256SUMS must bind only manifest and weights",
    )
    lineage_binding = _mapping(report, "heldout_lineage_binding")
    expected_lineage = {
        "corpus_manifest_sha256": inputs.expected_corpus_manifest_sha256,
        "corpus_content_sha256": inputs.expected_corpus_content_sha256,
        "bundle_manifest_sha256": inputs.expected_bundle_manifest_sha256,
        "bundle_weights_sha256": inputs.expected_bundle_weights_sha256,
        "report_used_for_predictions": False,
        "report_used_for_lineage_only": True,
    }
    _expect_equal(
        lineage_binding,
        expected_lineage,
        "paired_heldout_lineage_binding_mismatch",
        "paired report lineage binding",
    )
    _expect_equal(
        corpus_manifest.get("evaluation_role"),
        "held_out_evaluation",
        "corpus_role_mismatch",
        "corpus role",
    )
    _expect_equal(
        heldout_report.get("evaluation_role"),
        "held_out_evaluation",
        "heldout_report_role_mismatch",
        "held-out report role",
    )


def _validate_record_metrics(
    record: Mapping[str, Any], edge_count: int, uid: str
) -> None:
    numerator = _integer(record.get("candidate_recall_numerator"), "candidate numerator")
    denominator = _integer(
        record.get("candidate_recall_denominator"), "candidate denominator"
    )
    _expect(denominator > 0, "candidate_recall_denominator_zero", uid)
    _expect_equal(
        _finite_float(record.get("candidate_recall"), "candidate recall"),
        numerator / denominator,
        "candidate_recall_mismatch",
        uid,
    )
    for arm_name in ("control", "model"):
        arm = _mapping(record, arm_name)
        for layer_name in ("edge", "cluster_pairwise"):
            metric = _mapping(arm, layer_name)
            counts = {
                name: _integer(metric.get(name), f"{arm_name}.{layer_name}.{name}")
                for name in _COUNT_NAMES
            }
            if layer_name == "edge":
                _expect_equal(
                    sum(counts.values()),
                    edge_count,
                    "edge_confusion_denominator_mismatch",
                    f"{uid}:{arm_name}",
                )
            expected_metrics = _metrics_from_counts(counts)
            for name in ("precision", "recall", "f1", "false_merge_rate"):
                _expect_close(
                    metric.get(name),
                    expected_metrics[name],
                    "record_metric_mismatch",
                    f"{uid}:{arm_name}:{layer_name}:{name}",
                )
            if layer_name == "cluster_pairwise":
                _expect_equal(
                    _integer(
                        metric.get("erroneous_merge_pair_count"),
                        "erroneous merge count",
                    ),
                    counts["false_positive"],
                    "cluster_erroneous_merge_count_mismatch",
                    f"{uid}:{arm_name}",
                )
                _expect_equal(
                    _integer(
                        metric.get("same_target_split_pair_count"),
                        "same target split count",
                    ),
                    counts["false_negative"],
                    "cluster_split_count_mismatch",
                    f"{uid}:{arm_name}",
                )
        for name in (
            "scoring_latency_ms",
            "clustering_latency_ms",
            "total_latency_ms",
        ):
            value = _finite_float(arm.get(name), f"{arm_name}.{name}")
            _expect(value >= 0.0, "negative_latency", f"{uid}:{arm_name}:{name}")
        _expect_close(
            arm["total_latency_ms"],
            float(arm["scoring_latency_ms"]) + float(arm["clustering_latency_ms"]),
            "record_total_latency_mismatch",
            f"{uid}:{arm_name}",
        )


def _validate_recomputed_aggregates(
    records: Sequence[Mapping[str, Any]], report: Mapping[str, Any]
) -> dict[str, Any]:
    overall = _aggregate_records(records, "overall")
    _compare_aggregate(report.get("overall"), overall, "overall")
    by_seed = {
        int(item["group_id"].removeprefix("seed-")): item
        for item in _sequence(report, "seed_metrics")
    }
    _expect_equal(
        set(by_seed),
        set(D5_PAIRED_SHADOW_EXPECTED_SEEDS),
        "seed_metric_catalog_mismatch",
        "producer seed aggregate catalog",
    )
    for seed in D5_PAIRED_SHADOW_EXPECTED_SEEDS:
        expected = _aggregate_records(
            [record for record in records if int(record["seed"]) == seed],
            f"seed-{seed}",
        )
        _compare_aggregate(by_seed[seed], expected, f"seed-{seed}")
    by_cell = {
        (str(item["scenario"]), int(item["scale"])): item
        for item in _sequence(report, "cell_metrics")
    }
    _expect_equal(
        set(by_cell),
        set(D5_PAIRED_SHADOW_EXPECTED_CELLS),
        "cell_metric_catalog_mismatch",
        "producer cell aggregate catalog",
    )
    no_degradation = 0
    for scenario, scale in D5_PAIRED_SHADOW_EXPECTED_CELLS:
        expected = _aggregate_records(
            [
                record
                for record in records
                if str(record["scenario"]) == scenario and int(record["scale"]) == scale
            ],
            f"{scenario}-{scale}v{scale}",
            scenario=scenario,
            scale=scale,
        )
        actual = by_cell[(scenario, scale)]
        _compare_aggregate(actual, expected, expected["group_id"])
        _expect(
            actual.get("quality_not_degraded") is True,
            "cell_quality_degraded",
            expected["group_id"],
        )
        _expect(_quality_not_degraded(expected), "cell_quality_recompute_failed", expected["group_id"])
        no_degradation += 1
    return {
        "overall": overall,
        "seed_aggregate_count": len(by_seed),
        "cell_aggregate_count": len(by_cell),
        "cell_no_quality_degradation_count": no_degradation,
        "all_metrics_finite": True,
        "producer_seed_cell_overall_counts_consistent": True,
    }


def _aggregate_records(
    records: Sequence[Mapping[str, Any]],
    group_id: str,
    *,
    scenario: str | None = None,
    scale: int | None = None,
) -> dict[str, Any]:
    _expect(bool(records), "aggregate_group_empty", group_id)
    numerator = sum(int(item["candidate_recall_numerator"]) for item in records)
    denominator = sum(int(item["candidate_recall_denominator"]) for item in records)
    result: dict[str, Any] = {
        "group_id": group_id,
        "episode_count": len(records),
        "seed_count": len({int(item["seed"]) for item in records}),
        "node_count": sum(int(item["node_count"]) for item in records),
        "candidate_edge_count": sum(int(item["candidate_edge_count"]) for item in records),
        "candidate_recall_numerator": numerator,
        "candidate_recall_denominator": denominator,
        "candidate_recall": numerator / denominator,
        "control": _aggregate_arm(records, "control"),
        "model": _aggregate_arm(records, "model"),
    }
    coverage = {
        "candidate_edge_count": result["candidate_edge_count"],
        "same_target_candidate_count": numerator,
        "same_target_cross_camera_pair_count": denominator,
        "candidate_recall": result["candidate_recall"],
    }
    result["control"]["candidate_coverage"] = dict(coverage)
    result["model"]["candidate_coverage"] = dict(coverage)
    if scenario is not None:
        result["scenario"] = scenario
    if scale is not None:
        result["scale"] = int(scale)
    return result


def _aggregate_arm(
    records: Sequence[Mapping[str, Any]], arm_name: str
) -> dict[str, Any]:
    edge = {
        name: sum(int(item[arm_name]["edge"][name]) for item in records)
        for name in _COUNT_NAMES
    }
    cluster = {
        name: sum(int(item[arm_name]["cluster_pairwise"][name]) for item in records)
        for name in _COUNT_NAMES
    }
    scoring = np.asarray(
        [float(item[arm_name]["scoring_latency_ms"]) for item in records], dtype=float
    )
    clustering = np.asarray(
        [float(item[arm_name]["clustering_latency_ms"]) for item in records], dtype=float
    )
    total = scoring + clustering
    return {
        "edge": _metrics_from_counts(edge),
        "cluster_pairwise": {
            **_metrics_from_counts(cluster),
            "erroneous_merge_pair_count": cluster["false_positive"],
            "same_target_split_pair_count": cluster["false_negative"],
        },
        "same_camera_mutual_exclusion_violation_count": sum(
            int(item[arm_name]["same_camera_mutual_exclusion_violation_count"])
            for item in records
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


def _compare_aggregate(actual_value: Any, expected: Mapping[str, Any], context: str) -> None:
    actual = _mapping_value(actual_value, context)
    for name in (
        "group_id",
        "episode_count",
        "seed_count",
        "node_count",
        "candidate_edge_count",
        "candidate_recall_numerator",
        "candidate_recall_denominator",
        "candidate_recall",
    ):
        _expect_close_or_equal(
            actual.get(name),
            expected[name],
            "aggregate_summary_mismatch",
            f"{context}:{name}",
        )
    for optional in ("scenario", "scale"):
        if optional in expected:
            _expect_equal(
                actual.get(optional),
                expected[optional],
                "aggregate_summary_mismatch",
                f"{context}:{optional}",
            )
    for arm_name in ("control", "model"):
        actual_arm = _mapping(actual, arm_name)
        expected_arm = expected[arm_name]
        _expect_numeric_mapping_equal(
            _mapping(actual_arm, "edge"),
            expected_arm["edge"],
            f"aggregate_{context}_{arm_name}_edge_mismatch",
        )
        _expect_numeric_mapping_equal(
            _mapping(actual_arm, "cluster_pairwise"),
            expected_arm["cluster_pairwise"],
            f"aggregate_{context}_{arm_name}_cluster_mismatch",
        )
        _expect_numeric_mapping_equal(
            _mapping(actual_arm, "candidate_coverage"),
            expected_arm["candidate_coverage"],
            f"aggregate_{context}_{arm_name}_coverage_mismatch",
        )
        _expect_numeric_mapping_equal(
            _mapping(actual_arm, "latency_ms"),
            expected_arm["latency_ms"],
            f"aggregate_{context}_{arm_name}_latency_mismatch",
            tolerance=1.0e-9,
        )
        _expect_equal(
            actual_arm.get("same_camera_mutual_exclusion_violation_count"),
            expected_arm["same_camera_mutual_exclusion_violation_count"],
            "aggregate_same_camera_violation_mismatch",
            f"{context}:{arm_name}",
        )


def _quality_not_degraded(group: Mapping[str, Any]) -> bool:
    control = group["control"]
    model = group["model"]
    checks = [
        model["candidate_coverage"] == control["candidate_coverage"],
        model["candidate_coverage"]["candidate_recall"]
        >= D5_PAIRED_SHADOW_MINIMUM_CANDIDATE_RECALL,
        model["edge"]["false_merge_rate"]
        <= D5_PAIRED_SHADOW_MAXIMUM_FALSE_MERGE_RATE,
        model["edge"]["false_merge_rate"] <= control["edge"]["false_merge_rate"],
        model["cluster_pairwise"]["erroneous_merge_pair_count"]
        <= control["cluster_pairwise"]["erroneous_merge_pair_count"],
        model["cluster_pairwise"]["same_target_split_pair_count"]
        <= control["cluster_pairwise"]["same_target_split_pair_count"],
    ]
    for layer in ("edge", "cluster_pairwise"):
        for metric in ("precision", "recall", "f1"):
            checks.append(model[layer][metric] >= control[layer][metric])
    return all(checks)


def _audit_synthetic_separability(
    *,
    corpus_root: Path,
    corpus_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    all_features: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []
    cell_features: dict[tuple[str, int], list[np.ndarray]] = {}
    cell_labels: dict[tuple[str, int], list[np.ndarray]] = {}
    feature_names: tuple[str, ...] | None = None
    same_camera_edges = 0
    unlabeled_edges = 0
    truth_named_online_features: set[str] = set()
    for descriptor in _sequence(corpus_manifest, "episodes"):
        graph_path = _safe_child(
            corpus_root, f"heldout_dataset/{descriptor['graph_file']}"
        )
        label_path = _safe_child(
            corpus_root, f"heldout_dataset/{descriptor['labels_file']}"
        )
        label_payload = _load_json_object(label_path, "evaluator labels")
        label_by_key = {
            str(item["tracklet_key"]): str(item["truth_entity_id"])
            for item in _sequence(label_payload, "labels")
        }
        with np.load(graph_path, allow_pickle=False) as graph:
            names = tuple(str(item) for item in graph["edge_feature_names"].tolist())
            node_names = tuple(
                str(item) for item in graph["node_feature_names"].tolist()
            )
            if feature_names is None:
                feature_names = names
            _expect_equal(
                names,
                feature_names,
                "edge_feature_catalog_drift",
                str(descriptor["episode_uid"]),
            )
            truth_named_online_features.update(
                name
                for name in names + node_names
                if any(token in name.lower() for token in ("truth", "actor_id", "object_id"))
            )
            features = np.asarray(graph["edge_features"], dtype=np.float64)
            edge_index = np.asarray(graph["edge_index"], dtype=np.int64)
            tracklet_keys = tuple(str(item) for item in graph["tracklet_keys"].tolist())
            camera_keys = tuple(str(item) for item in graph["camera_keys"].tolist())
            labels = np.empty(features.shape[0], dtype=bool)
            for edge_number in range(features.shape[0]):
                left_index = int(edge_index[0, edge_number])
                right_index = int(edge_index[1, edge_number])
                if camera_keys[left_index] == camera_keys[right_index]:
                    same_camera_edges += 1
                left = label_by_key.get(tracklet_keys[left_index])
                right = label_by_key.get(tracklet_keys[right_index])
                if left is None or right is None:
                    unlabeled_edges += 1
                    labels[edge_number] = False
                else:
                    labels[edge_number] = left == right
            _expect(np.isfinite(features).all(), "graph_feature_nonfinite", str(graph_path))
        all_features.append(features)
        all_labels.append(labels)
        cell = (str(descriptor["scenario"]), int(descriptor["scale"]))
        cell_features.setdefault(cell, []).append(features)
        cell_labels.setdefault(cell, []).append(labels)
    assert feature_names is not None
    features = np.concatenate(all_features, axis=0)
    labels = np.concatenate(all_labels, axis=0)
    _expect_equal(
        features.shape[0],
        D5_PAIRED_SHADOW_EXPECTED_LABELED_EDGE_COUNT,
        "separability_edge_count_mismatch",
        "edge feature rows",
    )
    screen: list[dict[str, Any]] = []
    for index, name in enumerate(feature_names):
        item = screen_single_feature_separability(features[:, index], labels)
        item["feature_name"] = name
        screen.append(item)
    screen.sort(
        key=lambda item: (
            item["best_threshold_rule"]["f1"],
            item["best_threshold_rule"]["balanced_accuracy"],
            item["feature_name"],
        ),
        reverse=True,
    )
    by_name = {item["feature_name"]: item for item in screen}
    for required in _CENTER_BINDING_FEATURES:
        _expect(required in by_name, "center_binding_feature_missing", required)
    top = dict(screen[0])
    top_name = str(top["feature_name"])
    top_index = feature_names.index(top_name)
    cell_records: list[dict[str, Any]] = []
    for scenario, scale in D5_PAIRED_SHADOW_EXPECTED_CELLS:
        cell_x = np.concatenate(cell_features[(scenario, scale)], axis=0)[:, top_index]
        cell_y = np.concatenate(cell_labels[(scenario, scale)], axis=0)
        item = screen_single_feature_separability(cell_x, cell_y)
        cell_records.append(
            {
                "cell_id": f"{scenario}-{scale}v{scale}",
                "scenario": scenario,
                "scale": scale,
                "edge_count": int(cell_x.size),
                "best_threshold_rule": item["best_threshold_rule"],
                "near_perfect_separation": item["near_perfect_separation"],
            }
        )
    near_perfect = [item for item in screen if item["near_perfect_separation"]]
    center_shared = by_name["shared_global_track_count"]
    center_projection = by_name["global_projection_mahalanobis"]
    center_primary = bool(
        center_shared["near_perfect_separation"]
        or center_projection["near_perfect_separation"]
    )
    synthetic_risk = "high" if near_perfect else "low"
    return {
        "assessment_scope": "dataset_level_univariate_screen_not_model_attribution",
        "edge_count": int(features.shape[0]),
        "positive_edge_count": int(np.sum(labels)),
        "negative_edge_count": int(np.sum(~labels)),
        "feature_count": int(features.shape[1]),
        "same_camera_candidate_edge_count": same_camera_edges,
        "unlabeled_candidate_edge_count": unlabeled_edges,
        "truth_named_online_feature_names": sorted(truth_named_online_features),
        "feature_screen": screen,
        "top_single_feature": top,
        "near_perfect_feature_count": len(near_perfect),
        "near_perfect_feature_names": [item["feature_name"] for item in near_perfect],
        "top_feature_cell_coverage": {
            "feature_name": top_name,
            "cell_count": len(cell_records),
            "near_perfect_cell_count": sum(
                bool(item["near_perfect_separation"]) for item in cell_records
            ),
            "cells": cell_records,
        },
        "center_identity_cue_assessment": {
            "shared_global_track_count": center_shared,
            "global_projection_mahalanobis": center_projection,
            "primary_driver_supported": center_primary,
            "interpretation": (
                "center identity cue alone is sufficient to explain near-perfect labels"
                if center_primary
                else "center identity cues are not sufficient to explain the paired-shadow score"
            ),
        },
        "single_feature_explanation_available": bool(near_perfect),
        "synthetic_single_feature_separability_risk": synthetic_risk,
        "external_generalization_evidence_grade": (
            "synthetic_only_insufficient_for_external_generalization"
            if near_perfect
            else "supported"
        ),
        "interpretation": (
            "The perfect model score is reproducible on the frozen corpus, but at least one "
            "single synthetic feature nearly separates evaluator labels. This is sufficient "
            "to lower external-generalization evidence, without claiming model attribution."
            if near_perfect
            else "No near-perfect one-dimensional separation was found."
        ),
    }


def _validate_independent_safety(
    report: Mapping[str, Any],
    corpus_manifest: Mapping[str, Any],
    separability: Mapping[str, Any],
) -> None:
    report_safety = _mapping(report, "identity_and_truth_safety")
    corpus_safety = _mapping(corpus_manifest, "identity_and_truth_safety")
    for name in (
        "online_truth_feature_count",
        "same_camera_candidate_edge_count",
        "unlabeled_candidate_edge_count",
    ):
        _expect_equal(
            _integer(report_safety.get(name), name),
            0,
            "producer_safety_nonzero",
            name,
        )
    for name in (
        "online_truth_feature_count",
        "same_camera_candidate_edge_count",
    ):
        _expect_equal(
            _integer(corpus_safety.get(name), name),
            0,
            "corpus_safety_nonzero",
            name,
        )
    _expect_equal(
        _integer(report_safety.get("global_track_id_rewrite_count"), "global rewrite"),
        0,
        "global_track_id_rewrite_detected",
        "producer safety",
    )
    _expect(
        report_safety.get("global_track_id_created_or_rebound") is False,
        "global_track_id_created_or_rebound",
        "producer safety",
    )
    _validate_authority_mapping(report_safety, "identity_and_truth_safety")
    _expect_equal(
        separability.get("same_camera_candidate_edge_count"),
        0,
        "independent_same_camera_edge_detected",
        "graph scan",
    )
    _expect_equal(
        separability.get("unlabeled_candidate_edge_count"),
        0,
        "independent_unlabeled_edge_detected",
        "graph scan",
    )
    _expect_equal(
        separability.get("truth_named_online_feature_names"),
        [],
        "truth_named_online_feature_detected",
        "graph feature schema",
    )


def _validate_authoritative_v2_evidence(
    inputs: D5PairedShadowAuditInputs,
    report: Mapping[str, Any],
    separability: Mapping[str, Any],
) -> None:
    evidence = _mapping(report, "evidence_status")
    _expect_equal(
        evidence.get("status"),
        "authoritative",
        "paired_evidence_not_authoritative",
        "v2 evidence status",
    )
    supersedes = list(_sequence(evidence, "supersedes"))
    _expect_equal(
        len(supersedes),
        1,
        "superseded_evidence_catalog_mismatch",
        "authoritative v2 must name one preserved predecessor",
    )
    superseded = _mapping_value(supersedes[0], "superseded evidence")
    _expect_equal(
        superseded.get("status"),
        "superseded_preserved",
        "superseded_evidence_status_mismatch",
        "old evidence must be preserved and superseded",
    )
    _expect(superseded.get("files_deleted") is False, "superseded_files_deleted", "")
    _expect(superseded.get("files_modified") is False, "superseded_files_modified", "")
    _expect_equal(
        superseded.get("report_sha256"),
        inputs.expected_superseded_report_sha256,
        "superseded_report_sha256_mismatch",
        "evidence status",
    )
    _expect_equal(
        superseded.get("lineage_sha256"),
        inputs.expected_superseded_lineage_sha256,
        "superseded_lineage_sha256_mismatch",
        "evidence status",
    )
    catalog = _mapping(report, "catalog_integrity")
    expected_catalog = {
        "complete": True,
        "expected_frame_count": 900,
        "actual_frame_count": 900,
        "expected_seed_count": 20,
        "expected_cell_count": 45,
        "missing_seed_cell_count": 0,
        "extra_seed_cell_count": 0,
        "duplicate_record_count": 0,
    }
    for name, expected in expected_catalog.items():
        _expect_equal(
            catalog.get(name),
            expected,
            "producer_catalog_integrity_mismatch",
            name,
        )
    _expect_equal(
        catalog.get("seed_frame_counts"),
        {str(seed): 45 for seed in D5_PAIRED_SHADOW_EXPECTED_SEEDS},
        "producer_seed_frame_counts_mismatch",
        "catalog integrity",
    )
    _expect_equal(
        catalog.get("cell_frame_counts"),
        {
            f"{scenario}-{scale}v{scale}": 20
            for scenario, scale in D5_PAIRED_SHADOW_EXPECTED_CELLS
        },
        "producer_cell_frame_counts_mismatch",
        "catalog integrity",
    )

    diagnostics = _mapping(report, "feature_label_diagnostics")
    _expect_equal(
        diagnostics.get("scope"),
        "post_prediction_evaluator_only",
        "producer_separability_scope_mismatch",
        "feature diagnostics scope",
    )
    _expect_equal(
        diagnostics.get("interpretation_scope"),
        "dataset_separability_not_model_feature_attribution",
        "producer_separability_interpretation_overstated",
        "feature diagnostics interpretation",
    )
    _expect_equal(
        _integer(diagnostics.get("candidate_edge_count"), "diagnostic edges"),
        separability["edge_count"],
        "producer_separability_edge_count_mismatch",
        "feature diagnostics",
    )
    _expect_equal(
        _integer(diagnostics.get("positive_candidate_edge_count"), "positive edges"),
        separability["positive_edge_count"],
        "producer_separability_positive_count_mismatch",
        "feature diagnostics",
    )
    _expect_equal(
        _integer(diagnostics.get("negative_candidate_edge_count"), "negative edges"),
        separability["negative_edge_count"],
        "producer_separability_negative_count_mismatch",
        "feature diagnostics",
    )
    changes = _mapping(diagnostics, "changes_to_frozen_evaluation")
    for name in (
        "candidate_gate_changed",
        "predictions_recomputed_for_diagnostics",
        "temperature_reestimated",
        "threshold_reselected",
        "weights_updated",
    ):
        _expect(changes.get(name) is False, "producer_diagnostic_changed_evaluation", name)

    independent = {
        str(item["feature_name"]): item for item in separability["feature_screen"]
    }
    producer_features = {
        str(item["feature"]): item for item in _sequence(diagnostics, "features")
    }
    _expect_equal(
        set(producer_features),
        set(independent),
        "producer_feature_diagnostic_catalog_mismatch",
        "feature diagnostics",
    )
    for name, independent_item in independent.items():
        producer_item = _mapping_value(producer_features[name], name)
        _expect_equal(
            _integer(producer_item.get("sample_count"), "feature sample count"),
            independent_item["sample_count"],
            "producer_feature_sample_count_mismatch",
            name,
        )
        _expect_equal(
            _integer(producer_item.get("unique_value_count"), "unique values"),
            independent_item["unique_value_count"],
            "producer_feature_unique_count_mismatch",
            name,
        )
        for producer_label, independent_label in (
            ("positive", "positive_distribution"),
            ("negative", "negative_distribution"),
        ):
            producer_distribution = _mapping(producer_item, producer_label)
            expected_distribution = independent_item[independent_label]
            for field in (
                "count",
                "mean",
                "standard_deviation",
                "minimum",
                "maximum",
                "exact_zero_fraction",
            ):
                _expect_close_or_equal(
                    producer_distribution.get(field),
                    expected_distribution[field],
                    "producer_feature_distribution_mismatch",
                    f"{name}:{producer_label}:{field}",
                )
        producer_auc = _mapping(producer_item, "univariate_auc")
        expected_auc = independent_item["univariate_auc"]
        _expect_equal(
            producer_auc.get("available"),
            expected_auc["available"],
            "producer_feature_auc_availability_mismatch",
            name,
        )
        for field in ("auc", "best_direction_auc"):
            if expected_auc[field] is None:
                _expect_equal(
                    producer_auc.get(field),
                    None,
                    "producer_feature_auc_mismatch",
                    f"{name}:{field}",
                )
            else:
                _expect_close(
                    producer_auc.get(field),
                    expected_auc[field],
                    "producer_feature_auc_mismatch",
                    f"{name}:{field}",
                    tolerance=1.0e-10,
                )
    _expect_equal(
        set(diagnostics.get("near_deterministic_feature_names", [])),
        set(separability["near_perfect_feature_names"]),
        "producer_near_deterministic_feature_catalog_mismatch",
        "feature diagnostics",
    )
    flags = set(diagnostics.get("limitation_flags", []))
    _expect(
        "perfect_score_not_online_generalization_evidence" in flags,
        "producer_generalization_limitation_missing",
        "feature diagnostics",
    )
    _expect(
        "near_deterministic_synthetic_feature_separability" in flags,
        "producer_synthetic_separability_limitation_missing",
        "feature diagnostics",
    )
    shared = _mapping(diagnostics, "shared_global_track_count")
    _expect_close(
        shared.get("mutual_information_bits"),
        0.0,
        "shared_global_track_mutual_information_mismatch",
        "shared_global_track_count",
    )
    _expect(shared.get("near_deterministic") is False, "shared_global_track_overstated", "")


def _validate_authority_mapping(value: Mapping[str, Any], context: str) -> None:
    for name in ("g1", "assist", "authority"):
        if name in value:
            _expect(value.get(name) is False, "learning_authority_enabled", f"{context}:{name}")
    if "rule_fallback" in value:
        _expect(
            value.get("rule_fallback") is True,
            "rule_fallback_disabled",
            context,
        )
    if "runtime_default_changed" in value:
        _expect(
            value.get("runtime_default_changed") is False,
            "runtime_default_changed",
            context,
        )


def _validate_finite_numbers(report: Mapping[str, Any]) -> None:
    for path, value in _walk_values(report):
        if isinstance(value, float):
            _expect(math.isfinite(value), "nonfinite_report_metric", path)
    overall = _mapping(report, "overall")
    for arm_name in ("control", "model"):
        arm = _mapping(overall, arm_name)
        latency = _mapping(arm, "latency_ms")
        for name, value in latency.items():
            number = _finite_float(value, f"{arm_name}.latency.{name}")
            _expect(number >= 0.0, "negative_aggregate_latency", f"{arm_name}:{name}")
    model_p95 = float(overall["model"]["latency_ms"]["scoring_p95"])
    _expect(
        model_p95 <= D5_PAIRED_SHADOW_MAXIMUM_MODEL_P95_LATENCY_MS,
        "model_latency_budget_exceeded",
        str(model_p95),
    )


def _snapshot(paths: Mapping[str, Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, path in sorted(paths.items()):
        _expect(path.is_file(), "snapshot_input_missing", f"{name}:{path}")
        result[name] = _sha256_file(path)
    return result


def _snapshot_set_sha256(snapshot: Mapping[str, str]) -> str:
    return _sha256_json(
        {
            "artifacts": [
                {"name": name, "sha256": sha}
                for name, sha in sorted(snapshot.items())
            ]
        }
    )


def _snapshot_subset(
    snapshot: Mapping[str, str], paths: Mapping[str, Path]
) -> dict[str, str]:
    return {name: snapshot[name] for name in sorted(paths)}


def _snapshot_evidence(
    snapshot_before: Mapping[str, str],
    snapshot_after: Mapping[str, str],
    critical_paths: Mapping[str, Path],
    implementation_paths: Mapping[str, Path],
) -> dict[str, Any]:
    critical_before = _snapshot_subset(snapshot_before, critical_paths)
    critical_after = _snapshot_subset(snapshot_after, critical_paths)
    implementation_before = _snapshot_subset(snapshot_before, implementation_paths)
    implementation_after = _snapshot_subset(snapshot_after, implementation_paths)
    set_sha_before = _snapshot_set_sha256(snapshot_before)
    set_sha_after = _snapshot_set_sha256(snapshot_after)
    return {
        "input_artifact_count": len(snapshot_before),
        "input_artifact_set_sha256": set_sha_before,
        "input_artifact_set_sha256_before": set_sha_before,
        "input_artifact_set_sha256_after": set_sha_after,
        "critical_file_sha256": critical_before,
        "critical_file_sha256_after": critical_after,
        "implementation_binding_count": len(implementation_before),
        "implementation_file_sha256": implementation_before,
        "implementation_file_sha256_after": implementation_after,
    }


def _metrics_from_counts(counts: Mapping[str, int]) -> dict[str, Any]:
    tp = int(counts["true_positive"])
    fp = int(counts["false_positive"])
    fn = int(counts["false_negative"])
    predicted = tp + fp
    actual = tp + fn
    precision = tp / predicted if predicted else 0.0
    recall = tp / actual if actual else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        **{name: int(counts[name]) for name in _COUNT_NAMES},
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_merge_rate": fp / predicted if predicted else 0.0,
    }


def _distribution(values: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.float64)
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "standard_deviation": float(np.std(values)),
        "minimum": float(np.min(values)),
        "exact_zero_fraction": float(np.mean(values == 0.0)),
        "p05": float(np.percentile(values, 5)),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "maximum": float(np.max(values)),
    }


def _load_json_object(path: Path, context: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("json_input_invalid", f"{context}:{path}:{exc}")
    if not isinstance(value, dict):
        _fail("json_object_required", f"{context}:{path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    _fail("jsonl_blank_line", f"{path}:{line_number}")
                value = json.loads(line)
                if not isinstance(value, dict):
                    _fail("jsonl_object_required", f"{path}:{line_number}")
                result.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("jsonl_input_invalid", f"{path}:{exc}")
    return result


def _parse_sha256sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        parts = line.split(maxsplit=1)
        _expect_equal(len(parts), 2, "sha256sums_line_invalid", f"{path}:{line_number}")
        digest, filename = parts
        filename = filename.lstrip("*")
        _expect(_SHA256_RE.fullmatch(digest) is not None, "sha256sums_digest_invalid", digest)
        _expect(filename not in result, "sha256sums_duplicate_file", filename)
        result[filename] = digest
    return result


def _validate_content_sha256(payload: Mapping[str, Any], context: str) -> None:
    unsigned = dict(payload)
    claimed = str(unsigned.pop("content_sha256", ""))
    _expect(_SHA256_RE.fullmatch(claimed) is not None, "content_sha256_invalid", context)
    _expect_equal(
        _sha256_json(unsigned),
        claimed,
        "content_sha256_mismatch",
        context,
    )


def _with_content_sha256(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _sha256_json(result)
    return result


def _artifact_record(path: Path) -> dict[str, Any]:
    return {"path": path.name, "sha256": _sha256_file(path), "size_bytes": path.stat().st_size}


def _write_json(path: Path, payload: Any) -> None:
    path.write_bytes(_canonical_json_bytes(payload))


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_child(root: Path, relative: str) -> Path:
    path = Path(relative)
    _expect(
        bool(relative) and not path.is_absolute() and ".." not in path.parts,
        "unsafe_relative_path",
        relative,
    )
    resolved = (root / path).resolve()
    _expect(root == resolved or root in resolved.parents, "path_escapes_root", relative)
    return resolved


def _mapping(parent: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    return _mapping_value(parent.get(name), name)


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", context)
    return value


def _sequence(parent: Mapping[str, Any], name: str) -> Sequence[Any]:
    value = parent.get(name)
    if not isinstance(value, list):
        _fail("list_required", name)
    return value


def _integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        _fail("integer_required", f"{context}:{value!r}")
    result = int(value)
    if result < 0:
        _fail("nonnegative_integer_required", f"{context}:{value!r}")
    return result


def _finite_float(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        _fail("finite_number_required", f"{context}:{value!r}")
    result = float(value)
    if not math.isfinite(result):
        _fail("finite_number_required", f"{context}:{value!r}")
    return result


def _expect_numeric_mapping_equal(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    code: str,
    *,
    tolerance: float = 1.0e-12,
) -> None:
    for name, expected_value in expected.items():
        actual_value = actual.get(name)
        if isinstance(expected_value, float):
            _expect_close(actual_value, expected_value, code, name, tolerance=tolerance)
        else:
            _expect_equal(actual_value, expected_value, code, name)


def _expect_close_or_equal(
    actual: Any, expected: Any, code: str, detail: str
) -> None:
    if isinstance(expected, float):
        _expect_close(actual, expected, code, detail)
    else:
        _expect_equal(actual, expected, code, detail)


def _expect_close(
    actual: Any,
    expected: Any,
    code: str,
    detail: str,
    *,
    tolerance: float = 1.0e-12,
) -> None:
    actual_number = _finite_float(actual, detail)
    expected_number = _finite_float(expected, detail)
    if not math.isclose(actual_number, expected_number, rel_tol=tolerance, abs_tol=tolerance):
        _fail(code, f"{detail}: actual={actual_number}, expected={expected_number}")


def _expect_equal(actual: Any, expected: Any, code: str, detail: str) -> None:
    if actual != expected:
        _fail(code, f"{detail}: actual={actual!r}, expected={expected!r}")


def _expect(condition: bool, code: str, detail: str) -> None:
    if not condition:
        _fail(code, detail)


def _walk_values(value: Any, prefix: str = "root") -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_values(item, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_values(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def _fail(code: str, detail: str) -> None:
    raise D5PairedShadowAuditError(code, detail)
