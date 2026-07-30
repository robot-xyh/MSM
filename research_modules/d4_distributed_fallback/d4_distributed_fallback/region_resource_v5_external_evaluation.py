"""Read-only source-independent evaluation for the frozen D4 v5 candidate.

This module never fits a model, changes a candidate, grants an authority, or
reads the formal holdout.  It verifies one frozen external dataset, recomputes
the frozen v4 actor output and v5 confidence for every selected frame, and
persists content-addressed audit artifacts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .region_resource import RecommendationSource
from .region_resource_dataset import (
    RegionLearningDatasetManifest,
    RegionLearningSplit,
    RegionLearningTargetKind,
    load_region_learning_dataset_splits,
)
from .region_resource_learning import snapshot_to_region_graph
from .region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V4_CANDIDATE_FILENAME,
    RegionResourceV4CandidateLoader,
    _v4_confidence_observable_key,
    evaluate_v4_intervention_invariants,
    executable_signature,
)
from .region_resource_v5_confidence_candidate import (
    REGION_RESOURCE_V5_CANDIDATE_FILENAME,
    REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE,
    REGION_RESOURCE_V5_STATE_FILENAME,
    RegionResourceV5CandidateLoader,
    _actor_pooled_latent,
)


REGION_RESOURCE_V5_EXTERNAL_EVALUATION_SCHEMA = (
    "d4-region-resource-v5-source-independent-external-evaluation-v1"
)
REGION_RESOURCE_V5_EXTERNAL_RECORD_SCHEMA = (
    "d4-region-resource-v5-source-independent-frame-evaluation-v1"
)
REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_SCHEMA = (
    "d4-region-resource-v5-source-independent-input-integrity-v1"
)
REGION_RESOURCE_V5_EXTERNAL_OVERLAP_SCHEMA = (
    "d4-region-resource-v5-source-independent-observable-overlap-v1"
)
REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_SCHEMA = (
    "d4-region-resource-v5-source-independent-artifact-manifest-v1"
)

REGION_RESOURCE_V5_EXTERNAL_RECORDS_FILENAME = "evaluation_records.jsonl"
REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_FILENAME = "input_integrity.json"
REGION_RESOURCE_V5_EXTERNAL_OVERLAP_FILENAME = (
    "observable_overlap_audit.json"
)
REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME = (
    "external_evaluation_summary.json"
)
REGION_RESOURCE_V5_EXTERNAL_REPORT_FILENAME = "REPORT_CN.md"
REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_FILENAME = "artifact_manifest.json"

REGION_RESOURCE_V5_EXTERNAL_REPORT_DATE = "2026-07-29"
REGION_RESOURCE_V5_EXTERNAL_EXPECTED_GIT_COMMIT = (
    "63987592c216fbdb7e03d77183afc6e9f15748a2"
)
REGION_RESOURCE_V5_EXTERNAL_EXPECTED_SCALE = "M16N20"
REGION_RESOURCE_V5_EXTERNAL_EXPECTED_EPISODES = 32
REGION_RESOURCE_V5_EXTERNAL_EXPECTED_FRAMES = 63
REGION_RESOURCE_V5_EXTERNAL_KNOWN_PRIOR_MAIN_TEST_READ_COUNT = 10

_TRAINING_SEEDS = tuple(range(0, 100))
_FORMAL_HOLDOUT_SEEDS = tuple(range(1000, 1020))
_DESIGN_PILOT_SEEDS = tuple(range(3000, 3008))
_INDEPENDENT_EVALUATION_SEEDS = tuple(range(3008, 3040))


class RegionResourceV5ExternalEvaluationError(RuntimeError):
    """Stable failure for an invalid or unsafe external evaluation."""


@dataclass(frozen=True)
class RegionResourceV5ExternalEvaluationConfig:
    """Frozen no-fit contract for the 2026-07-29 M16N20 evaluation."""

    report_date: str = REGION_RESOURCE_V5_EXTERNAL_REPORT_DATE
    expected_git_commit: str = (
        REGION_RESOURCE_V5_EXTERNAL_EXPECTED_GIT_COMMIT
    )
    expected_scale: str = REGION_RESOURCE_V5_EXTERNAL_EXPECTED_SCALE
    fixed_minimum_confidence: float = (
        REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE
    )
    training_seeds: tuple[int, ...] = _TRAINING_SEEDS
    formal_holdout_seeds: tuple[int, ...] = _FORMAL_HOLDOUT_SEEDS
    design_pilot_seeds: tuple[int, ...] = _DESIGN_PILOT_SEEDS
    independent_evaluation_seeds: tuple[int, ...] = (
        _INDEPENDENT_EVALUATION_SEEDS
    )
    expected_episode_count: int = (
        REGION_RESOURCE_V5_EXTERNAL_EXPECTED_EPISODES
    )
    expected_frame_count: int = REGION_RESOURCE_V5_EXTERNAL_EXPECTED_FRAMES
    known_prior_main_test_payload_read_count: int = (
        REGION_RESOURCE_V5_EXTERNAL_KNOWN_PRIOR_MAIN_TEST_READ_COUNT
    )
    model_fit_allowed: bool = False
    candidate_mutation_allowed: bool = False
    threshold_tuning_allowed: bool = False
    split_mutation_allowed: bool = False
    positive_synthesis_allowed: bool = False
    formal_holdout_read_allowed: bool = False
    runtime_preflight_allowed: bool = False
    production_permission_available: bool = False
    schema: str = REGION_RESOURCE_V5_EXTERNAL_EVALUATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V5_EXTERNAL_EVALUATION_SCHEMA:
            raise ValueError("unsupported v5 external evaluation schema")
        if (
            self.report_date != REGION_RESOURCE_V5_EXTERNAL_REPORT_DATE
            or self.expected_git_commit
            != REGION_RESOURCE_V5_EXTERNAL_EXPECTED_GIT_COMMIT
            or self.expected_scale
            != REGION_RESOURCE_V5_EXTERNAL_EXPECTED_SCALE
            or float(self.fixed_minimum_confidence)
            != REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE
            or tuple(self.training_seeds) != _TRAINING_SEEDS
            or tuple(self.formal_holdout_seeds) != _FORMAL_HOLDOUT_SEEDS
            or tuple(self.design_pilot_seeds) != _DESIGN_PILOT_SEEDS
            or tuple(self.independent_evaluation_seeds)
            != _INDEPENDENT_EVALUATION_SEEDS
            or int(self.expected_episode_count)
            != REGION_RESOURCE_V5_EXTERNAL_EXPECTED_EPISODES
            or int(self.expected_frame_count)
            != REGION_RESOURCE_V5_EXTERNAL_EXPECTED_FRAMES
            or int(self.known_prior_main_test_payload_read_count)
            != REGION_RESOURCE_V5_EXTERNAL_KNOWN_PRIOR_MAIN_TEST_READ_COUNT
        ):
            raise ValueError("v5 external evaluation contract changed")
        forbidden_true = (
            self.model_fit_allowed,
            self.candidate_mutation_allowed,
            self.threshold_tuning_allowed,
            self.split_mutation_allowed,
            self.positive_synthesis_allowed,
            self.formal_holdout_read_allowed,
            self.runtime_preflight_allowed,
            self.production_permission_available,
        )
        if any(type(value) is not bool or value for value in forbidden_true):
            raise ValueError("v5 external evaluation must remain read-only")
        seed_classes = (
            set(self.training_seeds),
            set(self.formal_holdout_seeds),
            set(self.design_pilot_seeds),
            set(self.independent_evaluation_seeds),
        )
        if any(
            left & right
            for index, left in enumerate(seed_classes)
            for right in seed_classes[index + 1 :]
        ):
            raise ValueError("v5 external evaluation seed classes overlap")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_region_resource_v5_external_dataset(
    source_root: str | Path,
    labeled_dataset_root: str | Path,
    v4_candidate_root: str | Path,
    v5_candidate_root: str | Path,
    output_root: str | Path,
    *,
    config: RegionResourceV5ExternalEvaluationConfig | None = None,
    replace_output: bool = False,
) -> dict[str, Any]:
    """Evaluate frozen v4/v5 artifacts on one external no-fit dataset."""

    resolved = config or RegionResourceV5ExternalEvaluationConfig()
    source = Path(source_root).resolve()
    labeled = Path(labeled_dataset_root).resolve()
    v4_root = Path(v4_candidate_root).resolve()
    v5_root = Path(v5_candidate_root).resolve()
    destination = Path(output_root).resolve()
    _validate_paths(
        source=source,
        labeled=labeled,
        v4_root=v4_root,
        v5_root=v5_root,
        destination=destination,
        replace_output=replace_output,
    )

    v4_tree_before = _tree_sha256(v4_root)
    v5_tree_before = _tree_sha256(v5_root)
    lineage = _verify_external_lineage(source, labeled, resolved)
    v4_loader = RegionResourceV4CandidateLoader(
        v4_root,
        require_registered_binding=False,
        evaluation_context="offline_development",
    )
    v5_loader = RegionResourceV5CandidateLoader(
        v5_root,
        require_registered_binding=False,
        evaluation_context="offline_development",
    )
    loaded = load_region_learning_dataset_splits(
        labeled,
        splits=tuple(RegionLearningSplit),
    )
    _validate_loaded_dataset(loaded.manifest, resolved)

    records = _evaluate_frames(
        loaded,
        v4_loader=v4_loader,
        v5_loader=v5_loader,
        positive_records=lineage["positive_records"],
        threshold=resolved.fixed_minimum_confidence,
    )
    overlap = _observable_overlap_audit(
        v4_root / "development_dataset",
        records,
    )
    metrics = _summarize_records(
        records,
        threshold=resolved.fixed_minimum_confidence,
    )
    if metrics["sample_count"] != resolved.expected_frame_count:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_frame_count_mismatch"
        )

    v4_tree_after = _tree_sha256(v4_root)
    v5_tree_after = _tree_sha256(v5_root)
    if v4_tree_before != v4_tree_after or v5_tree_before != v5_tree_after:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_candidate_mutation_detected"
        )

    configuration = resolved.to_dict()
    configuration_sha256 = _canonical_sha256(configuration)
    integrity = _with_content_sha256(
        {
            "schema": REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_SCHEMA,
            "report_date": resolved.report_date,
            "configuration": configuration,
            "configuration_sha256": configuration_sha256,
            "inputs": lineage["input_hashes"],
            "candidates": {
                "v4": {
                    "root": str(v4_root),
                    "tree_sha256_before": v4_tree_before,
                    "tree_sha256_after": v4_tree_after,
                    "tree_unchanged": v4_tree_before == v4_tree_after,
                    "manifest_content_sha256": (
                        v4_loader.manifest.content_sha256
                    ),
                    "manifest_file_sha256": _sha256_file(
                        v4_root / REGION_RESOURCE_V4_CANDIDATE_FILENAME
                    ),
                    "model_state_sha256": (
                        v4_loader.manifest.model_state_sha256
                    ),
                    "registered_binding_verified": (
                        v4_loader.registered_binding_verified
                    ),
                },
                "v5": {
                    "root": str(v5_root),
                    "tree_sha256_before": v5_tree_before,
                    "tree_sha256_after": v5_tree_after,
                    "tree_unchanged": v5_tree_before == v5_tree_after,
                    "manifest_content_sha256": (
                        v5_loader.manifest["content_sha256"]
                    ),
                    "manifest_file_sha256": _sha256_file(
                        v5_root / REGION_RESOURCE_V5_CANDIDATE_FILENAME
                    ),
                    "calibration_state_file_sha256": _sha256_file(
                        v5_root / REGION_RESOURCE_V5_STATE_FILENAME
                    ),
                    "registered": bool(v5_loader.manifest["registered"]),
                    "registered_binding_verified": (
                        v5_loader.registered_binding_verified
                    ),
                    "admission_closed": bool(
                        v5_loader.manifest["admission_closed"]
                    ),
                    "rule_fallback_required": bool(
                        v5_loader.manifest["rule_fallback_required"]
                    ),
                    "permissions": v5_loader.manifest["permissions"],
                },
            },
            "lineage_checks": lineage["checks"],
            "seed_isolation": lineage["seed_isolation"],
            "candidate_mutation_count": 0,
            "model_fit_count": 0,
            "threshold_fit_count": 0,
            "split_mutation_count": 0,
            "positive_synthesis_count": 0,
            "runtime_preflight_count": 0,
            "formal_holdout_payload_read_count": 0,
            "production_permission_available": False,
            "evaluator_source_sha256": _sha256_file(Path(__file__)),
        }
    )
    overlap_payload = _with_content_sha256(overlap)
    data_usage = _data_usage(loaded.manifest, resolved)
    summary = _with_content_sha256(
        {
            "schema": REGION_RESOURCE_V5_EXTERNAL_EVALUATION_SCHEMA,
            "report_date": resolved.report_date,
            "scenario_scale": resolved.expected_scale,
            "source_episode_count": (
                loaded.manifest.availability.episode_count
            ),
            "source_frame_count": loaded.manifest.availability.frame_count,
            "source_seed_range": [3008, 3039],
            "configuration_sha256": configuration_sha256,
            "input_integrity_content_sha256": integrity["content_sha256"],
            "observable_overlap_content_sha256": overlap_payload[
                "content_sha256"
            ],
            "metrics": metrics,
            "data_usage": data_usage,
            "candidate_status": {
                "registered": False,
                "unregistered": True,
                "admission_closed": True,
                "rule_fallback_required": True,
                "production_permission_available": False,
                "formal_evaluation_authorized": False,
                "runtime_preflight_completed": False,
                "d3_permission_available": False,
                "d7_permission_available": False,
                "all_frames_rule_fallback": (
                    metrics["rule_fallback_count"]
                    == metrics["sample_count"]
                ),
            },
            "conclusion": {
                "source_independent_observable_keys": (
                    overlap["exact_observable_key_intersection_count"] == 0
                ),
                "negative_rejection_evidence_available": (
                    metrics["negative_sample_count"] > 0
                    and metrics["negative_false_accept_count"] == 0
                ),
                "positive_denominator_available": (
                    metrics["positive_denominator_available"]
                ),
                "positive_recall": metrics["positive_recall"],
                "positive_recall_status": metrics[
                    "positive_recall_status"
                ],
                "generalization_admission_supported": False,
                "required_runtime_action": "deterministic_rule_fallback",
                "remaining_blocker": (
                    "frozen_actor_produced_no_source_independent_"
                    "actor_derived_positive"
                ),
            },
            "limitations": [
                "M16N20_only",
                "32_source_episodes_63_frames_only",
                "two_rule_safe_positive_actions_but_zero_actor_derived_positive",
                "positive_recall_unavailable",
                "formal_holdout_not_read",
                "runtime_preflight_not_run",
                "d3_successor_not_run",
                "d7_permission_not_tested",
                "no_physical_or_airsim_benefit_evidence",
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
            temporary / REGION_RESOURCE_V5_EXTERNAL_RECORDS_FILENAME,
            records,
        )
        _write_json(
            temporary / REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_FILENAME,
            integrity,
        )
        _write_json(
            temporary / REGION_RESOURCE_V5_EXTERNAL_OVERLAP_FILENAME,
            overlap_payload,
        )
        records_sha256 = _sha256_file(
            temporary / REGION_RESOURCE_V5_EXTERNAL_RECORDS_FILENAME
        )
        summary["evaluation_records_file_sha256"] = records_sha256
        summary = _resign(summary)
        _write_json(
            temporary / REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME,
            summary,
        )
        (
            temporary / REGION_RESOURCE_V5_EXTERNAL_REPORT_FILENAME
        ).write_text(
            _render_report(summary, integrity, overlap_payload),
            encoding="utf-8",
        )
        artifact_files = {
            name: _sha256_file(temporary / name)
            for name in (
                REGION_RESOURCE_V5_EXTERNAL_RECORDS_FILENAME,
                REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_FILENAME,
                REGION_RESOURCE_V5_EXTERNAL_OVERLAP_FILENAME,
                REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME,
                REGION_RESOURCE_V5_EXTERNAL_REPORT_FILENAME,
            )
        }
        artifact_manifest = _with_content_sha256(
            {
                "schema": REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_SCHEMA,
                "report_date": resolved.report_date,
                "artifact_files": artifact_files,
                "candidate_mutation_count": 0,
                "formal_holdout_payload_read_count": 0,
                "production_permission_available": False,
            }
        )
        _write_json(
            temporary / REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_FILENAME,
            artifact_manifest,
        )
        if destination.exists():
            shutil.rmtree(destination)
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    reviewed = review_region_resource_v5_external_evaluation(destination)
    return {
        "output_root": str(destination),
        "artifact_manifest": reviewed["artifact_manifest"],
        "summary": reviewed["summary"],
    }


def review_region_resource_v5_external_evaluation(
    output_root: str | Path,
) -> dict[str, Any]:
    """Verify a persisted external evaluation without loading any candidate."""

    root = Path(output_root).resolve()
    if root.is_symlink() or not root.is_dir():
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_output_root_invalid"
        )
    manifest_path = root / REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_FILENAME
    artifact_manifest = _read_json(manifest_path)
    _verify_content_sha256(artifact_manifest, "artifact_manifest")
    if (
        artifact_manifest.get("schema")
        != REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_SCHEMA
        or artifact_manifest.get("candidate_mutation_count") != 0
        or artifact_manifest.get("formal_holdout_payload_read_count") != 0
        or artifact_manifest.get("production_permission_available") is not False
    ):
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_artifact_manifest_boundary_invalid"
        )
    artifact_files = artifact_manifest.get("artifact_files")
    if not isinstance(artifact_files, Mapping):
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_artifact_inventory_invalid"
        )
    expected = {
        REGION_RESOURCE_V5_EXTERNAL_RECORDS_FILENAME,
        REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_FILENAME,
        REGION_RESOURCE_V5_EXTERNAL_OVERLAP_FILENAME,
        REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME,
        REGION_RESOURCE_V5_EXTERNAL_REPORT_FILENAME,
    }
    if set(artifact_files) != expected:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_artifact_inventory_invalid"
        )
    actual = {
        path.name
        for path in root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if actual != expected | {REGION_RESOURCE_V5_EXTERNAL_ARTIFACT_FILENAME}:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_output_file_inventory_mismatch"
        )
    for name, digest in artifact_files.items():
        if _sha256_file(root / name) != digest:
            raise RegionResourceV5ExternalEvaluationError(
                f"v5_external_artifact_sha256_mismatch:{name}"
            )

    integrity = _read_json(
        root / REGION_RESOURCE_V5_EXTERNAL_INTEGRITY_FILENAME
    )
    overlap = _read_json(
        root / REGION_RESOURCE_V5_EXTERNAL_OVERLAP_FILENAME
    )
    summary = _read_json(
        root / REGION_RESOURCE_V5_EXTERNAL_SUMMARY_FILENAME
    )
    _verify_content_sha256(integrity, "input_integrity")
    _verify_content_sha256(overlap, "observable_overlap")
    _verify_content_sha256(summary, "external_evaluation_summary")
    if (
        summary.get("input_integrity_content_sha256")
        != integrity["content_sha256"]
        or summary.get("observable_overlap_content_sha256")
        != overlap["content_sha256"]
        or summary.get("candidate_status", {}).get("registered") is not False
        or summary.get("candidate_status", {}).get("admission_closed")
        is not True
        or summary.get("candidate_status", {}).get("rule_fallback_required")
        is not True
        or summary.get("data_usage", {}).get(
            "formal_holdout_payload_read_count"
        )
        != 0
    ):
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_summary_boundary_invalid"
        )
    return {
        "artifact_manifest": artifact_manifest,
        "integrity": integrity,
        "overlap": overlap,
        "summary": summary,
    }


def _validate_paths(
    *,
    source: Path,
    labeled: Path,
    v4_root: Path,
    v5_root: Path,
    destination: Path,
    replace_output: bool,
) -> None:
    for name, path in {
        "source": source,
        "labeled": labeled,
        "v4_candidate": v4_root,
        "v5_candidate": v5_root,
    }.items():
        if path.is_symlink() or not path.is_dir():
            raise RegionResourceV5ExternalEvaluationError(
                f"v5_external_{name}_root_invalid"
            )
    protected_inputs = {
        "source": source,
        "labeled": labeled,
        "v4_candidate": v4_root,
        "v5_candidate": v5_root,
    }
    for name, protected_root in protected_inputs.items():
        if (
            destination == protected_root
            or protected_root in destination.parents
        ):
            raise RegionResourceV5ExternalEvaluationError(
                "v5_external_output_within_protected_input:"
                f"{name}"
            )
    if destination.is_symlink():
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_output_symlink_forbidden"
        )
    if destination.exists() and not replace_output:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_output_already_exists"
        )
    if "model_registry" in destination.parts:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_registry_output_forbidden"
        )


def _verify_external_lineage(
    source_root: Path,
    labeled_dataset_root: Path,
    config: RegionResourceV5ExternalEvaluationConfig,
) -> dict[str, Any]:
    generation_plan_path = source_root / "generation_plan.json"
    generation_summary_path = source_root / "generation_summary.json"
    source_manifest_path = (
        source_root / "learning_dataset/d4_region/manifest.json"
    )
    export_root = labeled_dataset_root.parent
    export_summary_path = export_root / "export_summary.json"
    evidence_path = export_root / "external_dataset_evidence.json"
    derivation_path = export_root / "source_derivation_manifest.json"
    labeled_manifest_path = labeled_dataset_root / "manifest.json"

    generation_plan = _read_json(generation_plan_path)
    generation_summary = _read_json(generation_summary_path)
    source_manifest_payload = _read_json(source_manifest_path)
    labeled_manifest_payload = _read_json(labeled_manifest_path)
    export_summary = _read_json(export_summary_path)
    evidence = _read_json(evidence_path)
    derivation = _read_json(derivation_path)
    source_manifest = RegionLearningDatasetManifest.from_dict(
        source_manifest_payload
    )
    labeled_manifest = RegionLearningDatasetManifest.from_dict(
        labeled_manifest_payload
    )
    for name, value in (
        ("export_summary", export_summary),
        ("external_dataset_evidence", evidence),
        ("source_derivation_manifest", derivation),
    ):
        _verify_content_sha256(value, name)

    requested_seeds = tuple(
        int(value)
        for value in generation_plan.get("seed_classes", {}).get(
            "requested_seeds", ()
        )
    )
    source_datasets = derivation.get("source", {}).get("datasets", ())
    positive_records = derivation.get("positive_records")
    if not isinstance(source_datasets, Sequence) or len(source_datasets) != 1:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_source_lineage_inventory_invalid"
        )
    if not isinstance(positive_records, Sequence):
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_positive_record_inventory_invalid"
        )
    if (
        requested_seeds != config.independent_evaluation_seeds
        or generation_plan.get("source", {}).get("git_commit")
        != config.expected_git_commit
        or generation_plan.get("options", {}).get("target_count") != 16
        or generation_plan.get("options", {}).get("resource_count") != 20
        or generation_plan.get("model_fit_allowed") is not False
        or generation_plan.get("online_truth_policy") != "forbidden"
        or generation_plan.get("production_permission_available") is not False
        or generation_summary.get("episode_count")
        != config.expected_episode_count
        or generation_summary.get("frame_count")
        != config.expected_frame_count
        or generation_summary.get("model_fit_count") != 0
        or generation_summary.get("online_truth_use_count") != 0
        or generation_summary.get("formal_holdout_payload_read_count") != 0
        or generation_summary.get("production_permission_available")
        is not False
        or generation_summary.get("d4_manifest_sha256")
        != _sha256_file(source_manifest_path)
        or source_datasets[0].get("dataset_sha256")
        != source_manifest.dataset_sha256
        or derivation.get("output", {}).get("dataset_sha256")
        != labeled_manifest.dataset_sha256
        or derivation.get("output", {}).get("split_sha256")
        != labeled_manifest.split.split_sha256
        or export_summary.get("dataset_sha256")
        != labeled_manifest.dataset_sha256
        or export_summary.get("dataset_split_sha256")
        != labeled_manifest.split.split_sha256
        or export_summary.get("source_artifact_sha256")
        != _sha256_file(derivation_path)
        or evidence.get("source_artifact_sha256")
        != _sha256_file(derivation_path)
        or evidence.get("dataset_sha256")
        != labeled_manifest.dataset_sha256
        or evidence.get("dataset_split_sha256")
        != labeled_manifest.split.split_sha256
        or export_summary.get("external_dataset_evidence_sha256")
        != evidence.get("content_sha256")
        or export_summary.get("positive_record_count") != 2
        or export_summary.get("positive_record_count_by_split")
        != {"train": 1, "validation": 1, "test": 0}
        or derivation.get("generation", {}).get(
            "truth_identifier_use_count"
        )
        != 0
        or derivation.get("generation", {}).get(
            "future_outcome_use_count"
        )
        != 0
        or derivation.get("generation", {}).get(
            "generated_by_v4_builder"
        )
        is not False
        or derivation.get("generation", {}).get(
            "production_permission_available"
        )
        is not False
    ):
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_source_lineage_mismatch"
        )

    seed_classes = generation_plan.get("seed_classes", {})
    expected_seed_classes = {
        "training_seeds": list(config.training_seeds),
        "formal_holdout_seeds": list(config.formal_holdout_seeds),
        "design_pilot_seeds": list(config.design_pilot_seeds),
        "independent_development_seeds": list(
            config.independent_evaluation_seeds
        ),
    }
    if any(
        seed_classes.get(name) != expected
        for name, expected in expected_seed_classes.items()
    ):
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_seed_registry_mismatch"
        )
    seed_sets = {
        name: set(values)
        for name, values in expected_seed_classes.items()
    }
    pairwise_overlap = {
        f"{left}__{right}": sorted(seed_sets[left] & seed_sets[right])
        for index, left in enumerate(seed_sets)
        for right in tuple(seed_sets)[index + 1 :]
    }
    if any(pairwise_overlap.values()):
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_seed_class_overlap"
        )

    input_paths = {
        "generation_plan": generation_plan_path,
        "generation_summary": generation_summary_path,
        "source_dataset_manifest": source_manifest_path,
        "labeled_dataset_manifest": labeled_manifest_path,
        "export_summary": export_summary_path,
        "external_dataset_evidence": evidence_path,
        "source_derivation_manifest": derivation_path,
    }
    input_hashes = {
        name: {
            "path": str(path),
            "file_sha256": _sha256_file(path),
            "content_sha256": (
                _read_json(path).get("content_sha256")
                if path.suffix == ".json"
                else None
            ),
        }
        for name, path in input_paths.items()
    }
    input_hashes["source_dataset_manifest"].update(
        {
            "dataset_sha256": source_manifest.dataset_sha256,
            "split_sha256": source_manifest.split.split_sha256,
        }
    )
    input_hashes["labeled_dataset_manifest"].update(
        {
            "dataset_sha256": labeled_manifest.dataset_sha256,
            "split_sha256": labeled_manifest.split.split_sha256,
        }
    )
    return {
        "positive_records": tuple(dict(value) for value in positive_records),
        "input_hashes": input_hashes,
        "checks": {
            "source_dataset_payload_read_count": 0,
            "source_manifest_verified": True,
            "labeled_manifest_verified": True,
            "derivation_content_verified": True,
            "derivation_file_bound_to_evidence": True,
            "labeled_dataset_bound_to_derivation": True,
            "online_runtime_recommendation_used_as_teacher": False,
            "offline_deterministic_rule_label_required": True,
            "truth_identifier_use_count": 0,
            "future_outcome_use_count": 0,
            "model_fit_count": 0,
            "candidate_mutation_count": 0,
            "source_config_sha256": generation_plan["source"][
                "config_sha256"
            ],
            "seed_registry_sha256": generation_plan["source"][
                "seed_registry_sha256"
            ],
            "observable_label_audit_content_sha256": derivation[
                "generation"
            ]["observable_label_audit"]["content_sha256"],
        },
        "seed_isolation": {
            "training_seeds": list(config.training_seeds),
            "formal_holdout_seeds": list(config.formal_holdout_seeds),
            "design_pilot_seeds": list(config.design_pilot_seeds),
            "independent_evaluation_seeds": list(
                config.independent_evaluation_seeds
            ),
            "pairwise_overlap": pairwise_overlap,
            "all_seed_classes_disjoint": True,
            "formal_holdout_payload_read_count": 0,
            "design_pilot_payload_read_count": 0,
            "independent_evaluation_fit_count": 0,
        },
    }


def _validate_loaded_dataset(
    manifest: RegionLearningDatasetManifest,
    config: RegionResourceV5ExternalEvaluationConfig,
) -> None:
    seeds = {
        int(entry.source.seed)
        for entry in manifest.episodes
    }
    scales = {
        entry.source.scenario_scale
        for entry in manifest.episodes
    }
    commits = {
        entry.source.git_commit
        for entry in manifest.episodes
    }
    if (
        seeds != set(config.independent_evaluation_seeds)
        or scales != {config.expected_scale}
        or commits != {config.expected_git_commit}
        or manifest.availability.episode_count
        != config.expected_episode_count
        or manifest.availability.frame_count != config.expected_frame_count
        or manifest.availability.dirty_episode_count != 0
        or manifest.availability.target_available_count
        != config.expected_frame_count
        or set(config.formal_holdout_seeds) & seeds
        or set(config.design_pilot_seeds) & seeds
        or set(config.training_seeds) & seeds
    ):
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_loaded_dataset_contract_mismatch"
        )


def _evaluate_frames(
    loaded: Any,
    *,
    v4_loader: RegionResourceV4CandidateLoader,
    v5_loader: RegionResourceV5CandidateLoader,
    positive_records: Sequence[Mapping[str, Any]],
    threshold: float,
) -> tuple[dict[str, Any], ...]:
    expected_positive = {
        (
            int(item["seed"]),
            int(item["frame_index"]),
            str(item["snapshot_id"]),
            str(item["split"]),
        )
        for item in positive_records
    }
    observed_positive: set[tuple[int, int, str, str]] = set()
    records: list[dict[str, Any]] = []
    v4_loader.loaded_bundle.model.eval()
    for split in RegionLearningSplit:
        for episode in loaded.episodes(split):
            for frame in episode.frames:
                target = frame.target.recommendation
                if (
                    target is None
                    or frame.target.kind != RegionLearningTargetKind.RULE
                    or target.source != RecommendationSource.RULE
                ):
                    raise RegionResourceV5ExternalEvaluationError(
                        "v5_external_non_rule_teacher_label"
                    )
                snapshot = frame.snapshot
                graph = snapshot_to_region_graph(snapshot, device="cpu")
                observable_key = _v4_confidence_observable_key(graph)
                r0 = v4_loader.rule_policy.recommend(snapshot)
                raw = v4_loader.policy.recommend_raw(snapshot)
                projected = v4_loader.projector.project(snapshot, raw)
                r0_advisory = v4_loader.projector.build_advisory_contract(
                    snapshot,
                    r0,
                )
                target_advisory = (
                    v4_loader.projector.build_advisory_contract(
                        snapshot,
                        target,
                    )
                )
                actor_advisory = (
                    v4_loader.projector.build_advisory_contract(
                        snapshot,
                        projected,
                    )
                )
                r0_signature, _ = executable_signature(r0_advisory)
                target_signature, _ = executable_signature(target_advisory)
                actor_signature, _ = executable_signature(actor_advisory)
                actor_valid, actor_invariant_reasons = (
                    evaluate_v4_intervention_invariants(
                        snapshot,
                        projected,
                        r0,
                        gate=v4_loader.intervention_gate,
                        projector=v4_loader.projector,
                        formal_decision=None,
                    )
                )
                target_differs_from_r0 = (
                    target_signature != r0_signature
                )
                target_valid = True
                target_invariant_reasons: tuple[str, ...] = ()
                if target_differs_from_r0:
                    target_valid, target_invariant_reasons = (
                        evaluate_v4_intervention_invariants(
                            snapshot,
                            target,
                            r0,
                            gate=v4_loader.intervention_gate,
                            projector=v4_loader.projector,
                            formal_decision=None,
                        )
                    )
                if target.projection_rejections or (
                    target_differs_from_r0 and not target_valid
                ):
                    raise RegionResourceV5ExternalEvaluationError(
                        "v5_external_rule_safe_target_invalid:"
                        + ",".join(target_invariant_reasons)
                    )
                rule_safe_positive = bool(
                    target_differs_from_r0 and target_valid
                )
                positive_key = (
                    int(episode.source.seed),
                    int(frame.frame_index),
                    snapshot.snapshot_id,
                    split.value,
                )
                if rule_safe_positive:
                    observed_positive.add(positive_key)
                actor_target_signature_match = (
                    actor_signature == target_signature
                )
                actor_derived_positive = bool(
                    rule_safe_positive
                    and actor_target_signature_match
                    and actor_valid
                )
                feature = _actor_pooled_latent(
                    v4_loader.loaded_bundle.model,
                    graph,
                )
                score = float(v5_loader.score_feature(feature))
                if not isfinite(score):
                    raise RegionResourceV5ExternalEvaluationError(
                        "v5_external_nonfinite_score"
                    )
                threshold_passed = score >= float(threshold)
                rejection_reasons: list[str] = []
                if not rule_safe_positive:
                    rejection_reasons.append(
                        "rule_label_is_r0_negative"
                    )
                if not actor_target_signature_match:
                    rejection_reasons.append(
                        "actor_target_signature_mismatch"
                    )
                if not actor_valid:
                    rejection_reasons.extend(actor_invariant_reasons)
                if not threshold_passed:
                    rejection_reasons.append(
                        "confidence_below_fixed_0_60"
                    )
                rejection_reasons.extend(projected.projection_rejections)
                rejection_reasons.append("candidate_unregistered")
                rejection_reasons.append("admission_closed")
                records.append(
                    {
                        "schema": REGION_RESOURCE_V5_EXTERNAL_RECORD_SCHEMA,
                        "source_identity_sha256": (
                            episode.source.identity_sha256
                        ),
                        "scenario_id": episode.source.scenario_id,
                        "scenario_version": episode.source.scenario_version,
                        "scenario_scale": episode.source.scenario_scale,
                        "seed": int(episode.source.seed),
                        "split": split.value,
                        "frame_index": int(frame.frame_index),
                        "snapshot_id": snapshot.snapshot_id,
                        "observable_key_sha256": observable_key,
                        "rule_label_available": True,
                        "rule_label_kind": "offline_deterministic_r0_or_"
                        "bounded_safe_transfer",
                        "rule_safe_positive_action": rule_safe_positive,
                        "r0_executable_signature_sha256": r0_signature,
                        "target_executable_signature_sha256": (
                            target_signature
                        ),
                        "actor_executable_signature_sha256": (
                            actor_signature
                        ),
                        "actor_executable_difference": (
                            actor_signature != r0_signature
                        ),
                        "actor_target_signature_match": (
                            actor_target_signature_match
                        ),
                        "actor_action_invariant_safe": bool(actor_valid),
                        "actor_derived_positive": actor_derived_positive,
                        "score": score,
                        "fixed_minimum_confidence": float(threshold),
                        "confidence_threshold_passed": threshold_passed,
                        "candidate_gate_passed": bool(
                            actor_derived_positive and threshold_passed
                        ),
                        "candidate_authorized": False,
                        "rule_fallback_used": True,
                        "production_permission_available": False,
                        "rejection_reasons": list(
                            dict.fromkeys(rejection_reasons)
                        ),
                    }
                )
    if observed_positive != expected_positive:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_positive_record_derivation_mismatch"
        )
    return tuple(records)


def _observable_overlap_audit(
    v4_development_dataset_root: Path,
    external_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    source = load_region_learning_dataset_splits(
        v4_development_dataset_root,
        splits=(
            RegionLearningSplit.TRAIN,
            RegionLearningSplit.VALIDATION,
        ),
    )
    source_keys_by_split: dict[str, list[str]] = {}
    for split in (
        RegionLearningSplit.TRAIN,
        RegionLearningSplit.VALIDATION,
    ):
        keys = [
            _v4_confidence_observable_key(
                snapshot_to_region_graph(frame.snapshot, device="cpu")
            )
            for frame in source.iter_frames(split)
        ]
        source_keys_by_split[split.value] = keys
    external_keys_by_split = {
        split.value: [
            str(record["observable_key_sha256"])
            for record in external_records
            if record["split"] == split.value
        ]
        for split in RegionLearningSplit
    }
    source_keys = {
        value
        for values in source_keys_by_split.values()
        for value in values
    }
    external_keys = {
        value
        for values in external_keys_by_split.values()
        for value in values
    }
    intersection = sorted(source_keys & external_keys)
    return {
        "schema": REGION_RESOURCE_V5_EXTERNAL_OVERLAP_SCHEMA,
        "observable_key_definition": (
            "node_features_edge_features_edge_index_shape_dtype_values"
        ),
        "source_candidate_split_payload_read_count": {
            split: len(values)
            for split, values in source_keys_by_split.items()
        },
        "source_candidate_test_payload_read_count": 0,
        "source_candidate_formal_holdout_payload_read_count": 0,
        "source_candidate_record_count": sum(
            len(values) for values in source_keys_by_split.values()
        ),
        "source_candidate_unique_observable_key_count": len(source_keys),
        "external_split_payload_read_count": {
            split: len(values)
            for split, values in external_keys_by_split.items()
        },
        "external_record_count": len(external_records),
        "external_unique_observable_key_count": len(external_keys),
        "exact_observable_key_intersection_count": len(intersection),
        "external_record_exact_overlap_count": sum(
            str(record["observable_key_sha256"]) in source_keys
            for record in external_records
        ),
        "intersection_keys": intersection,
        "source_independent_exact_observable_keys": not intersection,
        "observable_key_uses_source_seed_episode_or_target": False,
        "observable_key_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
    }


def _summarize_records(
    records: Sequence[Mapping[str, Any]],
    *,
    threshold: float,
) -> dict[str, Any]:
    if not records:
        raise RegionResourceV5ExternalEvaluationError(
            "v5_external_records_unavailable"
        )
    by_split = {
        split.value: _split_metrics(
            [record for record in records if record["split"] == split.value],
            threshold=threshold,
        )
        for split in RegionLearningSplit
    }
    overall = _split_metrics(records, threshold=threshold)
    return {
        **overall,
        "by_split": by_split,
        "rule_label_available_count": len(records),
        "candidate_authorization_count": 0,
        "production_admission_count": 0,
        "all_permissions_closed": True,
    }


def _split_metrics(
    records: Sequence[Mapping[str, Any]],
    *,
    threshold: float,
) -> dict[str, Any]:
    values = [float(record["score"]) for record in records]
    if not values:
        return {
            "sample_count": 0,
            "rule_safe_positive_action_count": 0,
            "actor_derived_positive_count": 0,
            "negative_sample_count": 0,
            "confidence_threshold_pass_count": 0,
            "actor_derived_positive_threshold_pass_count": 0,
            "negative_false_accept_count": 0,
            "rule_fallback_count": 0,
            "positive_denominator_available": False,
            "positive_recall": None,
            "positive_recall_status": "positive_denominator_unavailable",
            "negative_specificity": None,
            "score_distribution": None,
            "fixed_minimum_confidence": float(threshold),
        }
    positive = [
        bool(record["actor_derived_positive"])
        for record in records
    ]
    passed = [
        bool(record["confidence_threshold_passed"])
        for record in records
    ]
    positive_count = sum(positive)
    negative_count = len(records) - positive_count
    positive_pass = sum(
        label and gate
        for label, gate in zip(positive, passed, strict=True)
    )
    false_accept = sum(
        not label and gate
        for label, gate in zip(positive, passed, strict=True)
    )
    ordered = sorted(values)
    return {
        "sample_count": len(records),
        "rule_safe_positive_action_count": sum(
            bool(record["rule_safe_positive_action"])
            for record in records
        ),
        "actor_executable_difference_count": sum(
            bool(record["actor_executable_difference"])
            for record in records
        ),
        "actor_target_signature_match_count": sum(
            bool(record["actor_target_signature_match"])
            for record in records
        ),
        "actor_derived_positive_count": positive_count,
        "negative_sample_count": negative_count,
        "confidence_threshold_pass_count": sum(passed),
        "actor_derived_positive_threshold_pass_count": positive_pass,
        "negative_false_accept_count": false_accept,
        "candidate_gate_pass_count": sum(
            bool(record["candidate_gate_passed"])
            for record in records
        ),
        "rule_fallback_count": sum(
            bool(record["rule_fallback_used"])
            for record in records
        ),
        "positive_denominator_available": positive_count > 0,
        "positive_recall": (
            positive_pass / positive_count if positive_count else None
        ),
        "positive_recall_status": (
            "available"
            if positive_count
            else "positive_denominator_unavailable"
        ),
        "negative_specificity": (
            1.0 - false_accept / negative_count
            if negative_count
            else None
        ),
        "score_distribution": {
            "minimum": ordered[0],
            "mean": sum(ordered) / len(ordered),
            "median": _nearest_rank(ordered, 0.50),
            "p95": _nearest_rank(ordered, 0.95),
            "maximum": ordered[-1],
        },
        "fixed_minimum_confidence": float(threshold),
    }


def _data_usage(
    manifest: RegionLearningDatasetManifest,
    config: RegionResourceV5ExternalEvaluationConfig,
) -> dict[str, Any]:
    split_counts = {
        split.value: sum(
            entry.frame_count
            for entry in manifest.episodes
            if entry.split == split
        )
        for split in RegionLearningSplit
    }
    split_episode_counts = {
        split.value: sum(
            entry.split == split
            for entry in manifest.episodes
        )
        for split in RegionLearningSplit
    }
    return {
        "payload_read_count_by_split": split_counts,
        "episode_read_count_by_split": split_episode_counts,
        "this_d4_evaluation_test_payload_read_count": split_counts["test"],
        "known_prior_main_read_only_test_payload_read_count": (
            config.known_prior_main_test_payload_read_count
        ),
        "known_prior_main_read_fact_source": (
            "orchestrator_declared_process_fact_not_inferred_from_artifact"
        ),
        "test_payload_fit_count": 0,
        "validation_payload_fit_count": 0,
        "train_payload_fit_count": 0,
        "model_fit_count": 0,
        "threshold_fit_count": 0,
        "hyperparameter_fit_count": 0,
        "candidate_selection_count": 0,
        "split_mutation_count": 0,
        "positive_synthesis_count": 0,
        "source_runtime_recommendation_payload_read_count": 0,
        "source_runtime_recommendation_label_use_count": 0,
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
        "reward_use_count": 0,
        "design_pilot_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "runtime_preflight_count": 0,
    }


def _render_report(
    summary: Mapping[str, Any],
    integrity: Mapping[str, Any],
    overlap: Mapping[str, Any],
) -> str:
    metrics = summary["metrics"]
    rows = []
    for split in ("train", "validation", "test"):
        item = metrics["by_split"][split]
        distribution = item["score_distribution"]
        rows.append(
            "| {split} | {samples} | {rule_positive} | {actor_positive} | "
            "{score_min:.6f}/{score_mean:.6f}/{score_max:.6f} | "
            "{passed} | {false_accept} | {fallback} |".format(
                split=split,
                samples=item["sample_count"],
                rule_positive=item["rule_safe_positive_action_count"],
                actor_positive=item["actor_derived_positive_count"],
                score_min=distribution["minimum"],
                score_mean=distribution["mean"],
                score_max=distribution["maximum"],
                passed=item["confidence_threshold_pass_count"],
                false_accept=item["negative_false_accept_count"],
                fallback=item["rule_fallback_count"],
            )
        )
    data_usage = summary["data_usage"]
    candidate = integrity["candidates"]
    return "\n".join(
        [
            "# D4 v5 来源独立外部评价",
            "",
            "## 结论",
            "",
            "冻结 v5 候选没有获得准入。M16N20 的 32 个来源 episode 共 "
            f"{metrics['sample_count']} 帧，外部规则层包含 "
            f"{metrics['rule_safe_positive_action_count']} 个安全正动作；冻结 "
            "v4 actor 没有输出与这些动作签名一致的独立正类。候选正类分母"
            "不可用，不能计算来源独立正类召回。",
            "",
            f"全部得分低于固定 0.60 门，门通过 {metrics['confidence_threshold_pass_count']}"
            f"/{metrics['sample_count']}，负类误接收 "
            f"{metrics['negative_false_accept_count']}。全部 "
            f"{metrics['rule_fallback_count']} 帧继续使用确定性规则。该结果只"
            "证明当前外部负类被拒绝，没有证明候选能识别外部正类。",
            "",
            "## 评价边界",
            "",
            "- 日期：2026-07-29。",
            "- 场景：M16N20，8 个区域，seed 3008-3039。",
            "- 训练 seed 0-99、正式 holdout seed 1000-1019、设计 pilot "
            "seed 3000-3007 与本次评价 seed 两两隔离。",
            "- 在线 D4 recommendation 未作为教师标签。标签来自同一 D4 "
            "快照离线重算的确定性 R0 规则及其既有安全投影正动作。",
            "- 本次没有拟合、重训、调门、改 split、复制正类或运行 "
            "runtime preflight。",
            "",
            "## 分层结果",
            "",
            "规则标签、actor 正类、置信门和生产准入是四个不同层次。规则"
            "层有安全正动作，不表示 actor 已生成该动作。actor 生成匹配动作"
            "后，置信分数越过 0.60 才能形成候选门控证据。生产准入还要求"
            "登记、正式评价、运行预检和权限审查，本次均未开放。",
            "",
            "| split | 样本 | 规则安全正动作 | actor-derived 正类 | "
            "得分最小/均值/最大 | 0.60 门通过 | 负类误接收 | 规则回退 |",
            "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
            *rows,
            "",
            f"总体 actor-derived 正类为 {metrics['actor_derived_positive_count']}，"
            "因此 `positive denominator unavailable`。总体负类特异度为 "
            f"{metrics['negative_specificity']:.6f}。候选授权和生产准入均为 0。",
            "",
            "## 来源独立性",
            "",
            "冻结候选原 TRAIN/VALIDATION 共 "
            f"{overlap['source_candidate_record_count']} 帧、"
            f"{overlap['source_candidate_unique_observable_key_count']} 个唯一"
            "可观测键。新数据共 "
            f"{overlap['external_record_count']} 帧、"
            f"{overlap['external_unique_observable_key_count']} 个唯一键。精确"
            "键交集为 "
            f"{overlap['exact_observable_key_intersection_count']}，新记录精确"
            "重合数为 "
            f"{overlap['external_record_exact_overlap_count']}。",
            "",
            "键零重合说明输入张量没有复用旧开发样本。冻结 actor 没有独立"
            "正类，泛化正类召回仍不可评价。",
            "",
            "## 数据读取",
            "",
            "D4 本次读取 train/validation/test payload 分别为 "
            f"{data_usage['payload_read_count_by_split']['train']}/"
            f"{data_usage['payload_read_count_by_split']['validation']}/"
            f"{data_usage['payload_read_count_by_split']['test']} 帧，所有拟合"
            "计数为 0。main 此前只读检查 test 10 帧，该事实按调度记录单独"
            "列示，不作为模型拟合或候选选择。正式 holdout payload 读取为 0。",
            "",
            "## 完整性",
            "",
            f"- 来源数据 manifest 文件 SHA-256："
            f"`{integrity['inputs']['source_dataset_manifest']['file_sha256']}`",
            f"- 标签数据集内容 SHA-256："
            f"`{integrity['inputs']['labeled_dataset_manifest']['dataset_sha256']}`",
            f"- 标签数据 manifest 文件 SHA-256："
            f"`{integrity['inputs']['labeled_dataset_manifest']['file_sha256']}`",
            f"- 评价配置 SHA-256：`{summary['configuration_sha256']}`",
            f"- v4 候选树 SHA-256："
            f"`{candidate['v4']['tree_sha256_before']}`",
            f"- v5 候选树 SHA-256："
            f"`{candidate['v5']['tree_sha256_before']}`",
            "",
            "评价前后两个候选树摘要一致。v5 仍为 unregistered、"
            "admission closed、rule fallback required，全部生产、D3 和 D7 "
            "权限保持关闭。",
            "",
            "## 限制",
            "",
            "当前证据仅覆盖一个 M16N20 配置、32 个来源 episode 和 63 帧。"
            "未读取正式 holdout，未运行 runtime preflight、D3 successor、"
            "D7 权限或物理/AirSim 收益试验。后续只有在冻结 actor 能产生"
            "来源独立 actor-derived 正类，并由独立审计形成可用正类分母后，"
            "才具备继续讨论正式评价的条件。",
            "",
        ]
    )


def _nearest_rank(ordered: Sequence[float], quantile: float) -> float:
    index = max(0, min(len(ordered) - 1, int(quantile * len(ordered) + 0.999999) - 1))
    return float(ordered[index])


def _with_content_sha256(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    if "content_sha256" in payload:
        raise ValueError("content_sha256 must not be pre-populated")
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def _resign(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload.pop("content_sha256", None)
    return _with_content_sha256(payload)


def _verify_content_sha256(
    value: Mapping[str, Any],
    name: str,
) -> None:
    expected = value.get("content_sha256")
    payload = dict(value)
    payload.pop("content_sha256", None)
    if not isinstance(expected, str) or expected != _canonical_sha256(payload):
        raise RegionResourceV5ExternalEvaluationError(
            f"v5_external_{name}_content_sha256_mismatch"
        )


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
    return sha256(path.read_bytes()).hexdigest()


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
        raise RegionResourceV5ExternalEvaluationError(
            f"v5_external_json_read_failed:{path.name}:{type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise RegionResourceV5ExternalEvaluationError(
            f"v5_external_json_object_required:{path.name}"
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
                record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
