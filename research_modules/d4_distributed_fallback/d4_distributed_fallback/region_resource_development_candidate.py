"""Evidence-bound development candidate pipeline for D4 regional advice.

The pipeline is intentionally limited to behavior cloning, confidence
calibration, and isolated/shadow evaluation.  It never emits a qualified model,
assist authority, or a production adoption record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from math import isclose, isfinite
import os
from pathlib import Path
import random
import shutil
import tempfile
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

try:
    import torch
except ImportError:  # pragma: no cover - optional dependency guard
    torch = None

from .canonical_seed_split import (
    CanonicalRegionLearningDatasetView,
    audit_canonical_region_learning_split_view,
    load_canonical_region_learning_split_view,
)
from .region_resource import (
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceConsumptionView,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
)
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningDatasetManifest,
    RegionLearningFrame,
    RegionLearningSplit,
    finalize_region_learning_dataset,
    load_region_learning_dataset,
    stage_region_learning_episode,
)
from .region_resource_isolated_rollout import (
    REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
    REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
    RegionResourceIsolatedCandidateGate,
)
from .region_resource_learning import (
    MODEL_LIFECYCLE_DEVELOPMENT,
    MODEL_MAXIMUM_MODE_SHADOW,
    BehaviorCloningSample,
    LearnedRegionResourcePolicy,
    RegionFeatureBounds,
    RegionGraph,
    RegionResourceModelManifest,
    SharedRegionGraphActorCritic,
    load_region_resource_model_bundle,
    recommendation_to_policy_target,
    save_region_resource_model_bundle,
    snapshot_to_region_graph,
)
from .region_resource_runtime_ack import canonical_runtime_payload_sha256


REGION_RESOURCE_DEVELOPMENT_CANDIDATE_SCHEMA = (
    "d4-region-resource-development-candidate-v1"
)
REGION_RESOURCE_DEVELOPMENT_DATA_SCHEMA = (
    "d4-region-resource-development-data-evidence-v1"
)
REGION_RESOURCE_DEVELOPMENT_TRAINING_SCHEMA = (
    "d4-region-resource-development-training-evidence-v1"
)
REGION_RESOURCE_DEVELOPMENT_CALIBRATION_SCHEMA = (
    "d4-region-resource-development-calibration-evidence-v1"
)
REGION_RESOURCE_DEVELOPMENT_GATE_SCHEMA = (
    "d4-region-resource-development-gate-diagnostics-v1"
)
REGION_RESOURCE_DEVELOPMENT_CANDIDATE_FILENAME = (
    "development_candidate_manifest.json"
)
REGION_RESOURCE_DEVELOPMENT_CANDIDATE_REPORT = (
    "DEVELOPMENT_CANDIDATE_REPORT_CN.md"
)
REGION_RESOURCE_DEVELOPMENT_MODEL_VERSION = (
    "d4-region-a2-bc-calibrated-development-v2"
)
REGION_RESOURCE_DEVELOPMENT_CANDIDATE_ID = (
    "region_resource_a2_development_calibrated_20260726_v1"
)
REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN = 0.05
REGION_RESOURCE_RESERVED_EVALUATION_SEEDS = tuple(range(1000, 1020))
REGION_RESOURCE_CANONICAL_SPLIT_COUNTS = {
    "train": 60,
    "validation": 20,
    "test": 20,
}
REGION_RESOURCE_CANDIDATE_IMPLEMENTATION_FILES = (
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_learning.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_development_candidate.py",
    "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
    "region_resource_paired_intervention.py",
)
_ALLOWED_PROJECTION_NOTES = (":clipped_by_safety_projection",)
_SHA256_LENGTH = 64


class RegionResourceDevelopmentCandidateError(RuntimeError):
    """Stable fail-closed error at the development candidate boundary."""


@dataclass(frozen=True)
class RegionResourceDevelopmentCandidateConfig:
    random_seed: int = 20260726
    hidden_dim: int = 64
    message_passing_steps: int = 2
    epochs: int = 70
    early_stopping_patience: int = 12
    learning_rate: float = 8.0e-4
    weight_decay: float = 1.0e-5
    max_grad_norm: float = 1.0
    supplemental_repeat: int = 5
    nonzero_continuous_weight: float = 6.0
    positive_binary_weight: float = 8.0
    confidence_epochs: int = 50
    confidence_learning_rate: float = 2.0e-3
    calibration_bins: int = 10
    minimum_confidence: float = REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE
    latency_limit_ms: float = REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS
    ood_margin: float = REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN
    model_version: str = REGION_RESOURCE_DEVELOPMENT_MODEL_VERSION
    candidate_id: str = REGION_RESOURCE_DEVELOPMENT_CANDIDATE_ID
    device: str = "cpu"
    torch_num_threads: int = 1

    def __post_init__(self) -> None:
        for name in (
            "random_seed",
            "hidden_dim",
            "message_passing_steps",
            "epochs",
            "early_stopping_patience",
            "supplemental_repeat",
            "confidence_epochs",
            "calibration_bins",
            "torch_num_threads",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in (
            "learning_rate",
            "max_grad_norm",
            "nonzero_continuous_weight",
            "positive_binary_weight",
            "confidence_learning_rate",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if not isfinite(float(self.weight_decay)) or self.weight_decay < 0.0:
            raise ValueError("weight_decay must be finite and non-negative")
        if not isclose(
            float(self.minimum_confidence),
            REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("development candidate confidence threshold must remain 0.6")
        if not isclose(
            float(self.latency_limit_ms),
            REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("development candidate latency limit must remain 50 ms")
        if not isclose(
            float(self.ood_margin),
            REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("development candidate OOD margin must remain 0.05")
        if not self.model_version or not self.candidate_id:
            raise ValueError("candidate and model identities must not be empty")


@dataclass(frozen=True)
class RegionResourceDevelopmentCandidateManifest:
    candidate_id: str
    model_version: str
    bundle_manifest_sha256: str
    model_state_sha256: str
    composite_dataset_manifest_sha256: str
    composite_dataset_sha256: str
    composite_split_sha256: str
    formal_dataset_sha256: str
    formal_canonical_view_sha256: str
    supplemental_dataset_sha256: str
    supplemental_canonical_view_sha256: str
    implementation_sha256: str
    implementation_files: Mapping[str, str]
    evidence_files: Mapping[str, str]
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    calibration_seeds: tuple[int, ...]
    reserved_evaluation_seeds: tuple[int, ...]
    action_inventory: Mapping[str, int]
    calibration_sample_count: int
    calibration_gate_pass_count: int
    calibration_ood_sample_count: int
    calibration_ood_rejected_count: int
    minimum_confidence: float
    latency_limit_ms: float
    ood_margin: float
    lifecycle_stage: str = MODEL_LIFECYCLE_DEVELOPMENT
    maximum_advisor_mode: str = MODEL_MAXIMUM_MODE_SHADOW
    isolated_shadow_candidate: bool = True
    calibration_passed: bool = True
    formal_holdout_evaluated: bool = False
    assist_enabled: bool = False
    authority_enabled: bool = False
    ppo_enabled: bool = False
    actual_system_benefit_claimed: bool = False
    content_sha256: str = ""
    schema: str = REGION_RESOURCE_DEVELOPMENT_CANDIDATE_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != REGION_RESOURCE_DEVELOPMENT_CANDIDATE_SCHEMA:
            raise ValueError("unsupported development candidate schema")
        if not self.candidate_id or not self.model_version:
            raise ValueError("development candidate identity must not be empty")
        for name in (
            "bundle_manifest_sha256",
            "model_state_sha256",
            "composite_dataset_manifest_sha256",
            "composite_dataset_sha256",
            "composite_split_sha256",
            "formal_dataset_sha256",
            "formal_canonical_view_sha256",
            "supplemental_dataset_sha256",
            "supplemental_canonical_view_sha256",
            "implementation_sha256",
        ):
            _require_sha256(str(getattr(self, name)), name)
        implementation_files = {
            str(path): str(digest).lower()
            for path, digest in self.implementation_files.items()
        }
        evidence_files = {
            str(path): str(digest).lower()
            for path, digest in self.evidence_files.items()
        }
        if set(implementation_files) != set(
            REGION_RESOURCE_CANDIDATE_IMPLEMENTATION_FILES
        ):
            raise ValueError("candidate implementation file inventory is incomplete")
        if set(evidence_files) != {
            "data_manifest.json",
            "training_report.json",
            "calibration_report.json",
            "candidate_gate_diagnostics.json",
            "composite_dataset_manifest.json",
            REGION_RESOURCE_DEVELOPMENT_CANDIDATE_REPORT,
        }:
            raise ValueError("candidate evidence file inventory is incomplete")
        for name, inventory in (
            ("implementation_files", implementation_files),
            ("evidence_files", evidence_files),
        ):
            for path, digest in inventory.items():
                if Path(path).is_absolute() or ".." in Path(path).parts:
                    raise ValueError(f"{name} contains an unsafe path")
                _require_sha256(digest, f"{name}.{path}")
        if _sha256_json(implementation_files) != self.implementation_sha256:
            raise ValueError("candidate implementation aggregate SHA256 mismatch")
        object.__setattr__(self, "implementation_files", implementation_files)
        object.__setattr__(self, "evidence_files", evidence_files)

        split_catalogs = {
            "train": _canonical_seed_tuple(self.train_seeds),
            "validation": _canonical_seed_tuple(self.validation_seeds),
            "test": _canonical_seed_tuple(self.calibration_seeds),
        }
        if {
            name: len(values) for name, values in split_catalogs.items()
        } != REGION_RESOURCE_CANONICAL_SPLIT_COUNTS:
            raise ValueError("candidate split must remain canonical 60/20/20")
        if (
            set(split_catalogs["train"]) & set(split_catalogs["validation"])
            or set(split_catalogs["train"]) & set(split_catalogs["test"])
            or set(split_catalogs["validation"]) & set(split_catalogs["test"])
        ):
            raise ValueError("candidate split seed catalogs overlap")
        reserved = _canonical_seed_tuple(self.reserved_evaluation_seeds)
        if reserved != REGION_RESOURCE_RESERVED_EVALUATION_SEEDS:
            raise ValueError("candidate reserved evaluation seed catalog changed")
        if set.union(*(set(values) for values in split_catalogs.values())) & set(
            reserved
        ):
            raise ValueError("reserved evaluation seed entered candidate evidence")
        object.__setattr__(self, "train_seeds", split_catalogs["train"])
        object.__setattr__(self, "validation_seeds", split_catalogs["validation"])
        object.__setattr__(self, "calibration_seeds", split_catalogs["test"])
        object.__setattr__(self, "reserved_evaluation_seeds", reserved)

        inventory = {
            str(name): int(count) for name, count in self.action_inventory.items()
        }
        required_actions = {
            "action_count",
            "resource_quota_nonzero_count",
            "transfer_count",
            "hold_true_count",
            "request_replan_true_count",
        }
        if set(inventory) != required_actions:
            raise ValueError("candidate action inventory is incomplete")
        if inventory["action_count"] <= 0 or any(
            inventory[name] <= 0 for name in required_actions - {"action_count"}
        ):
            raise ValueError("candidate does not carry all required positive actions")
        object.__setattr__(self, "action_inventory", inventory)
        if int(self.calibration_sample_count) <= 0:
            raise ValueError("candidate calibration requires samples")
        if not 0 < int(self.calibration_gate_pass_count) <= int(
            self.calibration_sample_count
        ):
            raise ValueError("candidate requires a positive isolated gate sample")
        if int(self.calibration_ood_sample_count) <= 0 or int(
            self.calibration_ood_rejected_count
        ) != int(self.calibration_ood_sample_count):
            raise ValueError("candidate OOD calibration must fail closed")
        if not isclose(
            float(self.minimum_confidence),
            REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("candidate manifest lowered the confidence gate")
        if not isclose(
            float(self.latency_limit_ms),
            REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("candidate manifest changed the latency gate")
        if not isclose(
            float(self.ood_margin),
            REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("candidate manifest changed the OOD margin")
        if (
            self.lifecycle_stage != MODEL_LIFECYCLE_DEVELOPMENT
            or self.maximum_advisor_mode != MODEL_MAXIMUM_MODE_SHADOW
            or self.isolated_shadow_candidate is not True
            or self.calibration_passed is not True
            or self.formal_holdout_evaluated
            or self.assist_enabled
            or self.authority_enabled
            or self.ppo_enabled
            or self.actual_system_benefit_claimed
        ):
            raise ValueError("candidate manifest crossed the development boundary")
        expected_content_sha = _sha256_json(self.content_dict())
        if self.content_sha256 and self.content_sha256 != expected_content_sha:
            raise ValueError("development candidate content SHA256 mismatch")
        object.__setattr__(self, "content_sha256", expected_content_sha)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "model_version": self.model_version,
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "model_state_sha256": self.model_state_sha256,
            "composite_dataset_manifest_sha256": (
                self.composite_dataset_manifest_sha256
            ),
            "composite_dataset_sha256": self.composite_dataset_sha256,
            "composite_split_sha256": self.composite_split_sha256,
            "formal_dataset_sha256": self.formal_dataset_sha256,
            "formal_canonical_view_sha256": self.formal_canonical_view_sha256,
            "supplemental_dataset_sha256": self.supplemental_dataset_sha256,
            "supplemental_canonical_view_sha256": (
                self.supplemental_canonical_view_sha256
            ),
            "implementation_sha256": self.implementation_sha256,
            "implementation_files": dict(sorted(self.implementation_files.items())),
            "evidence_files": dict(sorted(self.evidence_files.items())),
            "train_seeds": list(self.train_seeds),
            "validation_seeds": list(self.validation_seeds),
            "calibration_seeds": list(self.calibration_seeds),
            "reserved_evaluation_seeds": list(self.reserved_evaluation_seeds),
            "action_inventory": dict(sorted(self.action_inventory.items())),
            "calibration_sample_count": int(self.calibration_sample_count),
            "calibration_gate_pass_count": int(self.calibration_gate_pass_count),
            "calibration_ood_sample_count": int(self.calibration_ood_sample_count),
            "calibration_ood_rejected_count": int(
                self.calibration_ood_rejected_count
            ),
            "minimum_confidence": float(self.minimum_confidence),
            "latency_limit_ms": float(self.latency_limit_ms),
            "ood_margin": float(self.ood_margin),
            "lifecycle_stage": self.lifecycle_stage,
            "maximum_advisor_mode": self.maximum_advisor_mode,
            "isolated_shadow_candidate": self.isolated_shadow_candidate,
            "calibration_passed": self.calibration_passed,
            "formal_holdout_evaluated": self.formal_holdout_evaluated,
            "assist_enabled": self.assist_enabled,
            "authority_enabled": self.authority_enabled,
            "ppo_enabled": self.ppo_enabled,
            "actual_system_benefit_claimed": self.actual_system_benefit_claimed,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.content_dict(), "content_sha256": self.content_sha256}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "RegionResourceDevelopmentCandidateManifest":
        expected = set(cls.__dataclass_fields__)
        if set(value) != expected:
            missing = sorted(expected - set(value))
            extra = sorted(set(value) - expected)
            raise ValueError(
                f"development candidate keys mismatch: missing={missing};extra={extra}"
            )
        payload = dict(value)
        for name in (
            "train_seeds",
            "validation_seeds",
            "calibration_seeds",
            "reserved_evaluation_seeds",
        ):
            payload[name] = tuple(int(seed) for seed in payload[name])
        return cls(**payload)


@dataclass(frozen=True)
class RegionResourceDevelopmentGateEvaluation:
    gate: RegionResourceIsolatedCandidateGate
    recommendation: RegionResourceRecommendation | None
    projected_recommendation: RegionResourceRecommendation | None
    consumption: RegionResourceConsumptionView | None


@dataclass(frozen=True)
class _CandidateSample:
    source_kind: str
    split: RegionLearningSplit
    seed: int
    scenario_id: str
    frame_index: int
    snapshot: RegionResourceSnapshot
    target_recommendation: RegionResourceRecommendation
    sample: BehaviorCloningSample


def evaluate_region_resource_development_gate(
    policy: LearnedRegionResourcePolicy,
    snapshot: RegionResourceSnapshot,
    *,
    minimum_confidence: float = REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
    latency_limit_ms: float = REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
    ood_margin: float = REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
    latency_override_ms: float | None = None,
    projector: DeterministicResourceProjector | None = None,
) -> RegionResourceDevelopmentGateEvaluation:
    """Evaluate one development candidate without creating an adoption record."""

    if not isclose(
        float(minimum_confidence),
        REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise ValueError("candidate gate confidence threshold must remain 0.6")
    if not isclose(
        float(latency_limit_ms),
        REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise ValueError("candidate gate latency limit must remain 50 ms")
    if not isclose(
        float(ood_margin),
        REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise ValueError("candidate gate OOD margin must remain 0.05")

    started = perf_counter()
    try:
        recommendation = policy.recommend_raw(snapshot)
        ood_passed = not policy.is_ood(snapshot, margin=float(ood_margin))
    except Exception as exc:
        measured = 1000.0 * (perf_counter() - started)
        latency = float(latency_override_ms) if latency_override_ms is not None else measured
        reason = (
            "candidate_output_nonfinite"
            if "non_finite" in str(exc).lower() or "nonfinite" in str(exc).lower()
            else f"candidate_inference_failed:{type(exc).__name__}"
        )
        gate = RegionResourceIsolatedCandidateGate(
            candidate_considered=False,
            candidate_id=None,
            candidate_payload_sha256=None,
            candidate_confidence=None,
            minimum_confidence=float(minimum_confidence),
            candidate_ood_passed=None,
            candidate_latency_ms=None,
            candidate_latency_limit_ms=float(latency_limit_ms),
            candidate_finite=None,
            candidate_failure_gate_passed=None,
            candidate_safety_projection_passed=None,
            gate_pass=False,
            rule_fallback=True,
            rejection_reasons=(reason, f"measured_latency_ms:{latency:.9f}"),
        )
        return RegionResourceDevelopmentGateEvaluation(gate, None, None, None)

    measured = 1000.0 * (perf_counter() - started)
    latency = float(latency_override_ms) if latency_override_ms is not None else measured
    finite = _recommendation_finite(recommendation)
    confidence_passed = finite and recommendation.confidence >= minimum_confidence
    latency_passed = isfinite(latency) and 0.0 <= latency <= latency_limit_ms
    failure_gate_passed = True
    safety_passed = False
    projected: RegionResourceRecommendation | None = None
    consumption: RegionResourceConsumptionView | None = None
    rejection_reasons: list[str] = []
    if not confidence_passed:
        rejection_reasons.append("candidate_low_confidence")
    if not ood_passed:
        rejection_reasons.append("candidate_ood_rejected")
    if not latency_passed:
        rejection_reasons.append("candidate_inference_timeout")
    if not finite:
        rejection_reasons.append("candidate_output_nonfinite")

    resolved_projector = projector or DeterministicResourceProjector()
    if confidence_passed and ood_passed and latency_passed and finite:
        try:
            projected = resolved_projector.project(snapshot, recommendation)
            advisory = resolved_projector.build_advisory_contract(snapshot, projected)
            evaluation_time = min(
                snapshot.timestamp_s + 1.0e-3,
                min(node.lease_expires_at_s for node in snapshot.regions) - 1.0e-9,
            )
            consumption = resolved_projector.validate_for_consumption(
                advisory,
                snapshot,
                evaluated_at_s=max(snapshot.timestamp_s, evaluation_time),
            )
            invalid_projection_notes = tuple(
                note
                for note in projected.projection_rejections
                if not note.endswith(_ALLOWED_PROJECTION_NOTES)
            )
            safety_passed = bool(
                not invalid_projection_notes
                and not advisory.publication_rejections
                and consumption.consumable
            )
            rejection_reasons.extend(
                f"candidate_projection_rejected:{note}"
                for note in invalid_projection_notes
            )
            rejection_reasons.extend(
                f"candidate_publication_rejected:{reason}"
                for reason in advisory.publication_rejections
            )
            rejection_reasons.extend(
                f"candidate_consumption_rejected:{reason}"
                for reason in consumption.rejection_reasons
            )
        except Exception as exc:
            rejection_reasons.append(
                f"candidate_projection_failed:{type(exc).__name__}"
            )
    else:
        rejection_reasons.append("candidate_threshold_or_finite_gate_rejected")
    if not safety_passed:
        rejection_reasons.append("candidate_safety_projection_rejected")

    gate_pass = all(
        (
            confidence_passed,
            ood_passed,
            latency_passed,
            finite,
            failure_gate_passed,
            safety_passed,
        )
    )
    gate = RegionResourceIsolatedCandidateGate(
        candidate_considered=True,
        candidate_id=(
            f"{recommendation.policy_version}:{recommendation.model_sha256}"
        ),
        candidate_payload_sha256=_diagnostic_payload_sha256(
            recommendation.to_dict(), finite=finite
        ),
        candidate_confidence=(
            float(recommendation.confidence)
            if isfinite(float(recommendation.confidence))
            and 0.0 <= float(recommendation.confidence) <= 1.0
            else 0.0
        ),
        minimum_confidence=float(minimum_confidence),
        candidate_ood_passed=bool(ood_passed),
        candidate_latency_ms=float(latency),
        candidate_latency_limit_ms=float(latency_limit_ms),
        candidate_finite=bool(finite),
        candidate_failure_gate_passed=failure_gate_passed,
        candidate_safety_projection_passed=safety_passed,
        gate_pass=gate_pass,
        rule_fallback=not gate_pass,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
    )
    return RegionResourceDevelopmentGateEvaluation(
        gate=gate,
        recommendation=recommendation,
        projected_recommendation=projected,
        consumption=consumption,
    )


def load_region_resource_development_candidate_manifest(
    candidate_root: str | Path,
    *,
    expected_manifest_sha256: str | None = None,
    verify_current_implementation: bool = True,
) -> RegionResourceDevelopmentCandidateManifest:
    """Load and verify every content-addressed development candidate artifact."""

    root = Path(candidate_root)
    manifest_path = root / REGION_RESOURCE_DEVELOPMENT_CANDIDATE_FILENAME
    if root.is_symlink() or manifest_path.is_symlink():
        raise RegionResourceDevelopmentCandidateError(
            "development_candidate_symlink_forbidden"
        )
    try:
        actual_manifest_sha = _sha256_file(manifest_path)
    except OSError as exc:
        raise RegionResourceDevelopmentCandidateError(
            "development_candidate_manifest_unavailable"
        ) from exc
    if expected_manifest_sha256 is not None:
        _require_sha256(expected_manifest_sha256, "expected_manifest_sha256")
        if actual_manifest_sha != expected_manifest_sha256:
            raise RegionResourceDevelopmentCandidateError(
                "development_candidate_manifest_sha256_mismatch"
            )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = RegionResourceDevelopmentCandidateManifest.from_mapping(payload)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise RegionResourceDevelopmentCandidateError(
            f"development_candidate_manifest_invalid:{type(exc).__name__}"
        ) from exc
    if root.name != manifest.candidate_id:
        raise RegionResourceDevelopmentCandidateError(
            "development_candidate_directory_identity_mismatch"
        )
    for relative_path, expected_sha in manifest.evidence_files.items():
        path = root / relative_path
        if path.is_symlink() or _sha256_file(path) != expected_sha:
            raise RegionResourceDevelopmentCandidateError(
                f"development_candidate_evidence_mismatch:{relative_path}"
            )
    bundle = root / "bundle"
    if (
        _sha256_file(bundle / "manifest.json")
        != manifest.bundle_manifest_sha256
        or _sha256_file(bundle / "state_dict.pt") != manifest.model_state_sha256
    ):
        raise RegionResourceDevelopmentCandidateError(
            "development_candidate_bundle_binding_mismatch"
        )
    if verify_current_implementation:
        repository_root = Path(__file__).resolve().parents[3]
        observed = {
            relative_path: _sha256_file(repository_root / relative_path)
            for relative_path in manifest.implementation_files
        }
        if observed != dict(manifest.implementation_files):
            raise RegionResourceDevelopmentCandidateError(
                "development_candidate_implementation_lineage_mismatch"
            )
    return manifest


def build_region_resource_development_candidate(
    formal_dataset_dir: str | Path,
    supplemental_dataset_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    output_dir: str | Path,
    tracked_report_dir: str | Path | None = None,
    config: RegionResourceDevelopmentCandidateConfig | None = None,
    replace_output: bool = False,
    replace_tracked_report: bool = False,
) -> dict[str, Any]:
    """Build one calibrated development bundle and strict isolated evidence."""

    _require_torch()
    resolved = config or RegionResourceDevelopmentCandidateConfig()
    destination = Path(output_dir).resolve()
    if destination.name != resolved.candidate_id:
        raise RegionResourceDevelopmentCandidateError(
            "output directory name must equal candidate_id"
        )
    if destination.exists() and not replace_output:
        raise RegionResourceDevelopmentCandidateError(
            f"candidate output already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    )
    started = perf_counter()
    try:
        formal_view = load_canonical_region_learning_split_view(
            formal_dataset_dir,
            shared_registry_path=shared_seed_registry_path,
            training_seed_registry_path=training_seed_registry_path,
        )
        supplemental_view = load_canonical_region_learning_split_view(
            supplemental_dataset_dir,
            shared_registry_path=shared_seed_registry_path,
            training_seed_registry_path=training_seed_registry_path,
        )
        formal_audit = audit_canonical_region_learning_split_view(formal_view)
        supplemental_audit = audit_canonical_region_learning_split_view(
            supplemental_view
        )
        _validate_canonical_view(formal_view, formal_audit, expected_episodes=900)
        _validate_canonical_view(
            supplemental_view, supplemental_audit, expected_episodes=100
        )

        composite_dataset = _build_composite_dataset(
            formal_view,
            supplemental_view,
            staging / "composite_dataset_staging",
            staging / "composite_dataset",
        )
        composite_manifest_path = staging / "composite_dataset" / "manifest.json"
        shutil.copy2(
            composite_manifest_path, staging / "composite_dataset_manifest.json"
        )
        composite_view = load_canonical_region_learning_split_view(
            composite_dataset,
            shared_registry_path=shared_seed_registry_path,
            training_seed_registry_path=training_seed_registry_path,
        )
        _validate_canonical_view(
            composite_view,
            audit_canonical_region_learning_split_view(composite_view),
            expected_episodes=1000,
        )

        device = _resolve_device(resolved.device)
        torch.set_num_threads(int(resolved.torch_num_threads))
        _seed_everything(resolved.random_seed)
        records = _candidate_records(formal_view, supplemental_view, device=device)
        split_records = {
            split: tuple(record for record in records if record.split == split)
            for split in RegionLearningSplit
        }
        model, training_report = _train_action_model(
            split_records, resolved, device=device
        )
        feature_bounds = RegionFeatureBounds.from_graphs(
            [record.sample.graph for record in split_records[RegionLearningSplit.TRAIN]]
        )
        confidence_report = _fit_confidence_head(
            model,
            split_records[RegionLearningSplit.VALIDATION],
            feature_bounds,
            resolved,
            device=device,
        )

        action_inventory = _target_action_inventory(records)
        bundle_dir = staging / "bundle"
        bundle_manifest = save_region_resource_model_bundle(
            model,
            bundle_dir,
            model_version=resolved.model_version,
            training_graphs=tuple(
                record.sample.graph
                for record in split_records[RegionLearningSplit.TRAIN]
            ),
            created_at_utc="2026-07-26T00:00:00Z",
            training_dataset_manifest=composite_dataset.manifest,
            lifecycle_stage=MODEL_LIFECYCLE_DEVELOPMENT,
            maximum_advisor_mode=MODEL_MAXIMUM_MODE_SHADOW,
            reward_evidence_available=False,
            final_holdout_seed_count=0,
            action_diversity_sufficient=True,
            strategy_capability_claim_allowed=False,
            target_action_inventory=action_inventory,
            admission_reasons=(
                "development_bundle",
                "isolated_shadow_only",
                "reward_evidence_unavailable",
                "formal_holdout_not_evaluated",
                "assist_not_requested",
                "authority_not_requested",
            ),
        )
        loaded_bundle = load_region_resource_model_bundle(
            bundle_dir,
            expected_model_version=resolved.model_version,
            expected_state_dict_sha256=bundle_manifest.state_dict_sha256,
            map_location=device,
            require_training_dataset_manifest=True,
        )
        calibration_report, gate_diagnostics = _evaluate_calibration_split(
            loaded_bundle.manifest,
            loaded_bundle.model,
            split_records[RegionLearningSplit.TEST],
            feature_bounds,
            resolved,
        )
        data_manifest = _data_evidence(
            formal_view,
            supplemental_view,
            composite_view,
            action_inventory=action_inventory,
        )
        training_payload = {
            "schema": REGION_RESOURCE_DEVELOPMENT_TRAINING_SCHEMA,
            "config": asdict(resolved),
            "action_training": training_report,
            "confidence_fitting": confidence_report,
            "formal_holdout_evaluated": False,
            "assist_enabled": False,
            "authority_enabled": False,
            "ppo_enabled": False,
        }
        _write_json(staging / "data_manifest.json", data_manifest)
        _write_json(staging / "training_report.json", training_payload)
        _write_json(staging / "calibration_report.json", calibration_report)
        _write_json(
            staging / "candidate_gate_diagnostics.json", gate_diagnostics
        )
        (staging / REGION_RESOURCE_DEVELOPMENT_CANDIDATE_REPORT).write_text(
            _render_candidate_report(
                data_manifest,
                training_payload,
                calibration_report,
                gate_diagnostics,
                bundle_manifest,
            ),
            encoding="utf-8",
        )

        implementation_files = _implementation_hashes()
        evidence_files = {
            name: _sha256_file(staging / name)
            for name in (
                "data_manifest.json",
                "training_report.json",
                "calibration_report.json",
                "candidate_gate_diagnostics.json",
                "composite_dataset_manifest.json",
                REGION_RESOURCE_DEVELOPMENT_CANDIDATE_REPORT,
            )
        }
        manifest = RegionResourceDevelopmentCandidateManifest(
            candidate_id=resolved.candidate_id,
            model_version=resolved.model_version,
            bundle_manifest_sha256=_sha256_file(bundle_dir / "manifest.json"),
            model_state_sha256=bundle_manifest.state_dict_sha256,
            composite_dataset_manifest_sha256=_sha256_file(
                staging / "composite_dataset_manifest.json"
            ),
            composite_dataset_sha256=composite_dataset.manifest.dataset_sha256,
            composite_split_sha256=composite_dataset.manifest.split.split_sha256,
            formal_dataset_sha256=formal_view.binding.source_dataset_sha256,
            formal_canonical_view_sha256=formal_view.binding.view_sha256,
            supplemental_dataset_sha256=(
                supplemental_view.binding.source_dataset_sha256
            ),
            supplemental_canonical_view_sha256=(
                supplemental_view.binding.view_sha256
            ),
            implementation_sha256=_sha256_json(implementation_files),
            implementation_files=implementation_files,
            evidence_files=evidence_files,
            train_seeds=formal_view.binding.train_seeds,
            validation_seeds=formal_view.binding.validation_seeds,
            calibration_seeds=formal_view.binding.test_seeds,
            reserved_evaluation_seeds=REGION_RESOURCE_RESERVED_EVALUATION_SEEDS,
            action_inventory=action_inventory,
            calibration_sample_count=calibration_report["sample_count"],
            calibration_gate_pass_count=calibration_report["gate"]["pass_count"],
            calibration_ood_sample_count=calibration_report["ood"]["sample_count"],
            calibration_ood_rejected_count=calibration_report["ood"][
                "hard_gate_rejected_count"
            ],
            minimum_confidence=resolved.minimum_confidence,
            latency_limit_ms=resolved.latency_limit_ms,
            ood_margin=resolved.ood_margin,
        )
        _write_json(
            staging / REGION_RESOURCE_DEVELOPMENT_CANDIDATE_FILENAME,
            manifest.to_dict(),
        )
        shutil.rmtree(staging / "composite_dataset_staging", ignore_errors=True)
        if destination.exists():
            if not replace_output:
                raise RegionResourceDevelopmentCandidateError(
                    f"candidate output appeared during build: {destination}"
                )
            shutil.rmtree(destination)
        os.replace(staging, destination)
        loaded_manifest = load_region_resource_development_candidate_manifest(
            destination,
            expected_manifest_sha256=_sha256_file(
                destination / REGION_RESOURCE_DEVELOPMENT_CANDIDATE_FILENAME
            ),
        )
        tracked = None
        if tracked_report_dir is not None:
            tracked = publish_region_resource_development_candidate_evidence(
                destination,
                tracked_report_dir,
                replace_output=replace_tracked_report,
            )
        return {
            "output_dir": str(destination),
            "candidate_manifest": loaded_manifest.to_dict(),
            "calibration_report": calibration_report,
            "gate_diagnostics": gate_diagnostics,
            "tracked_report": tracked,
            "duration_s": perf_counter() - started,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def publish_region_resource_development_candidate_evidence(
    candidate_root: str | Path,
    tracked_report_dir: str | Path,
    *,
    replace_output: bool = False,
) -> dict[str, Any]:
    """Publish bounded text/JSON evidence while leaving weights in outputs."""

    source = Path(candidate_root).resolve()
    destination = Path(tracked_report_dir).resolve()
    manifest = load_region_resource_development_candidate_manifest(source)
    names = (
        REGION_RESOURCE_DEVELOPMENT_CANDIDATE_FILENAME,
        "data_manifest.json",
        "training_report.json",
        "calibration_report.json",
        "candidate_gate_diagnostics.json",
        REGION_RESOURCE_DEVELOPMENT_CANDIDATE_REPORT,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    )
    try:
        for name in names:
            shutil.copy2(source / name, staging / name)
        locator = {
            "schema": "d4-region-resource-development-candidate-locator-v1",
            "candidate_id": manifest.candidate_id,
            "model_version": manifest.model_version,
            "candidate_manifest_sha256": _sha256_file(
                source / REGION_RESOURCE_DEVELOPMENT_CANDIDATE_FILENAME
            ),
            "model_state_sha256": manifest.model_state_sha256,
            "local_candidate_locator": (
                Path("research_modules/d4_distributed_fallback/outputs")
                / manifest.candidate_id
            ).as_posix(),
            "weights_tracked_by_git": False,
            "lifecycle_stage": MODEL_LIFECYCLE_DEVELOPMENT,
            "maximum_advisor_mode": MODEL_MAXIMUM_MODE_SHADOW,
            "assist_enabled": False,
            "authority_enabled": False,
        }
        _write_json(staging / "LOCAL_CANDIDATE_LOCATION.json", locator)
        tracked_manifest = {
            "schema": "d4-region-resource-development-candidate-tracked-evidence-v1",
            "candidate_id": manifest.candidate_id,
            "files": {
                path.name: _sha256_file(path)
                for path in sorted(staging.iterdir())
                if path.is_file()
            },
        }
        _write_json(staging / "manifest.json", tracked_manifest)
        if destination.exists():
            if not replace_output:
                raise RegionResourceDevelopmentCandidateError(
                    f"tracked candidate evidence already exists: {destination}"
                )
            shutil.rmtree(destination)
        os.replace(staging, destination)
        return tracked_manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _build_composite_dataset(
    formal_view: CanonicalRegionLearningDatasetView,
    supplemental_view: CanonicalRegionLearningDatasetView,
    staging_dir: Path,
    dataset_dir: Path,
) -> LoadedRegionLearningDataset:
    for episode in (*formal_view.episode_records, *supplemental_view.episode_records):
        stage_region_learning_episode(staging_dir, episode.source, episode.frames)
    finalize_region_learning_dataset(
        staging_dir,
        dataset_dir,
        created_at_utc="2026-07-26T00:00:00Z",
        split_seed=20260720,
        minimum_unseen_seeds=40,
        train_fraction=0.60,
        validation_fraction=0.20,
        minimum_unique_seeds=100,
    )
    return load_region_learning_dataset(dataset_dir)


def _candidate_records(
    formal_view: CanonicalRegionLearningDatasetView,
    supplemental_view: CanonicalRegionLearningDatasetView,
    *,
    device: Any,
) -> tuple[_CandidateSample, ...]:
    records: list[_CandidateSample] = []
    for source_kind, view in (
        ("formal", formal_view),
        ("supplemental", supplemental_view),
    ):
        for episode in view.episode_records:
            for frame in episode.frames:
                target = frame.target.recommendation
                if target is None:
                    raise RegionResourceDevelopmentCandidateError(
                        "candidate corpus contains an unavailable target"
                    )
                graph = snapshot_to_region_graph(frame.snapshot, device=device)
                records.append(
                    _CandidateSample(
                        source_kind=source_kind,
                        split=episode.split,
                        seed=int(episode.source.seed),
                        scenario_id=episode.source.scenario_id,
                        frame_index=int(frame.frame_index),
                        snapshot=frame.snapshot,
                        target_recommendation=target,
                        sample=BehaviorCloningSample(
                            graph=graph,
                            target=recommendation_to_policy_target(
                                frame.snapshot, graph, target
                            ),
                        ),
                    )
                )
    return tuple(records)


def _train_action_model(
    split_records: Mapping[RegionLearningSplit, Sequence[_CandidateSample]],
    config: RegionResourceDevelopmentCandidateConfig,
    *,
    device: Any,
) -> tuple[SharedRegionGraphActorCritic, dict[str, Any]]:
    model = SharedRegionGraphActorCritic(
        hidden_dim=config.hidden_dim,
        message_passing_steps=config.message_passing_steps,
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    train_records = tuple(split_records[RegionLearningSplit.TRAIN])
    formal_train = tuple(
        record for record in train_records if record.source_kind == "formal"
    )
    supplemental_train = tuple(
        record for record in train_records if record.source_kind == "supplemental"
    )
    if not formal_train or not supplemental_train:
        raise RegionResourceDevelopmentCandidateError(
            "candidate training requires both formal and supplemental samples"
        )
    schedule = formal_train + supplemental_train * int(config.supplemental_repeat)
    best_state: dict[str, Any] | None = None
    best_validation = float("inf")
    best_epoch = 0
    stale_epochs = 0
    history: list[dict[str, float | int]] = []
    started = perf_counter()
    generator = random.Random(config.random_seed)
    for epoch in range(1, config.epochs + 1):
        model.train()
        order = list(range(len(schedule)))
        generator.shuffle(order)
        total_loss = 0.0
        for index in order:
            record = schedule[index]
            optimizer.zero_grad()
            loss = _balanced_action_loss(model, record.sample, config)
            if not torch.isfinite(loss):
                raise RegionResourceDevelopmentCandidateError(
                    "candidate action training loss became non-finite"
                )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()
            total_loss += float(loss.detach().cpu())
        validation = _group_balanced_loss(
            model,
            split_records[RegionLearningSplit.VALIDATION],
            config,
        )
        history.append(
            {
                "epoch": epoch,
                "train_loss": total_loss / len(order),
                "validation_loss": validation,
            }
        )
        if validation < best_validation - 1.0e-8:
            best_validation = validation
            best_epoch = epoch
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= config.early_stopping_patience:
                break
    if best_state is None:
        raise RegionResourceDevelopmentCandidateError(
            "candidate action training produced no checkpoint"
        )
    model.load_state_dict(best_state, strict=True)
    model.to(device)
    model.eval()
    return model, {
        "epochs_completed": len(history),
        "best_epoch": best_epoch,
        "best_validation_loss": best_validation,
        "duration_s": perf_counter() - started,
        "formal_train_sample_count": len(formal_train),
        "supplemental_train_sample_count": len(supplemental_train),
        "supplemental_repeat": int(config.supplemental_repeat),
        "effective_train_sample_count_per_epoch": len(schedule),
        "history": history,
    }


def _balanced_action_loss(
    model: SharedRegionGraphActorCritic,
    sample: BehaviorCloningSample,
    config: RegionResourceDevelopmentCandidateConfig,
) -> Any:
    output = model(sample.graph)
    target = sample.target
    continuous_error = (output.node_mean[:, :3] - target.node_continuous) ** 2
    continuous_weights = torch.where(
        target.node_continuous[:, :1].abs() > 1.0e-9,
        torch.full_like(
            target.node_continuous[:, :1], config.nonzero_continuous_weight
        ),
        torch.ones_like(target.node_continuous[:, :1]),
    )
    continuous_weights = torch.cat(
        (continuous_weights, torch.ones_like(target.node_continuous[:, 1:])),
        dim=1,
    )
    continuous_loss = (continuous_error * continuous_weights).mean()
    binary_loss = torch.nn.functional.binary_cross_entropy_with_logits(
        output.node_mean[:, 3:],
        target.node_binary,
        pos_weight=torch.full(
            (target.node_binary.shape[1],),
            config.positive_binary_weight,
            dtype=target.node_binary.dtype,
            device=target.node_binary.device,
        ),
    )
    if sample.graph.edge_count:
        edge_error = (output.edge_mean - target.edge_continuous) ** 2
        edge_weights = torch.where(
            target.edge_continuous.abs() > 1.0e-9,
            torch.full_like(
                target.edge_continuous, config.nonzero_continuous_weight
            ),
            torch.ones_like(target.edge_continuous),
        )
        edge_loss = (edge_error * edge_weights).mean()
    else:
        edge_loss = output.node_mean.sum() * 0.0
    return continuous_loss + binary_loss + edge_loss


def _group_balanced_loss(
    model: SharedRegionGraphActorCritic,
    records: Sequence[_CandidateSample],
    config: RegionResourceDevelopmentCandidateConfig,
) -> float:
    model.eval()
    values: dict[str, list[float]] = {"formal": [], "supplemental": []}
    with torch.no_grad():
        for record in records:
            loss = _balanced_action_loss(model, record.sample, config)
            values[record.source_kind].append(float(loss.detach().cpu()))
    if any(not group for group in values.values()):
        raise RegionResourceDevelopmentCandidateError(
            "validation split lost a candidate source group"
        )
    return sum(sum(group) / len(group) for group in values.values()) / len(values)


def _fit_confidence_head(
    model: SharedRegionGraphActorCritic,
    validation_records: Sequence[_CandidateSample],
    feature_bounds: RegionFeatureBounds,
    config: RegionResourceDevelopmentCandidateConfig,
    *,
    device: Any,
) -> dict[str, Any]:
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in model.confidence_head.parameters():
        parameter.requires_grad_(True)
    optimizer = torch.optim.Adam(
        model.confidence_head.parameters(), lr=config.confidence_learning_rate
    )
    positive_graphs = tuple(record.sample.graph for record in validation_records)
    negative_graphs = tuple(
        _make_ood_graph(graph, feature_bounds) for graph in positive_graphs
    )
    if not positive_graphs:
        raise RegionResourceDevelopmentCandidateError(
            "confidence fitting requires validation samples"
        )
    history: list[float] = []
    generator = random.Random(config.random_seed + 1)
    for _ in range(config.confidence_epochs):
        pairs = [(graph, 1.0) for graph in positive_graphs] + [
            (graph, 0.0) for graph in negative_graphs
        ]
        generator.shuffle(pairs)
        epoch_loss = 0.0
        model.train()
        for graph, label in pairs:
            optimizer.zero_grad()
            probability = model(graph).confidence.clamp(1.0e-6, 1.0 - 1.0e-6)
            target = torch.tensor(label, dtype=probability.dtype, device=device)
            loss = torch.nn.functional.binary_cross_entropy(probability, target)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach().cpu())
        history.append(epoch_loss / len(pairs))
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    model.eval()
    return {
        "fit_split": "validation",
        "positive_sample_count": len(positive_graphs),
        "synthetic_ood_sample_count": len(negative_graphs),
        "epochs": config.confidence_epochs,
        "final_loss": history[-1],
        "history": history,
        "threshold_tuned": False,
        "fixed_minimum_confidence": config.minimum_confidence,
        "reserved_evaluation_seed_use_count": 0,
    }


def _evaluate_calibration_split(
    manifest: RegionResourceModelManifest,
    model: SharedRegionGraphActorCritic,
    records: Sequence[_CandidateSample],
    feature_bounds: RegionFeatureBounds,
    config: RegionResourceDevelopmentCandidateConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = LearnedRegionResourcePolicy(model, manifest)
    gates: list[RegionResourceIsolatedCandidateGate] = []
    confidences: list[float] = []
    latencies: list[float] = []
    rejection_counts: dict[str, int] = {}
    positive_examples: list[dict[str, Any]] = []
    rejected_examples: list[dict[str, Any]] = []
    predicted_action_inventory = {
        "action_count": 0,
        "resource_quota_nonzero_count": 0,
        "transfer_count": 0,
        "hold_true_count": 0,
        "request_replan_true_count": 0,
    }
    action_quality = {
        "action_count": 0,
        "quota_exact_count": 0,
        "hold_correct_count": 0,
        "request_replan_correct_count": 0,
        "transfer_frame_count": 0,
        "transfer_frame_exact_count": 0,
    }
    for record in records:
        evaluation = evaluate_region_resource_development_gate(
            policy,
            record.snapshot,
            minimum_confidence=config.minimum_confidence,
            latency_limit_ms=config.latency_limit_ms,
            ood_margin=config.ood_margin,
        )
        gate = evaluation.gate
        gates.append(gate)
        if gate.candidate_confidence is not None:
            confidences.append(gate.candidate_confidence)
        if gate.candidate_latency_ms is not None:
            latencies.append(gate.candidate_latency_ms)
        for reason in gate.rejection_reasons:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        example = {
            "source_kind": record.source_kind,
            "scenario_id": record.scenario_id,
            "seed": record.seed,
            "frame_index": record.frame_index,
            "confidence": gate.candidate_confidence,
            "latency_ms": gate.candidate_latency_ms,
            "gate_pass": gate.gate_pass,
            "rejection_reasons": list(gate.rejection_reasons),
        }
        if gate.gate_pass and len(positive_examples) < 12:
            positive_examples.append(example)
        elif not gate.gate_pass and len(rejected_examples) < 12:
            rejected_examples.append(example)
        if evaluation.projected_recommendation is not None:
            predicted = evaluation.projected_recommendation
            _accumulate_action_inventory(predicted_action_inventory, predicted)
            _accumulate_action_quality(
                action_quality, predicted, record.target_recommendation
            )

    ood_confidences: list[float] = []
    ood_rejected = 0
    model.eval()
    with torch.no_grad():
        for record in records:
            graph = _make_ood_graph(record.sample.graph, feature_bounds)
            confidence = float(model(graph).confidence.detach().cpu())
            ood_confidences.append(confidence)
            ood_rejected += int(not feature_bounds.contains(graph, margin=config.ood_margin))
    labels = [1.0] * len(confidences) + [0.0] * len(ood_confidences)
    probabilities = confidences + ood_confidences
    calibration = _calibration_metrics(
        labels, probabilities, bins=config.calibration_bins
    )
    latency_summary = _distribution(latencies)
    gate_pass_count = sum(gate.gate_pass for gate in gates)
    calibration_report = {
        "schema": REGION_RESOURCE_DEVELOPMENT_CALIBRATION_SCHEMA,
        "split": "test_as_independent_calibration",
        "calibration_seed_count": len({record.seed for record in records}),
        "calibration_seeds": sorted({record.seed for record in records}),
        "sample_count": len(records),
        "reserved_evaluation_seed_use_count": len(
            {record.seed for record in records}
            & set(REGION_RESOURCE_RESERVED_EVALUATION_SEEDS)
        ),
        "confidence": _distribution(confidences),
        "latency_ms": latency_summary,
        "gate": {
            "minimum_confidence": config.minimum_confidence,
            "latency_limit_ms": config.latency_limit_ms,
            "pass_count": gate_pass_count,
            "reject_count": len(gates) - gate_pass_count,
            "pass_rate": gate_pass_count / len(gates),
            "rejection_counts": dict(sorted(rejection_counts.items())),
        },
        "ood": {
            "margin": config.ood_margin,
            "sample_count": len(ood_confidences),
            "hard_gate_rejected_count": ood_rejected,
            "hard_gate_rejection_rate": ood_rejected / len(ood_confidences),
            "confidence": _distribution(ood_confidences),
        },
        "calibration": calibration,
        "predicted_action_inventory": predicted_action_inventory,
        "action_quality": {
            **action_quality,
            "quota_exact_rate": _rate(
                action_quality["quota_exact_count"],
                action_quality["action_count"],
            ),
            "hold_accuracy": _rate(
                action_quality["hold_correct_count"],
                action_quality["action_count"],
            ),
            "request_replan_accuracy": _rate(
                action_quality["request_replan_correct_count"],
                action_quality["action_count"],
            ),
            "transfer_frame_exact_rate": _rate(
                action_quality["transfer_frame_exact_count"],
                action_quality["transfer_frame_count"],
            ),
        },
        "threshold_tuned_on_calibration_split": False,
        "formal_holdout_evaluated": False,
        "assist_eligible": False,
        "actual_system_benefit_evidence": False,
    }
    required_predicted_actions = all(
        predicted_action_inventory[name] > 0
        for name in (
            "resource_quota_nonzero_count",
            "transfer_count",
            "hold_true_count",
            "request_replan_true_count",
        )
    )
    calibration_report["development_candidate_gate"] = {
        "passed": bool(
            gate_pass_count > 0
            and latency_summary["p95"] <= config.latency_limit_ms
            and ood_rejected == len(ood_confidences)
            and required_predicted_actions
            and calibration_report["reserved_evaluation_seed_use_count"] == 0
        ),
        "required_predicted_actions_present": required_predicted_actions,
        "positive_gate_sample_available": gate_pass_count > 0,
        "latency_p95_passed": latency_summary["p95"] <= config.latency_limit_ms,
        "ood_fail_closed": ood_rejected == len(ood_confidences),
        "reserved_seed_isolation_passed": (
            calibration_report["reserved_evaluation_seed_use_count"] == 0
        ),
    }
    if not calibration_report["development_candidate_gate"]["passed"]:
        raise RegionResourceDevelopmentCandidateError(
            "development candidate calibration gate failed"
        )
    diagnostics = {
        "schema": REGION_RESOURCE_DEVELOPMENT_GATE_SCHEMA,
        "candidate_considered_count": sum(gate.candidate_considered for gate in gates),
        "candidate_gate_pass_count": gate_pass_count,
        "rule_fallback_count": sum(gate.rule_fallback for gate in gates),
        "positive_examples": positive_examples,
        "rejected_examples": rejected_examples,
        "failure_fixture_is_not_system_benefit_evidence": True,
        "required_regression_fallbacks": [
            "low_confidence",
            "ood",
            "timeout",
            "nonfinite",
            "stale_epoch_or_lease",
            "coalition_ack_incomplete",
            "safety_projection_failure",
        ],
        "minimum_confidence": config.minimum_confidence,
        "latency_limit_ms": config.latency_limit_ms,
    }
    return calibration_report, diagnostics


def _make_ood_graph(
    graph: RegionGraph, feature_bounds: RegionFeatureBounds
) -> RegionGraph:
    node_features = graph.node_features.detach().clone()
    index = 0
    scale = max(
        1.0,
        abs(float(feature_bounds.node_min[index])),
        abs(float(feature_bounds.node_max[index])),
    )
    node_features[:, index] = (
        float(feature_bounds.node_max[index])
        + 2.0 * REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN * scale
        + 1.0
    )
    return replace(graph, node_features=node_features)


def _validate_canonical_view(
    view: CanonicalRegionLearningDatasetView,
    audit: Mapping[str, Any],
    *,
    expected_episodes: int,
) -> None:
    counts = {
        split: len(view.episodes(split))
        for split in ("train", "validation", "test")
    }
    if {name: len(getattr(view.binding, f"{name}_seeds")) for name in counts} != (
        REGION_RESOURCE_CANONICAL_SPLIT_COUNTS
    ):
        raise RegionResourceDevelopmentCandidateError(
            "candidate source does not expose canonical 60/20/20 seeds"
        )
    if len(view.episode_records) != expected_episodes:
        raise RegionResourceDevelopmentCandidateError(
            f"candidate source episode count mismatch: {expected_episodes}"
        )
    if not audit["readiness"]["behavior_cloning_view_available"]:
        raise RegionResourceDevelopmentCandidateError(
            "candidate source canonical view is unavailable"
        )
    source_seeds = set(
        view.binding.train_seeds
        + view.binding.validation_seeds
        + view.binding.test_seeds
    )
    if source_seeds & set(REGION_RESOURCE_RESERVED_EVALUATION_SEEDS):
        raise RegionResourceDevelopmentCandidateError(
            "reserved evaluation seed entered candidate source"
        )


def _data_evidence(
    formal_view: CanonicalRegionLearningDatasetView,
    supplemental_view: CanonicalRegionLearningDatasetView,
    composite_view: CanonicalRegionLearningDatasetView,
    *,
    action_inventory: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "schema": REGION_RESOURCE_DEVELOPMENT_DATA_SCHEMA,
        "formal": {
            "dataset_sha256": formal_view.binding.source_dataset_sha256,
            "source_split_sha256": formal_view.binding.source_dataset_split_sha256,
            "canonical_view_sha256": formal_view.binding.view_sha256,
            "episode_count": len(formal_view.episode_records),
            "frame_count": sum(
                len(episode.frames) for episode in formal_view.episode_records
            ),
        },
        "supplemental": {
            "dataset_sha256": supplemental_view.binding.source_dataset_sha256,
            "source_split_sha256": (
                supplemental_view.binding.source_dataset_split_sha256
            ),
            "canonical_view_sha256": supplemental_view.binding.view_sha256,
            "episode_count": len(supplemental_view.episode_records),
            "frame_count": sum(
                len(episode.frames) for episode in supplemental_view.episode_records
            ),
        },
        "composite": {
            "dataset_sha256": composite_view.binding.source_dataset_sha256,
            "split_sha256": composite_view.binding.source_dataset_split_sha256,
            "canonical_view_sha256": composite_view.binding.view_sha256,
            "episode_count": len(composite_view.episode_records),
            "frame_count": sum(
                len(episode.frames) for episode in composite_view.episode_records
            ),
        },
        "canonical_split": {
            "train_seeds": list(formal_view.binding.train_seeds),
            "validation_seeds": list(formal_view.binding.validation_seeds),
            "calibration_seeds": list(formal_view.binding.test_seeds),
            "counts": REGION_RESOURCE_CANONICAL_SPLIT_COUNTS,
        },
        "reserved_evaluation_seeds": list(REGION_RESOURCE_RESERVED_EVALUATION_SEEDS),
        "reserved_evaluation_seed_use_count": 0,
        "action_inventory": dict(action_inventory),
        "truth_identifier_use_count": 0,
        "reward_available": False,
        "formal_holdout_evaluated": False,
    }


def _target_action_inventory(
    records: Sequence[_CandidateSample],
) -> dict[str, int]:
    inventory = {
        "action_count": 0,
        "resource_quota_nonzero_count": 0,
        "transfer_count": 0,
        "hold_true_count": 0,
        "request_replan_true_count": 0,
    }
    for record in records:
        _accumulate_action_inventory(inventory, record.target_recommendation)
    return inventory


def _accumulate_action_inventory(
    inventory: dict[str, int], recommendation: RegionResourceRecommendation
) -> None:
    inventory["action_count"] += len(recommendation.actions)
    inventory["resource_quota_nonzero_count"] += sum(
        action.resource_quota_delta != 0 for action in recommendation.actions
    )
    inventory["transfer_count"] += len(recommendation.transfers)
    inventory["hold_true_count"] += sum(action.hold for action in recommendation.actions)
    inventory["request_replan_true_count"] += sum(
        action.request_replan for action in recommendation.actions
    )


def _accumulate_action_quality(
    metrics: dict[str, int],
    predicted: RegionResourceRecommendation,
    target: RegionResourceRecommendation,
) -> None:
    predicted_actions = {action.region_id: action for action in predicted.actions}
    target_actions = {action.region_id: action for action in target.actions}
    for region_id, target_action in target_actions.items():
        predicted_action = predicted_actions[region_id]
        metrics["action_count"] += 1
        metrics["quota_exact_count"] += int(
            predicted_action.resource_quota_delta
            == target_action.resource_quota_delta
        )
        metrics["hold_correct_count"] += int(
            predicted_action.hold == target_action.hold
        )
        metrics["request_replan_correct_count"] += int(
            predicted_action.request_replan == target_action.request_replan
        )
    predicted_transfers = {
        (
            transfer.edge_id,
            transfer.source_region_id,
            transfer.target_region_id,
            transfer.resource_count,
        )
        for transfer in predicted.transfers
    }
    target_transfers = {
        (
            transfer.edge_id,
            transfer.source_region_id,
            transfer.target_region_id,
            transfer.resource_count,
        )
        for transfer in target.transfers
    }
    metrics["transfer_frame_count"] += 1
    metrics["transfer_frame_exact_count"] += int(
        predicted_transfers == target_transfers
    )


def _calibration_metrics(
    labels: Sequence[float], probabilities: Sequence[float], *, bins: int
) -> dict[str, float | int]:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("calibration labels and probabilities must align")
    brier = sum(
        (float(probability) - float(label)) ** 2
        for label, probability in zip(labels, probabilities, strict=True)
    ) / len(labels)
    ece = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        selected = [
            (label, probability)
            for label, probability in zip(labels, probabilities, strict=True)
            if low <= probability < high
            or (index == bins - 1 and probability == 1.0)
        ]
        if not selected:
            continue
        accuracy = sum(label for label, _ in selected) / len(selected)
        confidence = sum(probability for _, probability in selected) / len(selected)
        ece += len(selected) / len(labels) * abs(accuracy - confidence)
    return {
        "sample_count": len(labels),
        "brier_score": brier,
        "expected_calibration_error": ece,
        "bin_count": bins,
    }


def _recommendation_finite(recommendation: RegionResourceRecommendation) -> bool:
    values: list[float] = [recommendation.confidence, recommendation.created_at_s]
    for action in recommendation.actions:
        values.extend(
            (
                action.resource_quota_delta,
                action.reserve_ratio,
                action.reconnaissance_priority,
                action.expected_plan_version,
                action.expected_epoch,
                action.expected_lease_expires_at_s,
            )
        )
    for transfer in recommendation.transfers:
        values.extend(
            (
                transfer.resource_count,
                transfer.expected_transfer_time_s,
            )
        )
    return all(isfinite(float(value)) for value in values)


def _distribution(values: Sequence[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("distribution requires values")
    ordered = sorted(float(value) for value in values)
    if not all(isfinite(value) for value in ordered):
        raise ValueError("distribution values must be finite")
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": sum(ordered) / len(ordered),
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "max": ordered[-1],
    }


def _percentile(ordered: Sequence[float], fraction: float) -> float:
    if len(ordered) == 1:
        return float(ordered[0])
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _render_candidate_report(
    data: Mapping[str, Any],
    training: Mapping[str, Any],
    calibration: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    bundle: RegionResourceModelManifest,
) -> str:
    gate = calibration["gate"]
    confidence = calibration["confidence"]
    latency = calibration["latency_ms"]
    ood = calibration["ood"]
    predicted = calibration["predicted_action_inventory"]
    return "\n".join(
        (
            "# D4 A2 development 候选校准报告",
            "",
            "## 结论",
            "",
            "本次产物是 development/shadow 候选，只允许隔离和影子评估。"
            "它不具备 assist、正式 authority 或系统收益结论。",
            "",
            f"- 候选模型：`{bundle.model_version}`",
            f"- 权重 SHA256：`{bundle.state_dict_sha256}`",
            f"- 正门样本：{gate['pass_count']}/{calibration['sample_count']}",
            f"- 置信度 min/mean/max：{confidence['min']:.6f}/"
            f"{confidence['mean']:.6f}/{confidence['max']:.6f}",
            f"- 推理时延 P95/max：{latency['p95']:.6f}/"
            f"{latency['max']:.6f} ms，固定门限 50 ms",
            f"- OOD 硬门拒绝：{ood['hard_gate_rejected_count']}/"
            f"{ood['sample_count']}",
            "",
            "## 数据",
            "",
            f"- 正式语料：{data['formal']['episode_count']} episode，"
            f"{data['formal']['frame_count']} frame",
            f"- 补充课程：{data['supplemental']['episode_count']} episode，"
            f"{data['supplemental']['frame_count']} frame",
            "- 训练、验证、校准 seed 为 60/20/20；1000-1019 使用数为 0。",
            "",
            "## 动作覆盖",
            "",
            f"- 非零配额动作：{predicted['resource_quota_nonzero_count']}",
            f"- 跨区转移：{predicted['transfer_count']}",
            f"- hold：{predicted['hold_true_count']}",
            f"- request-replan：{predicted['request_replan_true_count']}",
            "",
            "## 边界",
            "",
            f"- failure fixture 项：{len(diagnostics['required_regression_fallbacks'])}",
            "- 低置信、分布外、超时、非有限、旧 epoch/lease、ACK 不完整和"
            "安全投影失败均保持规则回退。",
            "- 正门样本只证明候选合同可以进入后续隔离试验，不证明物理收益。",
            "- 正式 1000-1019 留出集、运行时 ACK、物理结果和因果收益仍未评估。",
            "",
        )
    )


def _implementation_hashes() -> dict[str, str]:
    repository_root = Path(__file__).resolve().parents[3]
    return {
        relative_path: _sha256_file(repository_root / relative_path)
        for relative_path in REGION_RESOURCE_CANDIDATE_IMPLEMENTATION_FILES
    }


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    try:
        torch.use_deterministic_algorithms(True)
    except (AttributeError, RuntimeError):
        pass


def _resolve_device(value: str) -> Any:
    device = torch.device(value)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RegionResourceDevelopmentCandidateError("requested CUDA is unavailable")
    return device


def _canonical_seed_tuple(values: Iterable[int]) -> tuple[int, ...]:
    result = tuple(sorted({int(value) for value in values}))
    if any(value < 0 for value in result):
        raise ValueError("seed catalogs must be non-negative")
    return result


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _diagnostic_payload_sha256(value: Any, *, finite: bool) -> str:
    if finite:
        return canonical_runtime_payload_sha256(value)
    return _sha256_json(_json_safe_nonfinite(value))


def _json_safe_nonfinite(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe_nonfinite(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe_nonfinite(item) for item in value]
    if isinstance(value, float) and not isfinite(value):
        if value != value:
            marker = "nan"
        elif value > 0.0:
            marker = "positive_infinity"
        else:
            marker = "negative_infinity"
        return {"nonfinite_float": marker}
    return value


def _require_sha256(value: str, name: str) -> None:
    if len(value) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in value.lower()
    ):
        raise ValueError(f"{name} must be a SHA256")


def _require_torch() -> None:
    if torch is None:
        raise RegionResourceDevelopmentCandidateError("torch_unavailable")
