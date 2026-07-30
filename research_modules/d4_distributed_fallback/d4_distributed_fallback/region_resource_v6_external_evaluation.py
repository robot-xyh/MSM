"""Read-only source-independent evaluation for the frozen-by-hash D4 v6 actor.

The evaluator loads one exact v6 bundle and one exact external dataset.  It
does not fit a model, select a checkpoint, tune a threshold, apply the
uncalibrated confidence head, register the candidate, or grant permissions.
Candidate and input trees are hashed before and after evaluation.
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
from .region_resource_learning import (
    LearnedRegionResourcePolicy,
    snapshot_to_region_graph,
)
from .region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V4_INTERVENTION_GATE,
    _PolicyIdentity,
    _V4_PROJECTION,
    _V4_RULE_CONFIG,
    _v4_confidence_observable_key,
    evaluate_v4_intervention_invariants,
    executable_signature,
)
from .region_resource_v6_transfer_candidate import (
    REGION_RESOURCE_V6_AUDIT_FILENAME,
    REGION_RESOURCE_V6_CANDIDATE_FILENAME,
    REGION_RESOURCE_V6_CANDIDATE_ID,
    REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE,
    REGION_RESOURCE_V6_MODEL_VERSION,
    REGION_RESOURCE_V6_STATE_MAGIC,
    _load_v6_model_bundle,
    _model_state_content_sha256,
    _validate_frozen_v4_source,
)


REGION_RESOURCE_V6_EXTERNAL_SCHEMA = (
    "d4-region-resource-v6-source-independent-external-evaluation-v1"
)
REGION_RESOURCE_V6_EXTERNAL_RECORD_SCHEMA = (
    "d4-region-resource-v6-source-independent-frame-evaluation-v1"
)
REGION_RESOURCE_V6_EXTERNAL_INTEGRITY_SCHEMA = (
    "d4-region-resource-v6-source-independent-input-integrity-v1"
)
REGION_RESOURCE_V6_EXTERNAL_OVERLAP_SCHEMA = (
    "d4-region-resource-v6-source-independent-observable-overlap-v1"
)
REGION_RESOURCE_V6_EXTERNAL_ARTIFACT_SCHEMA = (
    "d4-region-resource-v6-source-independent-artifact-manifest-v1"
)

REGION_RESOURCE_V6_EXTERNAL_RECORDS_FILENAME = "evaluation_records.jsonl"
REGION_RESOURCE_V6_EXTERNAL_CSV_FILENAME = "evaluation_records.csv"
REGION_RESOURCE_V6_EXTERNAL_INTEGRITY_FILENAME = "input_integrity.json"
REGION_RESOURCE_V6_EXTERNAL_OVERLAP_FILENAME = "observable_overlap_audit.json"
REGION_RESOURCE_V6_EXTERNAL_SUMMARY_FILENAME = "external_evaluation_summary.json"
REGION_RESOURCE_V6_EXTERNAL_REPORT_FILENAME = "REPORT_CN.md"
REGION_RESOURCE_V6_EXTERNAL_ARTIFACT_FILENAME = "artifact_manifest.json"

_EXPECTED_REPORT_DATE = "2026-07-30"
_EXPECTED_CANDIDATE_MANIFEST_CONTENT_SHA256 = (
    "f40064e7b25d4b9d908be466b12b5e50447b31b251e8ba0b308b1e5a6466a83f"
)
_EXPECTED_TRAINING_AUDIT_CONTENT_SHA256 = (
    "ebc1334dcc2e7f9ed0cbe87354555021a1bb6d90a49bb7bcee7594a3364bee9a"
)
_EXPECTED_MODEL_STATE_CONTENT_SHA256 = (
    "c09d1719c550c4dd35a72d1ea5b1538e198811045d61e9e72f81fac899dba9e6"
)
_EXPECTED_STATE_FILE_SHA256 = (
    "e92ea3aa55fd8f13d180e37aa15154e3e5fe58ab4611805805ba46bcd07b6ea8"
)
_EXPECTED_CANDIDATE_TREE_SHA256 = (
    "8c9d01796c4938effda3f2f3e6e4a82eec73813581a32dc544664d7fc51665e7"
)
_EXPECTED_EXTERNAL_ROOT_NAME = (
    "msm_d4_v6_transfer_labeled_m16n24_64seed_test8_9bdbe31"
)
_EXPECTED_EXTERNAL_TREE_SHA256 = (
    "b0c1044b278a16c328b0641dcb456d93cd4f3b26d8b9552f45b8069580cf9f96"
)
_EXPECTED_DATASET_TREE_SHA256 = (
    "95b7f64cf4df64e1cf0e33442c57946163ce69cbcadd3a6c93e2c6341a411ff5"
)
_EXPECTED_DATASET_SHA256 = (
    "b1295091d4d79e423e1ced02269895d486e2dbcca9d80834d5af0cc14882b42c"
)
_EXPECTED_SPLIT_SHA256 = (
    "c767a48b90f6e2a3f077be4f931d95102a6b2a925a2f813ca8440c8951aae332"
)
_EXPECTED_SOURCE_COMMIT = "ed9e086ea8cf5c2138035f710cf4deb3e4a2801e"
_EXPECTED_EXPORTER_COMMIT = "9bdbe31dee34907525eabc9cf278e0d11f7dd88a"
_EXPECTED_EXPORT_SUMMARY_CONTENT_SHA256 = (
    "862c9e4e937d2a629e83bdf8fdd8bb6002e7b132f58a9e2e6be9cc09e6daa808"
)
_EXPECTED_EVIDENCE_CONTENT_SHA256 = (
    "632f6aa09c7e8e559d5efb8631999742e939cfadf972cb50d3fbaf3e75f087d0"
)
_EXPECTED_DERIVATION_CONTENT_SHA256 = (
    "c4f85e1d9f09b99a764c575a1815daec73e21b39c0290a4a8b05777626d11740"
)
_EXPECTED_SEEDS = tuple(range(4016, 4080))
_FORBIDDEN_OLD_EVALUATION_SEEDS = frozenset(range(3008, 3040))
_FORBIDDEN_FORMAL_HOLDOUT_SEEDS = frozenset(range(1000, 1020))
_EXPECTED_FRAME_COUNTS = {"train": 89, "validation": 20, "test": 17}
_EXPECTED_POSITIVE_COUNTS = {"train": 24, "validation": 9, "test": 9}
_EXPECTED_EPISODE_COUNT = 64
_EXPECTED_FRAME_COUNT = 126
_EXPECTED_REGION_COUNT = 8
_EXPECTED_SCALE = "M16N24"


class RegionResourceV6ExternalEvaluationError(RuntimeError):
    """Stable fail-closed error for the v6 external evaluator."""


@dataclass(frozen=True)
class RegionResourceV6ExternalEvaluationConfig:
    """Immutable no-fit contract for the frozen 2026-07-30 evaluation."""

    report_date: str = _EXPECTED_REPORT_DATE
    expected_seeds: tuple[int, ...] = _EXPECTED_SEEDS
    expected_frame_counts: tuple[tuple[str, int], ...] = tuple(
        sorted(_EXPECTED_FRAME_COUNTS.items())
    )
    expected_positive_counts: tuple[tuple[str, int], ...] = tuple(
        sorted(_EXPECTED_POSITIVE_COUNTS.items())
    )
    fixed_minimum_confidence: float = (
        REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE
    )
    model_fit_allowed: bool = False
    checkpoint_update_allowed: bool = False
    threshold_tuning_allowed: bool = False
    confidence_gate_available: bool = False
    candidate_mutation_allowed: bool = False
    input_mutation_allowed: bool = False
    registration_allowed: bool = False
    admission_allowed: bool = False
    formal_holdout_read_allowed: bool = False
    old_external_evaluation_read_allowed: bool = False
    production_permission_available: bool = False
    schema: str = REGION_RESOURCE_V6_EXTERNAL_SCHEMA

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
            "fixed_minimum_confidence": (
                REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE
            ),
            "schema": REGION_RESOURCE_V6_EXTERNAL_SCHEMA,
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                raise ValueError("v6 external evaluation contract changed")
        forbidden = (
            self.model_fit_allowed,
            self.checkpoint_update_allowed,
            self.threshold_tuning_allowed,
            self.confidence_gate_available,
            self.candidate_mutation_allowed,
            self.input_mutation_allowed,
            self.registration_allowed,
            self.admission_allowed,
            self.formal_holdout_read_allowed,
            self.old_external_evaluation_read_allowed,
            self.production_permission_available,
        )
        if any(type(value) is not bool or value for value in forbidden):
            raise ValueError("v6 external evaluation must remain read-only")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_region_resource_v6_external_dataset(
    v6_candidate_root: str | Path,
    labeled_dataset_root: str | Path,
    external_evidence_path: str | Path,
    derivation_manifest_path: str | Path,
    export_summary_path: str | Path,
    frozen_v4_candidate_root: str | Path,
    output_root: str | Path,
    *,
    config: RegionResourceV6ExternalEvaluationConfig | None = None,
    replace_output: bool = False,
) -> dict[str, Any]:
    """Evaluate one exact v6 actor without fitting or granting authority."""

    resolved = config or RegionResourceV6ExternalEvaluationConfig()
    candidate = Path(v6_candidate_root).resolve()
    dataset = Path(labeled_dataset_root).resolve()
    evidence = Path(external_evidence_path).resolve()
    derivation = Path(derivation_manifest_path).resolve()
    export_summary = Path(export_summary_path).resolve()
    v4_candidate = Path(frozen_v4_candidate_root).resolve()
    destination = Path(output_root).resolve()
    external_root = dataset.parent
    _validate_paths(
        candidate=candidate,
        dataset=dataset,
        evidence=evidence,
        derivation=derivation,
        export_summary=export_summary,
        v4_candidate=v4_candidate,
        destination=destination,
        replace_output=replace_output,
    )

    candidate_tree_before = _tree_sha256(candidate)
    external_tree_before = _tree_sha256(external_root)
    dataset_tree_before = _tree_sha256(dataset)
    v4_tree_before = _tree_sha256(v4_candidate)
    if candidate_tree_before != _EXPECTED_CANDIDATE_TREE_SHA256:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_candidate_tree_identity_mismatch"
        )
    if (
        external_tree_before != _EXPECTED_EXTERNAL_TREE_SHA256
        or dataset_tree_before != _EXPECTED_DATASET_TREE_SHA256
    ):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_input_tree_identity_mismatch"
        )

    model, candidate_identity = _load_and_verify_candidate(candidate)
    loaded, input_identity = _load_and_verify_external_input(
        dataset,
        evidence,
        derivation,
        export_summary,
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
        != candidate_identity["training_dataset_sha256"]
        or v4_loaded.manifest.split.split_sha256
        != candidate_identity["training_split_sha256"]
    ):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_frozen_v4_training_identity_mismatch"
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
    external_tree_after = _tree_sha256(external_root)
    dataset_tree_after = _tree_sha256(dataset)
    v4_tree_after = _tree_sha256(v4_candidate)
    _assert_tree_unchanged(
        "candidate", candidate_tree_before, candidate_tree_after
    )
    _assert_tree_unchanged(
        "external_input", external_tree_before, external_tree_after
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
            "schema": REGION_RESOURCE_V6_EXTERNAL_INTEGRITY_SCHEMA,
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
            "external_input": {
                **input_identity,
                "root": str(external_root),
                "tree_sha256_before": external_tree_before,
                "tree_sha256_after": external_tree_after,
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
            "confidence_gate_application_count": 0,
            "old_external_evaluation_payload_read_count": 0,
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
            "schema": REGION_RESOURCE_V6_EXTERNAL_SCHEMA,
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
                "v6_confidence_head_uncalibrated_and_not_used",
                "candidate_unregistered_and_admission_closed",
                "formal_holdout_not_read",
                "old_3008_3039_evaluation_not_read",
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
            temporary / REGION_RESOURCE_V6_EXTERNAL_RECORDS_FILENAME,
            records,
        )
        _write_csv(
            temporary / REGION_RESOURCE_V6_EXTERNAL_CSV_FILENAME,
            records,
        )
        _write_json(
            temporary / REGION_RESOURCE_V6_EXTERNAL_INTEGRITY_FILENAME,
            integrity,
        )
        _write_json(
            temporary / REGION_RESOURCE_V6_EXTERNAL_OVERLAP_FILENAME,
            overlap_payload,
        )
        summary["evaluation_records_jsonl_sha256"] = _sha256_file(
            temporary / REGION_RESOURCE_V6_EXTERNAL_RECORDS_FILENAME
        )
        summary["evaluation_records_csv_sha256"] = _sha256_file(
            temporary / REGION_RESOURCE_V6_EXTERNAL_CSV_FILENAME
        )
        summary = _resign(summary)
        _write_json(
            temporary / REGION_RESOURCE_V6_EXTERNAL_SUMMARY_FILENAME,
            summary,
        )
        (
            temporary / REGION_RESOURCE_V6_EXTERNAL_REPORT_FILENAME
        ).write_text(
            _render_report(summary, integrity, overlap_payload),
            encoding="utf-8",
        )
        artifact_names = (
            REGION_RESOURCE_V6_EXTERNAL_RECORDS_FILENAME,
            REGION_RESOURCE_V6_EXTERNAL_CSV_FILENAME,
            REGION_RESOURCE_V6_EXTERNAL_INTEGRITY_FILENAME,
            REGION_RESOURCE_V6_EXTERNAL_OVERLAP_FILENAME,
            REGION_RESOURCE_V6_EXTERNAL_SUMMARY_FILENAME,
            REGION_RESOURCE_V6_EXTERNAL_REPORT_FILENAME,
        )
        artifact_manifest = _with_content_sha256(
            {
                "schema": REGION_RESOURCE_V6_EXTERNAL_ARTIFACT_SCHEMA,
                "report_date": resolved.report_date,
                "artifact_files": {
                    name: _sha256_file(temporary / name)
                    for name in artifact_names
                },
                "candidate_mutation_count": 0,
                "input_mutation_count": 0,
                "model_fit_count": 0,
                "confidence_gate_application_count": 0,
                "formal_holdout_payload_read_count": 0,
                "production_permission_available": False,
            }
        )
        _write_json(
            temporary / REGION_RESOURCE_V6_EXTERNAL_ARTIFACT_FILENAME,
            artifact_manifest,
        )
        if destination.exists():
            shutil.rmtree(destination)
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    reviewed = review_region_resource_v6_external_evaluation(destination)
    return {
        "output_root": str(destination),
        "artifact_manifest": reviewed["artifact_manifest"],
        "summary": reviewed["summary"],
    }


def review_region_resource_v6_external_evaluation(
    output_root: str | Path,
) -> dict[str, Any]:
    """Verify persisted v6 external-evaluation artifacts."""

    root = Path(output_root).resolve()
    if root.is_symlink() or not root.is_dir():
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_output_root_invalid"
        )
    artifact_manifest = _read_json(
        root / REGION_RESOURCE_V6_EXTERNAL_ARTIFACT_FILENAME
    )
    _verify_content_sha256(artifact_manifest, "artifact_manifest")
    if (
        artifact_manifest.get("schema")
        != REGION_RESOURCE_V6_EXTERNAL_ARTIFACT_SCHEMA
        or artifact_manifest.get("candidate_mutation_count") != 0
        or artifact_manifest.get("input_mutation_count") != 0
        or artifact_manifest.get("model_fit_count") != 0
        or artifact_manifest.get("confidence_gate_application_count") != 0
        or artifact_manifest.get("formal_holdout_payload_read_count") != 0
        or artifact_manifest.get("production_permission_available") is not False
    ):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_artifact_boundary_invalid"
        )
    files = artifact_manifest.get("artifact_files")
    if not isinstance(files, Mapping):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_artifact_inventory_invalid"
        )
    expected = {
        REGION_RESOURCE_V6_EXTERNAL_RECORDS_FILENAME,
        REGION_RESOURCE_V6_EXTERNAL_CSV_FILENAME,
        REGION_RESOURCE_V6_EXTERNAL_INTEGRITY_FILENAME,
        REGION_RESOURCE_V6_EXTERNAL_OVERLAP_FILENAME,
        REGION_RESOURCE_V6_EXTERNAL_SUMMARY_FILENAME,
        REGION_RESOURCE_V6_EXTERNAL_REPORT_FILENAME,
    }
    actual = {
        path.name
        for path in root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if set(files) != expected or actual != expected | {
        REGION_RESOURCE_V6_EXTERNAL_ARTIFACT_FILENAME
    }:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_output_file_inventory_mismatch"
        )
    for name, digest in files.items():
        if _sha256_file(root / name) != digest:
            raise RegionResourceV6ExternalEvaluationError(
                f"v6_external_artifact_sha256_mismatch:{name}"
            )
    integrity = _read_json(
        root / REGION_RESOURCE_V6_EXTERNAL_INTEGRITY_FILENAME
    )
    overlap = _read_json(
        root / REGION_RESOURCE_V6_EXTERNAL_OVERLAP_FILENAME
    )
    summary = _read_json(
        root / REGION_RESOURCE_V6_EXTERNAL_SUMMARY_FILENAME
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
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_summary_boundary_invalid"
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
        "dataset": dataset,
        "v4_candidate": v4_candidate,
    }
    for name, path in directories.items():
        if path.is_symlink() or not path.is_dir():
            raise RegionResourceV6ExternalEvaluationError(
                f"v6_external_{name}_root_invalid"
            )
    files = {
        "external_evidence": evidence,
        "derivation_manifest": derivation,
        "export_summary": export_summary,
    }
    for name, path in files.items():
        if path.is_symlink() or not path.is_file():
            raise RegionResourceV6ExternalEvaluationError(
                f"v6_external_{name}_invalid"
            )
    external_root = dataset.parent
    if (
        external_root.name != _EXPECTED_EXTERNAL_ROOT_NAME
        or evidence != external_root / "external_dataset_evidence.json"
        or derivation != external_root / "source_derivation_manifest.json"
        or export_summary != external_root / "export_summary.json"
    ):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_input_path_identity_mismatch"
        )
    protected = {
        "candidate": candidate,
        "external_input": external_root,
        "v4_candidate": v4_candidate,
    }
    for name, root in protected.items():
        if destination == root or root in destination.parents:
            raise RegionResourceV6ExternalEvaluationError(
                f"v6_external_output_within_protected_input:{name}"
            )
    if destination.is_symlink():
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_output_symlink_forbidden"
        )
    if destination.exists() and not replace_output:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_output_already_exists"
        )
    if "model_registry" in destination.parts:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_registry_output_forbidden"
        )


def _load_and_verify_candidate(
    root: Path,
) -> tuple[Any, dict[str, Any]]:
    if root.name != REGION_RESOURCE_V6_CANDIDATE_ID:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_candidate_directory_identity_mismatch"
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
        REGION_RESOURCE_V6_CANDIDATE_FILENAME,
    }
    if set(inventory) != expected_inventory:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_candidate_file_inventory_mismatch"
        )
    manifest = _read_json(root / REGION_RESOURCE_V6_CANDIDATE_FILENAME)
    _verify_content_sha256(manifest, "candidate_manifest")
    _verify_candidate_manifest_identity(manifest)
    artifact_files = manifest.get("artifact_files")
    if not isinstance(artifact_files, Mapping):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_candidate_artifact_inventory_invalid"
        )
    if set(artifact_files) != expected_inventory - {
        REGION_RESOURCE_V6_CANDIDATE_FILENAME
    }:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_candidate_artifact_inventory_mismatch"
        )
    for name, digest in artifact_files.items():
        if inventory[name] != digest:
            raise RegionResourceV6ExternalEvaluationError(
                f"v6_external_candidate_artifact_sha256_mismatch:{name}"
            )

    audit = _read_json(root / REGION_RESOURCE_V6_AUDIT_FILENAME)
    _verify_content_sha256(audit, "training_audit")
    if audit.get("content_sha256") != _EXPECTED_TRAINING_AUDIT_CONTENT_SHA256:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_training_audit_identity_mismatch"
        )
    state_path = root / "bundle/state_dict.pt"
    if (
        not state_path.read_bytes().startswith(REGION_RESOURCE_V6_STATE_MAGIC)
        or _sha256_file(state_path) != _EXPECTED_STATE_FILE_SHA256
    ):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_state_file_identity_mismatch"
        )
    model, bundle_manifest = _load_v6_model_bundle(
        root / "bundle",
        expected_model_version=REGION_RESOURCE_V6_MODEL_VERSION,
        expected_state_file_sha256=_EXPECTED_STATE_FILE_SHA256,
    )
    if (
        bundle_manifest.get("model_state_content_sha256")
        != _EXPECTED_MODEL_STATE_CONTENT_SHA256
        or _model_state_content_sha256(model)
        != _EXPECTED_MODEL_STATE_CONTENT_SHA256
        or bundle_manifest.get("runtime_confidence_gate_available") is not False
        or bundle_manifest.get("runtime_loader_registered") is not False
    ):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_model_content_identity_mismatch"
        )
    return model, {
        "candidate_id": REGION_RESOURCE_V6_CANDIDATE_ID,
        "model_version": REGION_RESOURCE_V6_MODEL_VERSION,
        "manifest_content_sha256": manifest["content_sha256"],
        "manifest_file_sha256": inventory[
            REGION_RESOURCE_V6_CANDIDATE_FILENAME
        ],
        "training_audit_content_sha256": audit["content_sha256"],
        "training_audit_file_sha256": inventory[
            REGION_RESOURCE_V6_AUDIT_FILENAME
        ],
        "model_state_content_sha256": _model_state_content_sha256(model),
        "state_file_sha256": inventory["bundle/state_dict.pt"],
        "training_dataset_sha256": manifest["dataset_sha256"],
        "training_split_sha256": manifest["dataset_split_sha256"],
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
        or manifest.get("candidate_id") != REGION_RESOURCE_V6_CANDIDATE_ID
        or manifest.get("model_version") != REGION_RESOURCE_V6_MODEL_VERSION
        or manifest.get("training_audit_content_sha256")
        != _EXPECTED_TRAINING_AUDIT_CONTENT_SHA256
        or manifest.get("model_state_content_sha256")
        != _EXPECTED_MODEL_STATE_CONTENT_SHA256
        or manifest.get("bundle_state_file_sha256")
        != _EXPECTED_STATE_FILE_SHA256
        or manifest.get("fixed_minimum_confidence")
        != REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE
        or manifest.get("candidate_status")
        != "unregistered_edge_transfer_development"
        or manifest.get("confidence_calibration_status")
        != "not_started_actor_must_freeze_first"
        or manifest.get("development_only") is not True
        or manifest.get("shadow_only") is not True
        or manifest.get("admission_closed") is not True
        or manifest.get("rule_fallback_required") is not True
        or manifest.get("formal_holdout_evaluated") is not False
        or manifest.get("runtime_preflight_completed") is not False
        or not permission_values
        or any(type(value) is not bool or value for value in permission_values.values())
    ):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_candidate_manifest_identity_mismatch"
        )


def _load_and_verify_external_input(
    dataset_root: Path,
    evidence_path: Path,
    derivation_path: Path,
    export_summary_path: Path,
    *,
    config: RegionResourceV6ExternalEvaluationConfig,
) -> tuple[LoadedRegionLearningDataset, dict[str, Any]]:
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
    ):
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_lineage_content_identity_mismatch"
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
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_dataset_identity_mismatch"
        )
    _validate_seed_isolation(seeds)
    for episode in loaded.episode_records:
        source = episode.source
        if (
            source.git_commit != _EXPECTED_SOURCE_COMMIT
            or source.git_dirty
            or source.scenario_scale != _EXPECTED_SCALE
        ):
            raise RegionResourceV6ExternalEvaluationError(
                "v6_external_source_episode_identity_mismatch"
            )
        for frame in episode.frames:
            if len(frame.snapshot.regions) != _EXPECTED_REGION_COUNT:
                raise RegionResourceV6ExternalEvaluationError(
                    "v6_external_region_count_mismatch"
                )

    source_artifact_sha256 = _sha256_file(derivation_path)
    if (
        export_summary.get("dataset_sha256") != _EXPECTED_DATASET_SHA256
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
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_lineage_identity_mismatch"
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
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_observable_label_contract_mismatch"
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
        "source_clean_commit": _EXPECTED_SOURCE_COMMIT,
        "exporter_clean_commit": _EXPECTED_EXPORTER_COMMIT,
        "seeds": list(seeds),
        "split_frame_counts": split_frame_counts,
        "external_dataset_used_for_v6_actor_training": False,
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
    actor = LearnedRegionResourcePolicy(
        model,
        _PolicyIdentity(
            REGION_RESOURCE_V6_MODEL_VERSION,
            _EXPECTED_STATE_FILE_SHA256,
        ),
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
                r0 = rule_policy.recommend(frame.snapshot)
                raw = actor.recommend_raw(frame.snapshot)
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
                        raise RegionResourceV6ExternalEvaluationError(
                            "v6_external_unsafe_positive_target:"
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
                transfer_errors = _classify_transfer_errors(
                    _transfer_map(target_payload),
                    _transfer_map(actor_payload),
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
                )
                negative_exact_r0 = bool(
                    not rule_positive
                    and actor_signature == r0_signature
                    and not rejection_reasons
                )
                actor_derived_positive = bool(
                    actor_executable
                    and actor_valid
                    and not rejection_reasons
                )
                failure_reasons: list[str] = []
                if rejection_reasons:
                    failure_reasons.append("projection_rejected")
                if actor_executable and not actor_valid:
                    failure_reasons.append("invariant_failure")
                if rule_positive and not exact_positive:
                    failure_reasons.append("positive_exact_action_missed")
                if not rule_positive and not negative_exact_r0:
                    failure_reasons.append("negative_r0_missed")
                if transfer_errors["wrong_direction_count"]:
                    failure_reasons.append("wrong_direction")
                if transfer_errors["wrong_quantity_count"]:
                    failure_reasons.append("wrong_quantity")
                if (
                    not rule_positive
                    and projected_transfer_count > 0
                ):
                    failure_reasons.append("false_transfer")
                records.append(
                    {
                        "schema": REGION_RESOURCE_V6_EXTERNAL_RECORD_SCHEMA,
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
                        "actor_raw_transfer_count": raw_transfer_count,
                        "actor_raw_transfer_resource_count": sum(
                            item.resource_count for item in raw.transfers
                        ),
                        "actor_projected_transfer_count": (
                            projected_transfer_count
                        ),
                        "actor_projected_transfer_resource_count": sum(
                            item.resource_count
                            for item in projected.transfers
                        ),
                        "correct_directed_edge_count": transfer_errors[
                            "correct_directed_edge_count"
                        ],
                        "correct_directed_edge_frame": bool(
                            rule_positive
                            and transfer_errors[
                                "correct_directed_edge_count"
                            ]
                            == len(target.transfers)
                            and len(target.transfers) > 0
                        ),
                        "projected_exact_positive_action": exact_positive,
                        "negative_exact_r0": negative_exact_r0,
                        "wrong_direction_count": transfer_errors[
                            "wrong_direction_count"
                        ],
                        "wrong_quantity_count": transfer_errors[
                            "wrong_quantity_count"
                        ],
                        "wrong_edge_count": transfer_errors[
                            "wrong_edge_count"
                        ],
                        "false_transfer_count": (
                            projected_transfer_count
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
        "schema": REGION_RESOURCE_V6_EXTERNAL_RECORD_SCHEMA,
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
        "actor_raw_transfer_count": None,
        "actor_raw_transfer_resource_count": None,
        "actor_projected_transfer_count": None,
        "actor_projected_transfer_resource_count": None,
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
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_action_inventory_mismatch"
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
        "schema": REGION_RESOURCE_V6_EXTERNAL_OVERLAP_SCHEMA,
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
        "source_independent_exact_observable_keys": len(intersection) == 0,
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
        "v6_actor_training_use_count_by_external_split": {
            split.value: 0 for split in RegionLearningSplit
        },
        "v6_checkpoint_selection_use_count_by_external_split": {
            split.value: 0 for split in RegionLearningSplit
        },
        "v6_threshold_tuning_use_count_by_external_split": {
            split.value: 0 for split in RegionLearningSplit
        },
        "test_payload_use": "read_only_external_evaluation",
        "model_fit_count": 0,
        "checkpoint_update_count": 0,
        "threshold_tuning_count": 0,
        "confidence_gate_application_count": 0,
        "old_external_evaluation_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "truth_identifier_use_count": 0,
        "production_permission_available": False,
    }


def _closed_candidate_status() -> dict[str, Any]:
    permissions = {
        "assist": False,
        "assignment": False,
        "degradation": False,
        "takeover": False,
        "coalition": False,
        "control": False,
        "physical": False,
        "d3": False,
        "d7": False,
    }
    return {
        "registered": False,
        "unregistered": True,
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
        "confidence_calibration_available": False,
        "confidence_gate_available": False,
        "uncalibrated_confidence_head_used_for_gate": False,
        "fixed_minimum_confidence_unchanged": (
            REGION_RESOURCE_V6_FIXED_MINIMUM_CONFIDENCE
        ),
        "permissions": permissions,
    }


def _conclusion(
    metrics_by_split: Mapping[str, Mapping[str, Any]],
    overlap: Mapping[str, Any],
) -> dict[str, Any]:
    test = metrics_by_split["test"]
    return {
        "source_independent_observable_keys": bool(
            overlap["source_independent_exact_observable_keys"]
        ),
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
        "generalization_admission_supported": False,
        "required_runtime_action": "deterministic_rule_fallback",
        "next_gate": (
            "freeze_actor_then_build_separate_train_only_confidence_"
            "calibrator_and_run_new_unseen_development_blind_review"
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
            "| {split} | {sample} | {positive} | {negative} | {raw} | "
            "{edge} | {exact} | {r0} | {direction} | {quantity} | "
            "{false_transfer} | {rejection} | {invariant} | {derived} |".format(
                split=split,
                sample=item["sample_count"],
                positive=item["rule_positive_count"],
                negative=item["rule_negative_count"],
                raw=item["actor_raw_transfer_count"],
                edge=item["correct_directed_edge_count"],
                exact=item["projected_exact_positive_action_count"],
                r0=item["negative_exact_r0_count"],
                direction=item["wrong_direction_count"],
                quantity=item["wrong_quantity_count"],
                false_transfer=item["false_transfer_count"],
                rejection=item["projection_rejection_count"],
                invariant=item["invariant_failure_count"],
                derived=item["actor_derived_positive_denominator_count"],
            )
        )
    candidate = integrity["candidate"]
    external = integrity["external_input"]
    test = summary["metrics_by_split"]["test"]
    return "\n".join(
        [
            "# D4 v6 来源独立外部评价",
            "",
            "## 结论",
            "",
            "本次评价只读取冻结的 v6 actor 和 M16N24、8 区域外部数据。"
            "评价没有拟合模型、更新检查点、调整阈值或使用置信输出准入。",
            "",
            f"测试划分包含 {test['sample_count']} 帧，其中规则正类 "
            f"{test['rule_positive_count']} 帧、负类 "
            f"{test['rule_negative_count']} 帧。投影后精确正动作命中 "
            f"{test['projected_exact_positive_action_count']} 帧，负类精确保持 "
            f"R0 {test['negative_exact_r0_count']} 帧。该结果只构成开发评价证据，"
            "不构成准入结论。",
            "",
            "## 分划分结果",
            "",
            "| 划分 | 样本 | 规则正类 | 规则负类 | actor 原始转移 | "
            "正确有向边 | 精确正动作 | 负类精确 R0 | 错误方向 | "
            "错误数量 | 虚假转移 | 投影拒绝 | 约束失败 | actor 正类分母 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
            "---:|---:|---:|---:|",
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
            "边特征、边索引及其形状、类型和值，不包含 seed、episode、目标标签或真值。",
            "",
            "外部数据的 train、validation、test 是本次外部数据自身的划分名称。"
            "三类数据均未参与 v6 actor 训练、检查点选择或阈值拟合；test 仅用于本次"
            "只读评价。",
            "",
            "## 完整性",
            "",
            f"- 候选 manifest 内容哈希：`{candidate['manifest_content_sha256']}`",
            f"- 训练审计内容哈希：`{candidate['training_audit_content_sha256']}`",
            f"- 模型参数内容哈希：`{candidate['model_state_content_sha256']}`",
            f"- 状态文件哈希：`{candidate['state_file_sha256']}`",
            f"- 外部数据集哈希：`{external['dataset_sha256']}`",
            f"- 外部划分哈希：`{external['dataset_split_sha256']}`",
            "- 候选树前后突变：0",
            "- 外部输入树前后突变：0",
            "- 冻结 v4 训练来源树前后突变：0",
            "",
            "## 权限",
            "",
            "v6 保持未注册、仅开发影子运行、准入关闭和规则回退。assist、assignment、"
            "degradation、takeover、coalition、control、physical、D3、D7 权限均为"
            " false。固定 0.60 门没有降低，但当前不存在置信校准器，因此该门没有"
            "执行。",
            "",
            "## 下一门",
            "",
            "下一门是冻结 actor 后单独构建只使用训练划分拟合的置信校准器，再由 D6 "
            "使用新的未见开发数据盲审。旧评价 seed 3008-3039 和正式 holdout "
            "seed 1000-1019 本次均未读取。",
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
    if values & _FORBIDDEN_OLD_EVALUATION_SEEDS:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_old_evaluation_seed_read_forbidden"
        )
    if values & _FORBIDDEN_FORMAL_HOLDOUT_SEEDS:
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_formal_holdout_seed_read_forbidden"
        )


def _assert_tree_unchanged(name: str, before: str, after: str) -> None:
    if before != after:
        raise RegionResourceV6ExternalEvaluationError(
            f"v6_external_{name}_mutation_detected"
        )


def _verify_content_sha256(
    value: Mapping[str, Any],
    name: str,
) -> None:
    expected = value.get("content_sha256")
    payload = dict(value)
    payload.pop("content_sha256", None)
    if not isinstance(expected, str) or expected != _canonical_sha256(payload):
        raise RegionResourceV6ExternalEvaluationError(
            f"v6_external_{name}_content_sha256_mismatch"
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
        raise RegionResourceV6ExternalEvaluationError(
            f"v6_external_json_read_failed:{path.name}:{type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise RegionResourceV6ExternalEvaluationError(
            f"v6_external_json_object_required:{path.name}"
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
        raise RegionResourceV6ExternalEvaluationError(
            "v6_external_csv_records_unavailable"
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
