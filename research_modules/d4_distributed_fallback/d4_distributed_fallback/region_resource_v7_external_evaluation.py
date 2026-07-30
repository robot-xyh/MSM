"""Read-only source-independent evaluation for the frozen-by-hash D4 v7 actor.

The evaluator binds one exact v7 bundle, raw source tree, labeled export,
dataset, and frozen v4 training source. It never fits a model, selects a
checkpoint, tunes a threshold, calibrates confidence, mutates an input,
registers the candidate, admits it, or grants runtime authority.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .region_resource import (
    DeterministicResourceProjector,
    RuleRegionResourcePolicy,
)
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningAvailability,
    RegionLearningSplit,
    load_region_learning_dataset_splits,
)
from .region_resource_learning import snapshot_to_region_graph
from .region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V4_INTERVENTION_GATE,
    _V4_PROJECTION,
    _V4_RULE_CONFIG,
    _v4_confidence_observable_key,
    evaluate_v4_intervention_invariants,
    executable_signature,
)
from .region_resource_v7_rule_node_residual_candidate import (
    REGION_RESOURCE_V7_AUDIT_FILENAME,
    REGION_RESOURCE_V7_CANDIDATE_FILENAME,
    REGION_RESOURCE_V7_CANDIDATE_ID,
    REGION_RESOURCE_V7_MODEL_VERSION,
    REGION_RESOURCE_V7_SOURCE_FILENAME,
    REGION_RESOURCE_V7_STATE_MAGIC,
    V7ModelIdentity,
    V7RuleNodeTransferResidualPolicy,
    _load_v7_model_bundle,
    _model_state_content_sha256,
    _validate_frozen_v4_source,
)


REGION_RESOURCE_V7_EXTERNAL_SCHEMA = (
    "d4-region-resource-v7-source-independent-external-evaluation-v1"
)
REGION_RESOURCE_V7_EXTERNAL_RECORD_SCHEMA = (
    "d4-region-resource-v7-source-independent-frame-evaluation-v1"
)
REGION_RESOURCE_V7_EXTERNAL_INTEGRITY_SCHEMA = (
    "d4-region-resource-v7-source-independent-input-integrity-v1"
)
REGION_RESOURCE_V7_EXTERNAL_OVERLAP_SCHEMA = (
    "d4-region-resource-v7-source-independent-observable-overlap-v1"
)
REGION_RESOURCE_V7_EXTERNAL_ARTIFACT_SCHEMA = (
    "d4-region-resource-v7-source-independent-artifact-manifest-v1"
)

REGION_RESOURCE_V7_EXTERNAL_RECORDS_FILENAME = "evaluation_records.jsonl"
REGION_RESOURCE_V7_EXTERNAL_CSV_FILENAME = "evaluation_records.csv"
REGION_RESOURCE_V7_EXTERNAL_INTEGRITY_FILENAME = "input_integrity.json"
REGION_RESOURCE_V7_EXTERNAL_OVERLAP_FILENAME = "observable_overlap_audit.json"
REGION_RESOURCE_V7_EXTERNAL_SUMMARY_FILENAME = "external_evaluation_summary.json"
REGION_RESOURCE_V7_EXTERNAL_REPORT_FILENAME = "REPORT_CN.md"
REGION_RESOURCE_V7_EXTERNAL_ARTIFACT_FILENAME = "artifact_manifest.json"

_EXPECTED_REPORT_DATE = "2026-07-30"
_EXPECTED_CANDIDATE_MANIFEST_CONTENT_SHA256 = (
    "fe9b18f6da8d9daf6d443a89f4cc321a9bda7645be3367b69c4ac29b3ac4f45f"
)
_EXPECTED_TRAINING_AUDIT_CONTENT_SHA256 = (
    "1d60fbd1e3841eddc76914f7dad4421ae024eaf4ff63190269dc1a2046f6385e"
)
_EXPECTED_SOURCE_BINDING_CONTENT_SHA256 = (
    "04f7986709c75c9138f10282aad678872ed74a2bfa1c82b506a5a202881c7002"
)
_EXPECTED_V7_IMPLEMENTATION_FILE_SHA256 = (
    "a27f0c1d8653a83b8a5a8036d8aa860ab9ded50e18e1dce7700f878bb6096338"
)
_EXPECTED_MODEL_STATE_CONTENT_SHA256 = (
    "bec99032bc176854f7ba265977ed35bf828d415be4bc260c9b6703a95d70082d"
)
_EXPECTED_STATE_FILE_SHA256 = (
    "d0f7f17599fba382d9aa436c6ae34ef5f23b582a5ed9068f3475cb545b4f88f5"
)
_EXPECTED_CANDIDATE_TREE_SHA256 = (
    "7bd5419f9d071d6c801f72415a8eb36ac0e36d259187e94229959f5f21d1a667"
)
_EXPECTED_SOURCE_ROOT_NAME = (
    "msm_d4_v7_transfer_independent_m16n24_64seed_4a83a37"
)
_EXPECTED_LABELED_ROOT_NAME = (
    "msm_d4_v7_transfer_labeled_m16n24_64seed_test8_4a83a37"
)
_EXPECTED_SOURCE_TREE_SHA256 = (
    "978f94c0165ce6f79446b601c8eddf5b2e157f641fab243582a3349250d5c9a1"
)
_EXPECTED_LABELED_TREE_SHA256 = (
    "05a375853c42a31ecf3a20b2c61d9be6f2a7932d8a5125665f04d30ebc3e6d1b"
)
_EXPECTED_DATASET_TREE_SHA256 = (
    "0b88d9afbb0e0e98cb2c59dc950a98cc57c7f5d5bd22d762278fdd81ce6a9282"
)
_EXPECTED_FROZEN_V4_TREE_SHA256 = (
    "2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0"
)
_EXPECTED_DATASET_SHA256 = (
    "f6c52bdd4ce630ae40787226383caab7833f3b034adfb0fc7e93d9e30c90ce67"
)
_EXPECTED_SPLIT_SHA256 = (
    "4179c0a766fa93b9127dc534176d69276face35fb110a8c247100d1807521215"
)
_EXPECTED_SOURCE_COMMIT = "4a83a373f4eb4e29704bb3cf9f62e3d54eee3aec"
_EXPECTED_EXPORTER_COMMIT = _EXPECTED_SOURCE_COMMIT
_EXPECTED_GENERATION_PLAN_FILE_SHA256 = (
    "16ee1200741c449dc0cfb875bd930725220447d1d565815a8e0348910c57d936"
)
_EXPECTED_GENERATION_SUMMARY_FILE_SHA256 = (
    "9ebaf151789e8fed7ac03639455a9b1ebda9e7524a4e11961f5e775ff40bc905"
)
_EXPECTED_BATCH_SUMMARY_FILE_SHA256 = (
    "992cf4cd6162a54360f3eec768a2f34603595831fd1c8d741c9768034e990692"
)
_EXPECTED_EXPORT_SUMMARY_CONTENT_SHA256 = (
    "793064c08c27b89bd7d08ee40cd85d4eed57194c790756b8f7eb504db0acd055"
)
_EXPECTED_EXPORT_SUMMARY_FILE_SHA256 = (
    "f47870b5132ada3b28666d22e950ffcfa4a1891c18b345b3164ed65a555639a5"
)
_EXPECTED_EVIDENCE_CONTENT_SHA256 = (
    "73b35dde68c75ff5d5f59f84089e002df0442a39f88a7909fb698514d2cde5f6"
)
_EXPECTED_EVIDENCE_FILE_SHA256 = (
    "58db40a15e07a91bd1323f5de84422a3717fc070f9c404fc5fe535671216dd8f"
)
_EXPECTED_DERIVATION_CONTENT_SHA256 = (
    "2a8941feaf6a58141ee8d7abccfddd40b3808c6b41426355bde6376bce640ed4"
)
_EXPECTED_DERIVATION_FILE_SHA256 = (
    "832acc6853fbf80aa91804fb1a5c01fb63e3dc256280070d4bbb7721b25480e1"
)
_EXPECTED_SEEDS = tuple(range(5216, 5280))
_FORBIDDEN_PRIOR_EVALUATION_SEEDS = frozenset(range(3008, 3040))
_FORBIDDEN_FORMAL_HOLDOUT_SEEDS = frozenset(range(1000, 1020))
_EXPECTED_FRAME_COUNTS = {"train": 90, "validation": 20, "test": 18}
_EXPECTED_POSITIVE_COUNTS = {"train": 24, "validation": 9, "test": 9}
_EXPECTED_EPISODE_COUNT = 64
_EXPECTED_FRAME_COUNT = 128
_EXPECTED_REGION_COUNT = 8
_EXPECTED_SCALE = "M16N24"


class RegionResourceV7ExternalEvaluationError(RuntimeError):
    """Stable fail-closed error for the v7 external evaluator."""


@dataclass(frozen=True)
class RegionResourceV7ExternalEvaluationConfig:
    """Immutable no-fit contract for the frozen 2026-07-30 evaluation."""

    report_date: str = _EXPECTED_REPORT_DATE
    expected_seeds: tuple[int, ...] = _EXPECTED_SEEDS
    expected_frame_counts: tuple[tuple[str, int], ...] = tuple(
        sorted(_EXPECTED_FRAME_COUNTS.items())
    )
    expected_positive_counts: tuple[tuple[str, int], ...] = tuple(
        sorted(_EXPECTED_POSITIVE_COUNTS.items())
    )
    evaluation_splits: tuple[str, ...] = ("train", "validation", "test")
    model_fit_allowed: bool = False
    checkpoint_update_allowed: bool = False
    threshold_tuning_allowed: bool = False
    confidence_calibration_allowed: bool = False
    confidence_gate_available: bool = False
    candidate_mutation_allowed: bool = False
    input_mutation_allowed: bool = False
    registration_allowed: bool = False
    admission_allowed: bool = False
    formal_holdout_read_allowed: bool = False
    prior_external_evaluation_read_allowed: bool = False
    production_permission_available: bool = False
    schema: str = REGION_RESOURCE_V7_EXTERNAL_SCHEMA

    def __post_init__(self) -> None:
        expected = {
            "report_date": _EXPECTED_REPORT_DATE,
            "expected_seeds": _EXPECTED_SEEDS,
            "expected_frame_counts": tuple(
                sorted(_EXPECTED_FRAME_COUNTS.items())
            ),
            "expected_positive_counts": tuple(
                sorted(_EXPECTED_POSITIVE_COUNTS.items())
            ),
            "evaluation_splits": ("train", "validation", "test"),
            "schema": REGION_RESOURCE_V7_EXTERNAL_SCHEMA,
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise ValueError("v7 external evaluation contract changed")
        forbidden = (
            self.model_fit_allowed,
            self.checkpoint_update_allowed,
            self.threshold_tuning_allowed,
            self.confidence_calibration_allowed,
            self.confidence_gate_available,
            self.candidate_mutation_allowed,
            self.input_mutation_allowed,
            self.registration_allowed,
            self.admission_allowed,
            self.formal_holdout_read_allowed,
            self.prior_external_evaluation_read_allowed,
            self.production_permission_available,
        )
        if any(type(value) is not bool or value for value in forbidden):
            raise ValueError("v7 external evaluation must remain read-only")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_region_resource_v7_external_dataset(
    v7_candidate_root: str | Path,
    source_root: str | Path,
    labeled_dataset_root: str | Path,
    external_evidence_path: str | Path,
    derivation_manifest_path: str | Path,
    export_summary_path: str | Path,
    frozen_v4_candidate_root: str | Path,
    output_root: str | Path,
    *,
    config: RegionResourceV7ExternalEvaluationConfig | None = None,
    replace_output: bool = False,
) -> dict[str, Any]:
    """Evaluate one exact v7 actor without fitting or granting authority."""

    resolved = config or RegionResourceV7ExternalEvaluationConfig()
    candidate = Path(v7_candidate_root).resolve()
    source = Path(source_root).resolve()
    dataset = Path(labeled_dataset_root).resolve()
    evidence = Path(external_evidence_path).resolve()
    derivation = Path(derivation_manifest_path).resolve()
    export_summary = Path(export_summary_path).resolve()
    v4_candidate = Path(frozen_v4_candidate_root).resolve()
    destination = Path(output_root).resolve()
    labeled_root = dataset.parent
    _validate_paths(
        candidate=candidate,
        source=source,
        dataset=dataset,
        evidence=evidence,
        derivation=derivation,
        export_summary=export_summary,
        v4_candidate=v4_candidate,
        destination=destination,
        replace_output=replace_output,
    )

    candidate_tree_before = _tree_sha256(candidate)
    source_tree_before = _tree_sha256(source)
    labeled_tree_before = _tree_sha256(labeled_root)
    dataset_tree_before = _tree_sha256(dataset)
    v4_tree_before = _tree_sha256(v4_candidate)
    if candidate_tree_before != _EXPECTED_CANDIDATE_TREE_SHA256:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_candidate_tree_identity_mismatch"
        )
    if source_tree_before != _EXPECTED_SOURCE_TREE_SHA256:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_source_tree_identity_mismatch"
        )
    if (
        labeled_tree_before != _EXPECTED_LABELED_TREE_SHA256
        or dataset_tree_before != _EXPECTED_DATASET_TREE_SHA256
        or v4_tree_before != _EXPECTED_FROZEN_V4_TREE_SHA256
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_input_tree_identity_mismatch"
        )

    model, candidate_identity = _load_and_verify_candidate(candidate)
    loaded, input_identity = _load_and_verify_external_input(
        dataset,
        evidence,
        derivation,
        export_summary,
        source,
        config=resolved,
    )
    v4_source_binding = _validate_frozen_v4_source(v4_candidate)
    v4_loaded = load_region_learning_dataset_splits(
        v4_candidate / "development_dataset",
        splits=(
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ),
    )
    if (
        v4_loaded.manifest.dataset_sha256
        != candidate_identity["source_a_dataset_sha256"]
        or v4_loaded.manifest.split.split_sha256
        != candidate_identity["source_a_split_sha256"]
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_frozen_v4_training_identity_mismatch"
        )

    records = _evaluate_records(loaded, model=model)
    metrics_by_split = {
        split.value: _summarize_records(
            tuple(item for item in records if item["split"] == split.value)
        )
        for split in RegionLearningSplit
    }
    _validate_external_action_inventory(metrics_by_split)
    aggregate_metrics = _summarize_records(records)
    overlap = _observable_overlap_audit(v4_loaded, loaded)

    candidate_tree_after = _tree_sha256(candidate)
    source_tree_after = _tree_sha256(source)
    labeled_tree_after = _tree_sha256(labeled_root)
    dataset_tree_after = _tree_sha256(dataset)
    v4_tree_after = _tree_sha256(v4_candidate)
    _assert_tree_unchanged(
        "candidate", candidate_tree_before, candidate_tree_after
    )
    _assert_tree_unchanged(
        "raw_source", source_tree_before, source_tree_after
    )
    _assert_tree_unchanged(
        "labeled_export", labeled_tree_before, labeled_tree_after
    )
    _assert_tree_unchanged(
        "external_dataset", dataset_tree_before, dataset_tree_after
    )
    _assert_tree_unchanged(
        "frozen_v4_training_source", v4_tree_before, v4_tree_after
    )

    config_payload = resolved.to_dict()
    config_sha256 = _canonical_sha256(config_payload)
    integrity = _with_content_sha256(
        {
            "schema": REGION_RESOURCE_V7_EXTERNAL_INTEGRITY_SCHEMA,
            "report_date": resolved.report_date,
            "configuration": config_payload,
            "configuration_sha256": config_sha256,
            "candidate": {
                **candidate_identity,
                "root": str(candidate),
                "tree_sha256_before": candidate_tree_before,
                "tree_sha256_after": candidate_tree_after,
                "tree_unchanged": True,
            },
            "raw_source": {
                "root": str(source),
                "tree_sha256_before": source_tree_before,
                "tree_sha256_after": source_tree_after,
                "tree_unchanged": True,
                "generation_plan_file_sha256": (
                    _EXPECTED_GENERATION_PLAN_FILE_SHA256
                ),
                "generation_summary_file_sha256": (
                    _EXPECTED_GENERATION_SUMMARY_FILE_SHA256
                ),
                "batch_summary_file_sha256": (
                    _EXPECTED_BATCH_SUMMARY_FILE_SHA256
                ),
            },
            "labeled_input": {
                **input_identity,
                "root": str(labeled_root),
                "tree_sha256_before": labeled_tree_before,
                "tree_sha256_after": labeled_tree_after,
                "tree_unchanged": True,
                "dataset_tree_sha256_before": dataset_tree_before,
                "dataset_tree_sha256_after": dataset_tree_after,
                "dataset_tree_unchanged": True,
            },
            "frozen_v4_training_source": {
                "root": str(v4_candidate),
                "source_binding": v4_source_binding,
                "tree_sha256_before": v4_tree_before,
                "tree_sha256_after": v4_tree_after,
                "tree_unchanged": True,
            },
            "candidate_mutation_count": 0,
            "input_mutation_count": 0,
            "model_fit_count": 0,
            "checkpoint_update_count": 0,
            "threshold_tuning_count": 0,
            "confidence_calibration_count": 0,
            "confidence_gate_application_count": 0,
            "prior_external_evaluation_payload_read_count": 0,
            "formal_holdout_payload_read_count": 0,
            "registration_count": 0,
            "admission_count": 0,
            "production_permission_available": False,
            "evaluator_source_sha256": _sha256_file(Path(__file__)),
        }
    )
    overlap_payload = _with_content_sha256(overlap)
    data_usage = _data_usage(metrics_by_split)
    candidate_status = _closed_candidate_status()
    summary = _with_content_sha256(
        {
            "schema": REGION_RESOURCE_V7_EXTERNAL_SCHEMA,
            "report_date": resolved.report_date,
            "scenario_scale": _EXPECTED_SCALE,
            "region_count": _EXPECTED_REGION_COUNT,
            "source_seed_range": [
                min(resolved.expected_seeds),
                max(resolved.expected_seeds),
            ],
            "source_episode_count": _EXPECTED_EPISODE_COUNT,
            "source_frame_count": _EXPECTED_FRAME_COUNT,
            "configuration_sha256": config_sha256,
            "input_integrity_content_sha256": integrity["content_sha256"],
            "observable_overlap_content_sha256": overlap_payload[
                "content_sha256"
            ],
            "metrics_by_split": metrics_by_split,
            "aggregate_metrics": aggregate_metrics,
            "data_usage": data_usage,
            "candidate_status": candidate_status,
            "conclusion": _conclusion(
                metrics_by_split,
                overlap_payload,
            ),
            "limitations": [
                "M16N24_8_region_external_fixture_only",
                "v7_has_no_confidence_calibrator_or_admission_gate",
                "candidate_unregistered_and_admission_closed",
                "formal_holdout_not_read",
                "prior_3008_3039_evaluation_not_read",
                "frozen_v4_observable_overlap_audit_only",
                "no_runtime_preflight_or_physical_benefit_claim",
            ],
        }
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    try:
        _write_jsonl(
            temporary / REGION_RESOURCE_V7_EXTERNAL_RECORDS_FILENAME,
            records,
        )
        _write_csv(
            temporary / REGION_RESOURCE_V7_EXTERNAL_CSV_FILENAME,
            records,
        )
        _write_json(
            temporary / REGION_RESOURCE_V7_EXTERNAL_INTEGRITY_FILENAME,
            integrity,
        )
        _write_json(
            temporary / REGION_RESOURCE_V7_EXTERNAL_OVERLAP_FILENAME,
            overlap_payload,
        )
        summary["evaluation_records_jsonl_sha256"] = _sha256_file(
            temporary / REGION_RESOURCE_V7_EXTERNAL_RECORDS_FILENAME
        )
        summary["evaluation_records_csv_sha256"] = _sha256_file(
            temporary / REGION_RESOURCE_V7_EXTERNAL_CSV_FILENAME
        )
        summary = _resign(summary)
        _write_json(
            temporary / REGION_RESOURCE_V7_EXTERNAL_SUMMARY_FILENAME,
            summary,
        )
        (
            temporary / REGION_RESOURCE_V7_EXTERNAL_REPORT_FILENAME
        ).write_text(
            _render_report(summary, integrity, overlap_payload),
            encoding="utf-8",
        )
        artifact_names = (
            REGION_RESOURCE_V7_EXTERNAL_RECORDS_FILENAME,
            REGION_RESOURCE_V7_EXTERNAL_CSV_FILENAME,
            REGION_RESOURCE_V7_EXTERNAL_INTEGRITY_FILENAME,
            REGION_RESOURCE_V7_EXTERNAL_OVERLAP_FILENAME,
            REGION_RESOURCE_V7_EXTERNAL_SUMMARY_FILENAME,
            REGION_RESOURCE_V7_EXTERNAL_REPORT_FILENAME,
        )
        artifact_manifest = _with_content_sha256(
            {
                "schema": REGION_RESOURCE_V7_EXTERNAL_ARTIFACT_SCHEMA,
                "report_date": resolved.report_date,
                "artifact_files": {
                    name: _sha256_file(temporary / name)
                    for name in artifact_names
                },
                "candidate_mutation_count": 0,
                "input_mutation_count": 0,
                "model_fit_count": 0,
                "checkpoint_update_count": 0,
                "threshold_tuning_count": 0,
                "confidence_calibration_count": 0,
                "confidence_gate_application_count": 0,
                "registration_count": 0,
                "admission_count": 0,
                "prior_external_evaluation_payload_read_count": 0,
                "formal_holdout_payload_read_count": 0,
                "production_permission_available": False,
            }
        )
        _write_json(
            temporary / REGION_RESOURCE_V7_EXTERNAL_ARTIFACT_FILENAME,
            artifact_manifest,
        )
        if destination.exists():
            shutil.rmtree(destination)
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    reviewed = review_region_resource_v7_external_evaluation(destination)
    return {
        "output_root": str(destination),
        "artifact_manifest": reviewed["artifact_manifest"],
        "summary": reviewed["summary"],
    }


def review_region_resource_v7_external_evaluation(
    output_root: str | Path,
) -> dict[str, Any]:
    """Verify persisted v7 external-evaluation artifacts."""

    root = Path(output_root).resolve()
    if root.is_symlink() or not root.is_dir():
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_output_root_invalid"
        )
    artifact_manifest = _read_json(
        root / REGION_RESOURCE_V7_EXTERNAL_ARTIFACT_FILENAME
    )
    _verify_content_sha256(artifact_manifest, "artifact_manifest")
    if (
        artifact_manifest.get("schema")
        != REGION_RESOURCE_V7_EXTERNAL_ARTIFACT_SCHEMA
        or artifact_manifest.get("candidate_mutation_count") != 0
        or artifact_manifest.get("input_mutation_count") != 0
        or artifact_manifest.get("model_fit_count") != 0
        or artifact_manifest.get("checkpoint_update_count") != 0
        or artifact_manifest.get("threshold_tuning_count") != 0
        or artifact_manifest.get("confidence_calibration_count") != 0
        or artifact_manifest.get("confidence_gate_application_count") != 0
        or artifact_manifest.get("registration_count") != 0
        or artifact_manifest.get("admission_count") != 0
        or artifact_manifest.get(
            "prior_external_evaluation_payload_read_count"
        )
        != 0
        or artifact_manifest.get("formal_holdout_payload_read_count") != 0
        or artifact_manifest.get("production_permission_available") is not False
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_artifact_boundary_invalid"
        )
    files = artifact_manifest.get("artifact_files")
    if not isinstance(files, Mapping):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_artifact_inventory_invalid"
        )
    expected = {
        REGION_RESOURCE_V7_EXTERNAL_RECORDS_FILENAME,
        REGION_RESOURCE_V7_EXTERNAL_CSV_FILENAME,
        REGION_RESOURCE_V7_EXTERNAL_INTEGRITY_FILENAME,
        REGION_RESOURCE_V7_EXTERNAL_OVERLAP_FILENAME,
        REGION_RESOURCE_V7_EXTERNAL_SUMMARY_FILENAME,
        REGION_RESOURCE_V7_EXTERNAL_REPORT_FILENAME,
    }
    actual = {
        path.name
        for path in root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if set(files) != expected or actual != expected | {
        REGION_RESOURCE_V7_EXTERNAL_ARTIFACT_FILENAME
    }:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_output_file_inventory_mismatch"
        )
    for name, digest in files.items():
        if _sha256_file(root / name) != digest:
            raise RegionResourceV7ExternalEvaluationError(
                f"v7_external_artifact_sha256_mismatch:{name}"
            )
    integrity = _read_json(
        root / REGION_RESOURCE_V7_EXTERNAL_INTEGRITY_FILENAME
    )
    overlap = _read_json(
        root / REGION_RESOURCE_V7_EXTERNAL_OVERLAP_FILENAME
    )
    summary = _read_json(
        root / REGION_RESOURCE_V7_EXTERNAL_SUMMARY_FILENAME
    )
    _verify_content_sha256(integrity, "input_integrity")
    _verify_content_sha256(overlap, "observable_overlap")
    _verify_content_sha256(summary, "summary")
    status = summary.get("candidate_status", {})
    if (
        summary.get("input_integrity_content_sha256")
        != integrity["content_sha256"]
        or summary.get("observable_overlap_content_sha256")
        != overlap["content_sha256"]
        or status.get("unregistered") is not True
        or status.get("admission_closed") is not True
        or status.get("rule_fallback_required") is not True
        or status.get("confidence_gate_available") is not False
        or status.get("permissions")
        != _closed_candidate_status()["permissions"]
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_summary_boundary_invalid"
        )
    return {
        "artifact_manifest": artifact_manifest,
        "integrity": integrity,
        "overlap": overlap,
        "summary": summary,
    }


def _validate_paths(
    *,
    candidate: Path,
    source: Path,
    dataset: Path,
    evidence: Path,
    derivation: Path,
    export_summary: Path,
    v4_candidate: Path,
    destination: Path,
    replace_output: bool,
) -> None:
    directories = {
        "candidate": candidate,
        "source": source,
        "dataset": dataset,
        "v4_candidate": v4_candidate,
    }
    for name, path in directories.items():
        if path.is_symlink() or not path.is_dir():
            raise RegionResourceV7ExternalEvaluationError(
                f"v7_external_{name}_root_invalid"
            )
    files = {
        "external_evidence": evidence,
        "derivation_manifest": derivation,
        "export_summary": export_summary,
    }
    for name, path in files.items():
        if path.is_symlink() or not path.is_file():
            raise RegionResourceV7ExternalEvaluationError(
                f"v7_external_{name}_invalid"
            )
    labeled_root = dataset.parent
    if (
        source.name != _EXPECTED_SOURCE_ROOT_NAME
        or labeled_root.name != _EXPECTED_LABELED_ROOT_NAME
        or dataset != labeled_root / "dataset"
        or evidence != labeled_root / "external_dataset_evidence.json"
        or derivation != labeled_root / "source_derivation_manifest.json"
        or export_summary != labeled_root / "export_summary.json"
        or not (source / "generation_plan.json").is_file()
        or not (source / "generation_summary.json").is_file()
        or not (
            source / "learning_dataset/batch_learning_export_summary.json"
        ).is_file()
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_input_path_identity_mismatch"
        )
    protected = {
        "candidate": candidate,
        "raw_source": source,
        "labeled_input": labeled_root,
        "v4_candidate": v4_candidate,
    }
    for name, root in protected.items():
        if destination == root or root in destination.parents:
            raise RegionResourceV7ExternalEvaluationError(
                f"v7_external_output_within_protected_input:{name}"
            )
    if destination.is_symlink():
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_output_symlink_forbidden"
        )
    if destination.exists() and not replace_output:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_output_already_exists"
        )
    if "model_registry" in destination.parts:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_registry_output_forbidden"
        )


def _load_and_verify_candidate(
    root: Path,
) -> tuple[Any, dict[str, Any]]:
    if root.name != REGION_RESOURCE_V7_CANDIDATE_ID:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_candidate_directory_identity_mismatch"
        )
    inventory = {
        str(path.relative_to(root)): _sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    expected_inventory = {
        "bundle/manifest.json",
        "bundle/state_dict.pt",
        "source_binding.json",
        "training_audit.json",
        "training_config.json",
        REGION_RESOURCE_V7_CANDIDATE_FILENAME,
    }
    if set(inventory) != expected_inventory:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_candidate_file_inventory_mismatch"
        )
    manifest = _read_json(root / REGION_RESOURCE_V7_CANDIDATE_FILENAME)
    _verify_content_sha256(manifest, "candidate_manifest")
    _verify_candidate_manifest_identity(manifest)
    artifact_files = manifest.get("artifact_files")
    if not isinstance(artifact_files, Mapping):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_candidate_artifact_inventory_invalid"
        )
    if set(artifact_files) != expected_inventory - {
        REGION_RESOURCE_V7_CANDIDATE_FILENAME
    }:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_candidate_artifact_inventory_mismatch"
        )
    for name, digest in artifact_files.items():
        if inventory[name] != digest:
            raise RegionResourceV7ExternalEvaluationError(
                f"v7_external_candidate_artifact_sha256_mismatch:{name}"
            )

    audit = _read_json(root / REGION_RESOURCE_V7_AUDIT_FILENAME)
    _verify_content_sha256(audit, "training_audit")
    if audit.get("content_sha256") != _EXPECTED_TRAINING_AUDIT_CONTENT_SHA256:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_training_audit_identity_mismatch"
        )
    state_path = root / "bundle/state_dict.pt"
    if (
        not state_path.read_bytes().startswith(REGION_RESOURCE_V7_STATE_MAGIC)
        or _sha256_file(state_path) != _EXPECTED_STATE_FILE_SHA256
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_state_file_identity_mismatch"
        )
    source_binding = _read_json(root / REGION_RESOURCE_V7_SOURCE_FILENAME)
    _verify_content_sha256(source_binding, "source_binding")
    if (
        source_binding.get("content_sha256")
        != _EXPECTED_SOURCE_BINDING_CONTENT_SHA256
        or source_binding.get("implementation_file_sha256")
        != _EXPECTED_V7_IMPLEMENTATION_FILE_SHA256
        or source_binding.get("fit_splits") != ["train"]
        or source_binding.get("checkpoint_splits") != ["validation"]
        or source_binding.get("payload_splits_read")
        != ["train", "validation"]
        or source_binding.get("test_payload_read_count") != 0
        or source_binding.get("formal_holdout_payload_read_count") != 0
        or source_binding.get("prior_evaluation_payload_read_count") != 0
        or source_binding.get("independent_evaluation_payload_read_count")
        != 0
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_source_binding_identity_mismatch"
        )
    if (
        audit.get("source_binding_content_sha256")
        != _EXPECTED_SOURCE_BINDING_CONTENT_SHA256
        or audit.get("independent_evaluation_payload_read_count") != 0
        or audit.get("formal_holdout_payload_read_count") != 0
        or audit.get("prior_evaluation_payload_read_count") != 0
        or audit.get("test_payload_fit_count") != 0
        or audit.get("confidence_calibration_available") is not False
        or audit.get("fixed_confidence_gate_applied") is not False
        or audit.get("development_gate", {}).get("passed") is not True
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_training_audit_boundary_mismatch"
        )
    model, bundle_manifest = _load_v7_model_bundle(
        root / "bundle",
        expected_model_version=REGION_RESOURCE_V7_MODEL_VERSION,
        expected_state_file_sha256=_EXPECTED_STATE_FILE_SHA256,
    )
    if (
        bundle_manifest.get("model_state_content_sha256")
        != _EXPECTED_MODEL_STATE_CONTENT_SHA256
        or _model_state_content_sha256(model)
        != _EXPECTED_MODEL_STATE_CONTENT_SHA256
        or bundle_manifest.get("runtime_confidence_gate_available") is not False
        or bundle_manifest.get("runtime_loader_registered") is not False
        or bundle_manifest.get("confidence_calibrator_available") is not False
        or bundle_manifest.get("fixed_minimum_confidence_gate_applied")
        is not False
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_model_content_identity_mismatch"
        )
    return model, {
        "candidate_id": REGION_RESOURCE_V7_CANDIDATE_ID,
        "model_version": REGION_RESOURCE_V7_MODEL_VERSION,
        "manifest_content_sha256": manifest["content_sha256"],
        "manifest_file_sha256": inventory[
            REGION_RESOURCE_V7_CANDIDATE_FILENAME
        ],
        "training_audit_content_sha256": audit["content_sha256"],
        "training_audit_file_sha256": inventory[
            REGION_RESOURCE_V7_AUDIT_FILENAME
        ],
        "model_state_content_sha256": _model_state_content_sha256(model),
        "state_file_sha256": inventory["bundle/state_dict.pt"],
        "source_binding_content_sha256": source_binding["content_sha256"],
        "source_binding_file_sha256": inventory[
            REGION_RESOURCE_V7_SOURCE_FILENAME
        ],
        "source_a_dataset_sha256": manifest["source_a_dataset_sha256"],
        "source_a_split_sha256": manifest["source_a_split_sha256"],
        "source_b_dataset_sha256": manifest["source_b_dataset_sha256"],
        "source_b_split_sha256": manifest["source_b_split_sha256"],
        "confidence_calibration_status": manifest[
            "confidence_calibration_status"
        ],
        "registered": False,
        "admission_closed": True,
        "rule_fallback_required": True,
        "permissions": manifest["permissions"],
    }


def _verify_candidate_manifest_identity(manifest: Mapping[str, Any]) -> None:
    permissions = manifest.get("permissions")
    permission_values = (
        {
            name: value
            for name, value in permissions.items()
            if name != "schema"
        }
        if isinstance(permissions, Mapping)
        else {}
    )
    if (
        manifest.get("content_sha256")
        != _EXPECTED_CANDIDATE_MANIFEST_CONTENT_SHA256
        or manifest.get("candidate_id") != REGION_RESOURCE_V7_CANDIDATE_ID
        or manifest.get("model_version") != REGION_RESOURCE_V7_MODEL_VERSION
        or manifest.get("training_audit_content_sha256")
        != _EXPECTED_TRAINING_AUDIT_CONTENT_SHA256
        or manifest.get("source_binding_content_sha256")
        != _EXPECTED_SOURCE_BINDING_CONTENT_SHA256
        or manifest.get("implementation_file_sha256")
        != _EXPECTED_V7_IMPLEMENTATION_FILE_SHA256
        or manifest.get("model_state_content_sha256")
        != _EXPECTED_MODEL_STATE_CONTENT_SHA256
        or manifest.get("bundle_state_file_sha256")
        != _EXPECTED_STATE_FILE_SHA256
        or manifest.get("candidate_status")
        != "unregistered_rule_node_transfer_residual_development"
        or manifest.get("confidence_calibration_status")
        != "not_available_actor_must_pass_independent_evaluation"
        or manifest.get("confidence_calibrator_available") is not False
        or manifest.get("fixed_minimum_confidence_gate_applied") is not False
        or manifest.get("source_independent_evaluation_status")
        != "not_started"
        or manifest.get("source_independent_evaluation_completed") is not False
        or manifest.get("development_gate_passed") is not True
        or manifest.get("development_only") is not True
        or manifest.get("shadow_only") is not True
        or manifest.get("admission_closed") is not True
        or manifest.get("rule_fallback_required") is not True
        or manifest.get("formal_holdout_evaluated") is not False
        or manifest.get("runtime_preflight_completed") is not False
        or not permission_values
        or any(type(value) is not bool or value for value in permission_values.values())
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_candidate_manifest_identity_mismatch"
        )


def _load_and_verify_external_input(
    dataset_root: Path,
    evidence_path: Path,
    derivation_path: Path,
    export_summary_path: Path,
    source_root: Path,
    *,
    config: RegionResourceV7ExternalEvaluationConfig,
) -> tuple[LoadedRegionLearningDataset, dict[str, Any]]:
    generation_plan_path = source_root / "generation_plan.json"
    generation_summary_path = source_root / "generation_summary.json"
    batch_summary_path = (
        source_root / "learning_dataset/batch_learning_export_summary.json"
    )
    generation_plan = _read_json(generation_plan_path)
    generation_summary = _read_json(generation_summary_path)
    batch_summary = _read_json(batch_summary_path)
    evidence = _read_json(evidence_path)
    derivation = _read_json(derivation_path)
    export_summary = _read_json(export_summary_path)
    _verify_content_sha256(evidence, "external_evidence")
    _verify_content_sha256(derivation, "derivation_manifest")
    _verify_content_sha256(export_summary, "export_summary")
    if (
        evidence.get("content_sha256")
        != _EXPECTED_EVIDENCE_CONTENT_SHA256
        or derivation.get("content_sha256")
        != _EXPECTED_DERIVATION_CONTENT_SHA256
        or export_summary.get("content_sha256")
        != _EXPECTED_EXPORT_SUMMARY_CONTENT_SHA256
        or _sha256_file(generation_plan_path)
        != _EXPECTED_GENERATION_PLAN_FILE_SHA256
        or _sha256_file(generation_summary_path)
        != _EXPECTED_GENERATION_SUMMARY_FILE_SHA256
        or _sha256_file(batch_summary_path)
        != _EXPECTED_BATCH_SUMMARY_FILE_SHA256
        or _sha256_file(evidence_path) != _EXPECTED_EVIDENCE_FILE_SHA256
        or _sha256_file(derivation_path)
        != _EXPECTED_DERIVATION_FILE_SHA256
        or _sha256_file(export_summary_path)
        != _EXPECTED_EXPORT_SUMMARY_FILE_SHA256
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_lineage_content_identity_mismatch"
        )

    loaded = load_region_learning_dataset_splits(
        dataset_root,
        splits=tuple(RegionLearningSplit),
    )
    manifest = loaded.manifest
    seeds = tuple(sorted({int(item.source.seed) for item in loaded.episode_records}))
    split_frame_counts = {
        split.value: sum(
            len(episode.frames) for episode in loaded.episodes(split)
        )
        for split in RegionLearningSplit
    }
    if (
        manifest.dataset_sha256 != _EXPECTED_DATASET_SHA256
        or manifest.split.split_sha256 != _EXPECTED_SPLIT_SHA256
        or manifest.availability.episode_count != _EXPECTED_EPISODE_COUNT
        or manifest.availability.frame_count != _EXPECTED_FRAME_COUNT
        or seeds != config.expected_seeds
        or split_frame_counts != _EXPECTED_FRAME_COUNTS
        or manifest.availability.target_unavailable_count != 0
        or manifest.availability.target_available_count
        != _EXPECTED_FRAME_COUNT
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_dataset_identity_mismatch"
        )
    _validate_seed_isolation(seeds)
    for episode in loaded.episode_records:
        source = episode.source
        if (
            source.git_commit != _EXPECTED_SOURCE_COMMIT
            or source.git_dirty
            or source.scenario_scale != _EXPECTED_SCALE
        ):
            raise RegionResourceV7ExternalEvaluationError(
                "v7_external_source_episode_identity_mismatch"
            )
        for frame in episode.frames:
            if len(frame.snapshot.regions) != _EXPECTED_REGION_COUNT:
                raise RegionResourceV7ExternalEvaluationError(
                    "v7_external_region_count_mismatch"
                )

    source_artifact_sha256 = _sha256_file(derivation_path)
    if (
        generation_plan.get("source", {}).get("git_commit")
        != _EXPECTED_SOURCE_COMMIT
        or generation_plan.get("source", {}).get("repository_dirty")
        is not False
        or tuple(generation_plan.get("options", {}).get("seeds", ()))
        != _EXPECTED_SEEDS
        or generation_plan.get("options", {}).get("target_count") != 16
        or generation_plan.get("options", {}).get("resource_count") != 24
        or generation_plan.get("options", {}).get("region_count") != 8
        or generation_plan.get("model_fit_allowed") is not False
        or generation_plan.get("production_permission_available") is not False
        or generation_summary.get("source", {}).get("git_commit")
        != _EXPECTED_SOURCE_COMMIT
        or generation_summary.get("source", {}).get("repository_dirty")
        is not False
        or generation_summary.get("episode_count")
        != _EXPECTED_EPISODE_COUNT
        or generation_summary.get("frame_count") != _EXPECTED_FRAME_COUNT
        or generation_summary.get("seed_count") != len(_EXPECTED_SEEDS)
        or generation_summary.get("model_fit_count") != 0
        or generation_summary.get("formal_holdout_payload_read_count") != 0
        or generation_summary.get("prior_evaluation_payload_read_count") != 0
        or generation_summary.get("production_permission_available")
        is not False
        or batch_summary.get("episode_count") != _EXPECTED_EPISODE_COUNT
        or batch_summary.get("frame_count") != _EXPECTED_FRAME_COUNT
        or batch_summary.get("model_fit_count") != 0
        or batch_summary.get("formal_holdout_payload_read_count") != 0
        or batch_summary.get("prior_evaluation_payload_read_count") != 0
        or export_summary.get("dataset_sha256") != _EXPECTED_DATASET_SHA256
        or export_summary.get("dataset_split_sha256")
        != _EXPECTED_SPLIT_SHA256
        or export_summary.get("source_artifact_sha256")
        != source_artifact_sha256
        or export_summary.get("external_dataset_evidence_sha256")
        != evidence["content_sha256"]
        or export_summary.get("positive_record_count") != 42
        or export_summary.get("positive_record_count_by_split")
        != _EXPECTED_POSITIVE_COUNTS
        or export_summary.get("production_permission_available") is not False
        or export_summary.get("test_payload_read_by_v4_builder") is not False
        or export_summary.get("truth_identifier_use_count") != 0
        or evidence.get("dataset_sha256") != _EXPECTED_DATASET_SHA256
        or evidence.get("dataset_split_sha256") != _EXPECTED_SPLIT_SHA256
        or evidence.get("source_artifact_sha256")
        != source_artifact_sha256
        or evidence.get("generated_by_v4_builder") is not False
        or evidence.get("source_worktree_dirty") is not False
        or evidence.get("truth_free_online_features") is not True
        or derivation.get("repository", {}).get("git_commit")
        != _EXPECTED_EXPORTER_COMMIT
        or derivation.get("repository", {}).get("source_worktree_dirty")
        is not False
        or derivation.get("output", {}).get("dataset_sha256")
        != _EXPECTED_DATASET_SHA256
        or derivation.get("output", {}).get("split_sha256")
        != _EXPECTED_SPLIT_SHA256
        or derivation.get("output", {}).get("frame_count")
        != _EXPECTED_FRAME_COUNT
        or derivation.get("generation", {}).get("truth_identifier_use_count")
        != 0
        or derivation.get("generation", {}).get("future_outcome_use_count")
        != 0
        or derivation.get("generation", {}).get("generated_by_v4_builder")
        is not False
        or derivation.get("governance", {}).get("test_payload_read_count")
        != 0
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_lineage_identity_mismatch"
        )
    label_audit = derivation.get("generation", {}).get(
        "observable_label_audit", {}
    )
    if (
        label_audit.get("model_input_key_scope")
        != "node_features_edge_features_edge_index_shape_dtype_values"
        or label_audit.get("observable_key_uses_source_seed_episode_or_target")
        is not False
        or label_audit.get("test_label_used_for_model_fit") is not False
        or label_audit.get(
            "validation_or_test_label_used_for_weight_fit"
        )
        is not False
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_observable_label_contract_mismatch"
        )
    return loaded, {
        "dataset_sha256": manifest.dataset_sha256,
        "dataset_split_sha256": manifest.split.split_sha256,
        "dataset_manifest_file_sha256": _sha256_file(
            dataset_root / "manifest.json"
        ),
        "export_summary_content_sha256": export_summary["content_sha256"],
        "export_summary_file_sha256": _sha256_file(export_summary_path),
        "external_evidence_content_sha256": evidence["content_sha256"],
        "external_evidence_file_sha256": _sha256_file(evidence_path),
        "derivation_content_sha256": derivation["content_sha256"],
        "derivation_file_sha256": source_artifact_sha256,
        "generation_plan_file_sha256": _sha256_file(generation_plan_path),
        "generation_summary_file_sha256": _sha256_file(
            generation_summary_path
        ),
        "batch_summary_file_sha256": _sha256_file(batch_summary_path),
        "source_clean_commit": _EXPECTED_SOURCE_COMMIT,
        "exporter_clean_commit": _EXPECTED_EXPORTER_COMMIT,
        "seeds": list(seeds),
        "split_frame_counts": split_frame_counts,
        "external_dataset_used_for_v7_actor_training": False,
        "external_dataset_used_for_checkpoint_selection": False,
        "external_dataset_used_for_threshold_tuning": False,
        "external_dataset_used_for_confidence_calibration": False,
    }


def _evaluate_records(
    loaded: LoadedRegionLearningDataset,
    *,
    model: Any,
) -> tuple[dict[str, Any], ...]:
    projector = DeterministicResourceProjector(_V4_PROJECTION)
    rule_policy = RuleRegionResourcePolicy(
        _V4_RULE_CONFIG,
        projector=projector,
    )
    actor = V7RuleNodeTransferResidualPolicy(
        model,
        V7ModelIdentity(
            REGION_RESOURCE_V7_MODEL_VERSION,
            _EXPECTED_MODEL_STATE_CONTENT_SHA256,
        ),
        rule_policy=rule_policy,
    )
    records: list[dict[str, Any]] = []
    for split in RegionLearningSplit:
        for episode in loaded.episodes(split):
            for frame in episode.frames:
                if (
                    frame.target.availability
                    != RegionLearningAvailability.AVAILABLE
                    or frame.target.recommendation is None
                ):
                    records.append(
                        _unavailable_record(
                            split=split,
                            episode_id=episode.source.episode_id,
                            seed=int(episode.source.seed),
                            frame_index=int(frame.frame_index),
                            reason=(
                                frame.target.unavailable_reason
                                or "target_unavailable"
                            ),
                        )
                    )
                    continue
                target = frame.target.recommendation
                decision = actor.decide(frame.snapshot)
                r0 = decision.baseline
                raw = decision.recommendation
                projected = projector.project(frame.snapshot, raw)
                target_signature, target_payload = executable_signature(
                    projector.build_advisory_contract(
                        frame.snapshot,
                        target,
                    )
                )
                r0_signature, r0_payload = executable_signature(
                    projector.build_advisory_contract(
                        frame.snapshot,
                        r0,
                    )
                )
                actor_signature, actor_payload = executable_signature(
                    projector.build_advisory_contract(
                        frame.snapshot,
                        projected,
                    )
                )
                raw_signature, raw_payload = executable_signature(
                    projector.build_advisory_contract(
                        frame.snapshot,
                        raw,
                    )
                )
                rule_positive = target_signature != r0_signature
                if rule_positive:
                    target_valid, target_reasons = (
                        evaluate_v4_intervention_invariants(
                            frame.snapshot,
                            target,
                            r0,
                            gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
                            projector=projector,
                            formal_decision=None,
                        )
                    )
                    if not target_valid:
                        raise RegionResourceV7ExternalEvaluationError(
                            "v7_external_unsafe_positive_target:"
                            + ",".join(target_reasons)
                        )
                actor_executable = actor_signature != r0_signature
                actor_valid = True
                invariant_reasons: tuple[str, ...] = ()
                if actor_executable:
                    actor_valid, invariant_reasons = (
                        evaluate_v4_intervention_invariants(
                            frame.snapshot,
                            projected,
                            r0,
                            gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
                            projector=projector,
                            formal_decision=None,
                        )
                    )
                rejection_reasons = tuple(projected.projection_rejections)
                projected_transfer_errors = _classify_transfer_errors(
                    _transfer_map(target_payload),
                    _transfer_map(actor_payload),
                )
                raw_transfer_errors = _classify_transfer_errors(
                    _transfer_map(target_payload),
                    _transfer_map(raw_payload),
                )
                r0_transfers = _transfer_map(r0_payload)
                raw_transfers = _transfer_map(raw_payload)
                projected_transfers = _transfer_map(actor_payload)
                raw_transfer_changes = _transfer_changes(
                    r0_transfers,
                    raw_transfers,
                )
                projected_transfer_changes = _transfer_changes(
                    r0_transfers,
                    projected_transfers,
                )
                raw_action_tuple_differences = _action_tuple_differences(
                    r0,
                    raw,
                )
                projected_action_tuple_differences = (
                    _action_tuple_differences(r0, projected)
                )
                r0_action_tuple_preserved = (
                    raw.actions == r0.actions
                    and not raw_action_tuple_differences
                )
                raw_transfer_count = len(raw.transfers)
                projected_transfer_count = len(projected.transfers)
                exact_target = actor_signature == target_signature
                exact_positive = bool(
                    rule_positive
                    and exact_target
                    and actor_executable
                    and actor_valid
                    and not rejection_reasons
                    and r0_action_tuple_preserved
                )
                negative_exact_r0 = bool(
                    not rule_positive
                    and actor_signature == r0_signature
                    and not rejection_reasons
                    and r0_action_tuple_preserved
                )
                actor_derived_positive = bool(
                    actor_executable
                    and actor_valid
                    and not rejection_reasons
                    and r0_action_tuple_preserved
                )
                failure_reasons: list[str] = []
                if rejection_reasons:
                    failure_reasons.append("projection_rejected")
                if actor_executable and not actor_valid:
                    failure_reasons.append("invariant_failure")
                if not r0_action_tuple_preserved:
                    failure_reasons.append("r0_action_tuple_deviation")
                if rule_positive and not exact_positive:
                    failure_reasons.append("positive_exact_action_missed")
                if not rule_positive and not negative_exact_r0:
                    failure_reasons.append("negative_r0_missed")
                if projected_transfer_errors["wrong_direction_count"]:
                    failure_reasons.append("wrong_direction")
                if projected_transfer_errors["wrong_quantity_count"]:
                    failure_reasons.append("wrong_quantity")
                if not rule_positive and projected_transfer_changes:
                    failure_reasons.append("false_transfer")
                records.append(
                    {
                        "schema": REGION_RESOURCE_V7_EXTERNAL_RECORD_SCHEMA,
                        "evaluation_available": True,
                        "unavailable_reason": None,
                        "split": split.value,
                        "source_episode_id": episode.source.episode_id,
                        "seed": int(episode.source.seed),
                        "frame_index": int(frame.frame_index),
                        "snapshot_id": frame.snapshot.snapshot_id,
                        "observable_key_sha256": (
                            _v4_confidence_observable_key(
                                snapshot_to_region_graph(
                                    frame.snapshot,
                                    device="cpu",
                                )
                            )
                        ),
                        "rule_positive": rule_positive,
                        "rule_negative": not rule_positive,
                        "target_transfer_count": len(target.transfers),
                        "target_transfer_resource_count": sum(
                            item.resource_count for item in target.transfers
                        ),
                        "target_transfer_payload": _transfer_payload(target),
                        "r0_action_tuple": _action_tuple_payload(r0),
                        "raw_action_tuple": _action_tuple_payload(raw),
                        "projected_action_tuple": _action_tuple_payload(
                            projected
                        ),
                        "r0_action_tuple_preserved": (
                            r0_action_tuple_preserved
                        ),
                        "r0_action_tuple_difference_count": len(
                            raw_action_tuple_differences
                        ),
                        "r0_action_tuple_differences": list(
                            raw_action_tuple_differences
                        ),
                        "projected_r0_action_tuple_difference_count": len(
                            projected_action_tuple_differences
                        ),
                        "projected_r0_action_tuple_differences": list(
                            projected_action_tuple_differences
                        ),
                        "actor_raw_residual_activation_count": len(
                            decision.activated_edge_keys
                        ),
                        "actor_raw_residual_activations": [
                            {
                                "edge_id": key[0],
                                "source_region_id": key[1],
                                "target_region_id": key[2],
                                "predicted_resource_count": int(count),
                            }
                            for key, count in zip(
                                decision.activated_edge_keys,
                                decision.predicted_resource_counts,
                            )
                        ],
                        "actor_raw_transfer_change_count": len(
                            raw_transfer_changes
                        ),
                        "actor_raw_transfer_changes": list(
                            raw_transfer_changes
                        ),
                        "actor_raw_transfer_count": raw_transfer_count,
                        "actor_raw_transfer_resource_count": sum(
                            item.resource_count for item in raw.transfers
                        ),
                        "actor_raw_transfer_payload": _transfer_payload(raw),
                        "actor_raw_signature_differs_from_r0": (
                            raw_signature != r0_signature
                        ),
                        "actor_projected_transfer_count": (
                            projected_transfer_count
                        ),
                        "actor_projected_transfer_resource_count": sum(
                            item.resource_count
                            for item in projected.transfers
                        ),
                        "actor_projected_transfer_payload": (
                            _transfer_payload(projected)
                        ),
                        "actor_projected_transfer_change_count": len(
                            projected_transfer_changes
                        ),
                        "actor_projected_transfer_changes": list(
                            projected_transfer_changes
                        ),
                        "projected_action": _recommendation_payload(
                            projected
                        ),
                        "raw_correct_directed_edge_count": (
                            raw_transfer_errors[
                                "correct_directed_edge_count"
                            ]
                        ),
                        "raw_wrong_direction_count": raw_transfer_errors[
                            "wrong_direction_count"
                        ],
                        "raw_wrong_quantity_count": raw_transfer_errors[
                            "wrong_quantity_count"
                        ],
                        "raw_wrong_edge_count": raw_transfer_errors[
                            "wrong_edge_count"
                        ],
                        "correct_directed_edge_count": (
                            projected_transfer_errors[
                            "correct_directed_edge_count"
                            ]
                        ),
                        "correct_directed_edge_frame": bool(
                            rule_positive
                            and projected_transfer_errors[
                                "correct_directed_edge_count"
                            ]
                            == len(target.transfers)
                            and len(target.transfers) > 0
                        ),
                        "projected_exact_positive_action": exact_positive,
                        "negative_exact_r0": negative_exact_r0,
                        "wrong_direction_count": projected_transfer_errors[
                            "wrong_direction_count"
                        ],
                        "wrong_quantity_count": projected_transfer_errors[
                            "wrong_quantity_count"
                        ],
                        "wrong_edge_count": projected_transfer_errors[
                            "wrong_edge_count"
                        ],
                        "false_transfer_count": (
                            len(projected_transfer_changes)
                            if not rule_positive
                            else 0
                        ),
                        "projection_rejection_count": len(
                            rejection_reasons
                        ),
                        "projection_rejected": bool(rejection_reasons),
                        "projection_rejection_reasons": list(
                            rejection_reasons
                        ),
                        "invariant_failure": bool(
                            actor_executable and not actor_valid
                        ),
                        "invariant_failure_reasons": list(
                            invariant_reasons
                        ),
                        "actor_executable_difference": actor_executable,
                        "actor_derived_positive": actor_derived_positive,
                        "confidence_gate_available": False,
                        "confidence_gate_applied": False,
                        "confidence_threshold_passed": None,
                        "admission_evaluated": False,
                        "rule_fallback_required": True,
                        "failure_reasons": list(
                            dict.fromkeys(failure_reasons)
                        ),
                    }
                )
    return tuple(records)


def _unavailable_record(
    *,
    split: RegionLearningSplit,
    episode_id: str,
    seed: int,
    frame_index: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema": REGION_RESOURCE_V7_EXTERNAL_RECORD_SCHEMA,
        "evaluation_available": False,
        "unavailable_reason": reason,
        "split": split.value,
        "source_episode_id": episode_id,
        "seed": seed,
        "frame_index": frame_index,
        "snapshot_id": None,
        "observable_key_sha256": None,
        "rule_positive": None,
        "rule_negative": None,
        "target_transfer_count": None,
        "target_transfer_resource_count": None,
        "target_transfer_payload": [],
        "r0_action_tuple": [],
        "raw_action_tuple": [],
        "projected_action_tuple": [],
        "r0_action_tuple_preserved": None,
        "r0_action_tuple_difference_count": None,
        "r0_action_tuple_differences": [],
        "projected_r0_action_tuple_difference_count": None,
        "projected_r0_action_tuple_differences": [],
        "actor_raw_residual_activation_count": None,
        "actor_raw_residual_activations": [],
        "actor_raw_transfer_change_count": None,
        "actor_raw_transfer_changes": [],
        "actor_raw_transfer_count": None,
        "actor_raw_transfer_resource_count": None,
        "actor_raw_transfer_payload": [],
        "actor_raw_signature_differs_from_r0": None,
        "actor_projected_transfer_count": None,
        "actor_projected_transfer_resource_count": None,
        "actor_projected_transfer_payload": [],
        "actor_projected_transfer_change_count": None,
        "actor_projected_transfer_changes": [],
        "projected_action": {},
        "raw_correct_directed_edge_count": None,
        "raw_wrong_direction_count": None,
        "raw_wrong_quantity_count": None,
        "raw_wrong_edge_count": None,
        "correct_directed_edge_count": None,
        "correct_directed_edge_frame": None,
        "projected_exact_positive_action": None,
        "negative_exact_r0": None,
        "wrong_direction_count": None,
        "wrong_quantity_count": None,
        "wrong_edge_count": None,
        "false_transfer_count": None,
        "projection_rejection_count": None,
        "projection_rejected": None,
        "projection_rejection_reasons": [],
        "invariant_failure": None,
        "invariant_failure_reasons": [],
        "actor_executable_difference": None,
        "actor_derived_positive": None,
        "confidence_gate_available": False,
        "confidence_gate_applied": False,
        "confidence_threshold_passed": None,
        "admission_evaluated": False,
        "rule_fallback_required": True,
        "failure_reasons": ["evaluation_unavailable"],
    }


def _action_tuple_payload(
    recommendation: Any,
) -> list[dict[str, Any]]:
    return [action.to_dict() for action in recommendation.actions]


def _action_tuple_differences(
    baseline: Any,
    candidate: Any,
) -> tuple[str, ...]:
    baseline_actions = {
        action.region_id: action.to_dict() for action in baseline.actions
    }
    candidate_actions = {
        action.region_id: action.to_dict() for action in candidate.actions
    }
    differences: list[str] = []
    if tuple(action.region_id for action in baseline.actions) != tuple(
        action.region_id for action in candidate.actions
    ):
        differences.append("action_tuple_order_or_region_set")
    for region_id in sorted(set(baseline_actions) | set(candidate_actions)):
        left = baseline_actions.get(region_id)
        right = candidate_actions.get(region_id)
        if left is None or right is None:
            differences.append(f"region:{region_id}:missing")
            continue
        for field_name in sorted(set(left) | set(right)):
            if left.get(field_name) != right.get(field_name):
                differences.append(f"region:{region_id}:{field_name}")
    return tuple(differences)


def _transfer_payload(recommendation: Any) -> list[dict[str, Any]]:
    return [
        transfer.to_dict()
        for transfer in sorted(
            recommendation.transfers,
            key=lambda item: (
                item.source_region_id,
                item.target_region_id,
                item.edge_id,
            ),
        )
    ]


def _recommendation_payload(
    recommendation: Any,
) -> dict[str, Any]:
    return {
        "actions": _action_tuple_payload(recommendation),
        "transfers": _transfer_payload(recommendation),
        "projected": bool(recommendation.projected),
        "projection_rejections": list(
            recommendation.projection_rejections
        ),
    }


def _transfer_changes(
    baseline: Mapping[tuple[str, str, str], int],
    candidate: Mapping[tuple[str, str, str], int],
) -> tuple[dict[str, Any], ...]:
    changes: list[dict[str, Any]] = []
    for source, target, edge_id in sorted(set(baseline) | set(candidate)):
        before = int(baseline.get((source, target, edge_id), 0))
        after = int(candidate.get((source, target, edge_id), 0))
        if before == after:
            continue
        changes.append(
            {
                "source_region_id": source,
                "target_region_id": target,
                "edge_id": edge_id,
                "r0_resource_count": before,
                "candidate_resource_count": after,
                "resource_count_delta": after - before,
            }
        )
    return tuple(changes)


def _transfer_map(
    advisory_payload: Mapping[str, Any],
) -> dict[tuple[str, str, str], int]:
    result: dict[tuple[str, str, str], int] = {}
    for item in advisory_payload["transfer_allowances"]:
        key = (
            str(item["source_region_id"]),
            str(item["target_region_id"]),
            str(item["edge_id"]),
        )
        result[key] = result.get(key, 0) + int(item["resource_count"])
    return result


def _classify_transfer_errors(
    target: Mapping[tuple[str, str, str], int],
    predicted: Mapping[tuple[str, str, str], int],
) -> dict[str, int]:
    """Separate directed-edge, direction, and transfer-count errors."""

    target_keys = set(target)
    predicted_keys = set(predicted)
    correct = target_keys & predicted_keys
    wrong_direction = 0
    wrong_edge = 0
    for source, destination, edge_id in predicted_keys - target_keys:
        reversed_direction = any(
            target_source == destination
            and target_destination == source
            for target_source, target_destination, _ in target_keys
        )
        if reversed_direction:
            wrong_direction += 1
        else:
            wrong_edge += 1
    wrong_quantity = sum(
        int(predicted[key] != target[key]) for key in correct
    )
    return {
        "correct_directed_edge_count": len(correct),
        "wrong_direction_count": wrong_direction,
        "wrong_quantity_count": wrong_quantity,
        "wrong_edge_count": wrong_edge,
    }


def _summarize_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    available = tuple(
        item for item in records if item["evaluation_available"]
    )
    unavailable_count = len(records) - len(available)
    positives = tuple(item for item in available if item["rule_positive"])
    negatives = tuple(item for item in available if item["rule_negative"])
    actor_derived = tuple(
        item for item in available if item["actor_derived_positive"]
    )
    exact_positive_count = sum(
        bool(item["projected_exact_positive_action"]) for item in available
    )
    negative_exact_count = sum(
        bool(item["negative_exact_r0"]) for item in available
    )
    actor_derived_exact_count = sum(
        bool(item["actor_derived_positive"])
        and bool(item["projected_exact_positive_action"])
        for item in available
    )
    positive_recall, positive_recall_status = _rate_or_unavailable(
        exact_positive_count,
        len(positives),
        unavailable_status="unavailable_zero_rule_positive_denominator",
    )
    negative_specificity, negative_specificity_status = _rate_or_unavailable(
        negative_exact_count,
        len(negatives),
        unavailable_status="unavailable_zero_rule_negative_denominator",
    )
    actor_derived_exact_rate, actor_derived_status = _rate_or_unavailable(
        actor_derived_exact_count,
        len(actor_derived),
        unavailable_status=(
            "unavailable_zero_actor_derived_positive_denominator"
        ),
    )
    return {
        "sample_count": len(records),
        "available_sample_count": len(available),
        "unavailable_sample_count": unavailable_count,
        "rule_positive_count": len(positives),
        "rule_negative_count": len(negatives),
        "actor_raw_residual_activation_count": sum(
            int(item["actor_raw_residual_activation_count"])
            for item in available
        ),
        "actor_raw_transfer_change_count": sum(
            int(item["actor_raw_transfer_change_count"])
            for item in available
        ),
        "actor_raw_transfer_change_frame_count": sum(
            bool(item["actor_raw_transfer_change_count"])
            for item in available
        ),
        "actor_raw_transfer_count": sum(
            int(item["actor_raw_transfer_count"]) for item in available
        ),
        "actor_raw_transfer_resource_count": sum(
            int(item["actor_raw_transfer_resource_count"])
            for item in available
        ),
        "actor_projected_transfer_count": sum(
            int(item["actor_projected_transfer_count"])
            for item in available
        ),
        "actor_projected_transfer_resource_count": sum(
            int(item["actor_projected_transfer_resource_count"])
            for item in available
        ),
        "actor_projected_transfer_change_count": sum(
            int(item["actor_projected_transfer_change_count"])
            for item in available
        ),
        "raw_correct_directed_edge_count": sum(
            int(item["raw_correct_directed_edge_count"])
            for item in available
        ),
        "raw_wrong_direction_count": sum(
            int(item["raw_wrong_direction_count"]) for item in available
        ),
        "raw_wrong_quantity_count": sum(
            int(item["raw_wrong_quantity_count"]) for item in available
        ),
        "raw_wrong_edge_count": sum(
            int(item["raw_wrong_edge_count"]) for item in available
        ),
        "correct_directed_edge_count": sum(
            int(item["correct_directed_edge_count"]) for item in available
        ),
        "correct_directed_edge_frame_count": sum(
            bool(item["correct_directed_edge_frame"]) for item in available
        ),
        "projected_exact_positive_action_count": exact_positive_count,
        "positive_exact_action_recall": positive_recall,
        "positive_exact_action_recall_status": positive_recall_status,
        "negative_exact_r0_count": negative_exact_count,
        "negative_exact_r0_rate": negative_specificity,
        "negative_exact_r0_rate_status": negative_specificity_status,
        "wrong_direction_count": sum(
            int(item["wrong_direction_count"]) for item in available
        ),
        "wrong_quantity_count": sum(
            int(item["wrong_quantity_count"]) for item in available
        ),
        "wrong_edge_count": sum(
            int(item["wrong_edge_count"]) for item in available
        ),
        "false_transfer_count": sum(
            int(item["false_transfer_count"]) for item in available
        ),
        "projection_rejection_count": sum(
            int(item["projection_rejection_count"]) for item in available
        ),
        "projection_rejection_frame_count": sum(
            bool(item["projection_rejected"]) for item in available
        ),
        "invariant_failure_count": sum(
            bool(item["invariant_failure"]) for item in available
        ),
        "r0_action_tuple_preservation_failure_count": sum(
            not bool(item["r0_action_tuple_preserved"])
            for item in available
        ),
        "r0_action_tuple_difference_count": sum(
            int(item["r0_action_tuple_difference_count"])
            for item in available
        ),
        "projected_r0_action_tuple_difference_frame_count": sum(
            bool(item["projected_r0_action_tuple_difference_count"])
            for item in available
        ),
        "actor_derived_positive_denominator_count": len(actor_derived),
        "actor_derived_positive_denominator_available": bool(actor_derived),
        "actor_derived_exact_positive_count": actor_derived_exact_count,
        "actor_derived_exact_positive_rate": actor_derived_exact_rate,
        "actor_derived_exact_positive_rate_status": actor_derived_status,
        "confidence_gate_available": False,
        "confidence_gate_application_count": 0,
        "admission_evaluation_count": 0,
        "all_frames_rule_fallback_required": True,
        "unavailable_reasons": _reason_inventory(
            item["unavailable_reason"]
            for item in records
            if not item["evaluation_available"]
        ),
        "failure_reasons": _reason_inventory(
            reason
            for item in available
            for reason in item["failure_reasons"]
        ),
        "projection_rejection_reasons": _reason_inventory(
            reason
            for item in available
            for reason in item["projection_rejection_reasons"]
        ),
        "invariant_failure_reasons": _reason_inventory(
            reason
            for item in available
            for reason in item["invariant_failure_reasons"]
        ),
    }


def _validate_external_action_inventory(
    metrics_by_split: Mapping[str, Mapping[str, Any]],
) -> None:
    frame_counts = {
        split: int(metrics["sample_count"])
        for split, metrics in metrics_by_split.items()
    }
    positive_counts = {
        split: int(metrics["rule_positive_count"])
        for split, metrics in metrics_by_split.items()
    }
    if (
        frame_counts != _EXPECTED_FRAME_COUNTS
        or positive_counts != _EXPECTED_POSITIVE_COUNTS
        or any(
            metrics["unavailable_sample_count"] != 0
            for metrics in metrics_by_split.values()
        )
    ):
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_action_inventory_mismatch"
        )


def _observable_overlap_audit(
    frozen_v4: LoadedRegionLearningDataset,
    external: LoadedRegionLearningDataset,
) -> dict[str, Any]:
    v4_keys = {
        _v4_confidence_observable_key(
            snapshot_to_region_graph(frame.snapshot, device="cpu")
        )
        for split in (
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        )
        for episode in frozen_v4.episodes(split)
        for frame in episode.frames
    }
    external_by_split = {
        split.value: {
            _v4_confidence_observable_key(
                snapshot_to_region_graph(frame.snapshot, device="cpu")
            )
            for episode in external.episodes(split)
            for frame in episode.frames
        }
        for split in RegionLearningSplit
    }
    external_keys = set().union(*external_by_split.values())
    intersection = v4_keys & external_keys
    return {
        "schema": REGION_RESOURCE_V7_EXTERNAL_OVERLAP_SCHEMA,
        "observable_key_scope": (
            "node_features_edge_features_edge_index_shape_dtype_values"
        ),
        "observable_key_uses_seed": False,
        "observable_key_uses_episode_identity": False,
        "observable_key_uses_target_label": False,
        "observable_key_uses_truth": False,
        "frozen_v4_train_validation_unique_key_count": len(v4_keys),
        "external_unique_key_count": len(external_keys),
        "exact_observable_key_intersection_count": len(intersection),
        "exact_observable_key_intersection_sha256": _canonical_sha256(
            sorted(intersection)
        ),
        "by_external_split": {
            split: {
                "unique_key_count": len(keys),
                "exact_overlap_count": len(keys & v4_keys),
            }
            for split, keys in external_by_split.items()
        },
        "frozen_v4_exact_observable_overlap_free": len(intersection) == 0,
        "full_v7_training_source_observable_overlap_status": (
            "unavailable_source_b_payload_not_supplied_to_evaluator"
        ),
    }


def _data_usage(
    metrics_by_split: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "payload_splits_read_for_evaluation": [
            split.value for split in RegionLearningSplit
        ],
        "payload_read_count_by_split": {
            split: int(metrics["sample_count"])
            for split, metrics in metrics_by_split.items()
        },
        "v7_actor_training_use_count_by_external_split": {
            split.value: 0 for split in RegionLearningSplit
        },
        "v7_checkpoint_selection_use_count_by_external_split": {
            split.value: 0 for split in RegionLearningSplit
        },
        "v7_threshold_tuning_use_count_by_external_split": {
            split.value: 0 for split in RegionLearningSplit
        },
        "v7_confidence_calibration_use_count_by_external_split": {
            split.value: 0 for split in RegionLearningSplit
        },
        "test_payload_use": "read_only_external_evaluation",
        "model_fit_count": 0,
        "checkpoint_update_count": 0,
        "threshold_tuning_count": 0,
        "confidence_calibration_count": 0,
        "confidence_gate_application_count": 0,
        "candidate_mutation_count": 0,
        "input_mutation_count": 0,
        "registration_count": 0,
        "admission_count": 0,
        "prior_external_evaluation_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "truth_identifier_use_count": 0,
        "production_permission_available": False,
    }


def _closed_candidate_status() -> dict[str, Any]:
    permissions = {
        "source_independent_evaluation": False,
        "assist": False,
        "authority": False,
        "assignment": False,
        "degradation": False,
        "takeover": False,
        "coalition": False,
        "control": False,
        "physical": False,
        "d3": False,
        "d7": False,
        "production_runtime_ack": False,
        "actual_adoption": False,
        "benefit_claim": False,
    }
    return {
        "registered": False,
        "unregistered": True,
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
        "confidence_calibration_available": False,
        "confidence_calibrator_available": False,
        "confidence_gate_available": False,
        "confidence_calibration_count": 0,
        "fixed_minimum_confidence_gate_applied": False,
        "permissions": permissions,
    }


def _conclusion(
    metrics_by_split: Mapping[str, Mapping[str, Any]],
    overlap: Mapping[str, Any],
) -> dict[str, Any]:
    test = metrics_by_split["test"]
    behavioral_failures: list[str] = []
    for split in ("train", "validation", "test"):
        metrics = metrics_by_split[split]
        if (
            metrics["rule_positive_count"] > 0
            and metrics["actor_raw_transfer_change_count"] == 0
        ):
            behavioral_failures.append(
                f"{split}_positive_targets_without_raw_transfer_change"
            )
        if (
            metrics["rule_positive_count"] > 0
            and metrics["projected_exact_positive_action_count"] == 0
        ):
            behavioral_failures.append(
                f"{split}_zero_projected_exact_positive_action"
            )
        if metrics["false_transfer_count"] > 0:
            behavioral_failures.append(f"{split}_false_transfer_observed")
        if metrics["invariant_failure_count"] > 0:
            behavioral_failures.append(f"{split}_invariant_failure_observed")
        if metrics["projection_rejection_count"] > 0:
            behavioral_failures.append(
                f"{split}_projection_rejection_observed"
            )
        if metrics["r0_action_tuple_preservation_failure_count"] > 0:
            behavioral_failures.append(
                f"{split}_r0_action_tuple_deviation_observed"
            )
    return {
        "evaluation_disposition": (
            "failed_closed" if behavioral_failures else "review_required"
        ),
        "behavioral_failure_reasons": behavioral_failures,
        "frozen_v4_exact_observable_overlap_free": bool(
            overlap["frozen_v4_exact_observable_overlap_free"]
        ),
        "full_v7_training_observable_overlap_available": False,
        "source_seed_identity_independent": True,
        "test_rule_positive_denominator_available": bool(
            test["rule_positive_count"]
        ),
        "test_actor_derived_positive_denominator_available": bool(
            test["actor_derived_positive_denominator_available"]
        ),
        "test_positive_exact_action_recall": test[
            "positive_exact_action_recall"
        ],
        "test_negative_exact_r0_rate": test["negative_exact_r0_rate"],
        "test_raw_transfer_change_count": test[
            "actor_raw_transfer_change_count"
        ],
        "test_invariant_failure_count": test["invariant_failure_count"],
        "test_projection_rejection_count": test[
            "projection_rejection_count"
        ],
        "test_r0_action_tuple_preservation_failure_count": test[
            "r0_action_tuple_preservation_failure_count"
        ],
        "source_independent_evaluation_completed": True,
        "generalization_admission_supported": False,
        "required_runtime_action": "deterministic_rule_fallback",
        "next_gate": (
            "main_and_d6_review_external_behavior_before_any_separate_"
            "confidence_calibration_or_admission_protocol"
        ),
    }


def _render_report(
    summary: Mapping[str, Any],
    integrity: Mapping[str, Any],
    overlap: Mapping[str, Any],
) -> str:
    rows = []
    for split in ("train", "validation", "test"):
        item = summary["metrics_by_split"][split]
        rows.append(
            "| {split} | {sample} | {positive} | {negative} | {activation} | "
            "{raw_change} | {edge} | {exact} | {r0} | {direction} | "
            "{quantity} | {false_transfer} | {rejection} | {invariant} | "
            "{node_deviation} | {derived} |".format(
                split=split,
                sample=item["sample_count"],
                positive=item["rule_positive_count"],
                negative=item["rule_negative_count"],
                activation=item["actor_raw_residual_activation_count"],
                raw_change=item["actor_raw_transfer_change_count"],
                edge=item["correct_directed_edge_count"],
                exact=item["projected_exact_positive_action_count"],
                r0=item["negative_exact_r0_count"],
                direction=item["wrong_direction_count"],
                quantity=item["wrong_quantity_count"],
                false_transfer=item["false_transfer_count"],
                rejection=item["projection_rejection_count"],
                invariant=item["invariant_failure_count"],
                node_deviation=item[
                    "r0_action_tuple_preservation_failure_count"
                ],
                derived=item["actor_derived_positive_denominator_count"],
            )
        )
    candidate = integrity["candidate"]
    source = integrity["raw_source"]
    external = integrity["labeled_input"]
    test = summary["metrics_by_split"]["test"]
    conclusion = summary["conclusion"]
    failure_text = "、".join(conclusion["behavioral_failure_reasons"])
    return "\n".join(
        [
            "# D4 v7 来源独立外部评价",
            "",
            "## 结论",
            "",
            "本次评价只读取冻结的 v7 actor、M16N24 原始来源、标签导出和"
            "冻结 v4 来源。评价没有拟合模型、更新检查点、调整阈值、校准置信度"
            "或执行准入。",
            "",
            f"测试划分包含 {test['sample_count']} 帧，其中规则正类 "
            f"{test['rule_positive_count']} 帧、负类 "
            f"{test['rule_negative_count']} 帧。投影后精确正动作命中 "
            f"{test['projected_exact_positive_action_count']} 帧，负类精确保持 "
            f"R0 {test['negative_exact_r0_count']} 帧。该结果只构成开发评价证据，"
            "不构成准入结论。",
            "",
            f"评价处置为 `{conclusion['evaluation_disposition']}`。逐划分事实失败项为："
            f"{failure_text}。候选继续使用确定性规则回退。",
            "",
            "## 分划分结果",
            "",
            "| 划分 | 样本 | 规则正类 | 规则负类 | 原始激活 | 原始转移变化 | "
            "正确有向边 | 精确正动作 | 负类精确 R0 | 错误方向 | 错误数量 | "
            "虚假转移 | 投影拒绝 | 约束失败 | R0 节点偏差 | actor 正类分母 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---:|---:|---:|---:|---:|",
            *rows,
            "",
            "actor 正类分母指 actor 投影后产生可执行差异、通过不变量检查且未发生"
            "投影拒绝的帧数。分母为零时，对应比率写为 unavailable，不以零代替。",
            "",
            "## 来源独立性",
            "",
            f"冻结 v4 训练与验证集共有 "
            f"{overlap['frozen_v4_train_validation_unique_key_count']} 个唯一在线可观测键，"
            f"外部数据共有 {overlap['external_unique_key_count']} 个。精确交集为 "
            f"{overlap['exact_observable_key_intersection_count']}。键只包含节点特征、"
            "边特征、边索引及其形状、类型和值，不包含 seed、episode、目标标签或真值。"
            "候选训练来源 B 的完整特征载荷没有作为本评价输入，因此本项只覆盖冻结 v4 "
            "来源，不据此宣称全部训练可观测键无交集。",
            "",
            "外部数据的 train、validation、test 是本次外部数据自身的划分名称。"
            "三类数据均未参与 v7 actor 训练、检查点选择或阈值拟合；test 仅用于本次"
            "只读评价。",
            "",
            "## 完整性",
            "",
            f"- 候选 manifest 内容哈希：`{candidate['manifest_content_sha256']}`",
            f"- 训练审计内容哈希：`{candidate['training_audit_content_sha256']}`",
            f"- 模型参数内容哈希：`{candidate['model_state_content_sha256']}`",
            f"- 状态文件哈希：`{candidate['state_file_sha256']}`",
            f"- 原始来源树哈希：`{source['tree_sha256_before']}`",
            f"- 外部数据集哈希：`{external['dataset_sha256']}`",
            f"- 外部划分哈希：`{external['dataset_split_sha256']}`",
            "- 候选树前后突变：0",
            "- 原始来源树前后突变：0",
            "- 标签导出树前后突变：0",
            "- 冻结 v4 训练来源树前后突变：0",
            "",
            "## 权限",
            "",
            "v7 保持未注册、仅开发影子运行、准入关闭和规则回退。assist、assignment、"
            "degradation、takeover、coalition、control、physical、D3、D7 权限均为"
            " false。候选没有置信校准器，固定置信门没有应用。",
            "",
            "## 下一门",
            "",
            "本报告先交由 main 与 D6 审阅逐帧失败原因。只有来源独立行为证据达到另行"
            "冻结的验收口径后，才可设计独立置信校准和准入协议。旧评价 seed "
            "3008-3039 和正式 holdout seed 1000-1019 本次均未读取。",
            "",
        ]
    )


def _rate_or_unavailable(
    numerator: int,
    denominator: int,
    *,
    unavailable_status: str,
) -> tuple[float | None, str]:
    if denominator <= 0:
        return None, unavailable_status
    return numerator / denominator, "available"


def _reason_inventory(values: Sequence[str] | Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        name = str(value)
        result[name] = result.get(name, 0) + 1
    return dict(sorted(result.items()))


def _validate_seed_isolation(seeds: Sequence[int]) -> None:
    values = set(int(value) for value in seeds)
    if values & _FORBIDDEN_PRIOR_EVALUATION_SEEDS:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_prior_evaluation_seed_read_forbidden"
        )
    if values & _FORBIDDEN_FORMAL_HOLDOUT_SEEDS:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_formal_holdout_seed_read_forbidden"
        )


def _assert_tree_unchanged(name: str, before: str, after: str) -> None:
    if before != after:
        raise RegionResourceV7ExternalEvaluationError(
            f"v7_external_{name}_mutation_detected"
        )


def _verify_content_sha256(
    value: Mapping[str, Any],
    name: str,
) -> None:
    expected = value.get("content_sha256")
    payload = dict(value)
    payload.pop("content_sha256", None)
    if not isinstance(expected, str) or expected != _canonical_sha256(payload):
        raise RegionResourceV7ExternalEvaluationError(
            f"v7_external_{name}_content_sha256_mismatch"
        )


def _with_content_sha256(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload.pop("content_sha256", None)
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def _resign(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload.pop("content_sha256", None)
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    inventory = {
        str(path.relative_to(root)): _sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    return _canonical_sha256(inventory)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegionResourceV7ExternalEvaluationError(
            f"v7_external_json_read_failed:{path.name}:{type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise RegionResourceV7ExternalEvaluationError(
            f"v7_external_json_object_required:{path.name}"
        )
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_jsonl(
    path: Path,
    records: Sequence[Mapping[str, Any]],
) -> None:
    path.write_text(
        "".join(
            json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
            for item in records
        ),
        encoding="utf-8",
    )


def _write_csv(
    path: Path,
    records: Sequence[Mapping[str, Any]],
) -> None:
    if not records:
        raise RegionResourceV7ExternalEvaluationError(
            "v7_external_csv_records_unavailable"
        )
    fields = tuple(records[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {
                name: (
                    json.dumps(value, sort_keys=True, ensure_ascii=True)
                    if isinstance(value, (list, dict))
                    else value
                )
                for name, value in record.items()
            }
            writer.writerow(row)
