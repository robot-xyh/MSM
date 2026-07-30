"""Unregistered D4 v5 confidence-calibration development candidate.

The v5 path leaves the frozen v4 actor, v4 candidate, and v3 registry
unchanged.  It fits a small k-nearest-neighbour confidence calibrator from
TRAIN actor latents, audits VALIDATION without fitting it, and never reads
TEST or formal-holdout payloads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import ceil, isclose, isfinite, sqrt
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .region_resource_dataset import (
    RegionLearningSplit,
    load_region_learning_dataset_splits,
)
from .region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V3_FROZEN_TREE_SHA256,
    REGION_RESOURCE_V4_CANDIDATE_FILENAME,
    REGION_RESOURCE_V4_CANDIDATE_ID,
    RegionResourceV4CandidateError,
    RegionResourceV4CandidateLoader,
    _confidence_records,
    _v4_confidence_observable_key,
)


try:  # v5 is an optional development path; deterministic D4 remains torch-free.
    import torch
except ImportError:  # pragma: no cover - covered by the dependency gate.
    torch = None


REGION_RESOURCE_V5_CANDIDATE_ID = (
    "region_resource_a2_confidence_knn_shadow_v5"
)
REGION_RESOURCE_V5_MODEL_VERSION = (
    "d4-region-resource-v4-actor-knn-confidence-v5"
)
REGION_RESOURCE_V5_CANDIDATE_SCHEMA = (
    "d4-region-resource-confidence-shadow-candidate-v5"
)
REGION_RESOURCE_V5_STATE_SCHEMA = (
    "d4-region-resource-confidence-knn-state-v5"
)
REGION_RESOURCE_V5_SUMMARY_SCHEMA = (
    "d4-region-resource-confidence-calibration-summary-v5"
)
REGION_RESOURCE_V5_GATE_SCHEMA = (
    "d4-region-resource-confidence-development-gate-v5"
)
REGION_RESOURCE_V5_PERMISSIONS_SCHEMA = (
    "d4-region-resource-confidence-shadow-permissions-v5"
)
REGION_RESOURCE_V5_FAILURE_SCHEMA = (
    "d4-region-resource-confidence-build-failure-v5"
)
REGION_RESOURCE_V5_OVERLAP_SCHEMA = (
    "d4-region-resource-train-validation-overlap-diagnostic-v5"
)
REGION_RESOURCE_V5_CANDIDATE_FILENAME = (
    "v5_confidence_candidate_manifest.json"
)
REGION_RESOURCE_V5_STATE_FILENAME = "calibration_state.json"
REGION_RESOURCE_V5_SUMMARY_FILENAME = "calibration_summary.json"
REGION_RESOURCE_V5_GATE_FILENAME = "development_gate.json"

REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE = 0.60
REGION_RESOURCE_V5_MINIMUM_POSITIVE_RECALL = 0.80
REGION_RESOURCE_V5_REQUIRED_NEGATIVE_SPECIFICITY = 1.0
REGION_RESOURCE_V5_MINIMUM_POSITIVE_MARGIN = 0.02
REGION_RESOURCE_V5_NEIGHBOUR_COUNT = 11
REGION_RESOURCE_V5_EXACT_MATCH_EPSILON = 1.0e-12
REGION_RESOURCE_V5_SCALE_EPSILON = 1.0e-12
REGION_RESOURCE_V5_CANDIDATE_CLASSIFICATION = (
    "memorization_development_control"
)
REGION_RESOURCE_V5_INDEPENDENCE_BLOCKERS = (
    "validation_same_frozen_development_source",
    "validation_raw_graph_overlap_with_train",
    "validation_actor_latent_overlap_with_train",
    "validation_near_duplicate_latents",
    "source_independent_perturbation_set_unavailable",
)

# D6 independently anchored these immutable v4 identities on 2026-07-29.
REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256 = (
    "4f3e973597469d394a594bec3dd7d2c16b24e80d2e97ba45f718d9ef8397e116"
)
REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256 = (
    "2986d166ad6de231896e46f78aa2d9304c21b6d68714eaf34dfe21439220bebe"
)
REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256 = (
    "33a28060f11277a549b90d2f2f365962fec057b2bfb50a70ab5a422059cb9fe5"
)
REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256 = (
    "b31fc43f3d3cff34ee53f2b2c33ece0b06d7624e46e26a36c4aa834135e7fb8c"
)
REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256 = (
    "c212fe9b48e9908fd4d47488711724ed361429cf9df29667ac32c3e88d094619"
)

# None is intentional.  v5 cannot be loaded as a registered runtime model.
REGION_RESOURCE_V5_REGISTERED_MANIFEST_FILE_SHA256: str | None = None
REGION_RESOURCE_V5_REGISTERED_MANIFEST_CONTENT_SHA256: str | None = None
REGION_RESOURCE_V5_REGISTERED_STATE_SHA256: str | None = None


class RegionResourceV5CandidateError(RuntimeError):
    """Stable fail-closed error for the v5 development candidate."""


@dataclass(frozen=True)
class RegionResourceV5Permissions:
    """Production capabilities that must remain false for v5."""

    formal_evaluation_authorized: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    assignment_enabled: bool = False
    takeover_enabled: bool = False
    coalition_commit_enabled: bool = False
    control_enabled: bool = False
    production_runtime_ack_enabled: bool = False
    physical_permission_available: bool = False
    d3_permission_available: bool = False
    d7_permission_available: bool = False
    actual_adoption_claimed: bool = False
    benefit_claimed: bool = False
    schema: str = REGION_RESOURCE_V5_PERMISSIONS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_V5_PERMISSIONS_SCHEMA:
            raise ValueError("unsupported v5 permissions schema")
        values = (
            value
            for name, value in asdict(self).items()
            if name != "schema"
        )
        if any(type(value) is not bool or value for value in values):
            raise ValueError("v5 development candidate cannot grant permissions")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionResourceV5DevelopmentGate:
    """Immutable development gate; passing it does not grant admission."""

    fixed_minimum_confidence: float = (
        REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE
    )
    minimum_train_positive_recall: float = (
        REGION_RESOURCE_V5_MINIMUM_POSITIVE_RECALL
    )
    minimum_validation_positive_recall: float = (
        REGION_RESOURCE_V5_MINIMUM_POSITIVE_RECALL
    )
    required_train_negative_specificity: float = (
        REGION_RESOURCE_V5_REQUIRED_NEGATIVE_SPECIFICITY
    )
    required_validation_negative_specificity: float = (
        REGION_RESOURCE_V5_REQUIRED_NEGATIVE_SPECIFICITY
    )
    minimum_train_positive_margin: float = (
        REGION_RESOURCE_V5_MINIMUM_POSITIVE_MARGIN
    )
    minimum_validation_positive_margin: float = (
        REGION_RESOURCE_V5_MINIMUM_POSITIVE_MARGIN
    )
    require_train_only_fit: bool = True
    require_zero_validation_fit: bool = True
    require_zero_test_payload_read_and_fit: bool = True
    require_zero_formal_holdout_payload_read_and_fit: bool = True
    require_v4_immutable: bool = True
    require_v3_registry_immutable: bool = True
    development_only: bool = True
    shadow_only: bool = True
    admission_closed: bool = True
    rule_fallback_required: bool = True
    schema: str = REGION_RESOURCE_V5_GATE_SCHEMA

    def __post_init__(self) -> None:
        expected_floats = {
            "fixed_minimum_confidence": (
                REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE
            ),
            "minimum_train_positive_recall": (
                REGION_RESOURCE_V5_MINIMUM_POSITIVE_RECALL
            ),
            "minimum_validation_positive_recall": (
                REGION_RESOURCE_V5_MINIMUM_POSITIVE_RECALL
            ),
            "required_train_negative_specificity": (
                REGION_RESOURCE_V5_REQUIRED_NEGATIVE_SPECIFICITY
            ),
            "required_validation_negative_specificity": (
                REGION_RESOURCE_V5_REQUIRED_NEGATIVE_SPECIFICITY
            ),
            "minimum_train_positive_margin": (
                REGION_RESOURCE_V5_MINIMUM_POSITIVE_MARGIN
            ),
            "minimum_validation_positive_margin": (
                REGION_RESOURCE_V5_MINIMUM_POSITIVE_MARGIN
            ),
        }
        if self.schema != REGION_RESOURCE_V5_GATE_SCHEMA:
            raise ValueError("unsupported v5 development gate schema")
        if any(
            not isclose(float(getattr(self, name)), expected)
            for name, expected in expected_floats.items()
        ):
            raise ValueError("v5 fixed development gate changed")
        required_true = (
            self.require_train_only_fit,
            self.require_zero_validation_fit,
            self.require_zero_test_payload_read_and_fit,
            self.require_zero_formal_holdout_payload_read_and_fit,
            self.require_v4_immutable,
            self.require_v3_registry_immutable,
            self.development_only,
            self.shadow_only,
            self.admission_closed,
            self.rule_fallback_required,
        )
        if any(type(value) is not bool or not value for value in required_true):
            raise ValueError("v5 development safety boundary changed")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["content_sha256"] = _canonical_sha256(payload)
        return payload


def build_region_resource_v5_confidence_candidate(
    v4_candidate_root: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Build one TRAIN-fit, VALIDATION-audited unregistered v5 candidate."""

    _require_torch()
    source_root = Path(v4_candidate_root).resolve()
    destination = Path(output_root).resolve()
    if destination.name != REGION_RESOURCE_V5_CANDIDATE_ID:
        raise RegionResourceV5CandidateError(
            "v5_candidate_directory_identity_mismatch"
        )
    if "model_registry" in destination.parts:
        raise RegionResourceV5CandidateError(
            "v5_unregistered_candidate_registry_output_forbidden"
        )
    if destination.exists() or destination.is_symlink():
        raise RegionResourceV5CandidateError(
            "v5_candidate_output_already_exists"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)

    builder_source_sha256 = _sha256_file(Path(__file__).resolve())
    source_tree_before = _tree_sha256(source_root)
    v3_root = (
        Path(__file__).resolve().parents[1]
        / "model_registry"
        / "region_resource_a2_8region_runtime_action_readiness_shadow_v3"
    )
    v3_tree_before = _tree_sha256(v3_root)
    if v3_tree_before != REGION_RESOURCE_V3_FROZEN_TREE_SHA256:
        raise RegionResourceV5CandidateError(
            "v5_v3_registry_prebuild_identity_mismatch"
        )

    try:
        v4_loader = RegionResourceV4CandidateLoader(
            source_root,
            require_registered_binding=False,
            evaluation_context="offline_development",
        )
    except RegionResourceV4CandidateError as exc:
        raise RegionResourceV5CandidateError(
            f"v5_base_v4_load_failed:{exc}"
        ) from exc
    _validate_base_v4_identity(source_root, v4_loader)

    try:
        loaded = load_region_learning_dataset_splits(
            source_root / "development_dataset",
            splits=(
                RegionLearningSplit.TRAIN,
                RegionLearningSplit.VALIDATION,
            ),
        )
        train_records = _confidence_records(
            v4_loader.loaded_bundle.model,
            loaded,
            split=RegionLearningSplit.TRAIN,
            projector=v4_loader.projector,
            rule_policy=v4_loader.rule_policy,
        )
        validation_records = _confidence_records(
            v4_loader.loaded_bundle.model,
            loaded,
            split=RegionLearningSplit.VALIDATION,
            projector=v4_loader.projector,
            rule_policy=v4_loader.rule_policy,
        )
    except Exception as exc:
        raise RegionResourceV5CandidateError(
            f"v5_development_data_read_failed:{type(exc).__name__}:{exc}"
        ) from exc

    state = _fit_train_only_calibrator(
        v4_loader.loaded_bundle.model,
        train_records,
    )
    train_metrics = _calibration_metrics(
        v4_loader.loaded_bundle.model,
        train_records,
        state,
    )
    validation_metrics = _calibration_metrics(
        v4_loader.loaded_bundle.model,
        validation_records,
        state,
    )
    overlap_diagnostic = _train_validation_overlap_diagnostic(
        v4_loader.loaded_bundle.model,
        train_records,
        validation_records,
        state,
    )
    data_usage = {
        "fit_split": RegionLearningSplit.TRAIN.value,
        "audit_split": RegionLearningSplit.VALIDATION.value,
        "train_payload_read_count": len(train_records),
        "train_fit_count": len(train_records),
        "validation_payload_read_count": len(validation_records),
        "validation_fit_count": 0,
        "validation_weight_fit_count": 0,
        "validation_threshold_fit_count": 0,
        "validation_hyperparameter_fit_count": 0,
        "validation_selection_count": 0,
        "validation_audit_count": len(validation_records),
        "validation_overlap_diagnostic_count": len(validation_records),
        "validation_overlap_diagnostic_fit_count": 0,
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "test_payload_weight_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "formal_holdout_payload_fit_count": 0,
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
        "reward_use_count": 0,
    }
    gate = RegionResourceV5DevelopmentGate()
    gate_passed, gate_reasons = evaluate_v5_development_gate(
        train_metrics,
        validation_metrics,
        data_usage,
        gate=gate,
    )
    if not gate_passed:
        failure = {
            "schema": REGION_RESOURCE_V5_FAILURE_SCHEMA,
            "candidate_id": REGION_RESOURCE_V5_CANDIDATE_ID,
            "candidate_created": False,
            "failure_reasons": list(gate_reasons),
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "train_validation_overlap_diagnostic": overlap_diagnostic,
            "data_usage": data_usage,
            "independence_evidence_available": False,
            "generalization_evidence_available": False,
            "candidate_classification": (
                REGION_RESOURCE_V5_CANDIDATE_CLASSIFICATION
            ),
            "independence_blockers": list(
                REGION_RESOURCE_V5_INDEPENDENCE_BLOCKERS
            ),
            "development_only": True,
            "shadow_only": True,
            "admission_closed": True,
            "rule_fallback_required": True,
            "permissions": RegionResourceV5Permissions().to_dict(),
        }
        failure_path = destination.with_name(
            f"{REGION_RESOURCE_V5_CANDIDATE_ID}.build_failure.json"
        )
        if failure_path.exists() or failure_path.is_symlink():
            raise RegionResourceV5CandidateError(
                "v5_build_failure_receipt_already_exists"
            )
        _write_json(failure_path, _with_content_sha256(failure))
        raise RegionResourceV5CandidateError(
            "v5_development_gate_failed:" + ",".join(gate_reasons)
        )

    source_tree_after_fit = _tree_sha256(source_root)
    v3_tree_after_fit = _tree_sha256(v3_root)
    if source_tree_after_fit != source_tree_before:
        raise RegionResourceV5CandidateError(
            "v5_base_v4_tree_changed_during_fit"
        )
    if v3_tree_after_fit != v3_tree_before:
        raise RegionResourceV5CandidateError(
            "v5_v3_registry_changed_during_fit"
        )

    state_payload = _with_content_sha256(state)
    gate_payload = gate.to_dict()
    summary = _with_content_sha256(
        {
            "schema": REGION_RESOURCE_V5_SUMMARY_SCHEMA,
            "candidate_id": REGION_RESOURCE_V5_CANDIDATE_ID,
            "model_version": REGION_RESOURCE_V5_MODEL_VERSION,
            "algorithm": (
                "TRAIN-standardized inverse-distance k-nearest-neighbour "
                "calibration over the frozen v4 actor pooled latent"
            ),
            "neighbour_count": REGION_RESOURCE_V5_NEIGHBOUR_COUNT,
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "train_validation_overlap_diagnostic": overlap_diagnostic,
            "data_usage": data_usage,
            "development_gate_passed": True,
            "development_gate_reasons": [],
            "independence_gate_passed": False,
            "independence_evidence_available": False,
            "generalization_evidence_available": False,
            "candidate_classification": (
                REGION_RESOURCE_V5_CANDIDATE_CLASSIFICATION
            ),
            "independence_blockers": list(
                REGION_RESOURCE_V5_INDEPENDENCE_BLOCKERS
            ),
            "v4_independent_audit_reference": {
                "audit_date": "2026-07-29",
                "integrity_passed": True,
                "fixed_minimum_confidence": 0.60,
                "train_positive_recall": 0.206897,
                "validation_positive_recall": 0.307692,
                "train_negative_specificity": 1.0,
                "validation_negative_specificity": 1.0,
                "minimum_positive_passing_margin": 0.000504935,
                "admission_allowed": False,
            },
            "base_v4_tree_sha256_before": source_tree_before,
            "base_v4_tree_sha256_after": source_tree_after_fit,
            "builder_source_sha256": builder_source_sha256,
            "v3_registry_tree_sha256_before": v3_tree_before,
            "v3_registry_tree_sha256_after": v3_tree_after_fit,
            "formal_holdout_completed": False,
            "runtime_preflight_completed": False,
            "registered": False,
            "production_permission_available": False,
            "d3_permission_available": False,
            "d7_permission_available": False,
            "development_only": True,
            "shadow_only": True,
            "admission_closed": True,
            "rule_fallback_required": True,
            "permissions": RegionResourceV5Permissions().to_dict(),
        }
    )

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{REGION_RESOURCE_V5_CANDIDATE_ID}.staging-",
            dir=destination.parent,
        )
    )
    try:
        _write_json(staging / REGION_RESOURCE_V5_STATE_FILENAME, state_payload)
        _write_json(staging / REGION_RESOURCE_V5_GATE_FILENAME, gate_payload)
        _write_json(
            staging / REGION_RESOURCE_V5_SUMMARY_FILENAME,
            summary,
        )
        artifact_files = {
            name: _sha256_file(staging / name)
            for name in (
                REGION_RESOURCE_V5_STATE_FILENAME,
                REGION_RESOURCE_V5_GATE_FILENAME,
                REGION_RESOURCE_V5_SUMMARY_FILENAME,
            )
        }
        manifest = _with_content_sha256(
            {
                "schema": REGION_RESOURCE_V5_CANDIDATE_SCHEMA,
                "candidate_id": REGION_RESOURCE_V5_CANDIDATE_ID,
                "model_version": REGION_RESOURCE_V5_MODEL_VERSION,
                "base_candidate_id": REGION_RESOURCE_V4_CANDIDATE_ID,
                "base_v4_manifest_content_sha256": (
                    REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256
                ),
                "base_v4_manifest_file_sha256": (
                    REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256
                ),
                "base_v4_model_state_sha256": (
                    REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256
                ),
                "base_v4_dataset_sha256": (
                    REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256
                ),
                "base_v4_split_sha256": (
                    REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256
                ),
                "base_v4_tree_sha256": source_tree_before,
                "builder_source_sha256": builder_source_sha256,
                "v3_registry_tree_sha256": v3_tree_before,
                "calibration_state_content_sha256": (
                    state_payload["content_sha256"]
                ),
                "calibration_summary_content_sha256": (
                    summary["content_sha256"]
                ),
                "development_gate_content_sha256": (
                    gate_payload["content_sha256"]
                ),
                "artifact_files": artifact_files,
                "formal_holdout_evaluated": False,
                "runtime_preflight_completed": False,
                "registered": False,
                "independence_evidence_available": False,
                "generalization_evidence_available": False,
                "candidate_classification": (
                    REGION_RESOURCE_V5_CANDIDATE_CLASSIFICATION
                ),
                "independence_blockers": list(
                    REGION_RESOURCE_V5_INDEPENDENCE_BLOCKERS
                ),
                "development_only": True,
                "shadow_only": True,
                "admission_closed": True,
                "rule_fallback_required": True,
                "permissions": RegionResourceV5Permissions().to_dict(),
            }
        )
        _write_json(
            staging / REGION_RESOURCE_V5_CANDIDATE_FILENAME,
            manifest,
        )
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if (
        _tree_sha256(source_root) != source_tree_before
        or _tree_sha256(v3_root) != v3_tree_before
    ):
        shutil.rmtree(destination, ignore_errors=True)
        raise RegionResourceV5CandidateError(
            "v5_source_or_registry_changed_during_persistence"
        )
    review_region_resource_v5_confidence_candidate(
        destination,
        require_registered_binding=False,
    )
    return _read_json(destination / REGION_RESOURCE_V5_CANDIDATE_FILENAME)


class RegionResourceV5CandidateLoader:
    """Verify an unregistered v5 artifact for offline development only."""

    def __init__(
        self,
        candidate_root: str | Path,
        *,
        require_registered_binding: bool = True,
        evaluation_context: str = "runtime",
    ) -> None:
        if require_registered_binding:
            if not _v5_registration_available():
                raise RegionResourceV5CandidateError(
                    "v5_candidate_unregistered"
                )
        elif evaluation_context != "offline_development":
            raise RegionResourceV5CandidateError(
                "v5_unregistered_runtime_loading_forbidden"
            )
        self.root = Path(candidate_root).resolve()
        self.manifest = review_region_resource_v5_confidence_candidate(
            self.root,
            require_registered_binding=require_registered_binding,
        )
        self.state = _read_json(
            self.root / REGION_RESOURCE_V5_STATE_FILENAME
        )
        self.registered_binding_verified = bool(
            require_registered_binding
        )
        self.evaluation_context = evaluation_context

    def score_feature(self, feature: Sequence[float]) -> float:
        """Return an offline-development confidence for one actor latent."""

        return _score_feature(feature, self.state)


def review_region_resource_v5_confidence_candidate(
    candidate_root: str | Path,
    *,
    require_registered_binding: bool = True,
) -> dict[str, Any]:
    """Verify v5 identity, artifacts, fixed gate, and closed permissions."""

    root = Path(candidate_root).resolve()
    if root.is_symlink() or root.name != REGION_RESOURCE_V5_CANDIDATE_ID:
        raise RegionResourceV5CandidateError(
            "v5_candidate_directory_identity_mismatch"
        )
    expected_files = {
        REGION_RESOURCE_V5_CANDIDATE_FILENAME,
        REGION_RESOURCE_V5_STATE_FILENAME,
        REGION_RESOURCE_V5_SUMMARY_FILENAME,
        REGION_RESOURCE_V5_GATE_FILENAME,
    }
    actual_files = {
        path.name
        for path in root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if actual_files != expected_files or any(
        path.is_symlink() or not path.is_file() for path in root.iterdir()
    ):
        raise RegionResourceV5CandidateError(
            "v5_candidate_file_inventory_mismatch"
        )
    manifest = _read_json(root / REGION_RESOURCE_V5_CANDIDATE_FILENAME)
    _verify_content_sha256(manifest, "v5_candidate_manifest")
    required_manifest_values = {
        "schema": REGION_RESOURCE_V5_CANDIDATE_SCHEMA,
        "candidate_id": REGION_RESOURCE_V5_CANDIDATE_ID,
        "model_version": REGION_RESOURCE_V5_MODEL_VERSION,
        "base_candidate_id": REGION_RESOURCE_V4_CANDIDATE_ID,
        "base_v4_manifest_content_sha256": (
            REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256
        ),
        "base_v4_manifest_file_sha256": (
            REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256
        ),
        "base_v4_model_state_sha256": (
            REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256
        ),
        "base_v4_dataset_sha256": (
            REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256
        ),
        "base_v4_split_sha256": REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256,
        "v3_registry_tree_sha256": REGION_RESOURCE_V3_FROZEN_TREE_SHA256,
        "formal_holdout_evaluated": False,
        "runtime_preflight_completed": False,
        "registered": False,
        "independence_evidence_available": False,
        "generalization_evidence_available": False,
        "candidate_classification": (
            REGION_RESOURCE_V5_CANDIDATE_CLASSIFICATION
        ),
        "independence_blockers": list(
            REGION_RESOURCE_V5_INDEPENDENCE_BLOCKERS
        ),
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
    }
    for name, expected in required_manifest_values.items():
        if manifest.get(name) != expected:
            raise RegionResourceV5CandidateError(
                f"v5_manifest_{name}_mismatch"
            )
    for name in ("base_v4_tree_sha256", "builder_source_sha256"):
        _require_sha256(str(manifest.get(name)), f"v5 manifest {name}")
    if (
        manifest["builder_source_sha256"]
        != _sha256_file(Path(__file__).resolve())
    ):
        raise RegionResourceV5CandidateError(
            "v5_builder_source_sha256_mismatch"
        )
    _validate_closed_permissions(manifest.get("permissions"))
    artifact_files = manifest.get("artifact_files")
    if not isinstance(artifact_files, Mapping) or set(
        artifact_files
    ) != expected_files - {REGION_RESOURCE_V5_CANDIDATE_FILENAME}:
        raise RegionResourceV5CandidateError(
            "v5_manifest_artifact_inventory_invalid"
        )
    for name, expected_sha256 in artifact_files.items():
        _require_sha256(str(expected_sha256), f"v5 artifact {name}")
        if _sha256_file(root / name) != expected_sha256:
            raise RegionResourceV5CandidateError(
                f"v5_candidate_artifact_sha256_mismatch:{name}"
            )

    state = _read_json(root / REGION_RESOURCE_V5_STATE_FILENAME)
    summary = _read_json(root / REGION_RESOURCE_V5_SUMMARY_FILENAME)
    gate = _read_json(root / REGION_RESOURCE_V5_GATE_FILENAME)
    _verify_content_sha256(state, "v5_calibration_state")
    _verify_content_sha256(summary, "v5_calibration_summary")
    _verify_content_sha256(gate, "v5_development_gate")
    if (
        manifest["calibration_state_content_sha256"]
        != state["content_sha256"]
        or manifest["calibration_summary_content_sha256"]
        != summary["content_sha256"]
        or manifest["development_gate_content_sha256"]
        != gate["content_sha256"]
    ):
        raise RegionResourceV5CandidateError(
            "v5_manifest_artifact_content_binding_mismatch"
        )
    if (
        manifest["base_v4_tree_sha256"]
        != summary.get("base_v4_tree_sha256_before")
        or manifest["builder_source_sha256"]
        != summary.get("builder_source_sha256")
    ):
        raise RegionResourceV5CandidateError(
            "v5_manifest_source_binding_mismatch"
        )
    _validate_state(state)
    parsed_gate = RegionResourceV5DevelopmentGate(
        **{
            name: gate[name]
            for name in RegionResourceV5DevelopmentGate.__dataclass_fields__
        }
    )
    if parsed_gate.to_dict() != gate:
        raise RegionResourceV5CandidateError(
            "v5_development_gate_payload_mismatch"
        )
    _validate_summary(summary, gate=parsed_gate)

    if require_registered_binding:
        registered = (
            REGION_RESOURCE_V5_REGISTERED_MANIFEST_FILE_SHA256,
            REGION_RESOURCE_V5_REGISTERED_MANIFEST_CONTENT_SHA256,
            REGION_RESOURCE_V5_REGISTERED_STATE_SHA256,
        )
        if not all(registered):
            raise RegionResourceV5CandidateError(
                "v5_candidate_unregistered"
            )
        if (
            _sha256_file(root / REGION_RESOURCE_V5_CANDIDATE_FILENAME)
            != REGION_RESOURCE_V5_REGISTERED_MANIFEST_FILE_SHA256
            or manifest["content_sha256"]
            != REGION_RESOURCE_V5_REGISTERED_MANIFEST_CONTENT_SHA256
            or _sha256_file(root / REGION_RESOURCE_V5_STATE_FILENAME)
            != REGION_RESOURCE_V5_REGISTERED_STATE_SHA256
        ):
            raise RegionResourceV5CandidateError(
                "v5_registered_binding_mismatch"
            )
    return manifest


def evaluate_v5_development_gate(
    train_metrics: Mapping[str, Any],
    validation_metrics: Mapping[str, Any],
    data_usage: Mapping[str, Any],
    *,
    gate: RegionResourceV5DevelopmentGate | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Evaluate the fixed development gate without granting admission."""

    gate = gate or RegionResourceV5DevelopmentGate()
    reasons: list[str] = []
    metric_requirements = (
        (
            "train_positive_recall_below_0_80",
            float(train_metrics.get("positive_recall", -1.0))
            >= gate.minimum_train_positive_recall,
        ),
        (
            "validation_positive_recall_below_0_80",
            float(validation_metrics.get("positive_recall", -1.0))
            >= gate.minimum_validation_positive_recall,
        ),
        (
            "train_negative_specificity_not_1_0",
            isclose(
                float(train_metrics.get("negative_specificity", -1.0)),
                gate.required_train_negative_specificity,
            ),
        ),
        (
            "validation_negative_specificity_not_1_0",
            isclose(
                float(
                    validation_metrics.get(
                        "negative_specificity", -1.0
                    )
                ),
                gate.required_validation_negative_specificity,
            ),
        ),
        (
            "train_positive_margin_below_0_02",
            float(
                train_metrics.get(
                    "minimum_positive_passing_margin", -1.0
                )
            )
            >= gate.minimum_train_positive_margin,
        ),
        (
            "validation_positive_margin_below_0_02",
            float(
                validation_metrics.get(
                    "minimum_positive_passing_margin", -1.0
                )
            )
            >= gate.minimum_validation_positive_margin,
        ),
    )
    reasons.extend(name for name, accepted in metric_requirements if not accepted)

    usage_requirements = {
        "validation_fit_count": 0,
        "validation_weight_fit_count": 0,
        "validation_threshold_fit_count": 0,
        "validation_hyperparameter_fit_count": 0,
        "validation_selection_count": 0,
        "validation_overlap_diagnostic_fit_count": 0,
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "test_payload_weight_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "formal_holdout_payload_fit_count": 0,
        "truth_identifier_use_count": 0,
        "future_outcome_use_count": 0,
        "reward_use_count": 0,
    }
    for name, expected in usage_requirements.items():
        if data_usage.get(name) != expected:
            reasons.append(f"v5_data_usage_{name}_invalid")
    if (
        data_usage.get("fit_split") != RegionLearningSplit.TRAIN.value
        or data_usage.get("audit_split")
        != RegionLearningSplit.VALIDATION.value
        or int(data_usage.get("train_fit_count", 0)) <= 0
    ):
        reasons.append("v5_train_only_fit_contract_invalid")
    return not reasons, tuple(dict.fromkeys(reasons))


def _fit_train_only_calibrator(
    actor_model: Any,
    train_records: Sequence[
        tuple[Any, bool, bool, bool, tuple[str, ...]]
    ],
) -> dict[str, Any]:
    if not train_records:
        raise RegionResourceV5CandidateError(
            "v5_train_records_unavailable"
        )
    features = [
        _actor_pooled_latent(actor_model, record[0])
        for record in train_records
    ]
    labels = [bool(record[1]) for record in train_records]
    if not any(labels) or all(labels):
        raise RegionResourceV5CandidateError(
            "v5_train_requires_positive_and_negative_labels"
        )
    dimension = len(features[0])
    if dimension <= 0 or any(len(row) != dimension for row in features):
        raise RegionResourceV5CandidateError(
            "v5_train_feature_dimension_invalid"
        )
    mean = [
        sum(row[index] for row in features) / len(features)
        for index in range(dimension)
    ]
    scale = []
    for index in range(dimension):
        variance = sum(
            (row[index] - mean[index]) ** 2 for row in features
        ) / len(features)
        value = sqrt(max(variance, 0.0))
        scale.append(
            value if value > REGION_RESOURCE_V5_SCALE_EPSILON else 1.0
        )
    normalized = [
        [
            (row[index] - mean[index]) / scale[index]
            for index in range(dimension)
        ]
        for row in features
    ]
    groups: dict[str, set[bool]] = {}
    for row, label in zip(normalized, labels, strict=True):
        key = _canonical_sha256(row)
        groups.setdefault(key, set()).add(label)
    conflict_count = sum(len(values) > 1 for values in groups.values())
    if conflict_count:
        raise RegionResourceV5CandidateError(
            "v5_train_latent_label_conflict:"
            f"groups={conflict_count}"
        )
    state = {
        "schema": REGION_RESOURCE_V5_STATE_SCHEMA,
        "algorithm": "standardized_inverse_distance_knn",
        "feature_source": "frozen_v4_actor_pooled_message_passing_latent",
        "feature_uses_target_identity": False,
        "feature_uses_source_identity": False,
        "feature_uses_truth_identifier": False,
        "feature_uses_future_outcome": False,
        "fit_split": RegionLearningSplit.TRAIN.value,
        "feature_dimension": dimension,
        "neighbour_count": REGION_RESOURCE_V5_NEIGHBOUR_COUNT,
        "exact_match_epsilon": REGION_RESOURCE_V5_EXACT_MATCH_EPSILON,
        "fixed_minimum_confidence": (
            REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE
        ),
        "train_feature_mean": mean,
        "train_feature_scale": scale,
        "normalized_train_features": normalized,
        "train_labels": labels,
        "train_sample_count": len(labels),
        "train_positive_count": sum(labels),
        "train_negative_count": sum(not label for label in labels),
        "latent_key_count": len(groups),
        "latent_conflicting_key_count": 0,
        "validation_fit_count": 0,
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "formal_holdout_payload_fit_count": 0,
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
    }
    _validate_state(state)
    return state


def _calibration_metrics(
    actor_model: Any,
    records: Sequence[
        tuple[Any, bool, bool, bool, tuple[str, ...]]
    ],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    if not records:
        raise RegionResourceV5CandidateError(
            "v5_calibration_metrics_records_unavailable"
        )
    labels = [bool(record[1]) for record in records]
    scores = [
        _score_feature(
            _actor_pooled_latent(actor_model, record[0]),
            state,
        )
        for record in records
    ]
    threshold = REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE
    passed = [score >= threshold for score in scores]
    positive_count = sum(labels)
    negative_count = len(labels) - positive_count
    if positive_count <= 0 or negative_count <= 0:
        raise RegionResourceV5CandidateError(
            "v5_metrics_require_positive_and_negative_labels"
        )
    positive_pass_count = sum(
        decision and label
        for decision, label in zip(passed, labels, strict=True)
    )
    negative_pass_count = sum(
        decision and not label
        for decision, label in zip(passed, labels, strict=True)
    )
    positive_margins = [
        score - threshold
        for score, decision, label in zip(
            scores, passed, labels, strict=True
        )
        if decision and label
    ]
    return {
        "sample_count": len(records),
        "target_positive_count": positive_count,
        "target_negative_count": negative_count,
        "positive_threshold_pass_count": positive_pass_count,
        "negative_threshold_pass_count": negative_pass_count,
        "positive_recall": positive_pass_count / positive_count,
        "negative_specificity": (
            negative_count - negative_pass_count
        )
        / negative_count,
        "minimum_positive_passing_margin": (
            min(positive_margins) if positive_margins else -1.0
        ),
        "confidence_minimum": min(scores),
        "confidence_mean": sum(scores) / len(scores),
        "confidence_maximum": max(scores),
        "fixed_minimum_confidence": threshold,
        "brier_score": sum(
            (score - float(label)) ** 2
            for score, label in zip(scores, labels, strict=True)
        )
        / len(scores),
    }


def _train_validation_overlap_diagnostic(
    actor_model: Any,
    train_records: Sequence[
        tuple[Any, bool, bool, bool, tuple[str, ...]]
    ],
    validation_records: Sequence[
        tuple[Any, bool, bool, bool, tuple[str, ...]]
    ],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure development-set overlap without fitting VALIDATION."""

    _validate_state(state)
    if not train_records or not validation_records:
        raise RegionResourceV5CandidateError(
            "v5_overlap_diagnostic_records_unavailable"
        )
    train_graph_labels: dict[str, set[bool]] = {}
    for record in train_records:
        key = _v4_confidence_observable_key(record[0])
        train_graph_labels.setdefault(key, set()).add(bool(record[1]))
    if any(len(labels) != 1 for labels in train_graph_labels.values()):
        raise RegionResourceV5CandidateError(
            "v5_overlap_train_graph_label_conflict"
        )

    train_latents = state["normalized_train_features"]
    train_labels = state["train_labels"]
    exact_epsilon = float(state["exact_match_epsilon"])
    nearest_distances: list[float] = []
    exact_graph_count = 0
    exact_latent_count = 0
    exact_graph_and_latent_count = 0
    graph_label_match_count = 0
    nearest_label_match_count = 0
    positive_exact_graph_count = 0
    positive_exact_latent_count = 0
    positive_count = 0

    for record in validation_records:
        label = bool(record[1])
        positive_count += int(label)
        graph_key = _v4_confidence_observable_key(record[0])
        graph_overlap = graph_key in train_graph_labels
        exact_graph_count += int(graph_overlap)
        if graph_overlap:
            graph_label_match_count += int(
                label in train_graph_labels[graph_key]
            )
            positive_exact_graph_count += int(label)

        feature = _actor_pooled_latent(actor_model, record[0])
        normalized = _normalize_feature(feature, state)
        distances = [
            (
                sqrt(
                    sum(
                        (
                            normalized[column]
                            - float(train_row[column])
                        )
                        ** 2
                        for column in range(len(normalized))
                    )
                ),
                index,
            )
            for index, train_row in enumerate(train_latents)
        ]
        nearest_distance, nearest_index = min(
            distances,
            key=lambda item: (item[0], item[1]),
        )
        nearest_distances.append(nearest_distance)
        latent_overlap = nearest_distance <= exact_epsilon
        exact_latent_count += int(latent_overlap)
        exact_graph_and_latent_count += int(
            graph_overlap and latent_overlap
        )
        positive_exact_latent_count += int(label and latent_overlap)
        nearest_label_match_count += int(
            bool(train_labels[nearest_index]) == label
        )

    ordered = sorted(nearest_distances)
    nonexact_lt_1e3 = sum(
        exact_epsilon < distance < 1.0e-3 for distance in ordered
    )
    ge_1e3_lt_1e1 = sum(
        1.0e-3 <= distance < 1.0e-1 for distance in ordered
    )
    ge_1e1 = sum(distance >= 1.0e-1 for distance in ordered)
    content = {
        "schema": REGION_RESOURCE_V5_OVERLAP_SCHEMA,
        "distance_space": (
            "TRAIN-standardized frozen-v4 actor pooled latent"
        ),
        "exact_overlap_epsilon": exact_epsilon,
        "train_record_count": len(train_records),
        "validation_record_count": len(validation_records),
        "validation_positive_count": positive_count,
        "exact_raw_graph_key_overlap_count": exact_graph_count,
        "exact_raw_graph_key_overlap_rate": (
            exact_graph_count / len(validation_records)
        ),
        "exact_latent_overlap_count": exact_latent_count,
        "exact_latent_overlap_rate": (
            exact_latent_count / len(validation_records)
        ),
        "exact_graph_and_latent_overlap_count": (
            exact_graph_and_latent_count
        ),
        "positive_exact_raw_graph_key_overlap_count": (
            positive_exact_graph_count
        ),
        "positive_exact_latent_overlap_count": (
            positive_exact_latent_count
        ),
        "nearest_train_label_match_count": (
            nearest_label_match_count
        ),
        "nearest_train_label_mismatch_count": (
            len(validation_records) - nearest_label_match_count
        ),
        "nearest_train_label_match_rate": (
            nearest_label_match_count / len(validation_records)
        ),
        "exact_graph_train_label_match_count": (
            graph_label_match_count
        ),
        "nearest_distance_bucket_counts": {
            "exact_le_1e_12": exact_latent_count,
            "nonexact_lt_1e_3": nonexact_lt_1e3,
            "ge_1e_3_lt_1e_1": ge_1e3_lt_1e1,
            "ge_1e_1": ge_1e1,
        },
        "nearest_distance_cumulative_counts": {
            "lt_1e_3_including_exact": sum(
                distance < 1.0e-3 for distance in ordered
            ),
            "lt_1e_1_including_exact": sum(
                distance < 1.0e-1 for distance in ordered
            ),
        },
        "nearest_distance_distribution": {
            "minimum": ordered[0],
            "mean": sum(ordered) / len(ordered),
            "p50_nearest_rank": _nearest_rank(ordered, 0.50),
            "p90_nearest_rank": _nearest_rank(ordered, 0.90),
            "p95_nearest_rank": _nearest_rank(ordered, 0.95),
            "maximum": ordered[-1],
        },
        "validation_fit_count": 0,
        "test_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "source_independence_available": False,
        "generalization_evidence_available": False,
        "classification": REGION_RESOURCE_V5_CANDIDATE_CLASSIFICATION,
        "blockers": list(REGION_RESOURCE_V5_INDEPENDENCE_BLOCKERS),
    }
    return _with_content_sha256(content)


def _normalize_feature(
    feature: Sequence[float],
    state: Mapping[str, Any],
) -> tuple[float, ...]:
    dimension = int(state["feature_dimension"])
    values = tuple(float(value) for value in feature)
    if len(values) != dimension or any(
        not isfinite(value) for value in values
    ):
        raise RegionResourceV5CandidateError(
            "v5_normalize_feature_invalid"
        )
    mean = tuple(float(value) for value in state["train_feature_mean"])
    scale = tuple(float(value) for value in state["train_feature_scale"])
    return tuple(
        (value - mean[index]) / scale[index]
        for index, value in enumerate(values)
    )


def _nearest_rank(
    ordered: Sequence[float],
    quantile: float,
) -> float:
    if (
        not ordered
        or not 0.0 < float(quantile) <= 1.0
        or any(not isfinite(float(value)) for value in ordered)
    ):
        raise RegionResourceV5CandidateError(
            "v5_nearest_rank_input_invalid"
        )
    index = max(0, ceil(float(quantile) * len(ordered)) - 1)
    return float(ordered[index])


def _actor_pooled_latent(actor_model: Any, graph: Any) -> tuple[float, ...]:
    """Recompute the frozen actor's online-observable pooled latent."""

    _require_torch()
    actor_model.eval()
    with torch.no_grad():
        node_hidden = actor_model.node_encoder(graph.node_features)
        edge_hidden = actor_model.edge_encoder(graph.edge_features)
        if graph.edge_count:
            source = graph.edge_index[0]
            target = graph.edge_index[1]
            for _ in range(actor_model.message_passing_steps):
                messages = actor_model.message_network(
                    torch.cat(
                        (
                            node_hidden[source],
                            node_hidden[target],
                            edge_hidden,
                        ),
                        dim=-1,
                    )
                )
                aggregate = torch.zeros_like(node_hidden)
                aggregate.index_add_(0, target, messages)
                degree = torch.zeros(
                    graph.node_count,
                    dtype=node_hidden.dtype,
                    device=node_hidden.device,
                )
                degree.index_add_(
                    0,
                    target,
                    torch.ones_like(target, dtype=node_hidden.dtype),
                )
                aggregate = (
                    aggregate / degree.clamp_min(1.0).unsqueeze(-1)
                )
                node_hidden = actor_model.node_update(
                    torch.cat((node_hidden, aggregate), dim=-1)
                )
        else:
            for _ in range(actor_model.message_passing_steps):
                node_hidden = actor_model.node_update(
                    torch.cat(
                        (node_hidden, torch.zeros_like(node_hidden)),
                        dim=-1,
                    )
                )
        pooled = node_hidden.mean(dim=0).detach().cpu()
    values = tuple(float(value) for value in pooled.tolist())
    if not values or any(not isfinite(value) for value in values):
        raise RegionResourceV5CandidateError(
            "v5_actor_pooled_latent_nonfinite"
        )
    return values


def _score_feature(
    feature: Sequence[float],
    state: Mapping[str, Any],
) -> float:
    _validate_state(state)
    dimension = int(state["feature_dimension"])
    normalized = _normalize_feature(feature, state)
    rows = state["normalized_train_features"]
    labels = state["train_labels"]
    distances = []
    for index, row in enumerate(rows):
        distance = sqrt(
            sum(
                (normalized[column] - float(row[column])) ** 2
                for column in range(dimension)
            )
        )
        distances.append((distance, index))
    distances.sort(key=lambda item: (item[0], item[1]))
    neighbours = distances[: min(int(state["neighbour_count"]), len(distances))]
    exact = [
        index
        for distance, index in neighbours
        if distance <= float(state["exact_match_epsilon"])
    ]
    if exact:
        score = sum(bool(labels[index]) for index in exact) / len(exact)
    else:
        weights = [
            1.0 / max(distance, REGION_RESOURCE_V5_EXACT_MATCH_EPSILON)
            for distance, _ in neighbours
        ]
        score = sum(
            weight * float(bool(labels[index]))
            for weight, (_, index) in zip(
                weights, neighbours, strict=True
            )
        ) / sum(weights)
    if not isfinite(score) or not 0.0 <= score <= 1.0:
        raise RegionResourceV5CandidateError(
            "v5_calibrated_confidence_invalid"
        )
    return score


def _validate_base_v4_identity(
    source_root: Path,
    loader: RegionResourceV4CandidateLoader,
) -> None:
    manifest_path = source_root / REGION_RESOURCE_V4_CANDIDATE_FILENAME
    expected = {
        "manifest_file": (
            _sha256_file(manifest_path),
            REGION_RESOURCE_V5_BASE_V4_MANIFEST_FILE_SHA256,
        ),
        "manifest_content": (
            loader.manifest.content_sha256,
            REGION_RESOURCE_V5_BASE_V4_MANIFEST_CONTENT_SHA256,
        ),
        "model_state": (
            loader.manifest.model_state_sha256,
            REGION_RESOURCE_V5_BASE_V4_MODEL_STATE_SHA256,
        ),
        "dataset": (
            loader.manifest.dataset_sha256,
            REGION_RESOURCE_V5_BASE_V4_DATASET_SHA256,
        ),
        "split": (
            loader.manifest.dataset_split_sha256,
            REGION_RESOURCE_V5_BASE_V4_SPLIT_SHA256,
        ),
    }
    for name, (actual, frozen) in expected.items():
        if actual != frozen:
            raise RegionResourceV5CandidateError(
                f"v5_base_v4_{name}_mismatch"
            )


def _validate_state(state: Mapping[str, Any]) -> None:
    if state.get("schema") != REGION_RESOURCE_V5_STATE_SCHEMA:
        raise RegionResourceV5CandidateError(
            "v5_calibration_state_schema_mismatch"
        )
    fixed = {
        "algorithm": "standardized_inverse_distance_knn",
        "fit_split": RegionLearningSplit.TRAIN.value,
        "neighbour_count": REGION_RESOURCE_V5_NEIGHBOUR_COUNT,
        "exact_match_epsilon": REGION_RESOURCE_V5_EXACT_MATCH_EPSILON,
        "fixed_minimum_confidence": (
            REGION_RESOURCE_V5_FIXED_MINIMUM_CONFIDENCE
        ),
        "feature_uses_target_identity": False,
        "feature_uses_source_identity": False,
        "feature_uses_truth_identifier": False,
        "feature_uses_future_outcome": False,
        "validation_fit_count": 0,
        "test_payload_read_count": 0,
        "test_payload_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "formal_holdout_payload_fit_count": 0,
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
    }
    for name, expected in fixed.items():
        actual = state.get(name)
        if isinstance(expected, float):
            valid = isclose(float(actual), expected)
        else:
            valid = actual == expected
        if not valid:
            raise RegionResourceV5CandidateError(
                f"v5_calibration_state_{name}_mismatch"
            )
    dimension = int(state.get("feature_dimension", 0))
    count = int(state.get("train_sample_count", 0))
    mean = state.get("train_feature_mean")
    scale = state.get("train_feature_scale")
    rows = state.get("normalized_train_features")
    labels = state.get("train_labels")
    if (
        dimension <= 0
        or count < REGION_RESOURCE_V5_NEIGHBOUR_COUNT
        or not isinstance(mean, list)
        or not isinstance(scale, list)
        or not isinstance(rows, list)
        or not isinstance(labels, list)
        or len(mean) != dimension
        or len(scale) != dimension
        or len(rows) != count
        or len(labels) != count
        or any(not isinstance(row, list) or len(row) != dimension for row in rows)
        or any(type(label) is not bool for label in labels)
        or any(not isfinite(float(value)) for value in mean)
        or any(
            not isfinite(float(value)) or float(value) <= 0.0
            for value in scale
        )
        or any(
            not isfinite(float(value)) for row in rows for value in row
        )
        or int(state.get("train_positive_count", -1)) != sum(labels)
        or int(state.get("train_negative_count", -1))
        != sum(not label for label in labels)
        or int(state.get("latent_conflicting_key_count", -1)) != 0
    ):
        raise RegionResourceV5CandidateError(
            "v5_calibration_state_shape_or_count_invalid"
        )


def _validate_summary(
    summary: Mapping[str, Any],
    *,
    gate: RegionResourceV5DevelopmentGate,
) -> None:
    _validate_closed_permissions(summary.get("permissions"))
    fixed = {
        "schema": REGION_RESOURCE_V5_SUMMARY_SCHEMA,
        "candidate_id": REGION_RESOURCE_V5_CANDIDATE_ID,
        "model_version": REGION_RESOURCE_V5_MODEL_VERSION,
        "neighbour_count": REGION_RESOURCE_V5_NEIGHBOUR_COUNT,
        "development_gate_passed": True,
        "independence_gate_passed": False,
        "independence_evidence_available": False,
        "generalization_evidence_available": False,
        "candidate_classification": (
            REGION_RESOURCE_V5_CANDIDATE_CLASSIFICATION
        ),
        "formal_holdout_completed": False,
        "runtime_preflight_completed": False,
        "registered": False,
        "production_permission_available": False,
        "d3_permission_available": False,
        "d7_permission_available": False,
        "development_only": True,
        "shadow_only": True,
        "admission_closed": True,
        "rule_fallback_required": True,
    }
    for name, expected in fixed.items():
        if summary.get(name) != expected:
            raise RegionResourceV5CandidateError(
                f"v5_calibration_summary_{name}_mismatch"
            )
    if summary.get("independence_blockers") != list(
        REGION_RESOURCE_V5_INDEPENDENCE_BLOCKERS
    ):
        raise RegionResourceV5CandidateError(
            "v5_calibration_summary_independence_blockers_mismatch"
        )
    _validate_overlap_diagnostic(
        _mapping(
            summary.get("train_validation_overlap_diagnostic"),
            "v5 train-validation overlap diagnostic",
        )
    )
    if (
        summary.get("development_gate_reasons") != []
        or summary.get("base_v4_tree_sha256_before")
        != summary.get("base_v4_tree_sha256_after")
        or summary.get("builder_source_sha256")
        != _sha256_file(Path(__file__).resolve())
        or summary.get("v3_registry_tree_sha256_before")
        != REGION_RESOURCE_V3_FROZEN_TREE_SHA256
        or summary.get("v3_registry_tree_sha256_after")
        != REGION_RESOURCE_V3_FROZEN_TREE_SHA256
    ):
        raise RegionResourceV5CandidateError(
            "v5_calibration_summary_immutability_mismatch"
        )
    accepted, reasons = evaluate_v5_development_gate(
        _mapping(summary.get("train_metrics"), "v5 train metrics"),
        _mapping(
            summary.get("validation_metrics"),
            "v5 validation metrics",
        ),
        _mapping(summary.get("data_usage"), "v5 data usage"),
        gate=gate,
    )
    if not accepted or reasons:
        raise RegionResourceV5CandidateError(
            "v5_calibration_summary_development_gate_mismatch"
        )


def _validate_overlap_diagnostic(value: Mapping[str, Any]) -> None:
    _verify_content_sha256(value, "v5_overlap_diagnostic")
    fixed = {
        "schema": REGION_RESOURCE_V5_OVERLAP_SCHEMA,
        "exact_overlap_epsilon": REGION_RESOURCE_V5_EXACT_MATCH_EPSILON,
        "validation_fit_count": 0,
        "test_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "source_independence_available": False,
        "generalization_evidence_available": False,
        "classification": REGION_RESOURCE_V5_CANDIDATE_CLASSIFICATION,
        "blockers": list(REGION_RESOURCE_V5_INDEPENDENCE_BLOCKERS),
    }
    for name, expected in fixed.items():
        actual = value.get(name)
        if isinstance(expected, float):
            valid = isclose(float(actual), expected)
        else:
            valid = actual == expected
        if not valid:
            raise RegionResourceV5CandidateError(
                f"v5_overlap_diagnostic_{name}_mismatch"
            )
    train_count = int(value.get("train_record_count", 0))
    validation_count = int(value.get("validation_record_count", 0))
    positive_count = int(value.get("validation_positive_count", -1))
    exact_graph_count = int(
        value.get("exact_raw_graph_key_overlap_count", -1)
    )
    exact_latent_count = int(value.get("exact_latent_overlap_count", -1))
    label_match_count = int(
        value.get("nearest_train_label_match_count", -1)
    )
    label_mismatch_count = int(
        value.get("nearest_train_label_mismatch_count", -1)
    )
    positive_exact_graph = int(
        value.get("positive_exact_raw_graph_key_overlap_count", -1)
    )
    positive_exact_latent = int(
        value.get("positive_exact_latent_overlap_count", -1)
    )
    buckets = _mapping(
        value.get("nearest_distance_bucket_counts"),
        "v5 nearest-distance buckets",
    )
    bucket_sum = sum(int(item) for item in buckets.values())
    if (
        train_count <= 0
        or validation_count <= 0
        or not 0 <= positive_count <= validation_count
        or not 0 <= exact_graph_count <= validation_count
        or not 0 <= exact_latent_count <= validation_count
        or label_match_count + label_mismatch_count != validation_count
        or not 0 <= positive_exact_graph <= positive_count
        or not 0 <= positive_exact_latent <= positive_count
        or bucket_sum != validation_count
        or exact_graph_count <= 0
        or exact_latent_count <= 0
    ):
        raise RegionResourceV5CandidateError(
            "v5_overlap_diagnostic_count_inconsistent"
        )
    if (
        not isclose(
            float(value.get("exact_raw_graph_key_overlap_rate", -1.0)),
            exact_graph_count / validation_count,
        )
        or not isclose(
            float(value.get("exact_latent_overlap_rate", -1.0)),
            exact_latent_count / validation_count,
        )
        or not isclose(
            float(value.get("nearest_train_label_match_rate", -1.0)),
            label_match_count / validation_count,
        )
    ):
        raise RegionResourceV5CandidateError(
            "v5_overlap_diagnostic_rate_inconsistent"
        )
    distribution = _mapping(
        value.get("nearest_distance_distribution"),
        "v5 nearest-distance distribution",
    )
    distance_values = tuple(float(item) for item in distribution.values())
    if any(not isfinite(item) or item < 0.0 for item in distance_values):
        raise RegionResourceV5CandidateError(
            "v5_overlap_diagnostic_distance_invalid"
        )


def _validate_closed_permissions(value: Any) -> None:
    mapping = _mapping(value, "v5 permissions")
    expected = RegionResourceV5Permissions().to_dict()
    if dict(mapping) != expected:
        raise RegionResourceV5CandidateError(
            "v5_production_permissions_not_closed"
        )


def _v5_registration_available() -> bool:
    values = (
        REGION_RESOURCE_V5_REGISTERED_MANIFEST_FILE_SHA256,
        REGION_RESOURCE_V5_REGISTERED_MANIFEST_CONTENT_SHA256,
        REGION_RESOURCE_V5_REGISTERED_STATE_SHA256,
    )
    if any(value is not None for value in values) and not all(
        value is not None for value in values
    ):
        raise RegionResourceV5CandidateError(
            "v5_registry_binding_partially_configured"
        )
    for value in values:
        if value is not None:
            _require_sha256(value, "v5 registered digest")
    return all(value is not None for value in values)


def _with_content_sha256(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    if "content_sha256" in payload:
        raise RegionResourceV5CandidateError(
            "v5_content_sha256_prepopulated"
        )
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def _verify_content_sha256(
    value: Mapping[str, Any],
    name: str,
) -> None:
    payload = dict(value)
    expected = payload.pop("content_sha256", None)
    _require_sha256(str(expected), f"{name} content SHA256")
    if _canonical_sha256(payload) != expected:
        raise RegionResourceV5CandidateError(
            f"{name}_content_sha256_mismatch"
        )


def _tree_sha256(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise RegionResourceV5CandidateError(
            "v5_immutable_tree_unavailable"
        )
    inventory: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RegionResourceV5CandidateError(
                "v5_immutable_tree_symlink_forbidden"
            )
        if path.is_file():
            inventory[str(path.relative_to(root))] = _sha256_file(path)
        elif not path.is_dir():
            raise RegionResourceV5CandidateError(
                "v5_immutable_tree_special_file_forbidden"
            )
    return _canonical_sha256(inventory)


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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RegionResourceV5CandidateError(
            f"v5_json_object_required:{path.name}"
        )
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            dict(value),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise RegionResourceV5CandidateError(f"{name} invalid")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegionResourceV5CandidateError(f"{name} must be a mapping")
    return value


def _require_torch() -> None:
    if torch is None:
        raise RegionResourceV5CandidateError(
            "v5 confidence candidate requires the optional torch dependency"
        )
