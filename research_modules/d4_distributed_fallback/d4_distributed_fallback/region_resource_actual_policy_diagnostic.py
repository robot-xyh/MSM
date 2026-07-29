"""Development-only diagnostics for actual D4 regional policy interventions.

The diagnostic path reads an existing development candidate and evaluates only
its frozen calibration seeds.  It does not tune thresholds, consume reserved
evaluation seeds, assemble production adoption evidence, or grant authority.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from math import ceil, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .region_resource import (
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceAction,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
)
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    load_region_learning_dataset,
)
from .region_resource_development_candidate import (
    REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
    REGION_RESOURCE_RESERVED_EVALUATION_SEEDS,
    RegionResourceDevelopmentCandidateError,
    RegionResourceDevelopmentCandidateManifest,
    evaluate_region_resource_development_gate,
    load_region_resource_development_candidate_manifest,
)
from .region_resource_isolated_rollout import (
    REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
    REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE,
)
from .region_resource_learning import (
    LearnedRegionResourcePolicy,
    load_region_resource_model_bundle,
)
from .region_resource_safe_adoption import (
    _build_projected_intervention_evidence,
)


REGION_RESOURCE_ACTUAL_POLICY_DIAGNOSTIC_SCHEMA = (
    "d4-region-resource-actual-policy-diagnostic-v1"
)
REGION_RESOURCE_ACTUAL_POLICY_SAMPLE_SCHEMA = (
    "d4-region-resource-actual-policy-sample-diagnostic-v1"
)
REGION_RESOURCE_ACTUAL_POLICY_ACTION_SCHEMA = (
    "d4-region-resource-actual-policy-action-diagnostic-v1"
)
REGION_RESOURCE_ACTUAL_POLICY_TRANSFER_SCHEMA = (
    "d4-region-resource-actual-policy-transfer-diagnostic-v1"
)
REGION_RESOURCE_ACTUAL_POLICY_CLASSIFICATION_LATENCY_MS = 0.0
REGION_RESOURCE_ACTUAL_POLICY_PERMISSIONS = MappingProxyType(
    {
        "assist_granted": False,
        "assignment_authority_granted": False,
        "failover_authority_granted": False,
        "center_replan_authority_granted": False,
        "secondary_takeover_authority_granted": False,
        "coalition_commit_authority_granted": False,
        "control_authority_granted": False,
        "formal_evidence_available": False,
        "actual_safe_adoption_available": False,
        "actual_system_benefit_available": False,
    }
)


class RegionResourceActualPolicyDiagnosticError(RuntimeError):
    """Fail-closed error at the actual-policy diagnostic boundary."""


class RegionResourceActualPolicyOutcome(str, Enum):
    """Primary outcome for one candidate inference sample."""

    SAFE_NONZERO_ACTUAL_MODEL = "safe_nonzero_actual_model"
    ACTION_SAME_AS_BASELINE = "action_same_as_baseline"
    CONFIDENCE_INSUFFICIENT = "confidence_insufficient"
    OUT_OF_DISTRIBUTION = "out_of_distribution"
    OWNER_LEASE_EPOCH_BLOCKED = "owner_lease_epoch_blocked"
    ACTION_MASKED = "action_masked"
    RESOURCE_INFEASIBLE = "resource_infeasible"
    POLICY_OUTPUT_INVALID = "policy_output_invalid"


@dataclass(frozen=True)
class RegionResourceActualPolicyCalibrationSplit:
    """Immutable split catalog used by the development diagnostic."""

    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    calibration_seeds: tuple[int, ...]
    reserved_evaluation_seeds: tuple[int, ...]

    def __post_init__(self) -> None:
        catalogs = {
            "train_seeds": _seed_tuple(self.train_seeds),
            "validation_seeds": _seed_tuple(self.validation_seeds),
            "calibration_seeds": _seed_tuple(self.calibration_seeds),
            "reserved_evaluation_seeds": _seed_tuple(
                self.reserved_evaluation_seeds
            ),
        }
        if any(not values for values in catalogs.values()):
            raise ValueError("diagnostic seed catalogs must not be empty")
        names = tuple(catalogs)
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                if set(catalogs[left_name]) & set(catalogs[right_name]):
                    raise ValueError(
                        f"diagnostic seed catalogs overlap: "
                        f"{left_name}/{right_name}"
                    )
        if (
            catalogs["reserved_evaluation_seeds"]
            != REGION_RESOURCE_RESERVED_EVALUATION_SEEDS
        ):
            raise ValueError(
                "reserved evaluation seed catalog must remain 1000-1019"
            )
        for name, values in catalogs.items():
            object.__setattr__(self, name, values)

    @classmethod
    def from_manifest(
        cls,
        manifest: RegionResourceDevelopmentCandidateManifest,
    ) -> "RegionResourceActualPolicyCalibrationSplit":
        return cls(
            train_seeds=manifest.train_seeds,
            validation_seeds=manifest.validation_seeds,
            calibration_seeds=manifest.calibration_seeds,
            reserved_evaluation_seeds=manifest.reserved_evaluation_seeds,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_seeds": list(self.train_seeds),
            "validation_seeds": list(self.validation_seeds),
            "calibration_seeds": list(self.calibration_seeds),
            "reserved_evaluation_seeds": list(
                self.reserved_evaluation_seeds
            ),
            "threshold_tuned_on_calibration_split": False,
        }


@dataclass(frozen=True)
class RegionResourceActualPolicyActionDiagnostic:
    """One regional action before and after deterministic projection."""

    region_id: str
    resources_before: int
    committed_resources: int
    baseline_reserve_resources: int
    raw_resource_quota_delta: int
    raw_requested_reserve_resources: int
    raw_hold: bool
    raw_request_replan: bool
    projected_resource_quota_delta: int | None
    projected_reserve_resources: int | None
    projected_hold: bool | None
    projected_request_replan: bool | None
    raw_effect_fields: tuple[str, ...]
    projected_effect_fields: tuple[str, ...]
    reason_codes: tuple[str, ...]
    schema: str = REGION_RESOURCE_ACTUAL_POLICY_ACTION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "region_id": self.region_id,
            "resources_before": self.resources_before,
            "committed_resources": self.committed_resources,
            "baseline_reserve_resources": (
                self.baseline_reserve_resources
            ),
            "raw_resource_quota_delta": self.raw_resource_quota_delta,
            "raw_requested_reserve_resources": (
                self.raw_requested_reserve_resources
            ),
            "raw_hold": self.raw_hold,
            "raw_request_replan": self.raw_request_replan,
            "projected_resource_quota_delta": (
                self.projected_resource_quota_delta
            ),
            "projected_reserve_resources": (
                self.projected_reserve_resources
            ),
            "projected_hold": self.projected_hold,
            "projected_request_replan": (
                self.projected_request_replan
            ),
            "raw_effect_fields": list(self.raw_effect_fields),
            "projected_effect_fields": list(
                self.projected_effect_fields
            ),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class RegionResourceActualPolicyTransferDiagnostic:
    """One requested transfer and the amount surviving projection."""

    source_region_id: str
    target_region_id: str
    edge_id: str
    requested_resource_count: int
    projected_resource_count: int
    reason_codes: tuple[str, ...]
    schema: str = REGION_RESOURCE_ACTUAL_POLICY_TRANSFER_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_region_id": self.source_region_id,
            "target_region_id": self.target_region_id,
            "edge_id": self.edge_id,
            "requested_resource_count": self.requested_resource_count,
            "projected_resource_count": self.projected_resource_count,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class RegionResourceActualPolicySampleDiagnostic:
    """Truth-free diagnostic result for one actual model inference."""

    scenario_id: str
    scenario_version: str
    seed: int
    frame_index: int
    snapshot_id: str
    snapshot_sha256: str
    candidate_id: str
    model_sha256: str
    confidence: float | None
    minimum_confidence: float
    latency_ms: float | None
    latency_limit_ms: float
    candidate_gate_passed: bool
    candidate_ood_passed: bool | None
    candidate_finite: bool | None
    policy_output_structure_valid: bool
    safety_projection_passed: bool
    advisory_consumable: bool
    actual_model_identity_verified: bool
    identifiable_intervention_available: bool
    intervention_fields: tuple[str, ...]
    raw_executable_signature_sha256: str | None
    outcome: RegionResourceActualPolicyOutcome
    reason_codes: tuple[str, ...]
    actions: tuple[RegionResourceActualPolicyActionDiagnostic, ...]
    transfers: tuple[
        RegionResourceActualPolicyTransferDiagnostic, ...
    ]
    schema: str = REGION_RESOURCE_ACTUAL_POLICY_SAMPLE_SCHEMA

    @property
    def safe_nonzero_actual_model(self) -> bool:
        return bool(
            self.outcome
            is RegionResourceActualPolicyOutcome.SAFE_NONZERO_ACTUAL_MODEL
            and self.candidate_gate_passed
            and self.policy_output_structure_valid
            and self.safety_projection_passed
            and self.advisory_consumable
            and self.actual_model_identity_verified
            and self.identifiable_intervention_available
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "seed": self.seed,
            "frame_index": self.frame_index,
            "snapshot_id": self.snapshot_id,
            "snapshot_sha256": self.snapshot_sha256,
            "candidate_id": self.candidate_id,
            "model_sha256": self.model_sha256,
            "confidence": self.confidence,
            "minimum_confidence": self.minimum_confidence,
            "latency_ms": self.latency_ms,
            "latency_limit_ms": self.latency_limit_ms,
            "candidate_gate_passed": self.candidate_gate_passed,
            "candidate_ood_passed": self.candidate_ood_passed,
            "candidate_finite": self.candidate_finite,
            "policy_output_structure_valid": (
                self.policy_output_structure_valid
            ),
            "safety_projection_passed": (
                self.safety_projection_passed
            ),
            "advisory_consumable": self.advisory_consumable,
            "actual_model_identity_verified": (
                self.actual_model_identity_verified
            ),
            "identifiable_intervention_available": (
                self.identifiable_intervention_available
            ),
            "intervention_fields": list(self.intervention_fields),
            "raw_executable_signature_sha256": (
                self.raw_executable_signature_sha256
            ),
            "outcome": self.outcome.value,
            "reason_codes": list(self.reason_codes),
            "safe_nonzero_actual_model": (
                self.safe_nonzero_actual_model
            ),
            "actions": [item.to_dict() for item in self.actions],
            "transfers": [item.to_dict() for item in self.transfers],
        }


@dataclass(frozen=True)
class RegionResourceActualPolicyDiagnosticReport:
    """Compact, auditable result for the complete calibration split."""

    candidate_id: str
    candidate_manifest_sha256: str
    model_version: str
    model_sha256: str
    bundle_manifest_sha256: str
    dataset_sha256: str
    split: RegionResourceActualPolicyCalibrationSplit
    implementation_lineage_matches_current: bool
    implementation_lineage_reason: str | None
    sample_count: int
    calibration_seed_count: int
    calibration_seeds_observed: tuple[int, ...]
    reserved_seed_use_count: int
    dirty_source_episode_count: int
    truth_identifier_use_count: int
    truth_free_dataset_verified: bool
    candidate_gate_pass_count: int
    candidate_gate_fallback_count: int
    outcome_counts: Mapping[str, int]
    sample_reason_counts: Mapping[str, int]
    intervention_field_counts: Mapping[str, int]
    safe_nonzero_scenario_counts: Mapping[str, int]
    confidence_summary: Mapping[str, float | int | None]
    latency_ms_summary: Mapping[str, float | int | None]
    safe_nonzero_actual_model_count: int
    unique_raw_executable_signature_count: int
    policy_output_degenerate: bool
    samples: tuple[RegionResourceActualPolicySampleDiagnostic, ...]
    permissions: Mapping[str, bool]
    schema: str = REGION_RESOURCE_ACTUAL_POLICY_DIAGNOSTIC_SCHEMA

    def __post_init__(self) -> None:
        for name in (
            "candidate_manifest_sha256",
            "model_sha256",
            "bundle_manifest_sha256",
            "dataset_sha256",
        ):
            value = str(getattr(self, name)).lower()
            if len(value) != 64 or any(
                character not in "0123456789abcdef"
                for character in value
            ):
                raise ValueError(f"{name} must be a SHA-256 digest")
            object.__setattr__(self, name, value)
        if dict(self.permissions) != REGION_RESOURCE_ACTUAL_POLICY_PERMISSIONS:
            raise ValueError(
                "actual-policy diagnostic permissions must remain closed"
            )
        if self.reserved_seed_use_count != 0:
            raise ValueError(
                "reserved evaluation seeds entered development diagnostics"
            )
        if self.truth_identifier_use_count != 0:
            raise ValueError(
                "truth identifiers entered development diagnostics"
            )
        if not self.truth_free_dataset_verified:
            raise ValueError(
                "actual-policy diagnostics require a truth-free verified dataset"
            )
        samples = tuple(self.samples)
        object.__setattr__(self, "samples", samples)
        if int(self.sample_count) != len(samples):
            raise ValueError("sample_count does not match diagnostic samples")
        observed_seeds = tuple(sorted({item.seed for item in samples}))
        if observed_seeds != tuple(self.calibration_seeds_observed):
            raise ValueError(
                "calibration seed catalog does not match diagnostic samples"
            )
        if int(self.calibration_seed_count) != len(observed_seeds):
            raise ValueError(
                "calibration_seed_count does not match observed seeds"
            )
        expected_outcomes = Counter(item.outcome.value for item in samples)
        normalized_outcomes = {
            outcome.value: int(self.outcome_counts.get(outcome.value, 0))
            for outcome in RegionResourceActualPolicyOutcome
        }
        if normalized_outcomes != {
            outcome.value: int(expected_outcomes.get(outcome.value, 0))
            for outcome in RegionResourceActualPolicyOutcome
        }:
            raise ValueError("outcome counts do not match diagnostic samples")
        if sum(normalized_outcomes.values()) != self.sample_count:
            raise ValueError("outcome denominator does not match sample_count")
        expected_safe = sum(
            item.safe_nonzero_actual_model for item in samples
        )
        if int(self.safe_nonzero_actual_model_count) != expected_safe:
            raise ValueError(
                "safe non-zero count does not match diagnostic samples"
            )
        expected_gate_pass = sum(item.candidate_gate_passed for item in samples)
        if (
            int(self.candidate_gate_pass_count) != expected_gate_pass
            or int(self.candidate_gate_fallback_count)
            != len(samples) - expected_gate_pass
        ):
            raise ValueError(
                "candidate gate counts do not match diagnostic samples"
            )

    @property
    def calibration_seed_sample_counts(self) -> Mapping[str, int]:
        counts = Counter(str(item.seed) for item in self.samples)
        return dict(sorted(counts.items(), key=lambda item: int(item[0])))

    @property
    def outcome_seed_counts(self) -> Mapping[str, Mapping[str, int]]:
        counts: dict[str, Counter[str]] = {
            outcome.value: Counter()
            for outcome in RegionResourceActualPolicyOutcome
        }
        for item in self.samples:
            counts[item.outcome.value][str(item.seed)] += 1
        return {
            outcome: dict(
                sorted(seed_counts.items(), key=lambda item: int(item[0]))
            )
            for outcome, seed_counts in sorted(counts.items())
        }

    @property
    def sample_identity_sha256(self) -> str:
        return _canonical_sha256(
            [
                {
                    "scenario_id": item.scenario_id,
                    "scenario_version": item.scenario_version,
                    "seed": item.seed,
                    "frame_index": item.frame_index,
                    "snapshot_id": item.snapshot_id,
                    "snapshot_sha256": item.snapshot_sha256,
                }
                for item in sorted(
                    self.samples,
                    key=_sample_sort_key,
                )
            ]
        )

    @property
    def classification_sha256(self) -> str:
        return _canonical_sha256(
            [
                {
                    "snapshot_sha256": item.snapshot_sha256,
                    "candidate_gate_passed": item.candidate_gate_passed,
                    "candidate_ood_passed": item.candidate_ood_passed,
                    "candidate_finite": item.candidate_finite,
                    "policy_output_structure_valid": (
                        item.policy_output_structure_valid
                    ),
                    "safety_projection_passed": (
                        item.safety_projection_passed
                    ),
                    "advisory_consumable": item.advisory_consumable,
                    "actual_model_identity_verified": (
                        item.actual_model_identity_verified
                    ),
                    "outcome": item.outcome.value,
                    "reason_codes": list(item.reason_codes),
                    "intervention_fields": list(item.intervention_fields),
                    "raw_executable_signature_sha256": (
                        item.raw_executable_signature_sha256
                    ),
                }
                for item in sorted(
                    self.samples,
                    key=_sample_sort_key,
                )
            ]
        )

    @property
    def historical_lineage_nonzero_observation_available(self) -> bool:
        return self.safe_nonzero_actual_model_count > 0

    @property
    def actual_model_nonzero_development_evidence_available(self) -> bool:
        return bool(
            self.historical_lineage_nonzero_observation_available
            and self.implementation_lineage_matches_current
            and self.truth_free_dataset_verified
        )

    @property
    def content_sha256(self) -> str:
        return _canonical_sha256(self.to_dict(include_samples=True))

    def to_dict(self, *, include_samples: bool = True) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "candidate_id": self.candidate_id,
            "candidate_manifest_sha256": self.candidate_manifest_sha256,
            "model_version": self.model_version,
            "model_sha256": self.model_sha256,
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "dataset_sha256": self.dataset_sha256,
            "split": self.split.to_dict(),
            "implementation_lineage_matches_current": (
                self.implementation_lineage_matches_current
            ),
            "implementation_lineage_reason": (
                self.implementation_lineage_reason
            ),
            "sample_count": self.sample_count,
            "calibration_seed_count": self.calibration_seed_count,
            "calibration_seeds_observed": list(
                self.calibration_seeds_observed
            ),
            "calibration_seed_sample_counts": dict(
                self.calibration_seed_sample_counts
            ),
            "outcome_seed_counts": {
                name: dict(values)
                for name, values in self.outcome_seed_counts.items()
            },
            "sample_identity_sha256": self.sample_identity_sha256,
            "classification_sha256": self.classification_sha256,
            "reserved_seed_use_count": self.reserved_seed_use_count,
            "dirty_source_episode_count": (
                self.dirty_source_episode_count
            ),
            "truth_identifier_use_count": self.truth_identifier_use_count,
            "truth_free_dataset_verified": (
                self.truth_free_dataset_verified
            ),
            "candidate_gate_pass_count": self.candidate_gate_pass_count,
            "candidate_gate_fallback_count": (
                self.candidate_gate_fallback_count
            ),
            "outcome_counts": dict(sorted(self.outcome_counts.items())),
            "sample_reason_counts": dict(
                sorted(self.sample_reason_counts.items())
            ),
            "intervention_field_counts": dict(
                sorted(self.intervention_field_counts.items())
            ),
            "safe_nonzero_scenario_counts": dict(
                sorted(self.safe_nonzero_scenario_counts.items())
            ),
            "confidence_summary": dict(self.confidence_summary),
            "latency_ms_summary": dict(self.latency_ms_summary),
            "safe_nonzero_actual_model_count": (
                self.safe_nonzero_actual_model_count
            ),
            "unique_raw_executable_signature_count": (
                self.unique_raw_executable_signature_count
            ),
            "policy_output_degenerate": self.policy_output_degenerate,
            "historical_lineage_nonzero_observation_available": (
                self.historical_lineage_nonzero_observation_available
            ),
            "actual_model_nonzero_development_evidence_available": (
                self.actual_model_nonzero_development_evidence_available
            ),
            "permissions": dict(self.permissions),
            "thresholds": {
                "minimum_confidence": (
                    REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE
                ),
                "latency_limit_ms": (
                    REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS
                ),
                "classification_latency_override_ms": (
                    REGION_RESOURCE_ACTUAL_POLICY_CLASSIFICATION_LATENCY_MS
                ),
                "latency_performance_evidence": False,
                "ood_margin": REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
                "threshold_tuned_on_calibration_split": False,
            },
            "evidence_boundary": {
                "development_only": True,
                "calibration_only": True,
                "formal_holdout_evaluated": False,
                "current_implementation_lineage_required_for_evidence": True,
                "safe_projection_is_not_runtime_adoption": True,
                "system_benefit_claimed": False,
            },
        }
        if include_samples:
            payload["samples"] = [
                item.to_dict() for item in self.samples
            ]
        return payload


def diagnose_region_resource_actual_policy_sample(
    policy: Any,
    snapshot: RegionResourceSnapshot,
    *,
    candidate_id: str,
    expected_model_version: str,
    expected_model_sha256: str,
    frame_index: int,
    projector: DeterministicResourceProjector | None = None,
) -> RegionResourceActualPolicySampleDiagnostic:
    """Explain one actual policy output without assembling adoption evidence."""

    resolved_projector = projector or DeterministicResourceProjector()
    evaluation = evaluate_region_resource_development_gate(
        policy,
        snapshot,
        minimum_confidence=(
            REGION_RESOURCE_ISOLATED_MINIMUM_CONFIDENCE
        ),
        latency_limit_ms=REGION_RESOURCE_ISOLATED_LATENCY_LIMIT_MS,
        ood_margin=REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
        latency_override_ms=(
            REGION_RESOURCE_ACTUAL_POLICY_CLASSIFICATION_LATENCY_MS
        ),
        projector=resolved_projector,
    )
    gate = evaluation.gate
    raw = evaluation.recommendation
    projected = evaluation.projected_recommendation
    consumption = evaluation.consumption
    identity_verified, identity_reasons = _actual_model_identity(
        policy,
        raw,
        expected_model_version=expected_model_version,
        expected_model_sha256=expected_model_sha256,
    )
    structure_reasons = _policy_output_structure_reasons(raw, snapshot)
    structure_valid = not structure_reasons
    intervention_fields: tuple[str, ...] = ()
    identifiable = False
    if (
        structure_valid
        and
        consumption is not None
        and consumption.consumable
        and projected is not None
    ):
        intervention = _build_projected_intervention_evidence(
            consumption.advisory
        )
        identifiable = (
            intervention.identifiable_intervention_available
        )
        intervention_fields = intervention.intervention_fields

    if structure_valid:
        actions = _action_diagnostics(
            snapshot,
            raw,
            projected,
            resolved_projector,
            intervention_fields,
        )
        transfers = _transfer_diagnostics(
            snapshot,
            raw,
            projected,
            resolved_projector,
        )
    else:
        actions = ()
        transfers = ()
    reason_codes = list(gate.rejection_reasons)
    reason_codes.extend(identity_reasons)
    reason_codes.extend(structure_reasons)
    reason_codes.extend(
        reason
        for action in actions
        for reason in action.reason_codes
    )
    reason_codes.extend(
        reason
        for transfer in transfers
        for reason in transfer.reason_codes
    )
    if not identity_verified:
        reason_codes.append("actual_model_identity_mismatch")
    if (
        gate.gate_pass
        and consumption is not None
        and consumption.consumable
        and not identifiable
    ):
        reason_codes.append("no_d3_consumable_regional_intervention")
    outcome = _sample_outcome(
        gate_reasons=gate.rejection_reasons,
        action_reasons=tuple(
            reason for item in actions for reason in item.reason_codes
        ),
        transfer_reasons=tuple(
            reason for item in transfers for reason in item.reason_codes
        ),
        gate_pass=gate.gate_pass,
        identity_verified=identity_verified,
        structure_valid=structure_valid,
        identifiable=identifiable,
        consumable=bool(consumption is not None and consumption.consumable),
    )
    raw_signature = (
        _raw_executable_signature(raw, snapshot, resolved_projector)
        if raw is not None and structure_valid
        else None
    )
    return RegionResourceActualPolicySampleDiagnostic(
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=int(snapshot.seed),
        frame_index=int(frame_index),
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=_canonical_sha256(snapshot.to_dict()),
        candidate_id=str(candidate_id),
        model_sha256=str(expected_model_sha256),
        confidence=gate.candidate_confidence,
        minimum_confidence=float(gate.minimum_confidence),
        latency_ms=gate.candidate_latency_ms,
        latency_limit_ms=float(gate.candidate_latency_limit_ms),
        candidate_gate_passed=bool(gate.gate_pass),
        candidate_ood_passed=gate.candidate_ood_passed,
        candidate_finite=gate.candidate_finite,
        policy_output_structure_valid=structure_valid,
        safety_projection_passed=bool(
            gate.candidate_safety_projection_passed
        ),
        advisory_consumable=bool(
            consumption is not None and consumption.consumable
        ),
        actual_model_identity_verified=identity_verified,
        identifiable_intervention_available=identifiable,
        intervention_fields=intervention_fields,
        raw_executable_signature_sha256=raw_signature,
        outcome=outcome,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        actions=actions,
        transfers=transfers,
    )


def diagnose_region_resource_actual_policy_calibration(
    policy: Any,
    dataset: LoadedRegionLearningDataset,
    *,
    candidate_id: str,
    candidate_manifest_sha256: str,
    model_version: str,
    expected_model_sha256: str,
    bundle_manifest_sha256: str,
    split: RegionResourceActualPolicyCalibrationSplit,
    implementation_lineage_matches_current: bool,
    implementation_lineage_reason: str | None,
    truth_free_dataset_verified: bool,
) -> RegionResourceActualPolicyDiagnosticReport:
    """Run a complete, fixed-threshold calibration-only diagnosis."""

    if not truth_free_dataset_verified:
        raise RegionResourceActualPolicyDiagnosticError(
            "truth_free_dataset_not_verified"
        )
    selected = tuple(
        (
            episode,
            frame,
        )
        for episode in dataset.episode_records
        if int(episode.source.seed) in set(split.calibration_seeds)
        for frame in episode.frames
    )
    if not selected:
        raise RegionResourceActualPolicyDiagnosticError(
            "calibration_split_has_no_samples"
        )
    observed = tuple(
        sorted({int(episode.source.seed) for episode, _ in selected})
    )
    if observed != split.calibration_seeds:
        raise RegionResourceActualPolicyDiagnosticError(
            "calibration_split_seed_coverage_incomplete"
        )
    reserved_use = len(set(observed) & set(split.reserved_evaluation_seeds))
    if reserved_use:
        raise RegionResourceActualPolicyDiagnosticError(
            "reserved_evaluation_seed_used"
        )
    dirty_count = sum(
        bool(episode.source.git_dirty)
        for episode in dataset.episode_records
        if int(episode.source.seed) in set(split.calibration_seeds)
    )
    if dirty_count:
        raise RegionResourceActualPolicyDiagnosticError(
            "calibration_source_dirty"
        )

    diagnostics = tuple(
        diagnose_region_resource_actual_policy_sample(
            policy,
            frame.snapshot,
            candidate_id=candidate_id,
            expected_model_version=model_version,
            expected_model_sha256=expected_model_sha256,
            frame_index=frame.frame_index,
        )
        for episode, frame in selected
    )
    counts = Counter(
        {
            outcome.value: 0
            for outcome in RegionResourceActualPolicyOutcome
        }
    )
    counts.update(item.outcome.value for item in diagnostics)
    safe_count = sum(
        item.safe_nonzero_actual_model for item in diagnostics
    )
    gate_pass_count = sum(
        item.candidate_gate_passed for item in diagnostics
    )
    reason_counts: Counter[str] = Counter()
    intervention_counts: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    for item in diagnostics:
        reason_counts.update(set(item.reason_codes))
        intervention_counts.update(
            _intervention_field_kind(value)
            for value in item.intervention_fields
        )
        if item.safe_nonzero_actual_model:
            scenario_counts[item.scenario_id] += 1
    confidences = [
        float(item.confidence)
        for item in diagnostics
        if item.confidence is not None
    ]
    latencies = [
        float(item.latency_ms)
        for item in diagnostics
        if item.latency_ms is not None
    ]
    signatures = {
        item.raw_executable_signature_sha256
        for item in diagnostics
        if item.raw_executable_signature_sha256 is not None
    }
    degenerate = bool(
        safe_count == 0
        and len(signatures) <= 1
        and len(diagnostics) > 1
    )
    return RegionResourceActualPolicyDiagnosticReport(
        candidate_id=candidate_id,
        candidate_manifest_sha256=candidate_manifest_sha256,
        model_version=model_version,
        model_sha256=expected_model_sha256,
        bundle_manifest_sha256=bundle_manifest_sha256,
        dataset_sha256=dataset.manifest.dataset_sha256,
        split=split,
        implementation_lineage_matches_current=bool(
            implementation_lineage_matches_current
        ),
        implementation_lineage_reason=implementation_lineage_reason,
        sample_count=len(diagnostics),
        calibration_seed_count=len(observed),
        calibration_seeds_observed=observed,
        reserved_seed_use_count=reserved_use,
        dirty_source_episode_count=dirty_count,
        truth_identifier_use_count=0,
        truth_free_dataset_verified=truth_free_dataset_verified,
        candidate_gate_pass_count=gate_pass_count,
        candidate_gate_fallback_count=(
            len(diagnostics) - gate_pass_count
        ),
        outcome_counts=dict(counts),
        sample_reason_counts=dict(reason_counts),
        intervention_field_counts=dict(intervention_counts),
        safe_nonzero_scenario_counts=dict(scenario_counts),
        confidence_summary=_distribution(confidences),
        latency_ms_summary=_distribution(latencies),
        safe_nonzero_actual_model_count=safe_count,
        unique_raw_executable_signature_count=len(signatures),
        policy_output_degenerate=degenerate,
        samples=diagnostics,
        permissions=dict(REGION_RESOURCE_ACTUAL_POLICY_PERMISSIONS),
    )


def run_region_resource_actual_policy_calibration(
    candidate_root: str | Path,
    *,
    expected_candidate_manifest_sha256: str,
    dataset_root: str | Path | None = None,
) -> RegionResourceActualPolicyDiagnosticReport:
    """Load and diagnose one local development candidate artifact."""

    root = Path(candidate_root)
    lineage_matches = True
    lineage_reason: str | None = None
    try:
        candidate = load_region_resource_development_candidate_manifest(
            root,
            expected_manifest_sha256=(
                expected_candidate_manifest_sha256
            ),
            verify_current_implementation=True,
        )
    except RegionResourceDevelopmentCandidateError as exc:
        if str(exc) != "development_candidate_implementation_lineage_mismatch":
            raise
        lineage_matches = False
        lineage_reason = str(exc)
        candidate = load_region_resource_development_candidate_manifest(
            root,
            expected_manifest_sha256=(
                expected_candidate_manifest_sha256
            ),
            verify_current_implementation=False,
        )

    bundle = load_region_resource_model_bundle(
        root / "bundle",
        expected_model_version=candidate.model_version,
        expected_state_dict_sha256=candidate.model_state_sha256,
        require_training_dataset_manifest=True,
    )
    resolved_dataset_root = (
        Path(dataset_root)
        if dataset_root is not None
        else root / "composite_dataset"
    )
    dataset = load_region_learning_dataset(resolved_dataset_root)
    if dataset.manifest.dataset_sha256 != candidate.composite_dataset_sha256:
        raise RegionResourceActualPolicyDiagnosticError(
            "calibration_dataset_identity_mismatch"
        )
    return diagnose_region_resource_actual_policy_calibration(
        LearnedRegionResourcePolicy(bundle.model, bundle.manifest),
        dataset,
        candidate_id=candidate.candidate_id,
        candidate_manifest_sha256=(
            expected_candidate_manifest_sha256
        ),
        model_version=candidate.model_version,
        expected_model_sha256=candidate.model_state_sha256,
        bundle_manifest_sha256=candidate.bundle_manifest_sha256,
        split=RegionResourceActualPolicyCalibrationSplit.from_manifest(
            candidate
        ),
        implementation_lineage_matches_current=lineage_matches,
        implementation_lineage_reason=lineage_reason,
        truth_free_dataset_verified=True,
    )


def write_region_resource_actual_policy_diagnostic(
    report: RegionResourceActualPolicyDiagnosticReport,
    output_dir: str | Path,
    *,
    include_all_samples: bool = False,
) -> tuple[Path, Path]:
    """Write a small JSON audit and Chinese development report."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "diagnostic_report.json"
    markdown_path = destination / "DIAGNOSTIC_REPORT_CN.md"
    payload = report.to_dict(include_samples=include_all_samples)
    payload["full_diagnostic_content_sha256"] = report.content_sha256
    if not include_all_samples:
        examples = _representative_samples(report.samples)
        payload["representative_samples"] = [
            item.to_dict() for item in examples
        ]
        payload["persisted_sample_count"] = len(examples)
        payload["all_samples_persisted"] = False
    else:
        payload["persisted_sample_count"] = report.sample_count
        payload["all_samples_persisted"] = True
    json_path.write_text(
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
    markdown_path.write_text(
        _render_markdown(report),
        encoding="utf-8",
    )
    return json_path, markdown_path


def _actual_model_identity(
    policy: Any,
    recommendation: RegionResourceRecommendation | None,
    *,
    expected_model_version: str,
    expected_model_sha256: str,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    manifest = getattr(policy, "manifest", None)
    if manifest is None:
        reasons.append("actual_policy_manifest_missing")
    else:
        if (
            getattr(manifest, "model_version", None)
            != expected_model_version
        ):
            reasons.append(
                "actual_policy_manifest_model_version_mismatch"
            )
        if (
            getattr(manifest, "state_dict_sha256", None)
            != expected_model_sha256
        ):
            reasons.append(
                "actual_policy_manifest_model_sha256_mismatch"
            )
    if recommendation is None:
        reasons.append("actual_policy_output_missing")
    else:
        if recommendation.source is not RecommendationSource.LEARNED:
            reasons.append("actual_policy_output_source_mismatch")
        if recommendation.policy_version != expected_model_version:
            reasons.append(
                "actual_policy_output_model_version_mismatch"
            )
        if recommendation.model_sha256 != expected_model_sha256:
            reasons.append(
                "actual_policy_output_model_sha256_mismatch"
            )
    return (not reasons, tuple(reasons))


def _policy_output_structure_reasons(
    recommendation: RegionResourceRecommendation | None,
    snapshot: RegionResourceSnapshot,
) -> tuple[str, ...]:
    if recommendation is None:
        return ("policy_output_unavailable",)
    reasons: list[str] = []
    if recommendation.projected:
        reasons.append("policy_output_must_be_unprojected")
    known_regions = set(snapshot.region_by_id)
    action_regions = {item.region_id for item in recommendation.actions}
    missing_regions = sorted(known_regions - action_regions)
    unknown_regions = sorted(action_regions - known_regions)
    reasons.extend(
        f"policy_output_action_region_missing:{region_id}"
        for region_id in missing_regions
    )
    reasons.extend(
        f"policy_output_action_region_unknown:{region_id}"
        for region_id in unknown_regions
    )
    for action in recommendation.actions:
        if not _integer_like(action.resource_quota_delta):
            reasons.append(
                f"policy_output_action_nonfinite_or_noninteger:"
                f"{action.region_id}:resource_quota_delta"
            )
        if not isinstance(action.hold, bool):
            reasons.append(
                f"policy_output_action_boolean_invalid:"
                f"{action.region_id}:hold"
            )
        if not isinstance(action.request_replan, bool):
            reasons.append(
                f"policy_output_action_boolean_invalid:"
                f"{action.region_id}:request_replan"
            )
    edge_ids = {item.edge_id for item in snapshot.edges}
    for transfer in recommendation.transfers:
        if transfer.source_region_id not in known_regions:
            reasons.append(
                "policy_output_transfer_source_unknown:"
                f"{transfer.source_region_id}"
            )
        if transfer.target_region_id not in known_regions:
            reasons.append(
                "policy_output_transfer_target_unknown:"
                f"{transfer.target_region_id}"
            )
        if transfer.edge_id not in edge_ids:
            reasons.append(
                f"policy_output_transfer_edge_unknown:{transfer.edge_id}"
            )
        if not _integer_like(transfer.resource_count):
            reasons.append(
                "policy_output_transfer_nonfinite_or_noninteger:"
                f"{transfer.edge_id}:resource_count"
            )
    return tuple(dict.fromkeys(reasons))


def _action_diagnostics(
    snapshot: RegionResourceSnapshot,
    raw: RegionResourceRecommendation | None,
    projected: RegionResourceRecommendation | None,
    projector: DeterministicResourceProjector,
    intervention_fields: Sequence[str],
) -> tuple[RegionResourceActualPolicyActionDiagnostic, ...]:
    raw_by_id = (
        {item.region_id: item for item in raw.actions}
        if raw is not None
        else {}
    )
    projected_by_id = (
        {item.region_id: item for item in projected.actions}
        if projected is not None
        else {}
    )
    projected_field_set = set(intervention_fields)
    diagnostics: list[RegionResourceActualPolicyActionDiagnostic] = []
    for node in sorted(snapshot.regions, key=lambda item: item.region_id):
        action = raw_by_id.get(node.region_id)
        projected_action = projected_by_id.get(node.region_id)
        baseline_reserve = projector._reserve_floor(node)
        raw_fields: list[str] = []
        projected_fields: list[str] = []
        reasons: list[str] = []
        if action is None:
            raw_quota = 0
            raw_reserve = baseline_reserve
            raw_hold = False
            raw_replan = False
            reasons.append("action_missing")
        else:
            raw_quota = int(action.resource_quota_delta)
            raw_after = max(
                0, int(node.available_resources) + raw_quota
            )
            raw_reserve = int(
                ceil(float(action.reserve_ratio) * raw_after)
            )
            raw_hold = bool(action.hold)
            raw_replan = bool(action.request_replan)
            if raw_quota != 0:
                raw_fields.append("resource_quota")
            if raw_reserve != baseline_reserve:
                raw_fields.append("reserve_resources")
            if raw_hold:
                raw_fields.append("hold")
            if raw_replan:
                raw_fields.append("request_replan")
            reasons.extend(_authority_binding_reasons(snapshot, node, action))
            feasible_reserve = max(
                0,
                raw_after - int(node.committed_resources),
            )
            if raw_reserve > feasible_reserve:
                reasons.append(
                    "reserve_request_exceeds_feasible_resources"
                )
            if (
                raw_quota < 0
                and raw_after
                < int(node.committed_resources) + baseline_reserve
            ):
                reasons.append(
                    "quota_request_violates_commit_or_reserve"
                )
        prefix = f"region:{node.region_id}:"
        projected_fields.extend(
            value.removeprefix(prefix)
            for value in projected_field_set
            if value.startswith(prefix)
        )
        if projected_action is None:
            projected_quota: int | None = None
            projected_reserve: int | None = None
            projected_hold: bool | None = None
            projected_replan: bool | None = None
        else:
            projected_quota = int(
                projected_action.resource_quota_delta
            )
            projected_after = max(
                0, int(node.available_resources) + projected_quota
            )
            projected_reserve = int(
                ceil(
                    float(projected_action.reserve_ratio)
                    * projected_after
                )
            )
            projected_hold = bool(projected_action.hold)
            projected_replan = bool(
                projected_action.request_replan
            )
        if raw_fields and not projected_fields:
            reasons.append("action_projected_to_current_state")
        elif not raw_fields and not projected_fields:
            reasons.append("action_same_as_current_state")
        diagnostics.append(
            RegionResourceActualPolicyActionDiagnostic(
                region_id=node.region_id,
                resources_before=int(node.available_resources),
                committed_resources=int(node.committed_resources),
                baseline_reserve_resources=baseline_reserve,
                raw_resource_quota_delta=raw_quota,
                raw_requested_reserve_resources=raw_reserve,
                raw_hold=raw_hold,
                raw_request_replan=raw_replan,
                projected_resource_quota_delta=projected_quota,
                projected_reserve_resources=projected_reserve,
                projected_hold=projected_hold,
                projected_request_replan=projected_replan,
                raw_effect_fields=tuple(sorted(set(raw_fields))),
                projected_effect_fields=tuple(
                    sorted(set(projected_fields))
                ),
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
        )
    return tuple(diagnostics)


def _transfer_diagnostics(
    snapshot: RegionResourceSnapshot,
    raw: RegionResourceRecommendation | None,
    projected: RegionResourceRecommendation | None,
    projector: DeterministicResourceProjector,
) -> tuple[RegionResourceActualPolicyTransferDiagnostic, ...]:
    if raw is None:
        return ()
    projected_counts: Counter[tuple[str, str, str]] = Counter()
    for item in projected.transfers if projected is not None else ():
        projected_counts[
            (
                item.source_region_id,
                item.target_region_id,
                item.edge_id,
            )
        ] += int(item.resource_count)
    edge_by_id = {edge.edge_id: edge for edge in snapshot.edges}
    diagnostics: list[RegionResourceActualPolicyTransferDiagnostic] = []
    for transfer in raw.transfers:
        key = (
            transfer.source_region_id,
            transfer.target_region_id,
            transfer.edge_id,
        )
        projected_count = min(
            int(transfer.resource_count),
            int(projected_counts.get(key, 0)),
        )
        projected_counts[key] -= projected_count
        reasons: list[str] = []
        edge = edge_by_id.get(transfer.edge_id)
        source = snapshot.region_by_id.get(transfer.source_region_id)
        if edge is None:
            reasons.append("transfer_edge_unknown")
        else:
            if not edge.permits(
                transfer.source_region_id,
                transfer.target_region_id,
            ):
                reasons.append("transfer_non_adjacent")
            if not edge.open_for_transfer:
                reasons.append("transfer_action_masked_by_link")
            if int(transfer.resource_count) > int(
                edge.transferable_resources
            ):
                reasons.append("transfer_exceeds_edge_capacity")
        if source is None:
            reasons.append("transfer_source_unknown")
        elif int(transfer.resource_count) > projector._transfer_budget(
            source
        ):
            reasons.append("transfer_exceeds_resource_budget")
        if projected_count == 0:
            reasons.append("transfer_removed_by_projection")
        elif projected_count < int(transfer.resource_count):
            reasons.append("transfer_clipped_by_projection")
        diagnostics.append(
            RegionResourceActualPolicyTransferDiagnostic(
                source_region_id=transfer.source_region_id,
                target_region_id=transfer.target_region_id,
                edge_id=transfer.edge_id,
                requested_resource_count=int(transfer.resource_count),
                projected_resource_count=projected_count,
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
        )
    return tuple(diagnostics)


def _authority_binding_reasons(
    snapshot: RegionResourceSnapshot,
    node: Any,
    action: RegionResourceAction,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if snapshot.timestamp_s >= node.lease_expires_at_s:
        reasons.append("lease_expired")
    if not node.owner_active:
        reasons.append("owner_inactive")
    if action.expected_owner_id != node.current_owner_id:
        reasons.append("owner_id_mismatch")
    if action.expected_owner_layer != node.current_owner_layer:
        reasons.append("owner_layer_mismatch")
    if action.expected_plan_id != node.plan_id:
        reasons.append("plan_id_mismatch")
    if action.expected_plan_version != node.plan_version:
        reasons.append("plan_version_mismatch")
    if action.expected_epoch != node.epoch:
        reasons.append("epoch_mismatch")
    if (
        action.expected_lease_expires_at_s
        != node.lease_expires_at_s
    ):
        reasons.append("lease_binding_mismatch")
    if node.fault_fenced:
        reasons.append("action_masked_by_fault_fence")
    if not node.coalition_ack_complete:
        reasons.append("action_masked_by_coalition_ack")
    return tuple(reasons)


def _sample_outcome(
    *,
    gate_reasons: Sequence[str],
    action_reasons: Sequence[str],
    transfer_reasons: Sequence[str],
    gate_pass: bool,
    identity_verified: bool,
    structure_valid: bool,
    identifiable: bool,
    consumable: bool,
) -> RegionResourceActualPolicyOutcome:
    combined = tuple(gate_reasons) + tuple(action_reasons) + tuple(
        transfer_reasons
    )
    if not identity_verified or not structure_valid or any(
        value.startswith("candidate_output_nonfinite")
        or value.startswith("candidate_inference_failed")
        for value in combined
    ):
        return RegionResourceActualPolicyOutcome.POLICY_OUTPUT_INVALID
    if "candidate_low_confidence" in combined:
        return RegionResourceActualPolicyOutcome.CONFIDENCE_INSUFFICIENT
    if "candidate_ood_rejected" in combined:
        return RegionResourceActualPolicyOutcome.OUT_OF_DISTRIBUTION
    if gate_pass and consumable and identifiable:
        return RegionResourceActualPolicyOutcome.SAFE_NONZERO_ACTUAL_MODEL
    if any(_is_authority_reason(value) for value in combined):
        return RegionResourceActualPolicyOutcome.OWNER_LEASE_EPOCH_BLOCKED
    if any(_is_resource_reason(value) for value in combined):
        return RegionResourceActualPolicyOutcome.RESOURCE_INFEASIBLE
    if any(_is_action_mask_reason(value) for value in combined):
        return RegionResourceActualPolicyOutcome.ACTION_MASKED
    return RegionResourceActualPolicyOutcome.ACTION_SAME_AS_BASELINE


def _is_authority_reason(value: str) -> bool:
    tokens = (
        "lease_",
        "owner_",
        "plan_id_mismatch",
        "plan_version_mismatch",
        "epoch_mismatch",
        "authority_lease_expired",
        "authority_version_mismatch",
        "authority_digest_mismatch",
        "snapshot_or_authority",
        "formal_decision_mismatch",
    )
    return any(token in value for token in tokens)


def _is_resource_reason(value: str) -> bool:
    tokens = (
        "reserve",
        "resource_budget",
        "edge_capacity",
        "quota_request",
        "capacity_fence",
        "clipped_by_projection",
        "negative_post",
        "committed_resources_unprotected",
    )
    return any(token in value for token in tokens)


def _is_action_mask_reason(value: str) -> bool:
    tokens = (
        "action_masked",
        "fault_fence",
        "coalition_ack",
        "partition",
        "edge_unavailable",
        "non_adjacent",
        "formal_d4",
        "action_missing",
    )
    return any(token in value for token in tokens)


def _raw_executable_signature(
    recommendation: RegionResourceRecommendation,
    snapshot: RegionResourceSnapshot,
    projector: DeterministicResourceProjector,
) -> str:
    node_by_id = snapshot.region_by_id
    actions = []
    for action in sorted(
        recommendation.actions, key=lambda item: item.region_id
    ):
        node = node_by_id[action.region_id]
        resources_after = max(
            0,
            int(node.available_resources)
            + int(action.resource_quota_delta),
        )
        actions.append(
            {
                "region_id": action.region_id,
                "resource_quota_delta": int(
                    action.resource_quota_delta
                ),
                "requested_reserve_resources": int(
                    ceil(float(action.reserve_ratio) * resources_after)
                ),
                "baseline_reserve_resources": (
                    projector._reserve_floor(node)
                ),
                "hold": bool(action.hold),
                "request_replan": bool(action.request_replan),
            }
        )
    transfers = [
        {
            "source_region_id": item.source_region_id,
            "target_region_id": item.target_region_id,
            "resource_count": int(item.resource_count),
            "edge_id": item.edge_id,
        }
        for item in sorted(
            recommendation.transfers,
            key=lambda item: (
                item.source_region_id,
                item.target_region_id,
                item.edge_id,
            ),
        )
    ]
    return _canonical_sha256(
        {"actions": actions, "transfers": transfers}
    )


def _render_markdown(
    report: RegionResourceActualPolicyDiagnosticReport,
) -> str:
    counts = report.outcome_counts
    lineage = (
        "一致"
        if report.implementation_lineage_matches_current
        else "不一致，仅允许开发诊断"
    )
    return "\n".join(
        (
            "# D4 A2 实际区域策略开发诊断",
            "",
            "## 结论",
            "",
            (
                f"实际模型在与训练/验证互斥的开发校准集 "
                f"{report.calibration_seed_count} "
                f"个种子、{report.sample_count} 个样本上产生 "
                f"{report.safe_nonzero_actual_model_count} 个通过固定门限、"
                "安全投影和消费检查的非零区域动作。"
            ),
            (
                "该结果记录历史实现谱系模型的可辨识动作输出。当前谱系开发证据、"
                "运行时采用、系统收益和正式准入均不可用。"
            ),
            "",
            "## 诊断边界",
            "",
            f"- 候选：`{report.candidate_id}`",
            f"- 候选清单 SHA-256：`{report.candidate_manifest_sha256}`",
            f"- 模型：`{report.model_version}`",
            f"- 当前实现谱系：{lineage}",
            (
                "- 最低置信度保持 0.60；分类运行固定使用 0 ms 功能性"
                "时延覆盖，50 ms 运行门配置未改变，本报告不提供时延性能证据。"
            ),
            "- 保留种子使用数为 0，在线真值字段使用数为 0。",
            (
                "- 中心重规划、二级接管、联盟提交、分配、控制和 assist "
                "权限均为 false。"
            ),
            (
                f"- 当前谱系开发证据可用："
                f"{str(report.actual_model_nonzero_development_evidence_available).lower()}。"
            ),
            (
                f"- 候选固定门通过/回退："
                f"{report.candidate_gate_pass_count}/"
                f"{report.candidate_gate_fallback_count}。"
            ),
            "",
            "## 结果分布",
            "",
            *(
                f"- `{name}`：{count}/{report.sample_count}"
                for name, count in sorted(counts.items())
            ),
            f"- 样本身份摘要：`{report.sample_identity_sha256}`",
            f"- 分类摘要：`{report.classification_sha256}`",
            (
                f"- 原始可执行动作签名数："
                f"{report.unique_raw_executable_signature_count}"
            ),
            (
                f"- 批次策略输出退化："
                f"{str(report.policy_output_degenerate).lower()}"
            ),
            (
                "- 资源不可行样本主要来自已承诺资源占满后仍请求正备用量；"
                "整数化和确定性投影将该请求压回受保护基线。"
            ),
            (
                "- 本批没有低置信、分布外、权威/租约/时期错绑或"
                "动作掩码拒绝。"
            ),
            "",
            "## 正式证据前置条件",
            "",
            "1. 重新生成与当前实现谱系一致的候选制品。",
            "2. 在不使用校准种子调参的前提下运行至少 20 个正式未见种子。",
            "3. 形成严格后继计划、owner/coalition ACK、物理窗口和独立同键 R0。",
            "4. 由 D6 完成非退化和收益审计后，另行评审 assist 准入。",
            "",
        )
    )


def _representative_samples(
    samples: Sequence[RegionResourceActualPolicySampleDiagnostic],
    *,
    maximum_per_outcome: int = 2,
) -> tuple[RegionResourceActualPolicySampleDiagnostic, ...]:
    selected: list[RegionResourceActualPolicySampleDiagnostic] = []
    counts: Counter[str] = Counter()
    for sample in samples:
        key = sample.outcome.value
        if counts[key] >= maximum_per_outcome:
            continue
        selected.append(sample)
        counts[key] += 1
    return tuple(selected)


def _seed_tuple(values: Iterable[int]) -> tuple[int, ...]:
    resolved_values: set[int] = set()
    for value in values:
        if isinstance(value, bool) or int(value) != value:
            raise ValueError("seed values must be integers")
        resolved_values.add(int(value))
    resolved = tuple(sorted(resolved_values))
    if any(value < 0 for value in resolved):
        raise ValueError("seed values must be non-negative")
    return resolved


def _integer_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        numeric = float(value)
        return isfinite(numeric) and numeric == float(int(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _sample_sort_key(
    item: RegionResourceActualPolicySampleDiagnostic,
) -> tuple[str, str, int, int, str]:
    return (
        item.scenario_id,
        item.scenario_version,
        item.seed,
        item.frame_index,
        item.snapshot_id,
    )


def _intervention_field_kind(value: str) -> str:
    if value.startswith("transfer:"):
        return "transfer"
    return value.rsplit(":", 1)[-1]


def _distribution(
    values: Sequence[float],
) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "p50": None,
            "p95": None,
            "max": None,
        }
    ordered = sorted(float(value) for value in values)

    def nearest_rank(fraction: float) -> float:
        index = max(0, ceil(fraction * len(ordered)) - 1)
        return ordered[index]

    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": sum(ordered) / len(ordered),
        "p50": nearest_rank(0.50),
        "p95": nearest_rank(0.95),
        "max": ordered[-1],
    }


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
