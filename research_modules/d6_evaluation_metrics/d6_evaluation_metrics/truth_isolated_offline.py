"""Truth-isolated D1/D2 adapters for scalable three-dimensional evaluation.

The adapters in this module consume public evaluator DTOs or persisted public
artifacts with an externally supplied SHA-256.  They do not import a tracker,
inspect private filter state, or infer a ``global_track_id`` to truth mapping.
Missing evidence remains explicitly unavailable.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


D6_TRUTH_ISOLATED_EPISODE_SCHEMA_VERSION = (
    "d6.scalable3d_truth_isolated_episode.v1"
)
D6_TRUTH_ISOLATED_BATCH_SCHEMA_VERSION = (
    "d6.scalable3d_truth_isolated_batch.v1"
)
D6_D1_CONSISTENCY_ADAPTER_SCHEMA_VERSION = (
    "d6.d1_offline_consistency_adapter.v1"
)
D6_D1_SENSOR_RANGE_RECORD_SCHEMA_VERSION = (
    "d6.d1_sensor_range_consistency.v1"
)
D6_D2_IDENTITY_ADAPTER_SCHEMA_VERSION = (
    "d6.d2_scalable3d_identity_adapter.v1"
)
D6_D2_PARTIAL_IDENTITY_ADAPTER_SCHEMA_VERSION = (
    "d6.d2_scalable3d_partial_identity_adapter.v1"
)
D6_D2_IDENTITY_COMMITMENT_ADAPTER_SCHEMA_VERSION = (
    "d6.d2_scalable3d_identity_commitment_adapter.v1"
)
D6_D2_IDENTITY_RECOVERY_CONFIG_PROVENANCE_SCHEMA_VERSION = (
    "d6.d2_identity_recovery_config_provenance.v1"
)
D6_TRUTH_ISOLATED_EVALUATION_DATE = "2026-07-23"

D1_OFFLINE_CONSISTENCY_RESULT_SCHEMA_VERSION = (
    "d1.consistency.offline_result.v1"
)
D1_OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION = (
    "d1.consistency.offline_result_record.v1"
)
D1_OFFLINE_CONSISTENCY_AGGREGATION_SCHEMA_VERSION = (
    "d1.consistency.offline_aggregation_record.v1"
)
D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1 = (
    "d2.scalable3d_identity_evaluation.v1"
)
D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V2 = (
    "d2.scalable3d_identity_evaluation.v2"
)
D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION = (
    D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1
)
D2_SCALABLE_3D_IDENTITY_METRICS_SCHEMA_VERSION = (
    "d2.scalable3d_identity_metrics.v1"
)
D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V1 = (
    "d2.scalable3d_identity_policy.v1"
)
D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V2 = (
    "d2.scalable3d_identity_commitment_policy.v2"
)
D2_SCALABLE_3D_IDENTITY_POLICY_VERSION = (
    D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V1
)
D2_SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2 = (
    "d2.scalable3d_identity_evidence.v2"
)
D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION_V2 = (
    "d2.identity-evidence-commitment.v2"
)
D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION_V2 = (
    "d2-structural-ambiguity-commitment-v2"
)
D2_SCALABLE_3D_IDENTITY_COMMITMENT_AUDIT_SCHEMA_VERSION_V2 = (
    "d2.scalable3d_identity_commitment_audit.v2"
)
D2_SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION = (
    "d2.scalable3d_partial_identity_diagnostics.v1"
)
D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V1 = (
    "scalable3d-offline-identity-evaluation-manifest-v1"
)
D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2 = (
    "scalable3d-offline-identity-evaluation-manifest-v2"
)
D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION = (
    D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V1
)
D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSIONS = frozenset(
    {
        D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V1,
        D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2,
    }
)
D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SCHEMA_VERSION = (
    "d2.identity-commitment-recovery-config.v2"
)
D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SOURCE = (
    "payload.association.identity_commitment.recovery_config"
)
D2_OBSERVATION_TRUTH_SCHEMA_VERSION_V2 = (
    "d2.scalable3d_observation_truth.v2"
)
D2_OBSERVATION_TRUTH_SCHEMA_VERSION_V1 = (
    "d2.scalable3d_observation_truth.v1"
)

DEFAULT_TRUTH_ISOLATED_BOOTSTRAP_RESAMPLES = 2_000
DEFAULT_TRUTH_ISOLATED_BOOTSTRAP_RNG_SEED = 20260720
REFERENCE_SCALABLE_3D_SCALES = (5, 20, 50, 100, 200)

_D1_METRIC_NAMES = (
    "position_rmse_m",
    "velocity_rmse_mps",
    "mean_nees",
    "mean_normalized_nees",
    "mean_nis",
    "mean_normalized_nis",
    "nis_gate_coverage",
)
_D1_TRUTH_METRIC_NAMES = (
    "position_rmse_m",
    "velocity_rmse_mps",
    "mean_nees",
    "mean_normalized_nees",
)
_D1_NIS_METRIC_NAMES = (
    "mean_nis",
    "mean_normalized_nis",
    "nis_gate_coverage",
)
_D2_METRIC_NAMES = (
    "id_switch_count",
    "track_continuity",
    "identity_continuity",
    "coverage_continuity",
    "duplicate_truth_to_track_count",
)
_D2_REQUIRED_SOURCE_HASHES = (
    "online_d1_records",
    "online_d2_records",
    "observation_truth_labels",
    "identity_evidence_bundle",
)
_D2_PARTIAL_METRIC_NAMES = (
    "evaluable_mapping_coverage",
    "evaluable_frame_coverage",
    "adjacent_transition_coverage",
    "id_switch_lower_bound",
    "anchor_interval_count",
)
_D2_PARTIAL_COUNT_NAMES = (
    "total_mapping_count",
    "available_mapping_count",
    "ambiguous_mapping_count",
    "unavailable_mapping_count",
    "scored_mapping_count",
    "non_scored_mapping_count",
    "evaluable_mapping_count",
    "ambiguous_scored_mapping_count",
    "unavailable_scored_mapping_count",
    "mapped_truth_not_present_mapping_count",
    "missing_identity_evidence_mapping_count",
    "evaluated_frame_count",
    "evaluable_frame_count",
    "transition_opportunity_count",
    "evaluable_transition_count",
    "lower_bound_anchor_excluded_truth_frame_count",
    "lower_bound_anchor_transition_count",
)
_D2_COMMITMENT_METRIC_NAMES = (
    "all_commitment_coverage",
    "observed_commitment_coverage",
    "all_record_count",
    "all_committed_count",
    "all_uncommitted_count",
    "observed_record_count",
    "observed_committed_count",
    "observed_uncommitted_count",
    "uncommitted_mapping_count",
    "recovery_blocker_record_count",
    "recovery_blocker_positive_record_count",
    "recovery_blocker_count_sum",
    "recovery_blocker_count_min",
    "recovery_blocker_count_mean",
    "recovery_blocker_count_max",
    "recovery_watermark_age_record_count",
    "recovery_watermark_age_seconds_min",
    "recovery_watermark_age_seconds_mean",
    "recovery_watermark_age_seconds_max",
    "recovery_blocker_overflow_record_count",
    "recovery_blocker_overflow_track_count",
    "uncommitted_candidate_binding_count",
    "uncommitted_candidate_binding_violation_count",
    "uncommitted_source_binding_violation_count",
)
_D2_PARTIAL_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "scope",
        "denominator_definitions",
        *_D2_PARTIAL_COUNT_NAMES,
        "evaluable_mapping_coverage",
        "evaluable_mapping_coverage_available",
        "evaluable_mapping_coverage_reason",
        "evaluable_frame_coverage",
        "evaluable_frame_coverage_available",
        "evaluable_frame_coverage_reason",
        "evaluable_transition_coverage",
        "evaluable_transition_coverage_available",
        "evaluable_transition_coverage_reason",
        "lower_bound_anchor_exclusion_reason_counts",
        "id_switch_lower_bound",
        "id_switch_lower_bound_available",
        "id_switch_lower_bound_reason",
        "id_switch_upper_bound",
        "id_switch_upper_bound_available",
        "id_switch_upper_bound_reason",
        "excluded_scored_mapping_reason_counts",
    }
)
D2_PARTIAL_IDENTITY_DENOMINATOR_DEFINITIONS = {
    "mapping_denominator": (
        "scored_mapping_count counts created or matched global-track/frame "
        "mappings; lost, dropped, and unmatched audit rows are not scored"
    ),
    "evaluable_mapping": (
        "a scored mapping with status available, exactly one truth target, "
        "and that truth target present in the frame sidecar window"
    ),
    "frame_denominator": (
        "evaluated_frame_count counts every persisted D2 frame represented "
        "by the evidence bundle or verified source records"
    ),
    "evaluable_frame": (
        "a frame with non-empty truth presence where every scored mapping is "
        "evaluable; a frame may be evaluable with zero assigned tracks"
    ),
    "transition_denominator": (
        "transition_opportunity_count is the sum over truth targets of "
        "max(number of truth-present frames minus one, zero)"
    ),
    "evaluable_transition": (
        "an adjacent pair of truth-present frames whose endpoints are both "
        "evaluable and each have exactly one unique evaluable global track "
        "for that truth target"
    ),
    "lower_bound_anchor": (
        "a truth-target/frame pair in an evaluable frame with exactly one "
        "unique evaluable global track; pairs with multiple evaluable global "
        "tracks are excluded rather than ordered into a representative"
    ),
    "lower_bound_anchor_exclusion": (
        "lower_bound_anchor_excluded_truth_frame_count counts truth-target/"
        "frame pairs with more than one unique evaluable global track; such "
        "pairs never become lower-bound anchors even when the frame is "
        "otherwise incomplete"
    ),
    "id_switch_lower_bound": (
        "changes of the unique global_track_id between consecutive "
        "lower-bound anchors for each truth target; anchor intervals are "
        "disjoint and duplicate mappings never select a representative, so "
        "the count is a conservative episode lower bound"
    ),
    "missing_identity_evidence_mapping": (
        "a scored mapping carrying source_lineage_missing, "
        "truth_label_missing, or truth_mapping_evidence_unavailable"
    ),
    "id_switch_upper_bound": (
        "not emitted because missing or ambiguous sidecar evidence does not "
        "establish a complete truth-assignment transition universe"
    ),
}
D2_IDENTITY_COMMITMENT_DENOMINATOR_POLICY = {
    "all_records": "all_persisted_v2_identity_evidence_records",
    "observed_records": (
        "v2_identity_evidence_records_with_association_state_created_or_matched"
    ),
    "committed": "identity_commitment_state_equals_committed",
    "uncommitted": "all_other_v2_identity_commitment_states",
    "recovery_blocker_count": (
        "all_v2_identity_evidence_records_including_zero"
    ),
    "watermark_age": (
        "frame_timestamp_minus_recovery_not_before_measurement_timestamp_"
        "for_records_with_watermark"
    ),
}
D2_UNCOMMITTED_BINDING_VIOLATION_POLICY = {
    "candidate": (
        "uncommitted_frame_mapping_carries_truth_target_or_candidate"
    ),
    "source": (
        "uncommitted_v2_evidence_or_frame_mapping_carries_source_"
        "observation_lineage"
    ),
    "required_value": 0,
}
D2_COMMITTED_ANCHOR_ACROSS_UNCOMMITTED_GAP_POLICY = (
    "compare_consecutive_committed_truth_anchors_across_uncommitted_gaps"
)
_D2_EVALUATION_POLICY_BY_SCHEMA = {
    D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1: (
        D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V1
    ),
    D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V2: (
        D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V2
    ),
}
_D2_COMMITMENT_STATES = frozenset(
    {
        "committed",
        "identity_uncommitted_ambiguity_hold",
        "identity_uncommitted_after_hold",
    }
)
_D2_OBSERVED_ASSOCIATION_STATES = frozenset({"created", "matched"})
_D2_V2_EVIDENCE_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "episode_id",
        "frame_index",
        "frame_timestamp",
        "global_track_id",
        "lifecycle_state",
        "association_state",
        "identity_commitment",
        "source_observations",
        "d1_record_sequences",
        "d2_record_sequence",
    }
)
_D2_V2_COMMITMENT_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "global_track_id",
        "association_state",
        "identity_commitment_state",
        "reason",
        "state_timestamp",
        "commitment_generation",
        "measurement_timestamp",
        "arrival_timestamp",
        "source_observation_evidence_key",
        "source_observation_evidence_generation",
        "source_observation_disposition",
        "ambiguity_component_key",
        "ambiguity_evidence_id",
        "ambiguity_component_generation",
        "publisher_node_id",
        "publisher_epoch",
        "active_lease_count",
        "active_lease_keys",
        "lease_first_seen_timestamp",
        "lease_soft_deadline",
        "lease_hard_deadline",
        "lease_expired_timestamp",
        "lease_expiration_reason",
        "recovery_blocker_count",
        "recovery_not_before_measurement_timestamp",
        "recovery_blocker_overflow",
        "online_truth_used",
    }
)
_SHA256_PREFIX = "sha256:"


class TruthIsolatedEvaluationError(ValueError):
    """Raised when a public evaluator artifact violates its frozen contract."""


class _PartialIdentityValidationError(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = str(reason)


class _IdentityRecoveryConfigValidationError(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = str(reason)


@dataclass(frozen=True, slots=True)
class PublicMetricEvidence:
    """One availability-aware metric retained without missing-to-zero coercion."""

    value: int | float | None
    available: bool
    sample_count: int
    unavailable_reason: str | None = None
    unavailability_reason_counts: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        available = bool(self.available)
        sample_count = int(self.sample_count)
        reason = (
            None
            if self.unavailable_reason is None
            else str(self.unavailable_reason).strip()
        )
        reasons = {
            str(key): int(value)
            for key, value in (self.unavailability_reason_counts or {}).items()
            if int(value) > 0
        }
        if sample_count < 0:
            raise ValueError("metric sample_count must be non-negative")
        if available:
            if self.value is None or reason is not None:
                raise ValueError(
                    "available metric requires a value and no unavailable reason"
                )
            value = _finite_metric_value(self.value)
        else:
            if self.value is not None or not reason:
                raise ValueError(
                    "unavailable metric requires a null value and a reason"
                )
            value = None
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "sample_count", sample_count)
        object.__setattr__(self, "unavailable_reason", reason)
        object.__setattr__(
            self,
            "unavailability_reason_counts",
            dict(sorted(reasons.items())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "availability": "available" if self.available else "unavailable",
            "available": self.available,
            "sample_count": self.sample_count,
            "unavailable_reason": self.unavailable_reason,
            "unavailability_reason_counts": dict(
                self.unavailability_reason_counts or {}
            ),
        }


@dataclass(frozen=True, slots=True)
class D2IdentityCommitmentEvidenceRecord:
    """D6-owned, availability-aware view of D2 identity commitment audit v2."""

    available: bool
    unavailable_reason: str | None
    metrics: Mapping[str, PublicMetricEvidence]
    state_counts: Mapping[str, int]
    reason_counts: Mapping[str, int]
    recovery_blocked_reason_counts: Mapping[str, int]
    denominator_policy: Mapping[str, Any] | None
    uncommitted_binding_violation_policy: Mapping[str, Any] | None
    committed_anchor_across_uncommitted_gap_policy: str | None
    producer_evaluation_schema_version: str | None
    producer_evaluation_policy_version: str | None
    producer_evidence_schema_version: str | None
    producer_commitment_schema_version: str | None
    producer_commitment_policy_version: str | None
    producer_audit_schema_version: str | None
    evidence_bundle_sha256_verified: bool
    schema_version: str = (
        D6_D2_IDENTITY_COMMITMENT_ADAPTER_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != D6_D2_IDENTITY_COMMITMENT_ADAPTER_SCHEMA_VERSION
        ):
            raise ValueError("unsupported D2 identity commitment adapter schema")
        available = bool(self.available)
        reason = (
            None
            if self.unavailable_reason is None
            else str(self.unavailable_reason).strip()
        )
        metrics = dict(self.metrics)
        if set(metrics) != set(_D2_COMMITMENT_METRIC_NAMES):
            raise ValueError("D2 identity commitment metric set is incomplete")
        state_counts = _validated_count_mapping(
            self.state_counts,
            "D2 identity commitment state counts",
        )
        reason_counts = _validated_count_mapping(
            self.reason_counts,
            "D2 identity commitment reason counts",
        )
        blocked_reasons = _validated_count_mapping(
            self.recovery_blocked_reason_counts,
            "D2 identity commitment recovery blocked reasons",
        )
        if available:
            if reason is not None:
                raise ValueError(
                    "available D2 identity commitment evidence cannot carry a reason"
                )
            if (
                self.producer_evaluation_schema_version
                != D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V2
                or self.producer_evaluation_policy_version
                != D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V2
                or self.producer_evidence_schema_version
                != D2_SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2
                or self.producer_commitment_schema_version
                != D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION_V2
                or self.producer_commitment_policy_version
                != D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION_V2
                or self.producer_audit_schema_version
                != D2_SCALABLE_3D_IDENTITY_COMMITMENT_AUDIT_SCHEMA_VERSION_V2
            ):
                raise ValueError(
                    "available D2 identity commitment evidence has incompatible versions"
                )
            if not self.evidence_bundle_sha256_verified:
                raise ValueError(
                    "available D2 identity commitment evidence requires SHA provenance"
                )
            if self.denominator_policy != D2_IDENTITY_COMMITMENT_DENOMINATOR_POLICY:
                raise ValueError(
                    "D2 identity commitment denominator policy is inconsistent"
                )
            if (
                self.uncommitted_binding_violation_policy
                != D2_UNCOMMITTED_BINDING_VIOLATION_POLICY
            ):
                raise ValueError(
                    "D2 uncommitted binding violation policy is inconsistent"
                )
            if (
                self.committed_anchor_across_uncommitted_gap_policy
                != D2_COMMITTED_ANCHOR_ACROSS_UNCOMMITTED_GAP_POLICY
            ):
                raise ValueError(
                    "D2 committed-anchor gap policy is inconsistent"
                )
        else:
            if not reason:
                raise ValueError(
                    "unavailable D2 identity commitment evidence requires a reason"
                )
            if any(metric.available for metric in metrics.values()):
                raise ValueError(
                    "unavailable D2 identity commitment evidence exposes metrics"
                )
            if state_counts or reason_counts or blocked_reasons:
                raise ValueError(
                    "unavailable D2 identity commitment evidence exposes counts"
                )
            if self.evidence_bundle_sha256_verified:
                raise ValueError(
                    "unavailable D2 identity commitment evidence cannot verify SHA provenance"
                )
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "unavailable_reason", reason)
        object.__setattr__(self, "metrics", dict(sorted(metrics.items())))
        object.__setattr__(self, "state_counts", state_counts)
        object.__setattr__(self, "reason_counts", reason_counts)
        object.__setattr__(
            self,
            "recovery_blocked_reason_counts",
            blocked_reasons,
        )
        object.__setattr__(
            self,
            "denominator_policy",
            (
                None
                if self.denominator_policy is None
                else dict(self.denominator_policy)
            ),
        )
        object.__setattr__(
            self,
            "uncommitted_binding_violation_policy",
            (
                None
                if self.uncommitted_binding_violation_policy is None
                else dict(self.uncommitted_binding_violation_policy)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "availability": "available" if self.available else "unavailable",
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "producer_evaluation_schema_version": (
                self.producer_evaluation_schema_version
            ),
            "producer_evaluation_policy_version": (
                self.producer_evaluation_policy_version
            ),
            "producer_evidence_schema_version": (
                self.producer_evidence_schema_version
            ),
            "producer_commitment_schema_version": (
                self.producer_commitment_schema_version
            ),
            "producer_commitment_policy_version": (
                self.producer_commitment_policy_version
            ),
            "producer_audit_schema_version": (
                self.producer_audit_schema_version
            ),
            "evidence_bundle_sha256_verified": (
                self.evidence_bundle_sha256_verified
            ),
            "denominator_policy": self.denominator_policy,
            "state_counts": dict(self.state_counts),
            "reason_counts": dict(self.reason_counts),
            "recovery_blocked_reason_counts": dict(
                self.recovery_blocked_reason_counts
            ),
            "uncommitted_binding_violation_policy": (
                self.uncommitted_binding_violation_policy
            ),
            "committed_anchor_across_uncommitted_gap_policy": (
                self.committed_anchor_across_uncommitted_gap_policy
            ),
            "metrics": {
                name: metric.to_dict()
                for name, metric in self.metrics.items()
            },
            "strict_id_switch_count_backfilled": False,
            "uncommitted_gap_treated_as_zero_id_switch": False,
            "offline_only": True,
            "evaluator_only": True,
            "control_consumed": False,
        }


@dataclass(frozen=True, slots=True)
class D2IdentityRecoveryConfigProvenanceRecord:
    """Manifest- and JSONL-bound D2 identity recovery configuration."""

    available: bool
    unavailable_reason: str | None
    config_snapshot: Mapping[str, Any] | None
    config_sha256: str | None
    config_schema_version: str | None
    config_version: str | None
    identity_manifest_schema_version: str | None
    identity_manifest_sha256: str | None
    online_d2_records_sha256: str | None
    config_record_count: int | None
    d2_record_count: int | None
    consistency_verified: bool
    source: str | None
    online_records_verified: bool
    verification_mode: str
    schema_version: str = (
        D6_D2_IDENTITY_RECOVERY_CONFIG_PROVENANCE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != D6_D2_IDENTITY_RECOVERY_CONFIG_PROVENANCE_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported D2 identity recovery config provenance schema"
            )
        available = bool(self.available)
        reason = (
            None
            if self.unavailable_reason is None
            else str(self.unavailable_reason).strip()
        )
        snapshot = (
            None
            if self.config_snapshot is None
            else dict(self.config_snapshot)
        )
        config_count = (
            None
            if self.config_record_count is None
            else int(self.config_record_count)
        )
        d2_count = (
            None if self.d2_record_count is None else int(self.d2_record_count)
        )
        if available:
            if reason is not None:
                raise ValueError(
                    "available recovery config provenance cannot carry a reason"
                )
            if not snapshot:
                raise ValueError(
                    "available recovery config provenance requires a snapshot"
                )
            if (
                self.config_schema_version
                != D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SCHEMA_VERSION
                or snapshot.get("schema_version")
                != D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SCHEMA_VERSION
            ):
                raise ValueError(
                    "available recovery config provenance has an unsupported schema"
                )
            if (
                self.identity_manifest_schema_version
                != D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2
            ):
                raise ValueError(
                    "available recovery config provenance requires manifest v2"
                )
            if (
                self.config_sha256 is None
                or self.identity_manifest_sha256 is None
                or self.online_d2_records_sha256 is None
            ):
                raise ValueError(
                    "available recovery config provenance requires SHA-256 bindings"
                )
            if (
                _normalized_sha256(self.config_sha256)
                != _canonical_payload_sha256(snapshot)
            ):
                raise ValueError(
                    "available recovery config provenance has a bad config digest"
                )
            _normalized_sha256(self.identity_manifest_sha256)
            _normalized_sha256(self.online_d2_records_sha256)
            if (
                config_count is None
                or d2_count is None
                or config_count <= 0
                or config_count != d2_count
            ):
                raise ValueError(
                    "available recovery config provenance has inconsistent counts"
                )
            if (
                not self.consistency_verified
                or not self.online_records_verified
                or self.source
                != D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SOURCE
            ):
                raise ValueError(
                    "available recovery config provenance is not independently verified"
                )
        else:
            if not reason:
                raise ValueError(
                    "unavailable recovery config provenance requires a reason"
                )
            if snapshot is not None or self.config_sha256 is not None:
                raise ValueError(
                    "unavailable recovery config provenance cannot expose a config"
                )
            if self.consistency_verified or self.online_records_verified:
                raise ValueError(
                    "unavailable recovery config provenance cannot be verified"
                )
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "unavailable_reason", reason)
        object.__setattr__(self, "config_snapshot", snapshot)
        object.__setattr__(self, "config_record_count", config_count)
        object.__setattr__(self, "d2_record_count", d2_count)
        object.__setattr__(
            self,
            "verification_mode",
            str(self.verification_mode).strip() or "unavailable",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "availability": "available" if self.available else "unavailable",
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "identity_commitment_recovery_config": (
                None
                if self.config_snapshot is None
                else dict(self.config_snapshot)
            ),
            "identity_commitment_recovery_config_sha256": (
                self.config_sha256
            ),
            "identity_commitment_recovery_config_schema_version": (
                self.config_schema_version
            ),
            "identity_commitment_recovery_config_version": self.config_version,
            "identity_commitment_recovery_config_record_count": (
                self.config_record_count
            ),
            "identity_commitment_recovery_config_consistency_verified": (
                self.consistency_verified
            ),
            "identity_commitment_recovery_config_source": self.source,
            "identity_manifest_schema_version": (
                self.identity_manifest_schema_version
            ),
            "identity_manifest_sha256": self.identity_manifest_sha256,
            "d2_record_count": self.d2_record_count,
            "online_d2_records_sha256": self.online_d2_records_sha256,
            "online_d2_records_verified": self.online_records_verified,
            "provenance_verified": self.available,
            "verification_mode": self.verification_mode,
            "offline_only": True,
            "evaluator_only": True,
            "control_consumed": False,
        }


@dataclass(frozen=True, slots=True)
class D2PartialIdentityDiagnosticsRecord:
    """D6 view of provenance-verified evaluator-only partial identity evidence."""

    available: bool
    unavailable_reason: str | None
    metrics: Mapping[str, PublicMetricEvidence]
    counts: Mapping[str, int]
    lower_bound_anchor_exclusion_reason_counts: Mapping[str, int]
    excluded_scored_mapping_reason_counts: Mapping[str, int]
    producer_schema_version: str | None
    identity_manifest_schema_version: str | None
    identity_manifest_sha256: str | None
    identity_evaluation_sha256: str | None
    provenance_verified: bool
    verification_mode: str
    schema_version: str = D6_D2_PARTIAL_IDENTITY_ADAPTER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D6_D2_PARTIAL_IDENTITY_ADAPTER_SCHEMA_VERSION:
            raise ValueError("unsupported D2 partial identity adapter schema")
        available = bool(self.available)
        reason = (
            None
            if self.unavailable_reason is None
            else str(self.unavailable_reason).strip()
        )
        metrics = dict(self.metrics)
        if set(metrics) != set(_D2_PARTIAL_METRIC_NAMES):
            raise ValueError("D2 partial identity metric set is incomplete")
        counts = _validated_count_mapping(
            self.counts,
            "D2 partial identity counts",
        )
        anchor_reasons = _validated_count_mapping(
            self.lower_bound_anchor_exclusion_reason_counts,
            "D2 partial identity anchor exclusion reasons",
        )
        excluded_reasons = _validated_count_mapping(
            self.excluded_scored_mapping_reason_counts,
            "D2 partial identity excluded mapping reasons",
        )
        if available:
            if reason is not None or not self.provenance_verified:
                raise ValueError(
                    "available D2 partial identity evidence requires verified provenance"
                )
            if set(counts) != set(_D2_PARTIAL_COUNT_NAMES):
                raise ValueError("D2 partial identity count set is incomplete")
            if (
                self.producer_schema_version
                != D2_SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION
            ):
                raise ValueError("available D2 partial identity schema is unsupported")
            if (
                self.identity_manifest_schema_version
                not in D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSIONS
            ):
                raise ValueError(
                    "available D2 partial identity manifest schema is unsupported"
                )
            if (
                self.identity_manifest_sha256 is None
                or self.identity_evaluation_sha256 is None
            ):
                raise ValueError(
                    "available D2 partial identity evidence requires SHA-256 bindings"
                )
        else:
            if not reason:
                raise ValueError(
                    "unavailable D2 partial identity evidence requires a reason"
                )
            if counts or anchor_reasons or excluded_reasons:
                raise ValueError(
                    "unavailable D2 partial identity evidence must not retain counts"
                )
            if any(metric.available for metric in metrics.values()):
                raise ValueError(
                    "unavailable D2 partial identity evidence cannot expose metrics"
                )
            if self.provenance_verified:
                raise ValueError(
                    "unavailable D2 partial identity evidence cannot verify provenance"
                )
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "unavailable_reason", reason)
        object.__setattr__(self, "metrics", dict(sorted(metrics.items())))
        object.__setattr__(self, "counts", counts)
        object.__setattr__(
            self,
            "lower_bound_anchor_exclusion_reason_counts",
            anchor_reasons,
        )
        object.__setattr__(
            self,
            "excluded_scored_mapping_reason_counts",
            excluded_reasons,
        )
        object.__setattr__(
            self,
            "verification_mode",
            str(self.verification_mode).strip() or "unavailable",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "producer_schema_version": self.producer_schema_version,
            "availability": "available" if self.available else "unavailable",
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "offline_only": True,
            "evaluator_only": True,
            "control_consumed": False,
            "provenance_verified": self.provenance_verified,
            "verification_mode": self.verification_mode,
            "identity_manifest_schema_version": (
                self.identity_manifest_schema_version
            ),
            "identity_manifest_sha256": self.identity_manifest_sha256,
            "identity_evaluation_sha256": self.identity_evaluation_sha256,
            "metrics": {
                name: metric.to_dict() for name, metric in self.metrics.items()
            },
            "counts": dict(self.counts),
            "lower_bound_anchor_exclusion_reason_counts": dict(
                self.lower_bound_anchor_exclusion_reason_counts
            ),
            "excluded_scored_mapping_reason_counts": dict(
                self.excluded_scored_mapping_reason_counts
            ),
            "strict_id_switch_count_backfilled": False,
            "id_switch_upper_bound_reported": False,
        }


@dataclass(frozen=True, slots=True)
class TruthIsolatedEpisodeContext:
    """Main-owned episode identity and actual scale, independent of scenario names."""

    episode_id: str
    scenario_id: str
    scenario_version: str
    run_id: str
    seed: int
    target_count: int
    resource_count: int
    recon_count: int = 0
    camera_count: int = 0

    def __post_init__(self) -> None:
        for name in ("episode_id", "scenario_id", "scenario_version", "run_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "seed", int(self.seed))
        for name in ("target_count", "resource_count"):
            value = int(getattr(self, name))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        for name in ("recon_count", "camera_count"):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "run_id": self.run_id,
            "seed": self.seed,
            "target_count": self.target_count,
            "resource_count": self.resource_count,
            "recon_count": self.recon_count,
            "camera_count": self.camera_count,
        }


@dataclass(frozen=True, slots=True)
class D1SensorRangeConsistencyRecord:
    """D1 consistency metrics grouped by explicit sensor and range bin."""

    scenario_id: str
    scenario_version: str
    run_id: str
    seed: int | None
    sensor_id: str
    sensor_type: str
    source_sensor_type: str
    range_bin: str
    metrics: Mapping[str, PublicMetricEvidence]
    offline_result_digest: str
    input_digests: Mapping[str, str | None]
    record_count: int
    schema_version: str = D6_D1_SENSOR_RANGE_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D6_D1_SENSOR_RANGE_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported D1 sensor/range adapter schema")
        for name in (
            "scenario_id",
            "scenario_version",
            "run_id",
            "sensor_id",
            "sensor_type",
            "source_sensor_type",
            "range_bin",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        metrics = dict(self.metrics)
        if set(metrics) != set(_D1_METRIC_NAMES):
            raise ValueError("D1 grouped metric set is incomplete")
        if int(self.record_count) <= 0:
            raise ValueError("D1 grouped record_count must be positive")
        object.__setattr__(self, "metrics", dict(sorted(metrics.items())))
        object.__setattr__(self, "input_digests", dict(self.input_digests))
        object.__setattr__(self, "record_count", int(self.record_count))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "run_id": self.run_id,
            "seed": self.seed,
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "source_sensor_type": self.source_sensor_type,
            "range_bin": self.range_bin,
            "record_count": self.record_count,
            "offline_result_digest": self.offline_result_digest,
            "input_digests": dict(self.input_digests),
            "metrics": {
                name: metric.to_dict() for name, metric in self.metrics.items()
            },
        }


@dataclass(frozen=True, slots=True)
class D1ConsistencyEvaluationRecord:
    """D6-normalized view of one public D1 offline consistency result."""

    scenario_id: str
    scenario_version: str
    run_id: str
    seed: int | None
    status: str
    metrics: Mapping[str, PublicMetricEvidence]
    sensor_range_records: tuple[D1SensorRangeConsistencyRecord, ...]
    artifact_digest: str | None
    external_file_sha256: str | None
    input_digests: Mapping[str, str | None]
    failure_reasons: tuple[str, ...]
    verification_mode: str
    schema_version: str = D6_D1_CONSISTENCY_ADAPTER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D6_D1_CONSISTENCY_ADAPTER_SCHEMA_VERSION:
            raise ValueError("unsupported D1 consistency adapter schema")
        if self.status not in {"available", "partial", "unavailable"}:
            raise ValueError("unsupported D1 consistency status")
        metrics = dict(self.metrics)
        if set(metrics) != set(_D1_METRIC_NAMES):
            raise ValueError("D1 result metric set is incomplete")
        object.__setattr__(self, "metrics", dict(sorted(metrics.items())))
        object.__setattr__(self, "sensor_range_records", tuple(self.sensor_range_records))
        object.__setattr__(self, "input_digests", dict(self.input_digests))
        object.__setattr__(
            self,
            "failure_reasons",
            tuple(dict.fromkeys(str(value) for value in self.failure_reasons)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "producer_schema_version": D1_OFFLINE_CONSISTENCY_RESULT_SCHEMA_VERSION,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "run_id": self.run_id,
            "seed": self.seed,
            "status": self.status,
            "artifact_digest": self.artifact_digest,
            "external_file_sha256": self.external_file_sha256,
            "input_digests": dict(self.input_digests),
            "verification_mode": self.verification_mode,
            "failure_reasons": list(self.failure_reasons),
            "metrics": {
                name: metric.to_dict() for name, metric in self.metrics.items()
            },
            "sensor_range_records": [
                record.to_dict() for record in self.sensor_range_records
            ],
        }


@dataclass(frozen=True, slots=True)
class D2IdentityEvaluationRecord:
    """D6-normalized view of one public D2 identity evaluation artifact."""

    episode_id: str
    producer_schema_version: str | None
    producer_policy_version: str | None
    metrics: Mapping[str, PublicMetricEvidence]
    evaluated_frame_count: int
    truth_frame_count: Mapping[str, int]
    truth_assigned_frame_count: Mapping[str, int]
    truth_identity_stable_frame_count: Mapping[str, int]
    confusion_matrix: Mapping[str, Mapping[str, int]] | None
    source_hashes: Mapping[str, str]
    artifact_digest: str | None
    external_file_sha256: str | None
    truth_isolation_verified: bool
    truth_metric_evidence_verified: bool
    truth_metric_evidence_reason: str | None
    source_verification: str
    configuration: Mapping[str, Any]
    audit: Mapping[str, Any]
    identity_commitment: D2IdentityCommitmentEvidenceRecord
    identity_recovery_config_provenance: (
        D2IdentityRecoveryConfigProvenanceRecord
    )
    partial_identity_diagnostics: D2PartialIdentityDiagnosticsRecord
    verification_mode: str
    schema_version: str = D6_D2_IDENTITY_ADAPTER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D6_D2_IDENTITY_ADAPTER_SCHEMA_VERSION:
            raise ValueError("unsupported D2 identity adapter schema")
        if not str(self.episode_id).strip():
            raise ValueError("episode_id must be non-empty")
        metrics = dict(self.metrics)
        if set(metrics) != set(_D2_METRIC_NAMES):
            raise ValueError("D2 identity metric set is incomplete")
        object.__setattr__(self, "metrics", dict(sorted(metrics.items())))
        object.__setattr__(self, "evaluated_frame_count", int(self.evaluated_frame_count))
        for name in (
            "truth_frame_count",
            "truth_assigned_frame_count",
            "truth_identity_stable_frame_count",
        ):
            object.__setattr__(
                self,
                name,
                _validated_count_mapping(getattr(self, name), name),
            )
        if self.confusion_matrix is not None:
            object.__setattr__(
                self,
                "confusion_matrix",
                _validated_confusion_matrix(self.confusion_matrix),
            )
        if not isinstance(
            self.identity_commitment,
            D2IdentityCommitmentEvidenceRecord,
        ):
            raise ValueError(
                "D2 identity commitment evidence uses an unsupported type"
            )
        if not isinstance(
            self.identity_recovery_config_provenance,
            D2IdentityRecoveryConfigProvenanceRecord,
        ):
            raise ValueError(
                "D2 identity recovery config provenance uses an unsupported type"
            )
        if not isinstance(
            self.partial_identity_diagnostics,
            D2PartialIdentityDiagnosticsRecord,
        ):
            raise ValueError(
                "D2 partial identity diagnostics use an unsupported type"
            )
        object.__setattr__(self, "source_hashes", dict(sorted(self.source_hashes.items())))
        object.__setattr__(self, "configuration", dict(self.configuration))
        object.__setattr__(self, "audit", dict(self.audit))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "producer_schema_version": self.producer_schema_version,
            "producer_policy_version": self.producer_policy_version,
            "episode_id": self.episode_id,
            "artifact_digest": self.artifact_digest,
            "external_file_sha256": self.external_file_sha256,
            "source_hashes": dict(self.source_hashes),
            "verification_mode": self.verification_mode,
            "truth_isolation_verified": self.truth_isolation_verified,
            "truth_metric_evidence_verified": (
                self.truth_metric_evidence_verified
            ),
            "truth_metric_evidence_reason": self.truth_metric_evidence_reason,
            "source_verification": self.source_verification,
            "policy_version": D2_SCALABLE_3D_IDENTITY_POLICY_VERSION,
            "configuration": dict(self.configuration),
            "evaluated_frame_count": self.evaluated_frame_count,
            "metrics": {
                name: metric.to_dict() for name, metric in self.metrics.items()
            },
            "id_switch_count": self.metrics["id_switch_count"].value,
            "id_switch_count_availability": (
                "available"
                if self.metrics["id_switch_count"].available
                else "unavailable"
            ),
            "id_switch_count_unavailable_reason": self.metrics[
                "id_switch_count"
            ].unavailable_reason,
            "truth_frame_count": dict(self.truth_frame_count),
            "truth_assigned_frame_count": dict(self.truth_assigned_frame_count),
            "truth_identity_stable_frame_count": dict(
                self.truth_identity_stable_frame_count
            ),
            "confusion_matrix": (
                None
                if self.confusion_matrix is None
                else {
                    truth_id: dict(track_counts)
                    for truth_id, track_counts in self.confusion_matrix.items()
                }
            ),
            "partial_identity_diagnostics": (
                self.partial_identity_diagnostics.to_dict()
            ),
            "identity_commitment": self.identity_commitment.to_dict(),
            "identity_recovery_config_provenance": (
                self.identity_recovery_config_provenance.to_dict()
            ),
            "audit": dict(self.audit),
        }


@dataclass(frozen=True, slots=True)
class TruthIsolatedEpisodeEvaluationRecord:
    """Combined D1/D2 evaluator record for one main-owned episode."""

    context: TruthIsolatedEpisodeContext
    d1: D1ConsistencyEvaluationRecord
    d2: D2IdentityEvaluationRecord
    schema_version: str = D6_TRUTH_ISOLATED_EPISODE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D6_TRUTH_ISOLATED_EPISODE_SCHEMA_VERSION:
            raise ValueError("unsupported truth-isolated episode schema")
        _validate_context_alignment(self.context, self.d1, self.d2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_date": D6_TRUTH_ISOLATED_EVALUATION_DATE,
            "context": self.context.to_dict(),
            "d1_consistency": self.d1.to_dict(),
            "d2_identity": self.d2.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class TruthIsolatedBatchSummary:
    """Serializable batch aggregate grouped by scenario and actual scale."""

    episode_count: int
    scale_values: tuple[int, ...]
    groups: tuple[Mapping[str, Any], ...]
    d1_sensor_range_groups: tuple[Mapping[str, Any], ...]
    reference_scale_coverage: Mapping[str, bool]
    schema_version: str = D6_TRUTH_ISOLATED_BATCH_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_date": D6_TRUTH_ISOLATED_EVALUATION_DATE,
            "episode_count": int(self.episode_count),
            "scale_values": list(self.scale_values),
            "reference_scale_coverage": dict(self.reference_scale_coverage),
            "groups": [dict(group) for group in self.groups],
            "d1_sensor_range_groups": [
                dict(group) for group in self.d1_sensor_range_groups
            ],
        }


class TruthIsolatedOfflineReportGenerator:
    """Write per-seed CSV, aggregate JSON, and Chinese Markdown."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        records: Sequence[TruthIsolatedEpisodeEvaluationRecord],
        bootstrap_resamples: int = DEFAULT_TRUTH_ISOLATED_BOOTSTRAP_RESAMPLES,
        bootstrap_rng_seed: int = DEFAULT_TRUTH_ISOLATED_BOOTSTRAP_RNG_SEED,
        title: str = "三维规模化真值隔离评估报告",
    ) -> dict[str, Path]:
        normalized = tuple(records)
        summary = aggregate_truth_isolated_episode_records(
            normalized,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
        )
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)

        episode_csv = output / "truth_isolated_per_seed.csv"
        _write_csv(episode_csv, [_episode_csv_row(record) for record in normalized])

        d1_group_csv = output / "d1_sensor_range_per_seed.csv"
        d1_rows = [
            _d1_group_csv_row(record.context, group)
            for record in normalized
            for group in record.d1.sensor_range_records
        ]
        _write_csv(d1_group_csv, d1_rows)

        aggregate_json = output / "truth_isolated_aggregate.json"
        aggregate_json.write_text(
            json.dumps(
                summary.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )

        markdown = output / "TRUTH_ISOLATED_EVALUATION_CN.md"
        markdown.write_text(
            render_truth_isolated_markdown(normalized, summary, title=title),
            encoding="utf-8",
        )
        return {
            "per_seed_csv": episode_csv,
            "d1_sensor_range_per_seed_csv": d1_group_csv,
            "aggregate_json": aggregate_json,
            "markdown": markdown,
        }


def adapt_d1_offline_consistency(
    source: object | Mapping[str, Any] | str | Path,
    *,
    expected_sha256: str | None = None,
) -> D1ConsistencyEvaluationRecord:
    """Adapt a public D1 result DTO or an externally hash-verified JSON artifact."""

    payload, external_hash, verification_mode = _public_payload(
        source,
        expected_sha256=expected_sha256,
        artifact_name="D1 offline consistency result",
    )
    if payload.get("schema_version") != D1_OFFLINE_CONSISTENCY_RESULT_SCHEMA_VERSION:
        raise TruthIsolatedEvaluationError(
            "unsupported D1 offline consistency result schema"
        )
    if payload.get("record_schema_version") != D1_OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION:
        raise TruthIsolatedEvaluationError(
            "unsupported D1 offline consistency record schema"
        )
    content_digest = _normalized_sha256(payload.get("content_digest"))
    unsigned = dict(payload)
    unsigned.pop("content_digest", None)
    if _canonical_payload_sha256(unsigned) != content_digest:
        raise TruthIsolatedEvaluationError(
            "D1 offline consistency content digest mismatch"
        )
    input_digests = _normalized_d1_input_digests(
        _mapping(payload.get("input_digests"), "D1 input digests")
    )

    records = _mapping_sequence(payload.get("records"), "D1 consistency records")
    if int(payload.get("record_count", -1)) != len(records):
        raise TruthIsolatedEvaluationError("D1 consistency record_count mismatch")
    aggregations = _d1_aggregation_records(
        source,
        payload,
        records,
        input_digests=input_digests,
    )
    _validate_d1_aggregation_records(
        aggregations,
        payload,
        content_digest,
        input_digests=input_digests,
        source_records=records,
    )
    if payload.get("truth_usage") != "offline_evaluation_only":
        raise TruthIsolatedEvaluationError(
            "D1 consistency result must declare offline-only truth usage"
        )

    result_metrics_payload = _mapping(payload.get("metrics"), "D1 metrics")
    if set(result_metrics_payload) != set(_D1_METRIC_NAMES):
        raise TruthIsolatedEvaluationError("D1 result metric set is incomplete")
    result_metrics = {
        name: _metric_from_d1_summary(result_metrics_payload[name], name)
        for name in _D1_METRIC_NAMES
    }
    status = str(payload.get("status", ""))
    _validate_d1_result_availability(
        status=status,
        metrics=result_metrics,
        input_digests=input_digests,
    )
    grouped = _group_d1_consistency_records(
        aggregations,
        input_digests=input_digests,
        offline_result_digest=content_digest,
    )
    failure_reasons_payload = payload.get("failure_reasons", ())
    if not isinstance(failure_reasons_payload, Sequence) or isinstance(
        failure_reasons_payload, (str, bytes)
    ):
        raise TruthIsolatedEvaluationError(
            "D1 failure_reasons must be a sequence"
        )
    failure_reasons = tuple(str(value) for value in failure_reasons_payload)
    return D1ConsistencyEvaluationRecord(
        scenario_id=_identifier(payload.get("scenario_id"), "D1 scenario_id"),
        scenario_version=_identifier(
            payload.get("scenario_version"), "D1 scenario_version"
        ),
        run_id=_identifier(payload.get("run_id"), "D1 run_id"),
        seed=_optional_int(payload.get("seed")),
        status=status,
        metrics=result_metrics,
        sensor_range_records=grouped,
        artifact_digest=content_digest,
        external_file_sha256=external_hash,
        input_digests=input_digests,
        failure_reasons=failure_reasons,
        verification_mode=verification_mode,
    )


def adapt_d2_scalable_3d_identity(
    source: object | Mapping[str, Any] | str | Path,
    *,
    expected_sha256: str | None = None,
    expected_source_hashes: Mapping[str, str] | None = None,
    identity_manifest: object | Mapping[str, Any] | str | Path | None = None,
    expected_identity_manifest_sha256: str | None = None,
    d2_online_d2_records: str | Path | None = None,
    d2_expected_online_d2_records_sha256: str | None = None,
) -> D2IdentityEvaluationRecord:
    """Adapt a public D2 identity DTO without reconstructing identity mappings."""

    payload, external_hash, verification_mode = _public_payload(
        source,
        expected_sha256=expected_sha256,
        artifact_name="D2 scalable 3D identity evaluation",
    )
    producer_schema_version = str(payload.get("schema_version", ""))
    if producer_schema_version not in _D2_EVALUATION_POLICY_BY_SCHEMA:
        raise TruthIsolatedEvaluationError(
            "unsupported D2 identity evaluation schema"
        )
    producer_policy_version = str(payload.get("policy_version", ""))
    if (
        producer_policy_version
        != _D2_EVALUATION_POLICY_BY_SCHEMA[producer_schema_version]
    ):
        raise TruthIsolatedEvaluationError("unsupported D2 identity policy")
    if payload.get("hash_algorithm") != "sha256":
        raise TruthIsolatedEvaluationError("D2 identity artifact requires sha256")

    source_hashes_payload = _mapping(
        payload.get("source_hashes"), "D2 source_hashes"
    )
    missing_source_hashes = set(_D2_REQUIRED_SOURCE_HASHES) - set(
        source_hashes_payload
    )
    if missing_source_hashes:
        raise TruthIsolatedEvaluationError(
            "D2 identity source hashes are incomplete: "
            + ",".join(sorted(missing_source_hashes))
        )
    source_hashes = {
        str(name): _normalized_sha256(value)
        for name, value in source_hashes_payload.items()
    }
    if (
        verification_mode == "sha256_verified_artifact"
        and expected_source_hashes is None
    ):
        raise TruthIsolatedEvaluationError(
            "D2 identity path requires expected_source_hashes"
        )
    if expected_source_hashes is not None:
        missing_expected_hashes = set(_D2_REQUIRED_SOURCE_HASHES) - {
            str(name) for name in expected_source_hashes
        }
        if missing_expected_hashes:
            raise TruthIsolatedEvaluationError(
                "D2 expected source hashes are incomplete: "
                + ",".join(sorted(missing_expected_hashes))
            )
        for name, expected in expected_source_hashes.items():
            if source_hashes.get(str(name)) != _normalized_sha256(expected):
                raise TruthIsolatedEvaluationError(
                    f"D2 identity source hash mismatch for {name}"
                )

    metrics_payload = _mapping(payload.get("metrics"), "D2 identity metrics")
    if (
        metrics_payload.get("schema_version")
        != D2_SCALABLE_3D_IDENTITY_METRICS_SCHEMA_VERSION
    ):
        raise TruthIsolatedEvaluationError("unsupported D2 identity metrics schema")
    audit = dict(_mapping(payload.get("audit"), "D2 identity audit"))
    identity_commitment = validate_d2_identity_commitment_evaluation(
        payload,
        source_hashes=source_hashes,
    )
    source_verification = str(audit.get("source_verification", "")).strip()
    truth_isolation_verified = (
        audit.get("online_truth_isolation_verified") is True
        and source_verification
        == "raw_source_hashes_and_record_sequences_verified"
        and audit.get("identity_heuristics_used") is False
    )
    truth_available = _required_bool(
        metrics_payload,
        "truth_metrics_available",
        context="D2 identity metrics",
    )
    audit["d6_observation_truth_disposition_acceptance"] = (
        _d2_observation_truth_disposition_acceptance(
            payload=payload,
            audit=audit,
            source_hashes=source_hashes,
            truth_metrics_available=truth_available,
            metrics_payload=metrics_payload,
        )
    )
    evaluated_frame_count = _nonnegative_int(
        metrics_payload.get("evaluated_frame_count"),
        "D2 evaluated_frame_count",
    )
    truth_frame_count = _validated_count_mapping(
        _mapping(
            metrics_payload.get("truth_frame_count", {}),
            "D2 truth_frame_count",
        ),
        "D2 truth_frame_count",
    )
    truth_assigned_frame_count = _validated_count_mapping(
        _mapping(
            metrics_payload.get("truth_assigned_frame_count", {}),
            "D2 truth_assigned_frame_count",
        ),
        "D2 truth_assigned_frame_count",
    )
    truth_identity_stable_frame_count = _validated_count_mapping(
        _mapping(
            metrics_payload.get("truth_identity_stable_frame_count", {}),
            "D2 truth_identity_stable_frame_count",
        ),
        "D2 truth_identity_stable_frame_count",
    )
    confusion_payload = metrics_payload.get("confusion_matrix")
    confusion = (
        None
        if confusion_payload is None
        else _validated_confusion_matrix(
            _mapping(confusion_payload, "D2 confusion_matrix")
        )
    )
    _validate_d2_truth_detail_contract(
        truth_available=truth_available,
        evaluated_frame_count=evaluated_frame_count,
        truth_frame_count=truth_frame_count,
        truth_assigned_frame_count=truth_assigned_frame_count,
        truth_identity_stable_frame_count=(
            truth_identity_stable_frame_count
        ),
        confusion_matrix=confusion,
        audit=audit,
    )
    truth_metric_evidence_reason = _d2_truth_metric_evidence_reason(
        truth_available=truth_available,
        evaluated_frame_count=evaluated_frame_count,
        truth_frame_count=truth_frame_count,
    )
    if not truth_available:
        truth_metric_evidence_reason = str(
            metrics_payload.get("truth_metrics_reason")
            or "d2_truth_metrics_unavailable"
        )
    availability_blocker = (
        "d2_online_truth_isolation_not_verified"
        if not truth_isolation_verified
        else truth_metric_evidence_reason
    )
    metrics = _d2_metric_evidence(
        metrics_payload,
        availability_blocker=availability_blocker,
    )
    retain_truth_details = availability_blocker is None
    try:
        artifact_digest = _canonical_payload_sha256(payload)
    except (TypeError, ValueError):
        artifact_digest = None
    partial_identity_diagnostics = _adapt_d2_partial_identity_diagnostics(
        payload.get("partial_identity_diagnostics"),
        identity_payload=payload,
        identity_source=source,
        identity_evaluation_sha256=external_hash or artifact_digest,
        identity_manifest=identity_manifest,
        expected_identity_manifest_sha256=(
            expected_identity_manifest_sha256
        ),
        source_hashes=source_hashes,
        strict_metrics=metrics,
        strict_truth_metrics_available=truth_available,
        strict_evaluated_frame_count=evaluated_frame_count,
        audit=audit,
        configuration=_mapping(
            payload.get("configuration", {}), "D2 identity configuration"
        ),
    )
    identity_recovery_config_provenance = (
        adapt_d2_identity_recovery_config_provenance(
            producer_evaluation_schema_version=producer_schema_version,
            identity_source=source,
            identity_manifest=identity_manifest,
            expected_identity_manifest_sha256=(
                expected_identity_manifest_sha256
            ),
            d2_online_d2_records=d2_online_d2_records,
            d2_expected_online_d2_records_sha256=(
                d2_expected_online_d2_records_sha256
            ),
            identity_source_hashes=source_hashes,
        )
    )
    return D2IdentityEvaluationRecord(
        episode_id=_identifier(payload.get("episode_id"), "D2 episode_id"),
        producer_schema_version=producer_schema_version,
        producer_policy_version=producer_policy_version,
        metrics=metrics,
        evaluated_frame_count=evaluated_frame_count,
        truth_frame_count=truth_frame_count if retain_truth_details else {},
        truth_assigned_frame_count=(
            truth_assigned_frame_count if retain_truth_details else {}
        ),
        truth_identity_stable_frame_count=(
            truth_identity_stable_frame_count if retain_truth_details else {}
        ),
        confusion_matrix=confusion if retain_truth_details else None,
        source_hashes=source_hashes,
        artifact_digest=artifact_digest,
        external_file_sha256=external_hash,
        truth_isolation_verified=truth_isolation_verified,
        truth_metric_evidence_verified=(
            truth_available and truth_metric_evidence_reason is None
        ),
        truth_metric_evidence_reason=truth_metric_evidence_reason,
        source_verification=source_verification or "unavailable",
        configuration=_mapping(
            payload.get("configuration", {}), "D2 identity configuration"
        ),
        audit=audit,
        identity_commitment=identity_commitment,
        identity_recovery_config_provenance=(
            identity_recovery_config_provenance
        ),
        partial_identity_diagnostics=partial_identity_diagnostics,
        verification_mode=verification_mode,
    )


def validate_d2_identity_commitment_evaluation(
    payload: Mapping[str, Any],
    *,
    source_hashes: Mapping[str, str] | None = None,
) -> D2IdentityCommitmentEvidenceRecord:
    """Independently validate the frozen D2 v1/v2 commitment boundary.

    D6 never derives identity or IDSW here.  For v2 it reconstructs the
    embedded evidence-bundle digest and every commitment audit aggregate.  For
    v1 it emits an explicitly unavailable record even when the producer
    carries legacy compatibility counters.
    """

    schema = str(payload.get("schema_version", ""))
    policy = str(payload.get("policy_version", ""))
    expected_policy = _D2_EVALUATION_POLICY_BY_SCHEMA.get(schema)
    if expected_policy is None:
        raise TruthIsolatedEvaluationError(
            "unsupported D2 identity evaluation schema"
        )
    if policy != expected_policy:
        raise TruthIsolatedEvaluationError(
            "unsupported D2 identity evaluation policy"
        )
    audit = _mapping(payload.get("audit"), "D2 identity audit")
    if schema == D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1:
        return _validate_d2_identity_commitment_v1(
            payload=payload,
            audit=audit,
            policy=policy,
        )
    return _validate_d2_identity_commitment_v2(
        payload=payload,
        audit=audit,
        policy=policy,
        source_hashes=source_hashes,
    )


def _validate_d2_identity_commitment_v1(
    *,
    payload: Mapping[str, Any],
    audit: Mapping[str, Any],
    policy: str,
) -> D2IdentityCommitmentEvidenceRecord:
    if "identity_evidence_records" in payload:
        raise TruthIsolatedEvaluationError(
            "D2 identity evaluation v1 cannot carry v2 evidence records"
        )
    legacy_expected = {
        "identity_commitment_contract_available": False,
        "identity_commitment_schema_version": None,
        "identity_commitment_policy_version": None,
        "identity_commitment_audit_schema_version": None,
        "identity_commitment_denominator_policy": None,
        "identity_commitment_record_count": 0,
        "identity_commitment_state_counts": {},
        "identity_commitment_coverage": None,
        "identity_commitment_all_records": None,
        "identity_commitment_observed_records": None,
        "identity_commitment_reason_counts": None,
        "identity_recovery_blocked_reason_counts": None,
        "identity_recovery_blocker_count_summary": None,
        "identity_recovery_watermark_age_seconds_summary": None,
        "identity_recovery_blocker_overflow_record_count": None,
        "identity_recovery_blocker_overflow_track_count": None,
        "uncommitted_mapping_count": None,
        "uncommitted_candidate_binding_count": None,
        "uncommitted_candidate_binding_violation_count": None,
        "uncommitted_source_binding_violation_count": None,
        "uncommitted_binding_violation_policy": None,
        "identity_switch_anchor_policy": None,
        "committed_anchor_across_uncommitted_gap_policy": None,
    }
    for name, expected in legacy_expected.items():
        if name in audit and not _commitment_audit_value_matches(
            audit[name],
            expected,
        ):
            raise TruthIsolatedEvaluationError(
                f"D2 identity evaluation v1 commitment field must remain "
                f"unavailable: {name}"
            )
    return _unavailable_d2_identity_commitment(
        "identity_commitment_unavailable_for_d2_evaluation_v1",
        producer_evaluation_schema_version=(
            D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1
        ),
        producer_evaluation_policy_version=policy,
    )


def _validate_d2_identity_commitment_v2(
    *,
    payload: Mapping[str, Any],
    audit: Mapping[str, Any],
    policy: str,
    source_hashes: Mapping[str, str] | None,
) -> D2IdentityCommitmentEvidenceRecord:
    episode_id = _identifier(payload.get("episode_id"), "D2 episode_id")
    raw_records = _mapping_sequence(
        payload.get("identity_evidence_records"),
        "D2 identity commitment evidence records",
    )
    configuration = _mapping(
        payload.get("configuration", {}),
        "D2 identity configuration",
    )
    tolerance = _d2_commitment_nonnegative_float(
        configuration.get("timestamp_tolerance_s", 1.0e-9),
        "D2 identity commitment timestamp_tolerance_s",
    )

    commitments: list[Mapping[str, Any]] = []
    observed_commitments: list[Mapping[str, Any]] = []
    blocker_counts: list[int] = []
    watermark_ages: list[float] = []
    overflow_track_ids: set[str] = set()
    source_binding_violations = 0
    for raw_record in raw_records:
        if set(raw_record) != set(_D2_V2_EVIDENCE_RECORD_KEYS):
            missing = sorted(
                set(_D2_V2_EVIDENCE_RECORD_KEYS) - set(raw_record)
            )
            extra = sorted(set(raw_record) - set(_D2_V2_EVIDENCE_RECORD_KEYS))
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity evidence record keys mismatch; "
                f"missing={missing}, extra={extra}"
            )
        if (
            raw_record.get("schema_version")
            != D2_SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2
        ):
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity evidence record schema is unsupported"
            )
        if raw_record.get("episode_id") != episode_id:
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity evidence episode_id mismatch"
            )
        _nonnegative_int(
            raw_record.get("frame_index"),
            "D2 v2 identity evidence frame_index",
        )
        frame_timestamp = _d2_commitment_nonnegative_float(
            raw_record.get("frame_timestamp"),
            "D2 v2 identity evidence frame_timestamp",
        )
        global_track_id = _identifier(
            raw_record.get("global_track_id"),
            "D2 v2 identity evidence global_track_id",
        )
        association_state = _identifier(
            raw_record.get("association_state"),
            "D2 v2 identity evidence association_state",
        ).lower()
        if association_state not in {
            "created",
            "matched",
            "unmatched",
            "lost",
            "dropped",
        }:
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity evidence association_state is unsupported"
            )
        _identifier(
            raw_record.get("lifecycle_state"),
            "D2 v2 identity evidence lifecycle_state",
        )
        source_observations = _mapping_sequence(
            raw_record.get("source_observations"),
            "D2 v2 identity evidence source_observations",
        )
        d1_sequences = raw_record.get("d1_record_sequences")
        if not isinstance(d1_sequences, Sequence) or isinstance(
            d1_sequences,
            (str, bytes),
        ):
            raise TruthIsolatedEvaluationError(
                "D2 v2 d1_record_sequences must be a sequence"
            )
        normalized_d1_sequences = [
            _nonnegative_int(value, "D2 v2 D1 record sequence")
            for value in d1_sequences
        ]
        if len(normalized_d1_sequences) != len(set(normalized_d1_sequences)):
            raise TruthIsolatedEvaluationError(
                "D2 v2 D1 record sequences contain duplicates"
            )
        if raw_record.get("d2_record_sequence") is not None:
            _nonnegative_int(
                raw_record.get("d2_record_sequence"),
                "D2 v2 D2 record sequence",
            )

        commitment = _mapping(
            raw_record.get("identity_commitment"),
            "D2 v2 identity commitment",
        )
        if set(commitment) != set(_D2_V2_COMMITMENT_KEYS):
            missing = sorted(set(_D2_V2_COMMITMENT_KEYS) - set(commitment))
            extra = sorted(set(commitment) - set(_D2_V2_COMMITMENT_KEYS))
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment keys mismatch; "
                f"missing={missing}, extra={extra}"
            )
        if (
            commitment.get("schema_version")
            != D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION_V2
            or commitment.get("policy_version")
            != D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION_V2
        ):
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment schema or policy is unsupported"
            )
        if commitment.get("online_truth_used") is not False:
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment exposed online truth"
            )
        if commitment.get("global_track_id") != global_track_id:
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment global_track_id mismatch"
            )
        if str(commitment.get("association_state", "")).lower() != (
            association_state
        ):
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment association_state mismatch"
            )
        state_timestamp = _d2_commitment_nonnegative_float(
            commitment.get("state_timestamp"),
            "D2 v2 identity commitment state_timestamp",
        )
        if abs(state_timestamp - frame_timestamp) > 1.0e-9:
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment state_timestamp mismatch"
            )
        state = str(commitment.get("identity_commitment_state", ""))
        if state not in _D2_COMMITMENT_STATES:
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment state is unsupported"
            )
        reason = _identifier(
            commitment.get("reason"),
            "D2 v2 identity commitment reason",
        )
        _nonnegative_int(
            commitment.get("commitment_generation"),
            "D2 v2 identity commitment generation",
        )
        _validate_d2_commitment_timestamp_pair(commitment)
        active_lease_count = _nonnegative_int(
            commitment.get("active_lease_count"),
            "D2 v2 identity commitment active_lease_count",
        )
        active_lease_keys = commitment.get("active_lease_keys")
        if not isinstance(active_lease_keys, Sequence) or isinstance(
            active_lease_keys,
            (str, bytes),
        ):
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment active_lease_keys must be a sequence"
            )
        normalized_lease_keys = [
            _identifier(value, "D2 v2 identity commitment active lease key")
            for value in active_lease_keys
        ]
        if (
            len(normalized_lease_keys) != active_lease_count
            or len(normalized_lease_keys) != len(set(normalized_lease_keys))
        ):
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity commitment active lease count is inconsistent"
            )
        blocker_count = _nonnegative_int(
            commitment.get("recovery_blocker_count"),
            "D2 v2 identity commitment recovery_blocker_count",
        )
        overflow = commitment.get("recovery_blocker_overflow")
        if not isinstance(overflow, bool):
            raise TruthIsolatedEvaluationError(
                "D2 v2 recovery_blocker_overflow must be boolean"
            )
        watermark_raw = commitment.get(
            "recovery_not_before_measurement_timestamp"
        )
        watermark = (
            None
            if watermark_raw is None
            else _d2_commitment_nonnegative_float(
                watermark_raw,
                "D2 v2 identity recovery watermark",
            )
        )
        if (blocker_count > 0 or overflow) and watermark is None:
            raise TruthIsolatedEvaluationError(
                "D2 v2 identity recovery blockers require a watermark"
            )
        if state == "committed":
            if (
                blocker_count != 0
                or overflow
                or watermark is not None
                or active_lease_count != 0
            ):
                raise TruthIsolatedEvaluationError(
                    "D2 committed identity retains recovery blockers or leases"
                )
            if (
                association_state in _D2_OBSERVED_ASSOCIATION_STATES
                and not source_observations
            ):
                raise TruthIsolatedEvaluationError(
                    "D2 committed observed identity lacks source observations"
                )
        else:
            if watermark is None:
                raise TruthIsolatedEvaluationError(
                    "D2 uncommitted identity requires a recovery watermark"
                )
            if commitment.get("source_observation_evidence_key") is not None:
                source_binding_violations += 1
            if source_observations:
                source_binding_violations += 1
        if watermark is not None:
            age = frame_timestamp - watermark
            if not math.isfinite(age) or age < -tolerance:
                raise TruthIsolatedEvaluationError(
                    "D2 identity recovery watermark age must be finite and non-negative"
                )
            watermark_ages.append(max(age, 0.0))
        if overflow:
            overflow_track_ids.add(global_track_id)
        commitments.append(commitment)
        blocker_counts.append(blocker_count)
        if association_state in _D2_OBSERVED_ASSOCIATION_STATES:
            observed_commitments.append(commitment)

    normalized_source_hashes = (
        {
            str(name): _normalized_sha256(value)
            for name, value in source_hashes.items()
        }
        if source_hashes is not None
        else {
            str(name): _normalized_sha256(value)
            for name, value in _mapping(
                payload.get("source_hashes"),
                "D2 identity source_hashes",
            ).items()
        }
    )
    for name in _D2_REQUIRED_SOURCE_HASHES:
        if name not in normalized_source_hashes:
            raise TruthIsolatedEvaluationError(
                f"D2 v2 identity source hash is missing: {name}"
            )
    evidence_bundle = {
        "schema_version": D2_SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2,
        "policy_version": D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V2,
        "hash_algorithm": "sha256",
        "episode_id": episode_id,
        "source_hashes": {
            name: normalized_source_hashes[name]
            for name in (
                "online_d1_records",
                "online_d2_records",
                "observation_truth_labels",
            )
        },
        "records": [dict(record) for record in raw_records],
    }
    if (
        _canonical_payload_sha256_with_newline(evidence_bundle)
        != normalized_source_hashes["identity_evidence_bundle"]
    ):
        raise TruthIsolatedEvaluationError(
            "D2 v2 embedded identity evidence bundle SHA-256 mismatch"
        )

    frames = _mapping_sequence(
        payload.get("frames"),
        "D2 identity frames",
    )
    uncommitted_mapping_count = 0
    candidate_binding_violations = 0
    legacy_combined_binding_count = 0
    for raw_frame in frames:
        _nonnegative_int(
            raw_frame.get("frame_index"),
            "D2 identity frame_index",
        )
        _d2_commitment_nonnegative_float(
            raw_frame.get("frame_timestamp"),
            "D2 identity frame_timestamp",
        )
        for raw_mapping in _mapping_sequence(
            raw_frame.get("mappings"),
            "D2 identity frame mappings",
        ):
            if raw_mapping.get("status") != "uncommitted":
                continue
            uncommitted_mapping_count += 1
            required_mapping_fields = {
                "global_track_id",
                "truth_target_id",
                "reason",
                "candidate_truth_target_ids",
                "source_observation_ids",
                "source_lineage_hashes",
                "evidence_count",
                "unique_lineage_count",
                "labeled_evidence_count",
            }
            missing = required_mapping_fields - set(raw_mapping)
            if missing:
                raise TruthIsolatedEvaluationError(
                    "D2 uncommitted mapping is missing binding audit fields: "
                    + ",".join(sorted(missing))
                )
            _identifier(
                raw_mapping.get("global_track_id"),
                "D2 uncommitted mapping global_track_id",
            )
            _identifier(
                raw_mapping.get("reason"),
                "D2 uncommitted mapping reason",
            )
            candidates = _commitment_sequence(
                raw_mapping.get("candidate_truth_target_ids"),
                "D2 uncommitted candidate_truth_target_ids",
            )
            source_observations = _commitment_sequence(
                raw_mapping.get("source_observation_ids"),
                "D2 uncommitted source_observation_ids",
            )
            source_hash_values = _commitment_sequence(
                raw_mapping.get("source_lineage_hashes"),
                "D2 uncommitted source_lineage_hashes",
            )
            evidence_count = _nonnegative_int(
                raw_mapping.get("evidence_count"),
                "D2 uncommitted evidence_count",
            )
            unique_lineage_count = _nonnegative_int(
                raw_mapping.get("unique_lineage_count"),
                "D2 uncommitted unique_lineage_count",
            )
            labeled_evidence_count = _nonnegative_int(
                raw_mapping.get("labeled_evidence_count"),
                "D2 uncommitted labeled_evidence_count",
            )
            candidate_violation = bool(
                raw_mapping.get("truth_target_id") or candidates
            )
            source_violation = bool(
                source_observations
                or source_hash_values
                or evidence_count
                or unique_lineage_count
                or labeled_evidence_count
            )
            candidate_binding_violations += int(candidate_violation)
            source_binding_violations += int(source_violation)
            legacy_combined_binding_count += int(
                candidate_violation or source_violation
            )

    all_summary = _d2_commitment_denominator_summary(commitments)
    observed_summary = _d2_commitment_denominator_summary(
        observed_commitments
    )
    state_counts = dict(
        sorted(
            Counter(
                str(item["identity_commitment_state"])
                for item in commitments
            ).items()
        )
    )
    reason_counts = dict(
        sorted(Counter(str(item["reason"]) for item in commitments).items())
    )
    blocked_reason_counts = {
        reason: count
        for reason, count in reason_counts.items()
        if reason.startswith("identity_recovery_blocked_")
    }
    blocker_summary = _d2_commitment_numeric_summary(
        blocker_counts,
        count_key="record_count",
        include_positive_count=True,
    )
    watermark_summary = _d2_commitment_numeric_summary(
        watermark_ages,
        count_key="count",
        include_positive_count=False,
    )
    overflow_record_count = sum(
        item.get("recovery_blocker_overflow") is True
        for item in commitments
    )
    expected_audit = {
        "identity_commitment_contract_available": True,
        "identity_commitment_schema_version": (
            D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION_V2
        ),
        "identity_commitment_policy_version": (
            D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION_V2
        ),
        "identity_commitment_audit_schema_version": (
            D2_SCALABLE_3D_IDENTITY_COMMITMENT_AUDIT_SCHEMA_VERSION_V2
        ),
        "identity_commitment_denominator_policy": (
            D2_IDENTITY_COMMITMENT_DENOMINATOR_POLICY
        ),
        "identity_commitment_record_count": len(commitments),
        "identity_commitment_state_counts": state_counts,
        "identity_commitment_coverage": all_summary["coverage"],
        "identity_commitment_all_records": all_summary,
        "identity_commitment_observed_records": observed_summary,
        "identity_commitment_reason_counts": reason_counts,
        "identity_recovery_blocked_reason_counts": blocked_reason_counts,
        "identity_recovery_blocker_count_summary": blocker_summary,
        "identity_recovery_watermark_age_seconds_summary": watermark_summary,
        "identity_recovery_blocker_overflow_record_count": (
            overflow_record_count
        ),
        "identity_recovery_blocker_overflow_track_count": len(
            overflow_track_ids
        ),
        "uncommitted_mapping_count": uncommitted_mapping_count,
        "uncommitted_candidate_binding_count": (
            legacy_combined_binding_count
        ),
        "uncommitted_candidate_binding_violation_count": (
            candidate_binding_violations
        ),
        "uncommitted_source_binding_violation_count": (
            source_binding_violations
        ),
        "uncommitted_binding_violation_policy": (
            D2_UNCOMMITTED_BINDING_VIOLATION_POLICY
        ),
        "identity_switch_anchor_policy": (
            D2_COMMITTED_ANCHOR_ACROSS_UNCOMMITTED_GAP_POLICY
        ),
        "committed_anchor_across_uncommitted_gap_policy": (
            D2_COMMITTED_ANCHOR_ACROSS_UNCOMMITTED_GAP_POLICY
        ),
    }
    for name, expected in expected_audit.items():
        if name not in audit:
            raise TruthIsolatedEvaluationError(
                f"D2 identity commitment audit is missing required field: {name}"
            )
        if not _commitment_audit_value_matches(audit[name], expected):
            raise TruthIsolatedEvaluationError(
                "D2 identity commitment audit contradicts embedded v2 "
                f"evidence: {name}"
            )
    if not (
        0
        <= overflow_record_count
        <= len(commitments)
        and 0
        <= len(overflow_track_ids)
        <= overflow_record_count
    ):
        raise TruthIsolatedEvaluationError(
            "D2 identity commitment overflow counts exceed their bounds"
        )
    if candidate_binding_violations or source_binding_violations:
        raise TruthIsolatedEvaluationError(
            "D2 uncommitted identity binding violation count must be zero"
        )

    metrics = _d2_identity_commitment_metrics(
        all_summary=all_summary,
        observed_summary=observed_summary,
        uncommitted_mapping_count=uncommitted_mapping_count,
        blocker_summary=blocker_summary,
        watermark_summary=watermark_summary,
        overflow_record_count=overflow_record_count,
        overflow_track_count=len(overflow_track_ids),
        uncommitted_candidate_binding_count=legacy_combined_binding_count,
        candidate_binding_violations=candidate_binding_violations,
        source_binding_violations=source_binding_violations,
    )
    return D2IdentityCommitmentEvidenceRecord(
        available=True,
        unavailable_reason=None,
        metrics=metrics,
        state_counts=state_counts,
        reason_counts=reason_counts,
        recovery_blocked_reason_counts=blocked_reason_counts,
        denominator_policy=D2_IDENTITY_COMMITMENT_DENOMINATOR_POLICY,
        uncommitted_binding_violation_policy=(
            D2_UNCOMMITTED_BINDING_VIOLATION_POLICY
        ),
        committed_anchor_across_uncommitted_gap_policy=(
            D2_COMMITTED_ANCHOR_ACROSS_UNCOMMITTED_GAP_POLICY
        ),
        producer_evaluation_schema_version=(
            D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V2
        ),
        producer_evaluation_policy_version=policy,
        producer_evidence_schema_version=(
            D2_SCALABLE_3D_IDENTITY_EVIDENCE_SCHEMA_VERSION_V2
        ),
        producer_commitment_schema_version=(
            D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION_V2
        ),
        producer_commitment_policy_version=(
            D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION_V2
        ),
        producer_audit_schema_version=(
            D2_SCALABLE_3D_IDENTITY_COMMITMENT_AUDIT_SCHEMA_VERSION_V2
        ),
        evidence_bundle_sha256_verified=True,
    )


def _validate_d2_commitment_timestamp_pair(
    commitment: Mapping[str, Any],
) -> None:
    measurement_raw = commitment.get("measurement_timestamp")
    arrival_raw = commitment.get("arrival_timestamp")
    if (measurement_raw is None) != (arrival_raw is None):
        raise TruthIsolatedEvaluationError(
            "D2 commitment measurement and arrival timestamps must be paired"
        )
    if measurement_raw is None:
        return
    measurement = _d2_commitment_nonnegative_float(
        measurement_raw,
        "D2 commitment measurement_timestamp",
    )
    arrival = _d2_commitment_nonnegative_float(
        arrival_raw,
        "D2 commitment arrival_timestamp",
    )
    if arrival + 1.0e-12 < measurement:
        raise TruthIsolatedEvaluationError(
            "D2 commitment arrival_timestamp precedes measurement_timestamp"
        )


def _d2_commitment_denominator_summary(
    commitments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    denominator = len(commitments)
    committed_count = sum(
        item.get("identity_commitment_state") == "committed"
        for item in commitments
    )
    return {
        "denominator": denominator,
        "committed_count": committed_count,
        "uncommitted_count": denominator - committed_count,
        "coverage": (
            committed_count / denominator if denominator else None
        ),
        "coverage_available": bool(denominator),
        "coverage_reason": (
            None if denominator else "no_v2_identity_evidence_records"
        ),
    }


def _d2_commitment_numeric_summary(
    values: Sequence[int | float],
    *,
    count_key: str,
    include_positive_count: bool,
) -> dict[str, Any]:
    output: dict[str, Any] = {count_key: len(values)}
    if include_positive_count:
        output["positive_record_count"] = sum(float(value) > 0 for value in values)
        output["sum"] = sum(values)
    output.update(
        {
            "min": min(values) if values else None,
            "mean": sum(values) / len(values) if values else None,
            "max": max(values) if values else None,
        }
    )
    return output


def _d2_identity_commitment_metrics(
    *,
    all_summary: Mapping[str, Any],
    observed_summary: Mapping[str, Any],
    uncommitted_mapping_count: int,
    blocker_summary: Mapping[str, Any],
    watermark_summary: Mapping[str, Any],
    overflow_record_count: int,
    overflow_track_count: int,
    uncommitted_candidate_binding_count: int,
    candidate_binding_violations: int,
    source_binding_violations: int,
) -> dict[str, PublicMetricEvidence]:
    all_denominator = int(all_summary["denominator"])
    observed_denominator = int(observed_summary["denominator"])
    blocker_record_count = int(blocker_summary["record_count"])
    watermark_count = int(watermark_summary["count"])
    metrics = {
        "all_commitment_coverage": _commitment_optional_metric(
            all_summary["coverage"],
            sample_count=all_denominator,
            unavailable_reason=str(
                all_summary["coverage_reason"]
                or "no_v2_identity_evidence_records"
            ),
        ),
        "observed_commitment_coverage": _commitment_optional_metric(
            observed_summary["coverage"],
            sample_count=observed_denominator,
            unavailable_reason=str(
                observed_summary["coverage_reason"]
                or "no_v2_observed_identity_evidence_records"
            ),
        ),
        "all_record_count": _commitment_count_metric(all_denominator),
        "all_committed_count": _commitment_count_metric(
            int(all_summary["committed_count"])
        ),
        "all_uncommitted_count": _commitment_count_metric(
            int(all_summary["uncommitted_count"])
        ),
        "observed_record_count": _commitment_count_metric(
            observed_denominator
        ),
        "observed_committed_count": _commitment_count_metric(
            int(observed_summary["committed_count"])
        ),
        "observed_uncommitted_count": _commitment_count_metric(
            int(observed_summary["uncommitted_count"])
        ),
        "uncommitted_mapping_count": _commitment_count_metric(
            uncommitted_mapping_count
        ),
        "recovery_blocker_record_count": _commitment_count_metric(
            blocker_record_count
        ),
        "recovery_blocker_positive_record_count": _commitment_count_metric(
            int(blocker_summary["positive_record_count"])
        ),
        "recovery_blocker_count_sum": _commitment_count_metric(
            int(blocker_summary["sum"])
        ),
        "recovery_blocker_count_min": _commitment_optional_metric(
            blocker_summary["min"],
            sample_count=blocker_record_count,
            unavailable_reason="no_v2_identity_evidence_records",
        ),
        "recovery_blocker_count_mean": _commitment_optional_metric(
            blocker_summary["mean"],
            sample_count=blocker_record_count,
            unavailable_reason="no_v2_identity_evidence_records",
        ),
        "recovery_blocker_count_max": _commitment_optional_metric(
            blocker_summary["max"],
            sample_count=blocker_record_count,
            unavailable_reason="no_v2_identity_evidence_records",
        ),
        "recovery_watermark_age_record_count": _commitment_count_metric(
            watermark_count
        ),
        "recovery_watermark_age_seconds_min": _commitment_optional_metric(
            watermark_summary["min"],
            sample_count=watermark_count,
            unavailable_reason="no_identity_recovery_watermark_records",
        ),
        "recovery_watermark_age_seconds_mean": _commitment_optional_metric(
            watermark_summary["mean"],
            sample_count=watermark_count,
            unavailable_reason="no_identity_recovery_watermark_records",
        ),
        "recovery_watermark_age_seconds_max": _commitment_optional_metric(
            watermark_summary["max"],
            sample_count=watermark_count,
            unavailable_reason="no_identity_recovery_watermark_records",
        ),
        "recovery_blocker_overflow_record_count": _commitment_count_metric(
            overflow_record_count
        ),
        "recovery_blocker_overflow_track_count": _commitment_count_metric(
            overflow_track_count
        ),
        "uncommitted_candidate_binding_count": _commitment_count_metric(
            uncommitted_candidate_binding_count
        ),
        "uncommitted_candidate_binding_violation_count": (
            _commitment_count_metric(candidate_binding_violations)
        ),
        "uncommitted_source_binding_violation_count": (
            _commitment_count_metric(source_binding_violations)
        ),
    }
    if set(metrics) != set(_D2_COMMITMENT_METRIC_NAMES):
        raise AssertionError("D2 commitment metric construction is incomplete")
    return metrics


def _commitment_count_metric(value: int) -> PublicMetricEvidence:
    return PublicMetricEvidence(
        value=value,
        available=True,
        sample_count=1,
    )


def _commitment_optional_metric(
    value: int | float | None,
    *,
    sample_count: int,
    unavailable_reason: str,
) -> PublicMetricEvidence:
    if value is None:
        return PublicMetricEvidence(
            value=None,
            available=False,
            sample_count=0,
            unavailable_reason=unavailable_reason,
        )
    return PublicMetricEvidence(
        value=value,
        available=True,
        sample_count=sample_count,
    )


def _commitment_audit_value_matches(actual: Any, expected: Any) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if isinstance(expected, int):
        return (
            isinstance(actual, int)
            and not isinstance(actual, bool)
            and actual == expected
        )
    if isinstance(expected, float):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isfinite(float(actual))
            and abs(float(actual) - expected) <= 1.0e-12
        )
    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(
                _commitment_audit_value_matches(actual[name], value)
                for name, value in expected.items()
            )
        )
    return actual == expected


def _d2_commitment_nonnegative_float(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise TruthIsolatedEvaluationError(
            f"{name} must be finite and non-negative"
        )
    return float(value)


def _commitment_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TruthIsolatedEvaluationError(f"{name} must be a sequence")
    return value


def _canonical_payload_sha256_with_newline(value: Any) -> str:
    try:
        encoded = (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise TruthIsolatedEvaluationError(
            "D2 v2 identity evidence bundle is not canonically hashable"
        ) from exc
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def build_truth_isolated_episode_record(
    context: TruthIsolatedEpisodeContext,
    *,
    d1_result: object | Mapping[str, Any] | str | Path | None,
    d2_evaluation: object | Mapping[str, Any] | str | Path | None,
    d1_expected_sha256: str | None = None,
    d2_expected_sha256: str | None = None,
    d2_expected_source_hashes: Mapping[str, str] | None = None,
    d2_identity_manifest: (
        object | Mapping[str, Any] | str | Path | None
    ) = None,
    d2_expected_identity_manifest_sha256: str | None = None,
    d2_online_d2_records: str | Path | None = None,
    d2_expected_online_d2_records_sha256: str | None = None,
) -> TruthIsolatedEpisodeEvaluationRecord:
    """Build one episode record from public DTOs or verified artifacts."""

    d1 = (
        _missing_d1_record(context)
        if d1_result is None
        else adapt_d1_offline_consistency(
            d1_result,
            expected_sha256=d1_expected_sha256,
        )
    )
    d2 = (
        _missing_d2_record(context)
        if d2_evaluation is None
        else adapt_d2_scalable_3d_identity(
            d2_evaluation,
            expected_sha256=d2_expected_sha256,
            expected_source_hashes=d2_expected_source_hashes,
            identity_manifest=d2_identity_manifest,
            expected_identity_manifest_sha256=(
                d2_expected_identity_manifest_sha256
            ),
            d2_online_d2_records=d2_online_d2_records,
            d2_expected_online_d2_records_sha256=(
                d2_expected_online_d2_records_sha256
            ),
        )
    )
    return TruthIsolatedEpisodeEvaluationRecord(context=context, d1=d1, d2=d2)


def aggregate_truth_isolated_episode_records(
    records: Sequence[TruthIsolatedEpisodeEvaluationRecord],
    *,
    bootstrap_resamples: int = DEFAULT_TRUTH_ISOLATED_BOOTSTRAP_RESAMPLES,
    bootstrap_rng_seed: int = DEFAULT_TRUTH_ISOLATED_BOOTSTRAP_RNG_SEED,
) -> TruthIsolatedBatchSummary:
    """Aggregate distinct-seed evidence by scenario and actual scale."""

    normalized = tuple(records)
    if not normalized:
        raise ValueError("at least one truth-isolated episode record is required")
    if int(bootstrap_resamples) <= 0:
        raise ValueError("bootstrap_resamples must be positive")
    episode_ids = [record.context.episode_id for record in normalized]
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("truth-isolated episode_id values must be unique")

    grouped: dict[tuple[Any, ...], list[TruthIsolatedEpisodeEvaluationRecord]] = (
        defaultdict(list)
    )
    for record in normalized:
        context = record.context
        key = (
            context.scenario_id,
            context.scenario_version,
            context.target_count,
            context.resource_count,
            context.recon_count,
            context.camera_count,
        )
        grouped[key].append(record)

    groups: list[dict[str, Any]] = []
    for key in sorted(grouped, key=_sortable_key):
        group_records = grouped[key]
        identity = {
            name: value
            for name, value in zip(
                (
                    "scenario_id",
                    "scenario_version",
                    "target_count",
                    "resource_count",
                    "recon_count",
                    "camera_count",
                ),
                key,
            )
        }
        metrics: dict[str, Any] = {}
        for name in _D1_METRIC_NAMES:
            metrics[f"d1.{name}"] = _aggregate_metric(
                [
                    (record.context.seed, record.d1.metrics[name])
                    for record in group_records
                ],
                metric_name=f"d1.{name}",
                group_identity=identity,
                bootstrap_resamples=int(bootstrap_resamples),
                bootstrap_rng_seed=int(bootstrap_rng_seed),
            )
        for name in _D2_METRIC_NAMES:
            metrics[f"d2.{name}"] = _aggregate_metric(
                [
                    (record.context.seed, record.d2.metrics[name])
                    for record in group_records
                ],
                metric_name=f"d2.{name}",
                group_identity=identity,
                bootstrap_resamples=int(bootstrap_resamples),
                bootstrap_rng_seed=int(bootstrap_rng_seed),
            )
        for name in _D2_PARTIAL_METRIC_NAMES:
            metrics[f"d2.partial_identity.{name}"] = _aggregate_metric(
                [
                    (
                        record.context.seed,
                        record.d2.partial_identity_diagnostics.metrics[name],
                    )
                    for record in group_records
                ],
                metric_name=f"d2.partial_identity.{name}",
                group_identity=identity,
                bootstrap_resamples=int(bootstrap_resamples),
                bootstrap_rng_seed=int(bootstrap_rng_seed),
            )
        for name in _D2_COMMITMENT_METRIC_NAMES:
            metrics[f"d2.identity_commitment.{name}"] = _aggregate_metric(
                [
                    (
                        record.context.seed,
                        record.d2.identity_commitment.metrics[name],
                    )
                    for record in group_records
                ],
                metric_name=f"d2.identity_commitment.{name}",
                group_identity=identity,
                bootstrap_resamples=int(bootstrap_resamples),
                bootstrap_rng_seed=int(bootstrap_rng_seed),
            )
        groups.append(
            {
                **identity,
                "episode_count": len(group_records),
                "seed_count": len({record.context.seed for record in group_records}),
                "seeds": sorted({record.context.seed for record in group_records}),
                "d1_status_distribution": dict(
                    sorted(Counter(record.d1.status for record in group_records).items())
                ),
                "d2_truth_isolation_verified_count": sum(
                    record.d2.truth_isolation_verified for record in group_records
                ),
                "d2_truth_metric_evidence_verified_count": sum(
                    record.d2.truth_metric_evidence_verified
                    for record in group_records
                ),
                "source_provenance_by_episode": [
                    _episode_source_provenance(record)
                    for record in sorted(
                        group_records,
                        key=lambda item: item.context.episode_id,
                    )
                ],
                "metrics": metrics,
                "d2_confusion_matrices_by_episode": [
                    {
                        "episode_id": record.context.episode_id,
                        "confusion_matrix": record.d2.confusion_matrix,
                    }
                    for record in group_records
                    if record.d2.confusion_matrix is not None
                ],
                "d2_coverage_counts_by_episode": [
                    {
                        "episode_id": record.context.episode_id,
                        "truth_frame_count": dict(record.d2.truth_frame_count),
                        "truth_assigned_frame_count": dict(
                            record.d2.truth_assigned_frame_count
                        ),
                        "truth_identity_stable_frame_count": dict(
                            record.d2.truth_identity_stable_frame_count
                        ),
                    }
                    for record in group_records
                ],
                "d2_coverage_count_totals": {
                    "truth_frame_count": sum(
                        sum(record.d2.truth_frame_count.values())
                        for record in group_records
                    ),
                    "truth_assigned_frame_count": sum(
                        sum(record.d2.truth_assigned_frame_count.values())
                        for record in group_records
                    ),
                    "truth_identity_stable_frame_count": sum(
                        sum(record.d2.truth_identity_stable_frame_count.values())
                        for record in group_records
                    ),
                },
                "d2_partial_identity_diagnostics": (
                    _aggregate_d2_partial_identity(group_records)
                ),
                "d2_identity_commitment": (
                    _aggregate_d2_identity_commitment(group_records)
                ),
                "d2_identity_recovery_config_provenance": (
                    _aggregate_d2_identity_recovery_config_provenance(
                        group_records
                    )
                ),
            }
        )

    d1_grouped: dict[tuple[Any, ...], list[tuple[int, D1SensorRangeConsistencyRecord]]] = (
        defaultdict(list)
    )
    for episode in normalized:
        for record in episode.d1.sensor_range_records:
            key = (
                episode.context.scenario_id,
                episode.context.scenario_version,
                episode.context.target_count,
                episode.context.resource_count,
                episode.context.recon_count,
                episode.context.camera_count,
                record.sensor_id,
                record.sensor_type,
                record.source_sensor_type,
                record.range_bin,
            )
            d1_grouped[key].append((episode.context.seed, record))
    d1_sensor_groups: list[dict[str, Any]] = []
    group_names = (
        "scenario_id",
        "scenario_version",
        "target_count",
        "resource_count",
        "recon_count",
        "camera_count",
        "sensor_id",
        "sensor_type",
        "source_sensor_type",
        "range_bin",
    )
    for key in sorted(d1_grouped, key=_sortable_key):
        identity = dict(zip(group_names, key))
        items = d1_grouped[key]
        d1_sensor_groups.append(
            {
                **identity,
                "episode_count": len(items),
                "seed_count": len({seed for seed, _ in items}),
                "metrics": {
                    name: _aggregate_metric(
                        [(seed, record.metrics[name]) for seed, record in items],
                        metric_name=f"d1.sensor_range.{name}",
                        group_identity=identity,
                        bootstrap_resamples=int(bootstrap_resamples),
                        bootstrap_rng_seed=int(bootstrap_rng_seed),
                    )
                    for name in _D1_METRIC_NAMES
                },
            }
        )

    scale_values = tuple(sorted({record.context.target_count for record in normalized}))
    return TruthIsolatedBatchSummary(
        episode_count=len(normalized),
        scale_values=scale_values,
        groups=tuple(groups),
        d1_sensor_range_groups=tuple(d1_sensor_groups),
        reference_scale_coverage={
            str(scale): scale in scale_values for scale in REFERENCE_SCALABLE_3D_SCALES
        },
    )


def _aggregate_d2_partial_identity(
    records: Sequence[TruthIsolatedEpisodeEvaluationRecord],
) -> dict[str, Any]:
    diagnostics = [
        record.d2.partial_identity_diagnostics for record in records
    ]
    available = [item for item in diagnostics if item.available]
    unavailable_reasons = Counter(
        item.unavailable_reason or "reason_unavailable"
        for item in diagnostics
        if not item.available
    )
    count_totals = (
        {
            name: sum(item.counts[name] for item in available)
            for name in _D2_PARTIAL_COUNT_NAMES
        }
        if available
        else {}
    )
    anchor_exclusion_reasons: Counter[str] = Counter()
    excluded_mapping_reasons: Counter[str] = Counter()
    for item in available:
        anchor_exclusion_reasons.update(
            item.lower_bound_anchor_exclusion_reason_counts
        )
        excluded_mapping_reasons.update(
            item.excluded_scored_mapping_reason_counts
        )

    coverage_specs = {
        "mapping": ("evaluable_mapping_count", "scored_mapping_count"),
        "frame": ("evaluable_frame_count", "evaluated_frame_count"),
        "adjacent_transition": (
            "evaluable_transition_count",
            "transition_opportunity_count",
        ),
    }
    coverage_totals = {
        name: _aggregate_partial_coverage_counts(
            numerator=sum(item.counts[numerator_name] for item in available),
            denominator=sum(
                item.counts[denominator_name] for item in available
            ),
            unavailable_reason=(
                "no_provenance_verified_partial_identity_episodes"
                if not available
                else f"no_{name}_coverage_denominator"
            ),
        )
        for name, (numerator_name, denominator_name) in coverage_specs.items()
    }
    lower_bounds = [
        item.metrics["id_switch_lower_bound"]
        for item in diagnostics
    ]
    lower_values = [
        int(metric.value)
        for metric in lower_bounds
        if metric.available and metric.value is not None
    ]
    lower_reasons = Counter(
        metric.unavailable_reason or "reason_unavailable"
        for metric in lower_bounds
        if not metric.available
    )
    return {
        "schema_version": D6_D2_PARTIAL_IDENTITY_ADAPTER_SCHEMA_VERSION,
        "availability": "available" if available else "unavailable",
        "available_episode_count": len(available),
        "unavailable_episode_count": len(diagnostics) - len(available),
        "unavailability_reason_distribution": dict(
            sorted(unavailable_reasons.items())
        ),
        "count_totals": count_totals,
        "coverage_totals": coverage_totals,
        "anchor_interval_count": count_totals.get(
            "lower_bound_anchor_transition_count",
            None,
        ),
        "id_switch_lower_bound": {
            "availability": (
                "available" if lower_values else "unavailable"
            ),
            "value": sum(lower_values) if lower_values else None,
            "available_episode_count": len(lower_values),
            "unavailability_reason_distribution": dict(
                sorted(lower_reasons.items())
            ),
        },
        "lower_bound_anchor_exclusion_reason_counts": dict(
            sorted(anchor_exclusion_reasons.items())
        ),
        "excluded_scored_mapping_reason_counts": dict(
            sorted(excluded_mapping_reasons.items())
        ),
        "strict_id_switch_count_backfilled": False,
        "id_switch_upper_bound_reported": False,
        "control_consumed": False,
    }


def _aggregate_d2_identity_commitment(
    records: Sequence[TruthIsolatedEpisodeEvaluationRecord],
) -> dict[str, Any]:
    evidence = [record.d2.identity_commitment for record in records]
    available = [item for item in evidence if item.available]
    unavailable_reasons = Counter(
        item.unavailable_reason or "reason_unavailable"
        for item in evidence
        if not item.available
    )
    reason_counts: Counter[str] = Counter()
    blocked_reason_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    for item in available:
        reason_counts.update(item.reason_counts)
        blocked_reason_counts.update(item.recovery_blocked_reason_counts)
        state_counts.update(item.state_counts)

    def total(name: str) -> int:
        return sum(
            int(item.metrics[name].value)
            for item in available
            if item.metrics[name].available
            and item.metrics[name].value is not None
        )

    all_denominator = total("all_record_count")
    all_committed = total("all_committed_count")
    all_uncommitted = total("all_uncommitted_count")
    observed_denominator = total("observed_record_count")
    observed_committed = total("observed_committed_count")
    observed_uncommitted = total("observed_uncommitted_count")
    blocker_record_count = total("recovery_blocker_record_count")
    blocker_sum = total("recovery_blocker_count_sum")
    watermark_count = total("recovery_watermark_age_record_count")
    watermark_weighted_sum = sum(
        float(item.metrics["recovery_watermark_age_seconds_mean"].value)
        * int(item.metrics["recovery_watermark_age_record_count"].value)
        for item in available
        if item.metrics["recovery_watermark_age_seconds_mean"].available
        and item.metrics["recovery_watermark_age_seconds_mean"].value
        is not None
        and item.metrics["recovery_watermark_age_record_count"].value
        is not None
    )
    blocker_min_values = [
        float(item.metrics["recovery_blocker_count_min"].value)
        for item in available
        if item.metrics["recovery_blocker_count_min"].available
        and item.metrics["recovery_blocker_count_min"].value is not None
    ]
    blocker_max_values = [
        float(item.metrics["recovery_blocker_count_max"].value)
        for item in available
        if item.metrics["recovery_blocker_count_max"].available
        and item.metrics["recovery_blocker_count_max"].value is not None
    ]
    watermark_min_values = [
        float(item.metrics["recovery_watermark_age_seconds_min"].value)
        for item in available
        if item.metrics["recovery_watermark_age_seconds_min"].available
        and item.metrics["recovery_watermark_age_seconds_min"].value
        is not None
    ]
    watermark_max_values = [
        float(item.metrics["recovery_watermark_age_seconds_max"].value)
        for item in available
        if item.metrics["recovery_watermark_age_seconds_max"].available
        and item.metrics["recovery_watermark_age_seconds_max"].value
        is not None
    ]
    return {
        "schema_version": D6_D2_IDENTITY_COMMITMENT_ADAPTER_SCHEMA_VERSION,
        "availability": "available" if available else "unavailable",
        "available_episode_count": len(available),
        "unavailable_episode_count": len(evidence) - len(available),
        "unavailability_reason_distribution": dict(
            sorted(unavailable_reasons.items())
        ),
        "all_records": {
            "denominator": all_denominator if available else None,
            "committed_count": all_committed if available else None,
            "uncommitted_count": all_uncommitted if available else None,
            "coverage": (
                all_committed / all_denominator
                if all_denominator > 0
                else None
            ),
            "availability": (
                "available" if all_denominator > 0 else "unavailable"
            ),
            "unavailable_reason": (
                None
                if all_denominator > 0
                else "no_v2_identity_evidence_records"
            ),
        },
        "observed_records": {
            "denominator": observed_denominator if available else None,
            "committed_count": observed_committed if available else None,
            "uncommitted_count": observed_uncommitted if available else None,
            "coverage": (
                observed_committed / observed_denominator
                if observed_denominator > 0
                else None
            ),
            "availability": (
                "available" if observed_denominator > 0 else "unavailable"
            ),
            "unavailable_reason": (
                None
                if observed_denominator > 0
                else "no_v2_observed_identity_evidence_records"
            ),
        },
        "uncommitted_mapping_count": (
            total("uncommitted_mapping_count") if available else None
        ),
        "state_counts": dict(sorted(state_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "recovery_blocked_reason_counts": dict(
            sorted(blocked_reason_counts.items())
        ),
        "recovery_blocker_count_summary": {
            "record_count": blocker_record_count if available else None,
            "positive_record_count": (
                total("recovery_blocker_positive_record_count")
                if available
                else None
            ),
            "sum": blocker_sum if available else None,
            "min": min(blocker_min_values) if blocker_min_values else None,
            "mean": (
                blocker_sum / blocker_record_count
                if blocker_record_count > 0
                else None
            ),
            "max": max(blocker_max_values) if blocker_max_values else None,
        },
        "recovery_watermark_age_seconds_summary": {
            "count": watermark_count if available else None,
            "min": (
                min(watermark_min_values) if watermark_min_values else None
            ),
            "mean": (
                watermark_weighted_sum / watermark_count
                if watermark_count > 0
                else None
            ),
            "max": (
                max(watermark_max_values) if watermark_max_values else None
            ),
        },
        "recovery_blocker_overflow_record_count": (
            total("recovery_blocker_overflow_record_count")
            if available
            else None
        ),
        "recovery_blocker_overflow_track_count": (
            total("recovery_blocker_overflow_track_count")
            if available
            else None
        ),
        "uncommitted_candidate_binding_count": (
            total("uncommitted_candidate_binding_count")
            if available
            else None
        ),
        "uncommitted_candidate_binding_violation_count": (
            total("uncommitted_candidate_binding_violation_count")
            if available
            else None
        ),
        "uncommitted_source_binding_violation_count": (
            total("uncommitted_source_binding_violation_count")
            if available
            else None
        ),
        "evidence_bundle_sha256_verified_episode_count": sum(
            item.evidence_bundle_sha256_verified for item in available
        ),
        "strict_id_switch_count_backfilled": False,
        "uncommitted_gap_treated_as_zero_id_switch": False,
        "control_consumed": False,
    }


def _aggregate_d2_identity_recovery_config_provenance(
    records: Sequence[TruthIsolatedEpisodeEvaluationRecord],
) -> dict[str, Any]:
    evidence = [
        record.d2.identity_recovery_config_provenance for record in records
    ]
    available = [item for item in evidence if item.available]
    unavailable_reasons = Counter(
        item.unavailable_reason or "reason_unavailable"
        for item in evidence
        if not item.available
    )
    config_sha_counts = Counter(
        str(item.config_sha256) for item in available
    )
    manifest_schema_counts = Counter(
        str(item.identity_manifest_schema_version) for item in evidence
    )
    manifest_sha_counts = Counter(
        str(item.identity_manifest_sha256)
        for item in evidence
        if item.identity_manifest_sha256 is not None
    )
    online_sha_counts = Counter(
        str(item.online_d2_records_sha256)
        for item in available
        if item.online_d2_records_sha256 is not None
    )
    config_snapshots_by_sha256 = {
        str(item.config_sha256): dict(item.config_snapshot or {})
        for item in available
    }
    return {
        "schema_version": (
            D6_D2_IDENTITY_RECOVERY_CONFIG_PROVENANCE_SCHEMA_VERSION
        ),
        "availability": "available" if available else "unavailable",
        "available_episode_count": len(available),
        "unavailable_episode_count": len(evidence) - len(available),
        "all_episode_provenance_verified": (
            bool(evidence) and len(available) == len(evidence)
        ),
        "unavailability_reason_distribution": dict(
            sorted(unavailable_reasons.items())
        ),
        "config_sha256_distribution": dict(sorted(config_sha_counts.items())),
        "config_snapshots_by_sha256": dict(
            sorted(config_snapshots_by_sha256.items())
        ),
        "identity_manifest_schema_distribution": dict(
            sorted(manifest_schema_counts.items())
        ),
        "identity_manifest_sha256_distribution": dict(
            sorted(manifest_sha_counts.items())
        ),
        "online_d2_records_sha256_distribution": dict(
            sorted(online_sha_counts.items())
        ),
        "record_count_total": sum(
            int(item.config_record_count or 0) for item in available
        ),
        "strict_id_switch_count_backfilled": False,
        "control_consumed": False,
    }


def _aggregate_partial_coverage_counts(
    *,
    numerator: int,
    denominator: int,
    unavailable_reason: str,
) -> dict[str, Any]:
    return {
        "availability": "available" if denominator > 0 else "unavailable",
        "value": (
            float(numerator / denominator) if denominator > 0 else None
        ),
        "numerator": numerator,
        "denominator": denominator,
        "unavailable_reason": None if denominator > 0 else unavailable_reason,
    }


def render_truth_isolated_markdown(
    records: Sequence[TruthIsolatedEpisodeEvaluationRecord],
    summary: TruthIsolatedBatchSummary,
    *,
    title: str,
) -> str:
    """Render a Chinese evidence report without inventing unavailable metrics."""

    lines = [
        f"# {title}",
        "",
        f"评估日期：{D6_TRUTH_ISOLATED_EVALUATION_DATE}",
        "",
        "## 结论",
        "",
        f"本次读取 {len(records)} 个 episode，按实际目标、资源、侦察节点和相机数量分组。场景名称不参与规模推断。",
        "D1 指标来自公开离线一致性结果及其逐观测聚合记录。D2 指标只来自公开身份评估制品；D6 未重新构造航迹与真值映射。",
        "缺少来源摘要、在线真值隔离审计或有效样本时，指标保持空值并记录原因。`id_switch_count` 在所有记录中显式存在，缺证据时不会写成零。",
        "严格 IDSW、identity commitment coverage 与 evaluator-only partial diagnostics 是三类独立证据。未提交空档降低 coverage，但不等于 `IDSW=0`；严格 IDSW 只消费 D2 已发布值，D6 不回算或覆盖。",
        "",
        "## Episode 结果",
        "",
        "| episode | 规模 T/R/Rc/Cam | seed | D1 状态 | 位置 RMSE | NEES | NIS 覆盖 | D2 真值隔离 | ID Switch | 身份连续率 | 重复映射 |",
        "| --- | --- | ---: | --- | --- | --- | --- | :---: | --- | --- | --- |",
    ]
    for record in records:
        context = record.context
        scale = "/".join(
            str(value)
            for value in (
                context.target_count,
                context.resource_count,
                context.recon_count,
                context.camera_count,
            )
        )
        lines.append(
            "| {episode} | {scale} | {seed} | {d1_status} | {rmse} | {nees} | "
            "{nis} | {truth} | {idsw} | {continuity} | {duplicate} |".format(
                episode=context.episode_id,
                scale=scale,
                seed=context.seed,
                d1_status=record.d1.status,
                rmse=_fmt_metric(record.d1.metrics["position_rmse_m"]),
                nees=_fmt_metric(record.d1.metrics["mean_nees"]),
                nis=_fmt_metric(record.d1.metrics["nis_gate_coverage"]),
                truth="是" if record.d2.truth_isolation_verified else "否",
                idsw=_fmt_metric(record.d2.metrics["id_switch_count"]),
                continuity=_fmt_metric(record.d2.metrics["identity_continuity"]),
                duplicate=_fmt_metric(
                    record.d2.metrics["duplicate_truth_to_track_count"]
                ),
            )
        )

    lines.extend(
        [
            "",
            "## 身份恢复配置谱系",
            "",
            "D6 对 identity manifest v2 中的恢复配置做独立复核。清单配置、规范 JSON 摘要、D2 在线记录文件摘要、逐帧配置和记录数全部一致后，本节才标记可用。历史 manifest v1 继续保留原有身份指标，本节显示谱系不可用。",
            "",
            "| episode | manifest | provenance | config schema | config SHA-256 | records | online JSONL |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for record in records:
        provenance = record.d2.identity_recovery_config_provenance
        lines.append(
            "| {episode} | {manifest} | {availability} | {schema} | {digest} | "
            "{records} | {online} |".format(
                episode=record.context.episode_id,
                manifest=provenance.identity_manifest_schema_version
                or "不可用",
                availability=(
                    "可用"
                    if provenance.available
                    else f"不可用（{provenance.unavailable_reason}）"
                ),
                schema=provenance.config_schema_version or "不可用",
                digest=provenance.config_sha256 or "不可用",
                records=(
                    provenance.config_record_count
                    if provenance.config_record_count is not None
                    else "不可用"
                ),
                online=provenance.online_d2_records_sha256 or "不可用",
            )
        )

    lines.extend(
        [
            "",
            "## 观测处置证据",
            "",
            "D6 只接受 D2 已归一化且由 SHA-256 绑定的评估结果。三态计数来自 D2 identity audit；D6 不读取在线目标身份，不从观测编号、距离或 actor 名称推断处置，也不利用该计数回填严格 ID Switch。",
            "",
            "| episode | schema | target | known false alarm | unknown | missing disposition | count source | IDSW backfill |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- | :---: |",
        ]
    )
    for record in records:
        disposition = record.d2.audit.get(
            "d6_observation_truth_disposition_acceptance",
            {},
        )
        if not isinstance(disposition, Mapping):
            disposition = {}
        lines.append(
            "| {episode} | {schema} | {target} | {false_alarm} | {unknown} | "
            "{missing} | {source} | {backfill} |".format(
                episode=record.context.episode_id,
                schema=disposition.get("source_schema_version") or "不可用",
                target=_fmt_disposition_count(disposition, "target_label"),
                false_alarm=_fmt_disposition_count(
                    disposition,
                    "known_false_alarm",
                ),
                unknown=_fmt_disposition_count(disposition, "unknown"),
                missing=_fmt_disposition_count(
                    disposition,
                    "missing_disposition",
                ),
                source=disposition.get("count_source") or "不可用",
                backfill=(
                    "是"
                    if disposition.get("strict_id_switch_backfilled") is True
                    else "否"
                ),
            )
        )

    lines.extend(
        [
            "",
            "## 身份提交 v2 证据",
            "",
            "D6 仅对 `d2.scalable3d_identity_evaluation.v2` 复核并聚合本节。v1 显式显示不可用；兼容字段中的零记录数不会转写为可用的零 coverage。两个 binding violation 必须恒为 0。",
            "",
            "| episode | evaluation schema | commitment | strict IDSW | all coverage (C/U) | observed coverage (C/U) | uncommitted mapping | blocked reasons | blocker sum/mean/max | watermark age min/mean/max | overflow record/track | binding violation candidate/source |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for record in records:
        commitment = record.d2.identity_commitment
        metrics = commitment.metrics
        lines.append(
            "| {episode} | {schema} | {availability} | {idsw} | "
            "{all_coverage} ({all_committed}/{all_uncommitted}) | "
            "{observed_coverage} ({observed_committed}/{observed_uncommitted}) | "
            "{uncommitted_mapping} | {blocked} | {blocker_summary} | "
            "{watermark_summary} | {overflow} | {violations} |".format(
                episode=record.context.episode_id,
                schema=record.d2.producer_schema_version or "不可用",
                availability=(
                    "可用"
                    if commitment.available
                    else f"不可用（{commitment.unavailable_reason}）"
                ),
                idsw=_fmt_metric(record.d2.metrics["id_switch_count"]),
                all_coverage=_fmt_metric(
                    metrics["all_commitment_coverage"]
                ),
                all_committed=_fmt_metric(
                    metrics["all_committed_count"]
                ),
                all_uncommitted=_fmt_metric(
                    metrics["all_uncommitted_count"]
                ),
                observed_coverage=_fmt_metric(
                    metrics["observed_commitment_coverage"]
                ),
                observed_committed=_fmt_metric(
                    metrics["observed_committed_count"]
                ),
                observed_uncommitted=_fmt_metric(
                    metrics["observed_uncommitted_count"]
                ),
                uncommitted_mapping=_fmt_metric(
                    metrics["uncommitted_mapping_count"]
                ),
                blocked=_fmt_count_mapping(
                    commitment.recovery_blocked_reason_counts
                ),
                blocker_summary=_fmt_metric_triplet(
                    metrics,
                    "recovery_blocker_count",
                ),
                watermark_summary=_fmt_metric_triplet(
                    metrics,
                    "recovery_watermark_age_seconds",
                ),
                overflow="{}/{}".format(
                    _fmt_metric(
                        metrics[
                            "recovery_blocker_overflow_record_count"
                        ]
                    ),
                    _fmt_metric(
                        metrics[
                            "recovery_blocker_overflow_track_count"
                        ]
                    ),
                ),
                violations="{}/{}".format(
                    _fmt_metric(
                        metrics[
                            "uncommitted_candidate_binding_violation_count"
                        ]
                    ),
                    _fmt_metric(
                        metrics[
                            "uncommitted_source_binding_violation_count"
                        ]
                    ),
                ),
            )
        )

    lines.extend(
        [
            "",
            "## Evaluator-only 部分身份诊断",
            "",
            "| episode | partial 证据 | strict ID Switch | mapping coverage | frame coverage | adjacent-transition coverage | IDSW lower bound | anchor 区间 | anchor 排除原因 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in records:
        partial = record.d2.partial_identity_diagnostics
        lines.append(
            "| {episode} | {availability} | {strict_idsw} | {mapping} | "
            "{frame} | {transition} | {lower} | {anchors} | {reasons} |".format(
                episode=record.context.episode_id,
                availability=(
                    "可用"
                    if partial.available
                    else f"不可用（{partial.unavailable_reason}）"
                ),
                strict_idsw=_fmt_metric(
                    record.d2.metrics["id_switch_count"]
                ),
                mapping=_fmt_metric(
                    partial.metrics["evaluable_mapping_coverage"]
                ),
                frame=_fmt_metric(
                    partial.metrics["evaluable_frame_coverage"]
                ),
                transition=_fmt_metric(
                    partial.metrics["adjacent_transition_coverage"]
                ),
                lower=_fmt_metric(
                    partial.metrics["id_switch_lower_bound"]
                ),
                anchors=_fmt_metric(
                    partial.metrics["anchor_interval_count"]
                ),
                reasons=_fmt_count_mapping(
                    partial.lower_bound_anchor_exclusion_reason_counts
                ),
            )
        )

    lines.extend(
        [
            "",
            "## 来源摘要",
            "",
            "| episode | D1 制品摘要 | D1 输入摘要 | D2 制品摘要 | D2 四类来源摘要 | D2 指标证据 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in records:
        lines.append(
            "| {episode} | {d1_artifact} | {d1_sources} | {d2_artifact} | "
            "{d2_sources} | {d2_evidence} |".format(
                episode=record.context.episode_id,
                d1_artifact=_fmt_hash(
                    record.d1.external_file_sha256 or record.d1.artifact_digest
                ),
                d1_sources=_fmt_hash_mapping(record.d1.input_digests),
                d2_artifact=_fmt_hash(
                    record.d2.external_file_sha256 or record.d2.artifact_digest
                ),
                d2_sources=_fmt_hash_mapping(record.d2.source_hashes),
                d2_evidence=(
                    "可用"
                    if (
                        record.d2.truth_isolation_verified
                        and record.d2.truth_metric_evidence_verified
                    )
                    else "不可用（{}）".format(
                        "d2_online_truth_isolation_not_verified"
                        if not record.d2.truth_isolation_verified
                        else record.d2.truth_metric_evidence_reason
                    )
                ),
            )
        )

    lines.extend(
        [
            "",
            "## 分组统计",
            "",
            "| 场景/版本 | 规模 T/R/Rc/Cam | episode/seed | D1 位置 RMSE 均值 | D1 NIS 覆盖均值 | D2 ID Switch 均值 | D2 连续率均值 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for group in summary.groups:
        metrics = group["metrics"]
        scale = "/".join(
            str(group[name])
            for name in (
                "target_count",
                "resource_count",
                "recon_count",
                "camera_count",
            )
        )
        lines.append(
            "| {scenario}/{version} | {scale} | {episodes}/{seeds} | {rmse} | "
            "{nis} | {idsw} | {continuity} |".format(
                scenario=group["scenario_id"],
                version=group["scenario_version"],
                scale=scale,
                episodes=group["episode_count"],
                seeds=group["seed_count"],
                rmse=_fmt_aggregate(metrics["d1.position_rmse_m"]),
                nis=_fmt_aggregate(metrics["d1.nis_gate_coverage"]),
                idsw=_fmt_aggregate(metrics["d2.id_switch_count"]),
                continuity=_fmt_aggregate(metrics["d2.identity_continuity"]),
            )
        )

    lines.extend(
        [
            "",
            "## 身份提交分组汇总",
            "",
            "| 场景/版本 | 规模 T/R/Rc/Cam | v2 episode | all coverage (C/U/D) | observed coverage (C/U/D) | uncommitted mapping | blocked reasons | blocker sum/mean/max | watermark min/mean/max | overflow record/track | binding violation candidate/source |",
            "| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for group in summary.groups:
        commitment = group["d2_identity_commitment"]
        all_records = commitment["all_records"]
        observed_records = commitment["observed_records"]
        scale = "/".join(
            str(group[name])
            for name in (
                "target_count",
                "resource_count",
                "recon_count",
                "camera_count",
            )
        )
        lines.append(
            "| {scenario}/{version} | {scale} | {available}/{episodes} | "
            "{all_coverage} ({all_committed}/{all_uncommitted}/{all_denominator}) | "
            "{observed_coverage} ({observed_committed}/{observed_uncommitted}/"
            "{observed_denominator}) | {uncommitted_mapping} | {blocked} | "
            "{blocker} | {watermark} | {overflow_record}/{overflow_track} | "
            "{candidate_violation}/{source_violation} |".format(
                scenario=group["scenario_id"],
                version=group["scenario_version"],
                scale=scale,
                available=commitment["available_episode_count"],
                episodes=group["episode_count"],
                all_coverage=_fmt_commitment_aggregate_coverage(all_records),
                all_committed=all_records["committed_count"],
                all_uncommitted=all_records["uncommitted_count"],
                all_denominator=all_records["denominator"],
                observed_coverage=_fmt_commitment_aggregate_coverage(
                    observed_records
                ),
                observed_committed=observed_records["committed_count"],
                observed_uncommitted=observed_records["uncommitted_count"],
                observed_denominator=observed_records["denominator"],
                uncommitted_mapping=commitment[
                    "uncommitted_mapping_count"
                ],
                blocked=_fmt_count_mapping(
                    commitment["recovery_blocked_reason_counts"]
                ),
                blocker=_fmt_summary_mapping(
                    commitment["recovery_blocker_count_summary"]
                ),
                watermark=_fmt_summary_mapping(
                    commitment[
                        "recovery_watermark_age_seconds_summary"
                    ]
                ),
                overflow_record=commitment[
                    "recovery_blocker_overflow_record_count"
                ],
                overflow_track=commitment[
                    "recovery_blocker_overflow_track_count"
                ],
                candidate_violation=commitment[
                    "uncommitted_candidate_binding_violation_count"
                ],
                source_violation=commitment[
                    "uncommitted_source_binding_violation_count"
                ],
            )
        )

    lines.extend(
        [
            "",
            "## 部分身份分组汇总",
            "",
            "| 场景/版本 | 规模 T/R/Rc/Cam | partial episode | mapping coverage | frame coverage | adjacent-transition coverage | IDSW lower bound 合计 | anchor 区间合计 | anchor 排除原因 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for group in summary.groups:
        partial = group["d2_partial_identity_diagnostics"]
        coverage = partial["coverage_totals"]
        scale = "/".join(
            str(group[name])
            for name in (
                "target_count",
                "resource_count",
                "recon_count",
                "camera_count",
            )
        )
        lines.append(
            "| {scenario}/{version} | {scale} | {available}/{episodes} | "
            "{mapping} | {frame} | {transition} | {lower} | {anchors} | "
            "{reasons} |".format(
                scenario=group["scenario_id"],
                version=group["scenario_version"],
                scale=scale,
                available=partial["available_episode_count"],
                episodes=group["episode_count"],
                mapping=_fmt_partial_coverage_total(coverage["mapping"]),
                frame=_fmt_partial_coverage_total(coverage["frame"]),
                transition=_fmt_partial_coverage_total(
                    coverage["adjacent_transition"]
                ),
                lower=_fmt_partial_total(partial["id_switch_lower_bound"]),
                anchors=(
                    "—"
                    if partial["availability"] != "available"
                    else str(partial["anchor_interval_count"])
                ),
                reasons=_fmt_count_mapping(
                    partial[
                        "lower_bound_anchor_exclusion_reason_counts"
                    ]
                ),
            )
        )

    lines.extend(
        [
            "",
            "## D1 传感器与距离分档",
            "",
            "| 场景/规模 | 传感器 | 距离分档 | episode/seed | 位置 RMSE | NEES | NIS 覆盖 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for group in summary.d1_sensor_range_groups:
        scale = f"{group['target_count']}/{group['resource_count']}"
        metrics = group["metrics"]
        lines.append(
            "| {scenario}/{scale} | {sensor}/{sensor_type} | {range_bin} | "
            "{episodes}/{seeds} | {rmse} | {nees} | {nis} |".format(
                scenario=group["scenario_id"],
                scale=scale,
                sensor=group["sensor_id"],
                sensor_type=group["sensor_type"],
                range_bin=group["range_bin"],
                episodes=group["episode_count"],
                seeds=group["seed_count"],
                rmse=_fmt_aggregate(metrics["position_rmse_m"]),
                nees=_fmt_aggregate(metrics["mean_nees"]),
                nis=_fmt_aggregate(metrics["nis_gate_coverage"]),
            )
        )

    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "本报告只说明公开评估合同和输入证据中的数值。单 seed 分组只给描述统计，不输出自助法置信区间。正式 5、20、50、100、200 规模结论仍需 main 提供冻结配置和多 seed 制品。",
            "完整来源摘要同时保存在逐 seed CSV 和聚合 JSON；路径制品必须由 main 提供文件摘要及 D2 四类来源摘要。",
            "D2 混淆矩阵和覆盖计数保存在聚合 JSON 中。它们用于离线诊断，不能回流到在线关联、分配或导引链路。",
            "identity commitment v2 只有在 evaluation/evidence/commitment/audit schema 与 policy 全部匹配、嵌入 evidence bundle SHA-256 可复算、分母与 coverage 守恒、恢复统计有限且两个 binding violation 为 0 时才可用。显式 uncommitted 只降低 coverage；普通谱系缺失继续使 D2 strict 指标失败关闭。",
            "部分身份诊断只有在 sidecar schema、identity manifest、评估文件 SHA-256、四类来源摘要及 evaluator-only audit 全部绑定后才可用。lower bound 与 strict `id_switch_count` 始终分栏，绝不回填；D6 不构造 upper bound，partial block 不参与控制。",
            "",
        ]
    )
    return "\n".join(lines)


def _public_payload(
    source: object | Mapping[str, Any] | str | Path,
    *,
    expected_sha256: str | None,
    artifact_name: str,
) -> tuple[dict[str, Any], str | None, str]:
    if isinstance(source, (str, Path)):
        if expected_sha256 is None:
            raise TruthIsolatedEvaluationError(
                f"{artifact_name} path requires expected_sha256"
            )
        path = Path(source)
        expected = _normalized_sha256(expected_sha256)
        actual = _sha256_file(path)
        if actual != expected:
            raise TruthIsolatedEvaluationError(
                f"{artifact_name} sha256 mismatch: expected {expected}, got {actual}"
            )
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TruthIsolatedEvaluationError(
                f"cannot load {artifact_name}"
            ) from exc
        return dict(_mapping(loaded, artifact_name)), actual, "sha256_verified_artifact"
    if isinstance(source, Mapping):
        if expected_sha256 is not None:
            raise TruthIsolatedEvaluationError(
                f"{artifact_name} expected_sha256 is only valid for a file path"
            )
        return dict(source), None, "public_mapping_validated"
    to_dict = getattr(source, "to_dict", None)
    if not callable(to_dict):
        raise TypeError(f"{artifact_name} must be a public DTO, mapping, or path")
    if expected_sha256 is not None:
        raise TruthIsolatedEvaluationError(
            f"{artifact_name} expected_sha256 is only valid for a file path"
        )
    return dict(_mapping(to_dict(), artifact_name)), None, "public_dto_validated"


def _normalized_d1_input_digests(
    payload: Mapping[str, Any],
) -> dict[str, str | None]:
    return {
        "online_evidence": _optional_sha256(payload.get("online_evidence")),
        "truth_sidecar": _optional_sha256(payload.get("truth_sidecar")),
        "d2_lineage_mapping": _resolve_d1_lineage_mapping_digest(
            payload,
            current_name="d2_lineage_mapping",
            legacy_name="canonical_mapping",
            context="D1 input_digests",
        ),
    }


def _resolve_d1_lineage_mapping_digest(
    payload: Mapping[str, Any],
    *,
    current_name: str,
    legacy_name: str,
    context: str,
) -> str | None:
    """Normalize the current D1 field while accepting one frozen legacy alias."""

    current_present = current_name in payload
    legacy_present = legacy_name in payload
    current = (
        _optional_sha256(payload.get(current_name))
        if current_present
        else None
    )
    legacy = (
        _optional_sha256(payload.get(legacy_name))
        if legacy_present
        else None
    )
    if current_present and legacy_present and current != legacy:
        raise TruthIsolatedEvaluationError(
            f"{context} has conflicting {current_name} and {legacy_name}"
        )
    return current if current_present else legacy


def _d1_aggregation_records(
    source: object | Mapping[str, Any] | str | Path,
    payload: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    input_digests: Mapping[str, str | None],
) -> tuple[Mapping[str, Any], ...]:
    method = getattr(source, "aggregation_records", None)
    if callable(method):
        return tuple(
            _mapping(value, "D1 aggregation record") for value in method()
        )
    context = {
        "schema_version": D1_OFFLINE_CONSISTENCY_AGGREGATION_SCHEMA_VERSION,
        "result_record_schema_version": D1_OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION,
        "scenario_id": payload.get("scenario_id"),
        "scenario_version": payload.get("scenario_version"),
        "run_id": payload.get("run_id"),
        "seed": payload.get("seed"),
        "offline_result_digest": payload.get("content_digest"),
        "online_evidence_digest": input_digests["online_evidence"],
        "truth_sidecar_digest": input_digests["truth_sidecar"],
        "d2_lineage_mapping_digest": input_digests["d2_lineage_mapping"],
    }
    return tuple({**dict(record), **context} for record in records)


def _validate_d1_aggregation_records(
    records: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
    content_digest: str,
    *,
    input_digests: Mapping[str, str | None],
    source_records: Sequence[Mapping[str, Any]],
) -> None:
    if len(records) != int(payload.get("record_count", -1)):
        raise TruthIsolatedEvaluationError("D1 aggregation record count mismatch")
    expected_context = {
        "scenario_id": payload.get("scenario_id"),
        "scenario_version": payload.get("scenario_version"),
        "run_id": payload.get("run_id"),
        "seed": payload.get("seed"),
        "offline_result_digest": content_digest,
        "online_evidence_digest": input_digests["online_evidence"],
        "truth_sidecar_digest": input_digests["truth_sidecar"],
    }
    for record, source_record in zip(records, source_records):
        if record.get("schema_version") != D1_OFFLINE_CONSISTENCY_AGGREGATION_SCHEMA_VERSION:
            raise TruthIsolatedEvaluationError(
                "unsupported D1 aggregation record schema"
            )
        if (
            record.get("result_record_schema_version")
            != D1_OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION
        ):
            raise TruthIsolatedEvaluationError(
                "unsupported D1 aggregation result record schema"
            )
        for name, expected in expected_context.items():
            if record.get(name) != expected:
                raise TruthIsolatedEvaluationError(
                    f"D1 aggregation provenance mismatch for {name}"
                )
        mapping_digest = _resolve_d1_lineage_mapping_digest(
            record,
            current_name="d2_lineage_mapping_digest",
            legacy_name="canonical_mapping_digest",
            context="D1 aggregation record",
        )
        if mapping_digest != input_digests["d2_lineage_mapping"]:
            raise TruthIsolatedEvaluationError(
                "D1 aggregation provenance mismatch for "
                "d2_lineage_mapping_digest"
            )
        for name, expected in source_record.items():
            if name == "schema_version":
                continue
            if record.get(name) != expected:
                raise TruthIsolatedEvaluationError(
                    f"D1 aggregation content mismatch for {name}"
                )


def _group_d1_consistency_records(
    records: Sequence[Mapping[str, Any]],
    *,
    input_digests: Mapping[str, str | None],
    offline_result_digest: str,
) -> tuple[D1SensorRangeConsistencyRecord, ...]:
    grouped: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        key = tuple(
            _identifier(record.get(name), f"D1 aggregation {name}")
            for name in (
                "scenario_id",
                "scenario_version",
                "run_id",
                "sensor_id",
                "sensor_type",
                "source_sensor_type",
                "range_bin",
            )
        )
        grouped[key].append(record)

    output: list[D1SensorRangeConsistencyRecord] = []
    for key in sorted(grouped):
        group_records = grouped[key]
        metrics = {
            "position_rmse_m": _metric_from_public_records(
                group_records,
                field="position_error_m",
                operation="rmse",
                availability_name="truth_alignment",
            ),
            "velocity_rmse_mps": _metric_from_public_records(
                group_records,
                field="velocity_error_mps",
                operation="rmse",
                availability_name="truth_alignment",
            ),
            "mean_nees": _metric_from_public_records(
                group_records,
                field="nees",
                operation="mean",
                availability_name="nees",
            ),
            "mean_normalized_nees": _metric_from_public_records(
                group_records,
                field="normalized_nees",
                operation="mean",
                availability_name="nees",
            ),
            "mean_nis": _metric_from_public_records(
                group_records,
                field="nis",
                operation="mean",
                availability_name=None,
            ),
            "mean_normalized_nis": _metric_from_public_records(
                group_records,
                field="normalized_nis",
                operation="mean",
                availability_name=None,
            ),
            "nis_gate_coverage": _metric_from_public_records(
                group_records,
                field="nis_within_gate",
                operation="mean",
                availability_name="nis_coverage",
            ),
        }
        (
            scenario_id,
            scenario_version,
            run_id,
            sensor_id,
            sensor_type,
            source_sensor_type,
            range_bin,
        ) = key
        output.append(
            D1SensorRangeConsistencyRecord(
                scenario_id=scenario_id,
                scenario_version=scenario_version,
                run_id=run_id,
                seed=_optional_int(group_records[0].get("seed")),
                sensor_id=sensor_id,
                sensor_type=sensor_type,
                source_sensor_type=source_sensor_type,
                range_bin=range_bin,
                metrics=metrics,
                offline_result_digest=offline_result_digest,
                input_digests=input_digests,
                record_count=len(group_records),
            )
        )
    return tuple(output)


def _metric_from_public_records(
    records: Sequence[Mapping[str, Any]],
    *,
    field: str,
    operation: str,
    availability_name: str | None,
) -> PublicMetricEvidence:
    values: list[float] = []
    reasons: Counter[str] = Counter()
    for record in records:
        value = record.get(field)
        if availability_name is not None:
            availability = _mapping(
                record.get("availability"),
                f"D1 record availability for {field}",
            )
            item = _mapping(
                availability.get(availability_name),
                f"D1 record {availability_name} availability",
            )
            field_available = _required_bool(
                item,
                "available",
                context=f"D1 record {availability_name} availability",
            )
            reason = item.get("reason")
            if field_available:
                if value is None or reason is not None:
                    raise TruthIsolatedEvaluationError(
                        f"available D1 record field lacks value: {field}"
                    )
            else:
                if value is not None or not str(reason or "").strip():
                    raise TruthIsolatedEvaluationError(
                        f"unavailable D1 record field must be null: {field}"
                    )
                reasons[str(reason)] += 1
                continue
        elif value is None:
            reasons[f"public_field_unavailable:{field}"] += 1
            continue
        values.append(_validated_d1_metric_value(field, value))
    if not values:
        return PublicMetricEvidence(
            value=None,
            available=False,
            sample_count=0,
            unavailable_reason=f"no_available_samples:{field}",
            unavailability_reason_counts=reasons,
        )
    array = np.asarray(values, dtype=float)
    if operation == "mean":
        result = float(np.mean(array))
    elif operation == "rmse":
        result = float(np.sqrt(np.mean(np.square(array))))
    else:
        raise ValueError(f"unsupported metric operation: {operation}")
    return PublicMetricEvidence(
        value=result,
        available=True,
        sample_count=len(values),
        unavailability_reason_counts=reasons,
    )


def _metric_from_d1_summary(payload: Any, name: str) -> PublicMetricEvidence:
    item = _mapping(payload, f"D1 metric {name}")
    available = _required_bool(item, "available", context=f"D1 metric {name}")
    value = item.get("value")
    reason = item.get("reason")
    sample_count = _nonnegative_int(
        item.get("sample_count"),
        f"D1 metric {name} sample_count",
    )
    if available:
        if value is None or sample_count == 0 or reason is not None:
            raise TruthIsolatedEvaluationError(
                f"available D1 metric lacks evidence: {name}"
            )
        normalized_value: int | float | None = _validated_d1_metric_value(
            name,
            value,
        )
        normalized_reason = None
    else:
        if value is not None or not str(reason or "").strip():
            raise TruthIsolatedEvaluationError(
                f"unavailable D1 metric must be null with a reason: {name}"
            )
        normalized_value = None
        normalized_reason = str(reason)
    return PublicMetricEvidence(
        value=normalized_value,
        available=available,
        sample_count=sample_count,
        unavailable_reason=normalized_reason,
    )


def _validate_d1_result_availability(
    *,
    status: str,
    metrics: Mapping[str, PublicMetricEvidence],
    input_digests: Mapping[str, str | None],
) -> None:
    available_count = sum(metric.available for metric in metrics.values())
    expected_status = (
        "available"
        if available_count == len(_D1_METRIC_NAMES)
        else "partial"
        if available_count > 0
        else "unavailable"
    )
    if status != expected_status:
        raise TruthIsolatedEvaluationError(
            "D1 status does not match metric availability"
        )
    if available_count and input_digests.get("online_evidence") is None:
        raise TruthIsolatedEvaluationError(
            "available D1 metrics require online_evidence digest"
        )
    if any(metrics[name].available for name in _D1_TRUTH_METRIC_NAMES):
        missing = [
            name
            for name in ("truth_sidecar", "d2_lineage_mapping")
            if input_digests.get(name) is None
        ]
        if missing:
            raise TruthIsolatedEvaluationError(
                "available D1 truth metrics require source digests: "
                + ",".join(missing)
            )


def _d2_metric_evidence(
    payload: Mapping[str, Any],
    *,
    availability_blocker: str | None,
) -> dict[str, PublicMetricEvidence]:
    truth_available = _required_bool(
        payload,
        "truth_metrics_available",
        context="D2 identity metrics",
    )
    producer_reason = str(
        payload.get("truth_metrics_reason") or "truth_metrics_unavailable"
    )
    if truth_available and payload.get("truth_metrics_reason") is not None:
        raise TruthIsolatedEvaluationError(
            "available D2 truth metrics must not carry an unavailable reason"
        )
    if not truth_available and not str(payload.get("truth_metrics_reason") or "").strip():
        raise TruthIsolatedEvaluationError(
            "unavailable D2 truth metrics require a reason"
        )
    evaluated_frames = _nonnegative_int(
        payload.get("evaluated_frame_count"),
        "D2 evaluated_frame_count",
    )
    output: dict[str, PublicMetricEvidence] = {}
    for name in _D2_METRIC_NAMES:
        availability_name = f"{name}_available"
        metric_available = _required_bool(
            payload,
            availability_name,
            context="D2 identity metrics",
        )
        value = payload.get(name)
        metric_reason = payload.get(f"{name}_reason")
        if metric_available != truth_available:
            raise TruthIsolatedEvaluationError(
                f"D2 identity metric availability conflicts with truth block: {name}"
            )
        if truth_available and (value is None or metric_reason is not None):
            raise TruthIsolatedEvaluationError(
                f"available D2 identity metric lacks value: {name}"
            )
        if not truth_available and (
            value is not None or not str(metric_reason or "").strip()
        ):
            raise TruthIsolatedEvaluationError(
                f"unavailable D2 identity metric must be null with a reason: {name}"
            )
        normalized_value = (
            _validated_d2_metric_value(name, value)
            if truth_available
            else None
        )
        is_available = truth_available and availability_blocker is None
        output[name] = PublicMetricEvidence(
            value=normalized_value if is_available else None,
            available=is_available,
            sample_count=evaluated_frames if is_available else 0,
            unavailable_reason=(
                None
                if is_available
                else str(availability_blocker or metric_reason or producer_reason)
            ),
        )
    duplicate = payload.get("duplicate_truth_to_track_count")
    if payload.get("duplicate_assignment_count") != duplicate:
        raise TruthIsolatedEvaluationError(
            "D2 duplicate_assignment_count alias mismatch"
        )
    if _required_bool(
        payload,
        "duplicate_assignment_count_available",
        context="D2 identity metrics",
    ) != truth_available:
        raise TruthIsolatedEvaluationError(
            "D2 duplicate assignment availability mismatch"
        )
    return output


def _d2_observation_truth_disposition_acceptance(
    *,
    payload: Mapping[str, Any],
    audit: Mapping[str, Any],
    source_hashes: Mapping[str, str],
    truth_metrics_available: bool,
    metrics_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate disposition evidence reported by D2 without reopening truth."""

    source_hash = source_hashes.get("observation_truth_labels")
    if source_hash is None:
        raise TruthIsolatedEvaluationError(
            "D2 observation truth source hash is missing"
        )
    schema = audit.get("observation_truth_schema_version")
    if schema is None:
        return {
            "availability": "unavailable",
            "unavailable_reason": (
                "d2_observation_truth_schema_not_reported_by_legacy_evaluation"
            ),
            "source_schema_version": None,
            "source_sha256": source_hash,
            "source_hash_bound": True,
            "count_source": None,
            "target_label": {
                "availability": "unavailable",
                "count": None,
                "reason": "legacy_d2_audit_does_not_report_disposition_schema",
            },
            "known_false_alarm": {
                "availability": "unavailable",
                "count": None,
                "reason": "legacy_d2_audit_does_not_report_disposition_schema",
            },
            "unknown": {
                "availability": "unavailable",
                "count": None,
                "reason": "legacy_d2_audit_does_not_report_disposition_schema",
            },
            "missing_disposition": {
                "availability": "unavailable",
                "count": None,
                "reason": "legacy_d2_audit_does_not_report_disposition_schema",
            },
            "known_false_alarm_treated_as_target": False,
            "strict_id_switch_source": "d2_identity_evaluation_only",
            "strict_id_switch_backfilled": False,
            "inference_sources_used": [],
        }
    if schema == D2_OBSERVATION_TRUTH_SCHEMA_VERSION_V1:
        target_count = _nonnegative_int(
            audit.get("truth_label_count"),
            "D2 v1 truth_label_count",
        )
        return {
            "availability": "available",
            "unavailable_reason": None,
            "source_schema_version": schema,
            "source_sha256": source_hash,
            "source_hash_bound": True,
            "count_source": "D2 identity audit truth_label_count",
            "target_label": {
                "availability": "available",
                "count": target_count,
                "reason": None,
            },
            "known_false_alarm": {
                "availability": "unavailable",
                "count": None,
                "reason": (
                    "v1_target_only_schema_cannot_report_non_target_dispositions"
                ),
            },
            "unknown": {
                "availability": "unavailable",
                "count": None,
                "reason": (
                    "v1_target_only_schema_cannot_report_non_target_dispositions"
                ),
            },
            "missing_disposition": {
                "availability": "available",
                "count": 0,
                "reason": None,
            },
            "known_false_alarm_treated_as_target": False,
            "strict_id_switch_source": "d2_identity_evaluation_only",
            "strict_id_switch_backfilled": False,
            "inference_sources_used": [],
        }
    if schema != D2_OBSERVATION_TRUTH_SCHEMA_VERSION_V2:
        raise TruthIsolatedEvaluationError(
            f"unsupported D2 observation truth audit schema: {schema!r}"
        )

    raw_counts = _mapping(
        audit.get("observation_truth_disposition_counts"),
        "D2 observation truth disposition counts",
    )
    allowed = {"target", "known_false_alarm", "unknown"}
    unsupported = set(raw_counts) - allowed
    if unsupported:
        raise TruthIsolatedEvaluationError(
            "D2 observation truth audit reports unsupported dispositions: "
            + ",".join(sorted(unsupported))
        )
    counts = {
        name: _nonnegative_int(
            raw_counts.get(name, 0),
            f"D2 observation truth disposition count {name}",
        )
        for name in sorted(allowed)
    }
    total = _nonnegative_int(
        audit.get("truth_label_count"),
        "D2 truth_label_count",
    )
    if sum(counts.values()) != total:
        raise TruthIsolatedEvaluationError(
            "D2 observation truth disposition counts do not cover the sidecar"
        )

    known_false_alarm_mapping_count = 0
    frames = payload.get("frames")
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)):
        raise TruthIsolatedEvaluationError("D2 identity frames must be a sequence")
    for raw_frame in frames:
        frame = _mapping(raw_frame, "D2 identity frame")
        mappings = frame.get("mappings")
        if not isinstance(mappings, Sequence) or isinstance(
            mappings,
            (str, bytes),
        ):
            raise TruthIsolatedEvaluationError(
                "D2 identity frame mappings must be a sequence"
            )
        for raw_mapping in mappings:
            mapping = _mapping(raw_mapping, "D2 identity mapping")
            if mapping.get("reason") != "known_false_alarm_only":
                continue
            known_false_alarm_mapping_count += 1
            if not (
                mapping.get("status") == "excluded"
                and mapping.get("truth_target_id") is None
                and not mapping.get("candidate_truth_target_ids")
            ):
                raise TruthIsolatedEvaluationError(
                    "D2 known false alarm was promoted to a target identity"
                )
    reported_exclusion_count = _nonnegative_int(
        audit.get("known_false_alarm_only_mapping_count", 0),
        "D2 known-false-alarm-only mapping count",
    )
    if reported_exclusion_count != known_false_alarm_mapping_count:
        raise TruthIsolatedEvaluationError(
            "D2 known-false-alarm exclusion count contradicts frame mappings"
        )

    blockers = audit.get("identity_metrics_blocking_reasons")
    if counts["unknown"] > 0:
        if not (
            truth_metrics_available is False
            and metrics_payload.get("id_switch_count_available") is False
            and metrics_payload.get("id_switch_count") is None
            and isinstance(blockers, Sequence)
            and not isinstance(blockers, (str, bytes))
            and "truth_label_unknown" in blockers
        ):
            raise TruthIsolatedEvaluationError(
                "D2 unknown truth dispositions did not block strict identity metrics"
            )

    return {
        "availability": "available",
        "unavailable_reason": None,
        "source_schema_version": schema,
        "source_sha256": source_hash,
        "source_hash_bound": True,
        "count_source": (
            "D2 identity evaluation audit "
            "observation_truth_disposition_counts"
        ),
        "target_label": {
            "availability": "available",
            "count": counts["target"],
            "reason": None,
        },
        "known_false_alarm": {
            "availability": "available",
            "count": counts["known_false_alarm"],
            "reason": None,
        },
        "unknown": {
            "availability": "available",
            "count": counts["unknown"],
            "reason": None,
        },
        "missing_disposition": {
            "availability": "available",
            "count": 0,
            "reason": None,
        },
        "known_false_alarm_only_mapping_count": (
            known_false_alarm_mapping_count
        ),
        "known_false_alarm_treated_as_target": False,
        "strict_id_switch_source": "d2_identity_evaluation_only",
        "strict_id_switch_backfilled": False,
        "inference_sources_used": [],
    }


def adapt_d2_identity_recovery_config_provenance(
    *,
    producer_evaluation_schema_version: str,
    identity_source: object | Mapping[str, Any] | str | Path,
    identity_manifest: object | Mapping[str, Any] | str | Path | None,
    expected_identity_manifest_sha256: str | None,
    d2_online_d2_records: str | Path | None,
    d2_expected_online_d2_records_sha256: str | None,
    identity_source_hashes: Mapping[str, str],
) -> D2IdentityRecoveryConfigProvenanceRecord:
    """Independently bind manifest v2 recovery config to every D2 JSONL row."""

    manifest_schema: str | None = None
    manifest_sha: str | None = None
    verification_mode = "identity_recovery_config_manifest_unavailable"
    try:
        manifest_payload, manifest_sha, verification_mode = (
            _load_d2_partial_identity_manifest(
                identity_source=identity_source,
                identity_manifest=identity_manifest,
                expected_sha256=expected_identity_manifest_sha256,
            )
        )
    except _PartialIdentityValidationError as exc:
        if (
            exc.reason == "d2_identity_manifest_missing"
            and producer_evaluation_schema_version
            == D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1
        ):
            return _unavailable_d2_identity_recovery_config(
                "identity_recovery_config_not_manifest_bound_v1",
                verification_mode="legacy_manifest_v1_compatible",
            )
        return _unavailable_d2_identity_recovery_config(
            exc.reason,
            verification_mode=verification_mode,
        )

    manifest_schema = (
        None
        if manifest_payload.get("schema_version") is None
        else str(manifest_payload.get("schema_version"))
    )
    if manifest_schema == D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V1:
        return _unavailable_d2_identity_recovery_config(
            "identity_recovery_config_not_manifest_bound_v1",
            identity_manifest_schema_version=manifest_schema,
            identity_manifest_sha256=manifest_sha,
            verification_mode=f"{verification_mode}_legacy_v1_compatible",
        )
    if manifest_schema != D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2:
        return _unavailable_d2_identity_recovery_config(
            "unsupported_d2_identity_manifest_schema",
            identity_manifest_schema_version=manifest_schema,
            identity_manifest_sha256=manifest_sha,
            verification_mode=verification_mode,
        )

    online_records_sha: str | None = None
    try:
        (
            config_snapshot,
            config_sha,
            config_count,
            d2_record_count,
            online_records_sha,
        ) = _validate_d2_identity_recovery_config_v2(
            manifest_payload,
            identity_source=identity_source,
            identity_manifest=identity_manifest,
            d2_online_d2_records=d2_online_d2_records,
            d2_expected_online_d2_records_sha256=(
                d2_expected_online_d2_records_sha256
            ),
            identity_source_hashes=identity_source_hashes,
        )
    except _IdentityRecoveryConfigValidationError as exc:
        return _unavailable_d2_identity_recovery_config(
            exc.reason,
            identity_manifest_schema_version=manifest_schema,
            identity_manifest_sha256=manifest_sha,
            online_d2_records_sha256=online_records_sha,
            verification_mode=verification_mode,
        )

    return D2IdentityRecoveryConfigProvenanceRecord(
        available=True,
        unavailable_reason=None,
        config_snapshot=config_snapshot,
        config_sha256=config_sha,
        config_schema_version=str(config_snapshot["schema_version"]),
        config_version=(
            None
            if config_snapshot.get("config_version") is None
            else str(config_snapshot.get("config_version"))
        ),
        identity_manifest_schema_version=manifest_schema,
        identity_manifest_sha256=manifest_sha,
        online_d2_records_sha256=online_records_sha,
        config_record_count=config_count,
        d2_record_count=d2_record_count,
        consistency_verified=True,
        source=D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SOURCE,
        online_records_verified=True,
        verification_mode=f"{verification_mode}_online_jsonl_verified",
    )


def _validate_d2_identity_recovery_config_v2(
    manifest: Mapping[str, Any],
    *,
    identity_source: object | Mapping[str, Any] | str | Path,
    identity_manifest: object | Mapping[str, Any] | str | Path | None,
    d2_online_d2_records: str | Path | None,
    d2_expected_online_d2_records_sha256: str | None,
    identity_source_hashes: Mapping[str, str],
) -> tuple[dict[str, Any], str, int, int, str]:
    if manifest.get("available") is not True or manifest.get("reason") is not None:
        _identity_recovery_config_error(
            "d2_identity_manifest_unavailable",
            "D2 identity manifest v2 is not available",
        )
    config_raw = manifest.get("identity_commitment_recovery_config")
    if not isinstance(config_raw, Mapping) or not config_raw:
        _identity_recovery_config_error(
            "identity_recovery_config_missing",
            "D2 identity manifest v2 recovery config is missing or empty",
        )
    config = dict(config_raw)
    if (
        config.get("schema_version")
        != D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SCHEMA_VERSION
    ):
        _identity_recovery_config_error(
            "identity_recovery_config_schema_unsupported",
            "D2 identity recovery config schema is unsupported",
        )
    try:
        calculated_config_sha = _canonical_payload_sha256(config)
        claimed_config_sha = _normalized_sha256(
            manifest.get("identity_commitment_recovery_config_sha256")
        )
    except (TruthIsolatedEvaluationError, TypeError, ValueError) as exc:
        raise _IdentityRecoveryConfigValidationError(
            "identity_recovery_config_sha256_invalid",
            "D2 identity recovery config SHA-256 is invalid",
        ) from exc
    if calculated_config_sha != claimed_config_sha:
        _identity_recovery_config_error(
            "identity_recovery_config_sha256_mismatch",
            "D2 identity recovery config canonical SHA-256 does not match",
        )
    config_count = _identity_recovery_positive_int(
        manifest.get("identity_commitment_recovery_config_record_count"),
        "identity recovery config record count",
    )
    d2_record_count = _identity_recovery_positive_int(
        manifest.get("d2_record_count"),
        "D2 record count",
    )
    if config_count != d2_record_count:
        _identity_recovery_config_error(
            "identity_recovery_config_record_count_mismatch",
            "D2 identity recovery config count does not match d2_record_count",
        )
    if (
        manifest.get(
            "identity_commitment_recovery_config_consistency_verified"
        )
        is not True
    ):
        _identity_recovery_config_error(
            "identity_recovery_config_consistency_not_verified",
            "D2 identity recovery config consistency is not verified",
        )
    if (
        manifest.get("identity_commitment_recovery_config_source")
        != D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SOURCE
    ):
        _identity_recovery_config_error(
            "identity_recovery_config_source_mismatch",
            "D2 identity recovery config source declaration is invalid",
        )

    manifest_hashes = manifest.get("source_hashes")
    if not isinstance(manifest_hashes, Mapping):
        _identity_recovery_config_error(
            "d2_identity_manifest_source_hashes_missing",
            "D2 identity manifest source hashes are missing",
        )
    try:
        manifest_online_sha = _normalized_sha256(
            manifest_hashes.get("online_d2_records")
        )
        evaluation_online_sha = _normalized_sha256(
            identity_source_hashes.get("online_d2_records")
        )
    except TruthIsolatedEvaluationError as exc:
        raise _IdentityRecoveryConfigValidationError(
            "identity_recovery_config_online_d2_records_source_hash_invalid",
            "D2 online record source SHA-256 is invalid",
        ) from exc
    if manifest_online_sha != evaluation_online_sha:
        _identity_recovery_config_error(
            "identity_recovery_config_online_d2_records_source_hash_mismatch",
            "manifest and identity evaluation disagree on D2 online records",
        )

    online_path = _resolve_d2_online_records_path(
        explicit_path=d2_online_d2_records,
        identity_source=identity_source,
        identity_manifest=identity_manifest,
    )
    if online_path is None or not online_path.is_file():
        _identity_recovery_config_error(
            "identity_recovery_config_online_d2_records_missing",
            "D2 online records JSONL is required for manifest v2",
        )
    try:
        online_sha = _sha256_file(online_path)
    except TruthIsolatedEvaluationError as exc:
        raise _IdentityRecoveryConfigValidationError(
            "identity_recovery_config_online_d2_records_unreadable",
            "D2 online records JSONL cannot be read",
        ) from exc
    if d2_expected_online_d2_records_sha256 is not None:
        try:
            expected_online_sha = _normalized_sha256(
                d2_expected_online_d2_records_sha256
            )
        except TruthIsolatedEvaluationError as exc:
            raise _IdentityRecoveryConfigValidationError(
                "identity_recovery_config_online_d2_records_sha256_invalid",
                "expected D2 online records SHA-256 is invalid",
            ) from exc
        if online_sha != expected_online_sha:
            _identity_recovery_config_error(
                "identity_recovery_config_online_d2_records_sha256_mismatch",
                "D2 online records file SHA-256 does not match the expected value",
            )
    if online_sha != manifest_online_sha:
        _identity_recovery_config_error(
            "identity_recovery_config_online_d2_records_source_hash_mismatch",
            "D2 online records file does not match manifest/evaluation source hash",
        )

    record_count = _validate_online_d2_recovery_config_records(
        online_path,
        expected_config=config,
    )
    if record_count != config_count or record_count != d2_record_count:
        _identity_recovery_config_error(
            "identity_recovery_config_record_count_mismatch",
            "D2 online JSONL count does not match manifest record counts",
        )
    return config, claimed_config_sha, config_count, d2_record_count, online_sha


def _resolve_d2_online_records_path(
    *,
    explicit_path: str | Path | None,
    identity_source: object | Mapping[str, Any] | str | Path,
    identity_manifest: object | Mapping[str, Any] | str | Path | None,
) -> Path | None:
    if explicit_path is not None:
        return Path(explicit_path)
    for candidate_source in (identity_manifest, identity_source):
        if isinstance(candidate_source, (str, Path)):
            candidate = Path(candidate_source).parent / "online_d2_records.jsonl"
            if candidate.is_file():
                return candidate
    return None


def _validate_online_d2_recovery_config_records(
    path: Path,
    *,
    expected_config: Mapping[str, Any],
) -> int:
    count = 0
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    _identity_recovery_config_error(
                        "identity_recovery_config_online_d2_records_invalid_jsonl",
                        f"D2 online JSONL line {line_number} is empty",
                    )
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise _IdentityRecoveryConfigValidationError(
                        "identity_recovery_config_online_d2_records_invalid_jsonl",
                        f"D2 online JSONL line {line_number} is invalid",
                    ) from exc
                record = _identity_recovery_mapping(
                    raw,
                    f"D2 online JSONL line {line_number}",
                )
                if (
                    record.get("topic") != "modules.d2.associated_tracks"
                    or record.get("source") != "D2"
                ):
                    _identity_recovery_config_error(
                        "identity_recovery_config_online_d2_record_topic_mismatch",
                        (
                            f"D2 online JSONL line {line_number} has the wrong "
                            "topic or source"
                        ),
                    )
                payload = _identity_recovery_mapping(
                    record.get("payload"),
                    f"D2 online JSONL line {line_number} payload",
                )
                association = _identity_recovery_mapping(
                    payload.get("association"),
                    f"D2 online JSONL line {line_number} association",
                )
                commitment = _identity_recovery_mapping(
                    association.get("identity_commitment"),
                    f"D2 online JSONL line {line_number} identity commitment",
                )
                recovery_config = _identity_recovery_mapping(
                    commitment.get("recovery_config"),
                    f"D2 online JSONL line {line_number} recovery config",
                )
                if (
                    not recovery_config
                    or dict(recovery_config) != dict(expected_config)
                ):
                    _identity_recovery_config_error(
                        "identity_recovery_config_online_record_drift",
                        "D2 identity recovery config changed within the episode",
                    )
                try:
                    _canonical_payload_sha256(recovery_config)
                except (TypeError, ValueError) as exc:
                    raise _IdentityRecoveryConfigValidationError(
                        "identity_recovery_config_online_record_non_canonical",
                        "D2 online recovery config is not canonical JSON",
                    ) from exc
                count += 1
    except (OSError, UnicodeError) as exc:
        raise _IdentityRecoveryConfigValidationError(
            "identity_recovery_config_online_d2_records_unreadable",
            "D2 online records JSONL cannot be read",
        ) from exc
    if count == 0:
        _identity_recovery_config_error(
            "identity_recovery_config_online_d2_records_empty",
            "D2 online records JSONL is empty",
        )
    return count


def _identity_recovery_mapping(
    value: Any,
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _identity_recovery_config_error(
            "identity_recovery_config_online_record_missing_fields",
            f"{context} must be a mapping",
        )
    return value


def _identity_recovery_positive_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _identity_recovery_config_error(
            "identity_recovery_config_record_count_invalid",
            f"{context} must be a positive integer",
        )
    return value


def _identity_recovery_config_error(reason: str, message: str) -> None:
    raise _IdentityRecoveryConfigValidationError(reason, message)


def _adapt_d2_partial_identity_diagnostics(
    raw: Any,
    *,
    identity_payload: Mapping[str, Any],
    identity_source: object | Mapping[str, Any] | str | Path,
    identity_evaluation_sha256: str | None,
    identity_manifest: object | Mapping[str, Any] | str | Path | None,
    expected_identity_manifest_sha256: str | None,
    source_hashes: Mapping[str, str],
    strict_metrics: Mapping[str, PublicMetricEvidence],
    strict_truth_metrics_available: bool,
    strict_evaluated_frame_count: int,
    audit: Mapping[str, Any],
    configuration: Mapping[str, Any],
) -> D2PartialIdentityDiagnosticsRecord:
    if raw is None:
        return _unavailable_d2_partial_identity(
            "partial_identity_diagnostics_missing"
        )
    if not isinstance(raw, Mapping):
        return _unavailable_d2_partial_identity(
            "partial_identity_diagnostics_invalid_type"
        )

    producer_schema = (
        None
        if raw.get("schema_version") is None
        else str(raw.get("schema_version"))
    )
    manifest_schema: str | None = None
    manifest_sha: str | None = None
    verification_mode = "partial_payload_validation_failed"
    try:
        counts, metrics, anchor_reasons, excluded_reasons = (
            _validate_d2_partial_identity_payload(
                raw,
                strict_metrics=strict_metrics,
                strict_evaluated_frame_count=strict_evaluated_frame_count,
                audit=audit,
                configuration=configuration,
            )
        )
        manifest_payload, manifest_sha, verification_mode = (
            _load_d2_partial_identity_manifest(
                identity_source=identity_source,
                identity_manifest=identity_manifest,
                expected_sha256=expected_identity_manifest_sha256,
            )
        )
        manifest_schema = (
            None
            if manifest_payload.get("schema_version") is None
            else str(manifest_payload.get("schema_version"))
        )
        _validate_d2_partial_identity_manifest(
            manifest_payload,
            identity_payload=identity_payload,
            identity_evaluation_sha256=identity_evaluation_sha256,
            source_hashes=source_hashes,
            strict_truth_metrics_available=strict_truth_metrics_available,
        )
    except _PartialIdentityValidationError as exc:
        return _unavailable_d2_partial_identity(
            exc.reason,
            producer_schema_version=producer_schema,
            identity_manifest_schema_version=manifest_schema,
            identity_manifest_sha256=manifest_sha,
            identity_evaluation_sha256=identity_evaluation_sha256,
            verification_mode=verification_mode,
        )

    return D2PartialIdentityDiagnosticsRecord(
        available=True,
        unavailable_reason=None,
        metrics=metrics,
        counts=counts,
        lower_bound_anchor_exclusion_reason_counts=anchor_reasons,
        excluded_scored_mapping_reason_counts=excluded_reasons,
        producer_schema_version=producer_schema,
        identity_manifest_schema_version=manifest_schema,
        identity_manifest_sha256=manifest_sha,
        identity_evaluation_sha256=identity_evaluation_sha256,
        provenance_verified=True,
        verification_mode=verification_mode,
    )


def _validate_d2_partial_identity_payload(
    payload: Mapping[str, Any],
    *,
    strict_metrics: Mapping[str, PublicMetricEvidence],
    strict_evaluated_frame_count: int,
    audit: Mapping[str, Any],
    configuration: Mapping[str, Any],
) -> tuple[
    dict[str, int],
    dict[str, PublicMetricEvidence],
    dict[str, int],
    dict[str, int],
]:
    schema = payload.get("schema_version")
    if schema != D2_SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION:
        _partial_identity_error(
            "unsupported_partial_identity_diagnostics_schema",
            "D2 partial identity diagnostics schema is unsupported",
        )
    missing = _D2_PARTIAL_PAYLOAD_KEYS - set(payload)
    if missing:
        _partial_identity_error(
            "partial_identity_diagnostics_missing_fields",
            "D2 partial identity diagnostics are missing required fields",
        )
    unexpected = set(payload) - _D2_PARTIAL_PAYLOAD_KEYS
    if unexpected:
        _partial_identity_error(
            "partial_identity_diagnostics_unexpected_fields",
            "D2 partial identity diagnostics contain unsupported fields",
        )
    if payload.get("scope") != "offline_lineage_truth_sidecar_only":
        _partial_identity_error(
            "partial_identity_diagnostics_invalid_scope",
            "D2 partial identity diagnostics are not evaluator-only",
        )
    definitions = payload.get("denominator_definitions")
    if (
        not isinstance(definitions, Mapping)
        or dict(definitions) != D2_PARTIAL_IDENTITY_DENOMINATOR_DEFINITIONS
    ):
        _partial_identity_error(
            "partial_identity_denominator_policy_mismatch",
            "D2 partial identity denominator definitions do not match policy",
        )

    counts = {
        name: _partial_nonnegative_int(payload.get(name), name)
        for name in _D2_PARTIAL_COUNT_NAMES
    }
    if (
        counts["available_mapping_count"]
        + counts["ambiguous_mapping_count"]
        + counts["unavailable_mapping_count"]
        != counts["total_mapping_count"]
    ):
        _partial_count_conservation_error("mapping status counts")
    if (
        counts["scored_mapping_count"] + counts["non_scored_mapping_count"]
        != counts["total_mapping_count"]
    ):
        _partial_count_conservation_error("scored mapping counts")
    if (
        counts["evaluable_mapping_count"]
        + counts["ambiguous_scored_mapping_count"]
        + counts["unavailable_scored_mapping_count"]
        + counts["mapped_truth_not_present_mapping_count"]
        != counts["scored_mapping_count"]
    ):
        _partial_count_conservation_error("scored mapping categories")
    if counts["missing_identity_evidence_mapping_count"] > (
        counts["ambiguous_scored_mapping_count"]
        + counts["unavailable_scored_mapping_count"]
    ):
        _partial_count_conservation_error("missing identity evidence mappings")
    if counts["evaluable_frame_count"] > counts["evaluated_frame_count"]:
        _partial_count_conservation_error("evaluable frame count")
    if (
        counts["evaluable_transition_count"]
        > counts["transition_opportunity_count"]
        or counts["lower_bound_anchor_transition_count"]
        > counts["transition_opportunity_count"]
    ):
        _partial_count_conservation_error("identity transition counts")

    anchor_reasons = _partial_count_mapping(
        payload.get("lower_bound_anchor_exclusion_reason_counts"),
        "lower_bound anchor exclusion reasons",
    )
    if set(anchor_reasons) - {
        "multiple_evaluable_global_tracks_for_truth_frame"
    }:
        _partial_identity_error(
            "partial_identity_exclusion_reason_unsupported",
            "D2 partial identity anchor exclusion reason is unsupported",
        )
    if sum(anchor_reasons.values()) != counts[
        "lower_bound_anchor_excluded_truth_frame_count"
    ]:
        _partial_count_conservation_error("anchor exclusion reasons")
    excluded_reasons = _partial_count_mapping(
        payload.get("excluded_scored_mapping_reason_counts"),
        "excluded scored mapping reasons",
    )

    metrics = {
        "evaluable_mapping_coverage": _partial_coverage_metric(
            payload,
            source_name="evaluable_mapping_coverage",
            numerator=counts["evaluable_mapping_count"],
            denominator=counts["scored_mapping_count"],
            zero_reason="no_scored_identity_mappings",
        ),
        "evaluable_frame_coverage": _partial_coverage_metric(
            payload,
            source_name="evaluable_frame_coverage",
            numerator=counts["evaluable_frame_count"],
            denominator=counts["evaluated_frame_count"],
            zero_reason="no_evaluated_identity_frames",
        ),
        "adjacent_transition_coverage": _partial_coverage_metric(
            payload,
            source_name="evaluable_transition_coverage",
            numerator=counts["evaluable_transition_count"],
            denominator=counts["transition_opportunity_count"],
            zero_reason="no_truth_presence_transition_opportunities",
        ),
    }
    anchor_interval_count = counts["lower_bound_anchor_transition_count"]
    metrics["anchor_interval_count"] = PublicMetricEvidence(
        value=anchor_interval_count,
        available=True,
        sample_count=anchor_interval_count,
    )
    metrics["id_switch_lower_bound"] = _partial_lower_bound_metric(
        payload,
        anchor_interval_count=anchor_interval_count,
    )
    strict_id_switch = strict_metrics["id_switch_count"]
    lower_bound = metrics["id_switch_lower_bound"]
    if (
        strict_id_switch.available
        and lower_bound.available
        and int(lower_bound.value) > int(strict_id_switch.value)
    ):
        _partial_identity_error(
            "partial_identity_lower_bound_exceeds_strict_id_switch_count",
            "D2 ID-switch lower bound exceeds the available strict count",
        )

    upper_bound = payload.get("id_switch_upper_bound")
    if isinstance(upper_bound, float) and not math.isfinite(upper_bound):
        _partial_identity_error(
            "partial_identity_diagnostics_non_finite_value",
            "D2 partial identity upper bound contains a non-finite value",
        )
    if (
        upper_bound is not None
        or payload.get("id_switch_upper_bound_available") is not False
        or payload.get("id_switch_upper_bound_reason")
        != "not_provided_incomplete_identity_evidence"
    ):
        _partial_identity_error(
            "partial_identity_upper_bound_forbidden",
            "D2 partial identity diagnostics must not publish an upper bound",
        )

    if counts["evaluated_frame_count"] != strict_evaluated_frame_count:
        _partial_identity_error(
            "partial_identity_evaluated_frame_count_mismatch",
            "D2 partial and strict evaluated frame counts differ",
        )
    if (
        configuration.get("partial_identity_diagnostic_contract")
        != D2_SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION
    ):
        _partial_identity_error(
            "partial_identity_configuration_binding_mismatch",
            "D2 partial identity configuration contract is not bound",
        )
    if (
        audit.get("partial_identity_diagnostics_available") is not True
        or audit.get("partial_identity_diagnostics_schema_version")
        != D2_SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION
    ):
        _partial_identity_error(
            "partial_identity_audit_binding_mismatch",
            "D2 partial identity audit contract is not bound",
        )
    if (
        audit.get("online_truth_isolation_verified") is not True
        or audit.get("source_verification")
        != "raw_source_hashes_and_record_sequences_verified"
        or audit.get("identity_heuristics_used") is not False
    ):
        _partial_identity_error(
            "partial_identity_truth_isolation_not_verified",
            "D2 partial identity evaluator-only isolation is not verified",
        )
    direct_audit_count_bindings = {
        "evaluated_frame_count": "evaluated_frame_count",
        "available_mapping_count": "available_mapping_count",
        "ambiguous_mapping_count": "ambiguous_mapping_count",
    }
    for audit_name, count_name in direct_audit_count_bindings.items():
        try:
            audit_count = _partial_nonnegative_int(
                audit.get(audit_name),
                f"audit {audit_name}",
            )
        except _PartialIdentityValidationError:
            _partial_identity_error(
                "partial_identity_audit_binding_mismatch",
                "D2 partial identity audit count is missing or invalid",
            )
        if audit_count != counts[count_name]:
            _partial_identity_error(
                "partial_identity_audit_binding_mismatch",
                "D2 partial identity audit counts contradict diagnostics",
            )

    audit_unavailable_categories: dict[str, int] = {}
    for audit_name in (
        "unavailable_mapping_count",
        "excluded_mapping_count",
        "uncommitted_mapping_count",
    ):
        raw_count = audit.get(audit_name)
        if raw_count is None and audit_name != "unavailable_mapping_count":
            audit_unavailable_categories[audit_name] = 0
            continue
        try:
            audit_unavailable_categories[audit_name] = (
                _partial_nonnegative_int(
                    raw_count,
                    f"audit {audit_name}",
                )
            )
        except _PartialIdentityValidationError:
            _partial_identity_error(
                "partial_identity_audit_binding_mismatch",
                "D2 partial identity audit count is missing or invalid",
            )

    partial_unavailable_count = sum(audit_unavailable_categories.values())
    if partial_unavailable_count != counts["unavailable_mapping_count"]:
        _partial_identity_error(
            "partial_identity_audit_binding_mismatch",
            "D2 partial identity unavailable categories contradict diagnostics",
        )
    if (
        counts["available_mapping_count"]
        + counts["ambiguous_mapping_count"]
        + partial_unavailable_count
        != counts["total_mapping_count"]
    ):
        _partial_identity_error(
            "partial_identity_audit_binding_mismatch",
            "D2 partial identity audit categories do not cover all mappings",
        )
    return counts, metrics, anchor_reasons, excluded_reasons


def _partial_coverage_metric(
    payload: Mapping[str, Any],
    *,
    source_name: str,
    numerator: int,
    denominator: int,
    zero_reason: str,
) -> PublicMetricEvidence:
    available = payload.get(f"{source_name}_available")
    if not isinstance(available, bool):
        _partial_identity_error(
            "partial_identity_coverage_availability_invalid",
            f"{source_name} availability must be boolean",
        )
    value = payload.get(source_name)
    reason = _partial_optional_reason(payload.get(f"{source_name}_reason"))
    if denominator == 0:
        if value is not None or available or reason != zero_reason:
            _partial_identity_error(
                "partial_identity_coverage_inconsistent",
                f"{source_name} must be unavailable for a zero denominator",
            )
        return PublicMetricEvidence(
            value=None,
            available=False,
            sample_count=0,
            unavailable_reason=reason,
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _partial_identity_error(
            "partial_identity_coverage_value_invalid",
            f"{source_name} must be numeric",
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _partial_identity_error(
            "partial_identity_diagnostics_non_finite_value",
            f"{source_name} must be finite",
        )
    expected = numerator / denominator
    if (
        not available
        or reason is not None
        or not 0.0 <= normalized <= 1.0
        or abs(normalized - expected) > 1.0e-12
    ):
        _partial_identity_error(
            "partial_identity_coverage_inconsistent",
            f"{source_name} contradicts its numerator or denominator",
        )
    return PublicMetricEvidence(
        value=normalized,
        available=True,
        sample_count=denominator,
    )


def _partial_lower_bound_metric(
    payload: Mapping[str, Any],
    *,
    anchor_interval_count: int,
) -> PublicMetricEvidence:
    available = payload.get("id_switch_lower_bound_available")
    if not isinstance(available, bool):
        _partial_identity_error(
            "partial_identity_lower_bound_availability_invalid",
            "D2 ID-switch lower-bound availability must be boolean",
        )
    value = payload.get("id_switch_lower_bound")
    reason = _partial_optional_reason(
        payload.get("id_switch_lower_bound_reason")
    )
    if anchor_interval_count == 0:
        if (
            value is not None
            or available
            or reason != "no_evaluable_identity_transitions"
        ):
            _partial_identity_error(
                "partial_identity_lower_bound_inconsistent",
                "D2 ID-switch lower bound requires an anchor interval",
            )
        return PublicMetricEvidence(
            value=None,
            available=False,
            sample_count=0,
            unavailable_reason=reason,
        )
    lower_bound = _partial_nonnegative_int(value, "id_switch_lower_bound")
    if (
        not available
        or reason is not None
        or lower_bound > anchor_interval_count
    ):
        _partial_identity_error(
            "partial_identity_lower_bound_inconsistent",
            "D2 ID-switch lower bound exceeds its anchor intervals",
        )
    return PublicMetricEvidence(
        value=lower_bound,
        available=True,
        sample_count=anchor_interval_count,
    )


def _load_d2_partial_identity_manifest(
    *,
    identity_source: object | Mapping[str, Any] | str | Path,
    identity_manifest: object | Mapping[str, Any] | str | Path | None,
    expected_sha256: str | None,
) -> tuple[dict[str, Any], str, str]:
    selected = identity_manifest
    mode = "explicit_identity_manifest"
    if selected is None and isinstance(identity_source, (str, Path)):
        candidate = Path(identity_source).parent / "manifest.json"
        if candidate.is_file():
            selected = candidate
            mode = "sibling_identity_manifest"
    if selected is None:
        _partial_identity_error(
            "d2_identity_manifest_missing",
            "D2 identity manifest is required for partial diagnostics",
        )

    if isinstance(selected, (str, Path)):
        path = Path(selected)
        try:
            manifest_sha = _sha256_file(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise _PartialIdentityValidationError(
                "d2_identity_manifest_unreadable",
                "D2 identity manifest cannot be loaded",
            ) from exc
        if not isinstance(payload, Mapping):
            _partial_identity_error(
                "d2_identity_manifest_invalid_type",
                "D2 identity manifest must be a mapping",
            )
        verification_mode = f"{mode}_sha256_bound"
    else:
        if isinstance(selected, Mapping):
            payload = dict(selected)
        else:
            to_dict = getattr(selected, "to_dict", None)
            if not callable(to_dict):
                _partial_identity_error(
                    "d2_identity_manifest_invalid_type",
                    "D2 identity manifest must be a public DTO, mapping, or path",
                )
            mapped = to_dict()
            if not isinstance(mapped, Mapping):
                _partial_identity_error(
                    "d2_identity_manifest_invalid_type",
                    "D2 identity manifest DTO must return a mapping",
                )
            payload = dict(mapped)
        try:
            manifest_sha = _canonical_payload_sha256(payload)
        except (TypeError, ValueError) as exc:
            raise _PartialIdentityValidationError(
                "d2_identity_manifest_non_canonical",
                "D2 identity manifest is not canonically hashable",
            ) from exc
        verification_mode = "canonical_identity_manifest_bound"

    if expected_sha256 is not None:
        try:
            expected = _normalized_sha256(expected_sha256)
        except TruthIsolatedEvaluationError as exc:
            raise _PartialIdentityValidationError(
                "d2_identity_manifest_sha256_invalid",
                "D2 identity manifest expected SHA-256 is invalid",
            ) from exc
        if manifest_sha != expected:
            _partial_identity_error(
                "d2_identity_manifest_sha256_mismatch",
                "D2 identity manifest SHA-256 does not match",
            )
    return dict(payload), manifest_sha, verification_mode


def _validate_d2_partial_identity_manifest(
    manifest: Mapping[str, Any],
    *,
    identity_payload: Mapping[str, Any],
    identity_evaluation_sha256: str | None,
    source_hashes: Mapping[str, str],
    strict_truth_metrics_available: bool,
) -> None:
    if (
        manifest.get("schema_version")
        not in D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSIONS
    ):
        _partial_identity_error(
            "unsupported_d2_identity_manifest_schema",
            "D2 identity manifest schema is unsupported",
        )
    if (
        manifest.get("available") is not True
        or manifest.get("reason") is not None
    ):
        _partial_identity_error(
            "d2_identity_manifest_unavailable",
            "D2 identity manifest is unavailable",
        )
    if manifest.get("episode_id") != identity_payload.get("episode_id"):
        _partial_identity_error(
            "d2_identity_manifest_episode_mismatch",
            "D2 identity manifest episode does not match evaluation",
        )
    if manifest.get("online_truth_isolation_verified") is not True:
        _partial_identity_error(
            "d2_identity_manifest_truth_isolation_not_verified",
            "D2 identity manifest did not verify truth isolation",
        )
    if (
        not isinstance(manifest.get("identity_metrics_available"), bool)
        or manifest.get("identity_metrics_available")
        is not strict_truth_metrics_available
    ):
        _partial_identity_error(
            "d2_identity_manifest_metric_availability_mismatch",
            "D2 identity manifest strict metric availability is inconsistent",
        )
    manifest_hashes = manifest.get("source_hashes")
    if not isinstance(manifest_hashes, Mapping):
        _partial_identity_error(
            "d2_identity_manifest_source_hashes_missing",
            "D2 identity manifest source hashes are missing",
        )
    if identity_evaluation_sha256 is None:
        _partial_identity_error(
            "d2_identity_evaluation_sha256_unavailable",
            "D2 identity evaluation SHA-256 cannot be bound",
        )
    try:
        evaluation_manifest_hash = _normalized_sha256(
            manifest_hashes.get("identity_evaluation")
        )
    except TruthIsolatedEvaluationError as exc:
        raise _PartialIdentityValidationError(
            "d2_identity_manifest_source_hash_invalid",
            "D2 identity manifest evaluation SHA-256 is invalid",
        ) from exc
    if evaluation_manifest_hash != identity_evaluation_sha256:
        _partial_identity_error(
            "d2_identity_manifest_evaluation_sha256_mismatch",
            "D2 identity manifest does not bind the evaluation artifact",
        )
    source_bindings = {
        "online_d1_records": "online_d1_records",
        "online_d2_records": "online_d2_records",
        "observation_truth_labels": "observation_truth_labels",
        "identity_evidence_bundle": "identity_evidence",
    }
    for evaluation_name, manifest_name in source_bindings.items():
        try:
            manifest_hash = _normalized_sha256(
                manifest_hashes.get(manifest_name)
            )
        except TruthIsolatedEvaluationError as exc:
            raise _PartialIdentityValidationError(
                "d2_identity_manifest_source_hash_invalid",
                f"D2 identity manifest source SHA-256 is invalid: {manifest_name}",
            ) from exc
        if manifest_hash != source_hashes[evaluation_name]:
            _partial_identity_error(
                "d2_identity_manifest_source_hash_mismatch",
                f"D2 identity manifest source hash mismatch: {manifest_name}",
            )


def _partial_nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, float) and not math.isfinite(value):
        _partial_identity_error(
            "partial_identity_diagnostics_non_finite_value",
            f"{name} must be finite",
        )
    if isinstance(value, bool) or not isinstance(value, int):
        _partial_identity_error(
            "partial_identity_diagnostics_invalid_count",
            f"{name} must be an integer",
        )
    if value < 0:
        _partial_identity_error(
            "partial_identity_diagnostics_invalid_count",
            f"{name} must be non-negative",
        )
    return value


def _partial_count_mapping(value: Any, name: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        _partial_identity_error(
            "partial_identity_diagnostics_invalid_count_mapping",
            f"{name} must be a mapping",
        )
    output: dict[str, int] = {}
    for key, raw in value.items():
        identifier = str(key).strip()
        if not identifier:
            _partial_identity_error(
                "partial_identity_diagnostics_invalid_count_mapping",
                f"{name} keys must be non-empty",
            )
        output[identifier] = _partial_nonnegative_int(raw, f"{name} count")
    return dict(sorted(output.items()))


def _partial_optional_reason(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _partial_identity_error(
            "partial_identity_diagnostics_invalid_reason",
            "D2 partial identity reason must be a non-empty string or null",
        )
    return value.strip()


def _partial_count_conservation_error(name: str) -> None:
    _partial_identity_error(
        "partial_identity_count_conservation_failed",
        f"D2 partial identity {name} do not conserve counts",
    )


def _partial_identity_error(reason: str, message: str) -> None:
    raise _PartialIdentityValidationError(reason, message)


def _unavailable_d2_partial_identity(
    reason: str,
    *,
    producer_schema_version: str | None = None,
    identity_manifest_schema_version: str | None = None,
    identity_manifest_sha256: str | None = None,
    identity_evaluation_sha256: str | None = None,
    verification_mode: str = "unavailable",
) -> D2PartialIdentityDiagnosticsRecord:
    return D2PartialIdentityDiagnosticsRecord(
        available=False,
        unavailable_reason=reason,
        metrics={
            name: _unavailable_metric(reason)
            for name in _D2_PARTIAL_METRIC_NAMES
        },
        counts={},
        lower_bound_anchor_exclusion_reason_counts={},
        excluded_scored_mapping_reason_counts={},
        producer_schema_version=producer_schema_version,
        identity_manifest_schema_version=identity_manifest_schema_version,
        identity_manifest_sha256=identity_manifest_sha256,
        identity_evaluation_sha256=identity_evaluation_sha256,
        provenance_verified=False,
        verification_mode=verification_mode,
    )


def _unavailable_d2_identity_commitment(
    reason: str,
    *,
    producer_evaluation_schema_version: str | None = None,
    producer_evaluation_policy_version: str | None = None,
) -> D2IdentityCommitmentEvidenceRecord:
    return D2IdentityCommitmentEvidenceRecord(
        available=False,
        unavailable_reason=reason,
        metrics={
            name: _unavailable_metric(reason)
            for name in _D2_COMMITMENT_METRIC_NAMES
        },
        state_counts={},
        reason_counts={},
        recovery_blocked_reason_counts={},
        denominator_policy=None,
        uncommitted_binding_violation_policy=None,
        committed_anchor_across_uncommitted_gap_policy=None,
        producer_evaluation_schema_version=(
            producer_evaluation_schema_version
        ),
        producer_evaluation_policy_version=(
            producer_evaluation_policy_version
        ),
        producer_evidence_schema_version=None,
        producer_commitment_schema_version=None,
        producer_commitment_policy_version=None,
        producer_audit_schema_version=None,
        evidence_bundle_sha256_verified=False,
    )


def _unavailable_d2_identity_recovery_config(
    reason: str,
    *,
    identity_manifest_schema_version: str | None = None,
    identity_manifest_sha256: str | None = None,
    online_d2_records_sha256: str | None = None,
    verification_mode: str = "unavailable",
) -> D2IdentityRecoveryConfigProvenanceRecord:
    return D2IdentityRecoveryConfigProvenanceRecord(
        available=False,
        unavailable_reason=reason,
        config_snapshot=None,
        config_sha256=None,
        config_schema_version=None,
        config_version=None,
        identity_manifest_schema_version=identity_manifest_schema_version,
        identity_manifest_sha256=identity_manifest_sha256,
        online_d2_records_sha256=online_d2_records_sha256,
        config_record_count=None,
        d2_record_count=None,
        consistency_verified=False,
        source=None,
        online_records_verified=False,
        verification_mode=verification_mode,
    )


def _missing_d1_record(
    context: TruthIsolatedEpisodeContext,
) -> D1ConsistencyEvaluationRecord:
    reason = "d1_offline_consistency_artifact_missing"
    return D1ConsistencyEvaluationRecord(
        scenario_id=context.scenario_id,
        scenario_version=context.scenario_version,
        run_id=context.run_id,
        seed=context.seed,
        status="unavailable",
        metrics={name: _unavailable_metric(reason) for name in _D1_METRIC_NAMES},
        sensor_range_records=(),
        artifact_digest=None,
        external_file_sha256=None,
        input_digests={
            "online_evidence": None,
            "truth_sidecar": None,
            "d2_lineage_mapping": None,
        },
        failure_reasons=(reason,),
        verification_mode="artifact_missing",
    )


def _missing_d2_record(
    context: TruthIsolatedEpisodeContext,
) -> D2IdentityEvaluationRecord:
    reason = "d2_identity_evaluation_artifact_missing"
    return D2IdentityEvaluationRecord(
        episode_id=context.episode_id,
        producer_schema_version=None,
        producer_policy_version=None,
        metrics={name: _unavailable_metric(reason) for name in _D2_METRIC_NAMES},
        evaluated_frame_count=0,
        truth_frame_count={},
        truth_assigned_frame_count={},
        truth_identity_stable_frame_count={},
        confusion_matrix=None,
        source_hashes={},
        artifact_digest=None,
        external_file_sha256=None,
        truth_isolation_verified=False,
        truth_metric_evidence_verified=False,
        truth_metric_evidence_reason=reason,
        source_verification="artifact_missing",
        configuration={},
        audit={},
        identity_commitment=_unavailable_d2_identity_commitment(reason),
        identity_recovery_config_provenance=(
            _unavailable_d2_identity_recovery_config(reason)
        ),
        partial_identity_diagnostics=_unavailable_d2_partial_identity(
            reason
        ),
        verification_mode="artifact_missing",
    )


def _validate_context_alignment(
    context: TruthIsolatedEpisodeContext,
    d1: D1ConsistencyEvaluationRecord,
    d2: D2IdentityEvaluationRecord,
) -> None:
    expected_d1 = (
        context.scenario_id,
        context.scenario_version,
        context.run_id,
        context.seed,
    )
    actual_d1 = (d1.scenario_id, d1.scenario_version, d1.run_id, d1.seed)
    if actual_d1 != expected_d1:
        raise TruthIsolatedEvaluationError(
            "D1 consistency provenance does not match episode context"
        )
    if d2.episode_id != context.episode_id:
        raise TruthIsolatedEvaluationError(
            "D2 identity episode_id does not match episode context"
        )


def _aggregate_metric(
    items: Sequence[tuple[int, PublicMetricEvidence]],
    *,
    metric_name: str,
    group_identity: Mapping[str, Any],
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
) -> dict[str, Any]:
    seed_values: dict[int, list[float]] = defaultdict(list)
    sample_count = 0
    reasons: Counter[str] = Counter()
    for seed, metric in items:
        sample_count += metric.sample_count
        if metric.available and metric.value is not None:
            seed_values[int(seed)].append(float(metric.value))
        else:
            reasons[metric.unavailable_reason or "reason_unavailable"] += 1
    if not seed_values:
        return {
            "availability": "unavailable",
            "unavailable_reason": "no_available_seed_values",
            "unavailability_reason_distribution": dict(sorted(reasons.items())),
            "episode_value_count": 0,
            "seed_value_count": 0,
            "total_sample_count": sample_count,
            "mean": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
            "sum": None,
            "bootstrap_ci95_low": None,
            "bootstrap_ci95_high": None,
            "bootstrap_availability": "unavailable",
            "bootstrap_unavailable_reason": "no_available_seed_values",
        }
    seed_means = np.asarray(
        [float(np.mean(seed_values[seed])) for seed in sorted(seed_values)],
        dtype=float,
    )
    episode_values = [
        value
        for values in seed_values.values()
        for value in values
    ]
    if len(seed_means) >= 2:
        material = json.dumps(
            {"group": group_identity, "metric": metric_name},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        offset = int.from_bytes(hashlib.sha256(material).digest()[:4], "big")
        rng = np.random.default_rng(
            (int(bootstrap_rng_seed) + offset) % (2**32)
        )
        indices = rng.integers(
            0,
            len(seed_means),
            size=(int(bootstrap_resamples), len(seed_means)),
        )
        means = np.mean(seed_means[indices], axis=1)
        low = float(np.percentile(means, 2.5))
        high = float(np.percentile(means, 97.5))
        bootstrap_availability = "available"
        bootstrap_reason = None
    else:
        low = high = None
        bootstrap_availability = "unavailable"
        bootstrap_reason = "single_seed_descriptive_only"
    return {
        "availability": "available",
        "unavailable_reason": None,
        "unavailability_reason_distribution": dict(sorted(reasons.items())),
        "episode_value_count": len(episode_values),
        "seed_value_count": len(seed_means),
        "total_sample_count": sample_count,
        "mean": float(np.mean(seed_means)),
        "standard_deviation": float(np.std(seed_means, ddof=0)),
        "minimum": float(np.min(seed_means)),
        "maximum": float(np.max(seed_means)),
        "sum": float(np.sum(seed_means)),
        "bootstrap_ci95_low": low,
        "bootstrap_ci95_high": high,
        "bootstrap_availability": bootstrap_availability,
        "bootstrap_unavailable_reason": bootstrap_reason,
        "bootstrap_resamples": int(bootstrap_resamples),
        "bootstrap_rng_seed": int(bootstrap_rng_seed),
    }


def _episode_source_provenance(
    record: TruthIsolatedEpisodeEvaluationRecord,
) -> dict[str, Any]:
    return {
        "episode_id": record.context.episode_id,
        "seed": record.context.seed,
        "d1_artifact_digest": record.d1.artifact_digest,
        "d1_external_file_sha256": record.d1.external_file_sha256,
        "d1_input_digests": dict(record.d1.input_digests),
        "d1_verification_mode": record.d1.verification_mode,
        "d2_artifact_digest": record.d2.artifact_digest,
        "d2_external_file_sha256": record.d2.external_file_sha256,
        "d2_source_hashes": dict(record.d2.source_hashes),
        "d2_verification_mode": record.d2.verification_mode,
        "d2_source_verification": record.d2.source_verification,
        "d2_truth_isolation_verified": record.d2.truth_isolation_verified,
        "d2_truth_metric_evidence_verified": (
            record.d2.truth_metric_evidence_verified
        ),
        "d2_truth_metric_evidence_reason": (
            record.d2.truth_metric_evidence_reason
        ),
        "d2_producer_schema_version": record.d2.producer_schema_version,
        "d2_producer_policy_version": record.d2.producer_policy_version,
        "d2_identity_commitment": {
            "availability": (
                "available"
                if record.d2.identity_commitment.available
                else "unavailable"
            ),
            "unavailable_reason": (
                record.d2.identity_commitment.unavailable_reason
            ),
            "producer_evidence_schema_version": (
                record.d2.identity_commitment.producer_evidence_schema_version
            ),
            "producer_commitment_schema_version": (
                record.d2.identity_commitment.producer_commitment_schema_version
            ),
            "producer_audit_schema_version": (
                record.d2.identity_commitment.producer_audit_schema_version
            ),
            "evidence_bundle_sha256_verified": (
                record.d2.identity_commitment.evidence_bundle_sha256_verified
            ),
        },
        "d2_identity_recovery_config_provenance": (
            record.d2.identity_recovery_config_provenance.to_dict()
        ),
        "d2_partial_identity_diagnostics": {
            "availability": (
                "available"
                if record.d2.partial_identity_diagnostics.available
                else "unavailable"
            ),
            "unavailable_reason": (
                record.d2.partial_identity_diagnostics.unavailable_reason
            ),
            "producer_schema_version": (
                record.d2.partial_identity_diagnostics.producer_schema_version
            ),
            "identity_manifest_schema_version": (
                record.d2.partial_identity_diagnostics.identity_manifest_schema_version
            ),
            "identity_manifest_sha256": (
                record.d2.partial_identity_diagnostics.identity_manifest_sha256
            ),
            "identity_evaluation_sha256": (
                record.d2.partial_identity_diagnostics.identity_evaluation_sha256
            ),
            "provenance_verified": (
                record.d2.partial_identity_diagnostics.provenance_verified
            ),
        },
    }


def _episode_csv_row(record: TruthIsolatedEpisodeEvaluationRecord) -> dict[str, Any]:
    disposition = record.d2.audit.get(
        "d6_observation_truth_disposition_acceptance",
        {},
    )
    if not isinstance(disposition, Mapping):
        disposition = {}
    row = {
        **record.context.to_dict(),
        "schema_version": record.schema_version,
        "d1_status": record.d1.status,
        "d1_artifact_digest": record.d1.artifact_digest,
        "d1_external_file_sha256": record.d1.external_file_sha256,
        "d1_verification_mode": record.d1.verification_mode,
        "d1_input_digests_json": record.d1.input_digests,
        "d2_artifact_digest": record.d2.artifact_digest,
        "d2_external_file_sha256": record.d2.external_file_sha256,
        "d2_verification_mode": record.d2.verification_mode,
        "d2_truth_isolation_verified": record.d2.truth_isolation_verified,
        "d2_truth_metric_evidence_verified": (
            record.d2.truth_metric_evidence_verified
        ),
        "d2_truth_metric_evidence_reason": (
            record.d2.truth_metric_evidence_reason
        ),
        "d2_source_verification": record.d2.source_verification,
        "d2_producer_schema_version": record.d2.producer_schema_version,
        "d2_producer_policy_version": record.d2.producer_policy_version,
        "d2_source_hashes_json": record.d2.source_hashes,
        "d2_confusion_matrix_json": record.d2.confusion_matrix,
        "d2_truth_frame_count_json": record.d2.truth_frame_count,
        "d2_truth_assigned_frame_count_json": record.d2.truth_assigned_frame_count,
        "d2_truth_identity_stable_frame_count_json": (
            record.d2.truth_identity_stable_frame_count
        ),
        "d2_partial_identity_availability": (
            "available"
            if record.d2.partial_identity_diagnostics.available
            else "unavailable"
        ),
        "d2_partial_identity_unavailable_reason": (
            record.d2.partial_identity_diagnostics.unavailable_reason
        ),
        "d2_partial_identity_provenance_verified": (
            record.d2.partial_identity_diagnostics.provenance_verified
        ),
        "d2_partial_identity_manifest_sha256": (
            record.d2.partial_identity_diagnostics.identity_manifest_sha256
        ),
        "d2_partial_identity_counts_json": (
            record.d2.partial_identity_diagnostics.counts
        ),
        "d2_partial_identity_anchor_exclusion_reasons_json": (
            record.d2.partial_identity_diagnostics.lower_bound_anchor_exclusion_reason_counts
        ),
        "d2_partial_identity_excluded_mapping_reasons_json": (
            record.d2.partial_identity_diagnostics.excluded_scored_mapping_reason_counts
        ),
        "d2_identity_commitment_availability": (
            "available"
            if record.d2.identity_commitment.available
            else "unavailable"
        ),
        "d2_identity_commitment_unavailable_reason": (
            record.d2.identity_commitment.unavailable_reason
        ),
        "d2_identity_commitment_evidence_bundle_sha256_verified": (
            record.d2.identity_commitment.evidence_bundle_sha256_verified
        ),
        "d2_identity_commitment_state_counts_json": (
            record.d2.identity_commitment.state_counts
        ),
        "d2_identity_commitment_reason_counts_json": (
            record.d2.identity_commitment.reason_counts
        ),
        "d2_identity_commitment_recovery_blocked_reason_counts_json": (
            record.d2.identity_commitment.recovery_blocked_reason_counts
        ),
        "d2_identity_recovery_config_availability": (
            "available"
            if record.d2.identity_recovery_config_provenance.available
            else "unavailable"
        ),
        "d2_identity_recovery_config_unavailable_reason": (
            record.d2.identity_recovery_config_provenance.unavailable_reason
        ),
        "d2_identity_recovery_config_json": (
            record.d2.identity_recovery_config_provenance.config_snapshot
        ),
        "d2_identity_recovery_config_sha256": (
            record.d2.identity_recovery_config_provenance.config_sha256
        ),
        "d2_identity_recovery_config_manifest_schema": (
            record.d2.identity_recovery_config_provenance.identity_manifest_schema_version
        ),
        "d2_identity_recovery_config_manifest_sha256": (
            record.d2.identity_recovery_config_provenance.identity_manifest_sha256
        ),
        "d2_identity_recovery_config_online_d2_records_sha256": (
            record.d2.identity_recovery_config_provenance.online_d2_records_sha256
        ),
        "d2_identity_recovery_config_record_count": (
            record.d2.identity_recovery_config_provenance.config_record_count
        ),
        "d2_identity_recovery_config_d2_record_count": (
            record.d2.identity_recovery_config_provenance.d2_record_count
        ),
        "d2_identity_recovery_config_consistency_verified": (
            record.d2.identity_recovery_config_provenance.consistency_verified
        ),
        "d2_identity_recovery_config_online_records_verified": (
            record.d2.identity_recovery_config_provenance.online_records_verified
        ),
        "d2_identity_recovery_config_source": (
            record.d2.identity_recovery_config_provenance.source
        ),
        "d2_identity_recovery_config_verification_mode": (
            record.d2.identity_recovery_config_provenance.verification_mode
        ),
        "d2_observation_truth_disposition_availability": disposition.get(
            "availability",
            "unavailable",
        ),
        "d2_observation_truth_disposition_schema": disposition.get(
            "source_schema_version"
        ),
        "d2_observation_truth_disposition_source_sha256": disposition.get(
            "source_sha256"
        ),
        "d2_observation_truth_target_label_count": _nested_count(
            disposition,
            "target_label",
        ),
        "d2_observation_truth_known_false_alarm_count": _nested_count(
            disposition,
            "known_false_alarm",
        ),
        "d2_observation_truth_unknown_count": _nested_count(
            disposition,
            "unknown",
        ),
        "d2_observation_truth_missing_disposition_count": _nested_count(
            disposition,
            "missing_disposition",
        ),
        "d2_observation_truth_strict_id_switch_backfilled": disposition.get(
            "strict_id_switch_backfilled",
            False,
        ),
    }
    for prefix, metrics in (("d1", record.d1.metrics), ("d2", record.d2.metrics)):
        for name, metric in metrics.items():
            row[f"{prefix}_{name}"] = metric.value
            row[f"{prefix}_{name}_availability"] = (
                "available" if metric.available else "unavailable"
            )
            row[f"{prefix}_{name}_sample_count"] = metric.sample_count
            row[f"{prefix}_{name}_unavailable_reason"] = metric.unavailable_reason
    for name, metric in record.d2.partial_identity_diagnostics.metrics.items():
        column = f"d2_partial_identity_{name}"
        row[column] = metric.value
        row[f"{column}_availability"] = (
            "available" if metric.available else "unavailable"
        )
        row[f"{column}_sample_count"] = metric.sample_count
        row[f"{column}_unavailable_reason"] = metric.unavailable_reason
    for name, metric in record.d2.identity_commitment.metrics.items():
        column = f"d2_identity_commitment_{name}"
        row[column] = metric.value
        row[f"{column}_availability"] = (
            "available" if metric.available else "unavailable"
        )
        row[f"{column}_sample_count"] = metric.sample_count
        row[f"{column}_unavailable_reason"] = metric.unavailable_reason
    if "d2_id_switch_count" not in row:
        raise AssertionError("D6 must always emit explicit d2_id_switch_count")
    return row


def _nested_count(payload: Mapping[str, Any], name: str) -> int | None:
    item = payload.get(name)
    if not isinstance(item, Mapping) or item.get("availability") != "available":
        return None
    value = item.get("count")
    return (
        int(value)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def _d1_group_csv_row(
    context: TruthIsolatedEpisodeContext,
    record: D1SensorRangeConsistencyRecord,
) -> dict[str, Any]:
    row = {
        **context.to_dict(),
        "schema_version": record.schema_version,
        "sensor_id": record.sensor_id,
        "sensor_type": record.sensor_type,
        "source_sensor_type": record.source_sensor_type,
        "range_bin": record.range_bin,
        "record_count": record.record_count,
        "offline_result_digest": record.offline_result_digest,
        "input_digests_json": record.input_digests,
    }
    for name, metric in record.metrics.items():
        row[name] = metric.value
        row[f"{name}_availability"] = (
            "available" if metric.available else "unavailable"
        )
        row[f"{name}_sample_count"] = metric.sample_count
        row[f"{name}_unavailable_reason"] = metric.unavailable_reason
        row[f"{name}_unavailability_reasons_json"] = (
            metric.unavailability_reason_counts
        )
    return row


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        if not fieldnames:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: _csv_value(row.get(key))
                    for key in fieldnames
                }
            )


def _unavailable_metric(reason: str) -> PublicMetricEvidence:
    return PublicMetricEvidence(
        value=None,
        available=False,
        sample_count=0,
        unavailable_reason=str(reason),
    )


def _required_bool(
    payload: Mapping[str, Any],
    name: str,
    *,
    context: str,
) -> bool:
    if name not in payload or not isinstance(payload[name], bool):
        raise TruthIsolatedEvaluationError(
            f"{context} requires boolean {name}"
        )
    return payload[name]


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TruthIsolatedEvaluationError(f"{name} must be an integer")
    if value < 0:
        raise TruthIsolatedEvaluationError(f"{name} must be non-negative")
    return value


def _validated_d1_metric_value(name: str, value: Any) -> int | float:
    if name == "nis_within_gate":
        if not isinstance(value, bool):
            raise TruthIsolatedEvaluationError(
                "D1 nis_within_gate must be boolean"
            )
        return int(value)
    if isinstance(value, bool):
        raise TruthIsolatedEvaluationError(
            f"D1 metric {name} must be numeric"
        )
    normalized = _finite_metric_value(value)
    if normalized < 0:
        raise TruthIsolatedEvaluationError(
            f"D1 metric {name} must be non-negative"
        )
    if name == "nis_gate_coverage" and normalized > 1:
        raise TruthIsolatedEvaluationError(
            "D1 nis_gate_coverage must be in [0, 1]"
        )
    return normalized


def _validated_d2_metric_value(name: str, value: Any) -> int | float:
    if name in {"id_switch_count", "duplicate_truth_to_track_count"}:
        return _nonnegative_int(value, f"D2 metric {name}")
    if isinstance(value, bool):
        raise TruthIsolatedEvaluationError(
            f"D2 metric {name} must be numeric"
        )
    normalized = float(_finite_metric_value(value))
    if not 0.0 <= normalized <= 1.0:
        raise TruthIsolatedEvaluationError(
            f"D2 metric {name} must be in [0, 1]"
        )
    return normalized


def _validate_d2_truth_detail_contract(
    *,
    truth_available: bool,
    evaluated_frame_count: int,
    truth_frame_count: Mapping[str, int],
    truth_assigned_frame_count: Mapping[str, int],
    truth_identity_stable_frame_count: Mapping[str, int],
    confusion_matrix: Mapping[str, Mapping[str, int]] | None,
    audit: Mapping[str, Any],
) -> None:
    details_present = bool(
        truth_frame_count
        or truth_assigned_frame_count
        or truth_identity_stable_frame_count
        or confusion_matrix is not None
    )
    if not truth_available and details_present:
        raise TruthIsolatedEvaluationError(
            "unavailable D2 metrics must not carry truth detail counts"
        )
    if truth_available and confusion_matrix is None:
        raise TruthIsolatedEvaluationError(
            "available D2 metrics require an explicit confusion matrix"
        )
    for truth_id, count in truth_assigned_frame_count.items():
        if truth_id not in truth_frame_count or count > truth_frame_count[truth_id]:
            raise TruthIsolatedEvaluationError(
                "D2 assigned frame count exceeds truth frame count"
            )
    for truth_id, count in truth_identity_stable_frame_count.items():
        if (
            truth_id not in truth_assigned_frame_count
            or count > truth_assigned_frame_count[truth_id]
        ):
            raise TruthIsolatedEvaluationError(
                "D2 stable frame count exceeds assigned frame count"
            )
    if any(count > evaluated_frame_count for count in truth_frame_count.values()):
        raise TruthIsolatedEvaluationError(
            "D2 truth frame count exceeds evaluated_frame_count"
        )
    if confusion_matrix is not None and any(
        truth_id not in truth_frame_count for truth_id in confusion_matrix
    ):
        raise TruthIsolatedEvaluationError(
            "D2 confusion matrix contains unknown truth identity"
        )
    if "evaluated_frame_count" in audit and _nonnegative_int(
        audit["evaluated_frame_count"],
        "D2 audit evaluated_frame_count",
    ) != evaluated_frame_count:
        raise TruthIsolatedEvaluationError(
            "D2 audit evaluated_frame_count mismatch"
        )


def _d2_truth_metric_evidence_reason(
    *,
    truth_available: bool,
    evaluated_frame_count: int,
    truth_frame_count: Mapping[str, int],
) -> str | None:
    if not truth_available:
        return "d2_truth_metrics_unavailable"
    if evaluated_frame_count == 0:
        return "d2_evaluated_frames_unavailable"
    if not truth_frame_count or not any(truth_frame_count.values()):
        return "d2_truth_frame_evidence_unavailable"
    return None


def _validated_count_mapping(
    value: Mapping[str, Any],
    name: str,
) -> dict[str, int]:
    output: dict[str, int] = {}
    for key, raw in value.items():
        identifier = str(key).strip()
        if not identifier:
            raise TruthIsolatedEvaluationError(
                f"{name} identifiers must be non-empty"
            )
        output[identifier] = _nonnegative_int(raw, f"{name} count")
    return dict(sorted(output.items()))


def _validated_confusion_matrix(
    value: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    return {
        str(truth_id): _validated_count_mapping(track_counts, "confusion_matrix")
        for truth_id, track_counts in sorted(value.items())
    }


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TruthIsolatedEvaluationError(f"{name} must be a mapping")
    return value


def _mapping_sequence(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TruthIsolatedEvaluationError(f"{name} must be a sequence")
    return tuple(_mapping(item, name) for item in value)


def _identifier(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result or result == "None":
        raise TruthIsolatedEvaluationError(f"{name} must be non-empty")
    return result


def _finite_metric_value(value: Any) -> int | float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("metric values must be finite")
    return result


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _normalized_sha256(value: Any) -> str:
    text = str(value).strip().lower()
    if not text.startswith(_SHA256_PREFIX):
        text = f"{_SHA256_PREFIX}{text}"
    digest = text[len(_SHA256_PREFIX) :]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise TruthIsolatedEvaluationError("invalid sha256 digest")
    return text


def _optional_sha256(value: Any) -> str | None:
    return None if value is None else _normalized_sha256(value)


def _canonical_payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise TruthIsolatedEvaluationError(f"cannot read artifact: {path}") from exc
    return f"sha256:{digest.hexdigest()}"


def _csv_value(value: Any) -> Any:
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if value is None:
        return ""
    return value


def _sortable_key(value: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple("" if item is None else str(item) for item in value)


def _fmt_metric(metric: PublicMetricEvidence) -> str:
    if not metric.available:
        return f"不可用（{metric.unavailable_reason}）"
    return _fmt_number(metric.value)


def _fmt_disposition_count(payload: Mapping[str, Any], name: str) -> str:
    item = payload.get(name)
    if not isinstance(item, Mapping) or item.get("availability") != "available":
        reason = item.get("reason") if isinstance(item, Mapping) else "unavailable"
        return f"不可用（{reason}）"
    return str(item.get("count"))


def _fmt_hash(value: str | None) -> str:
    return "不可用" if value is None else f"`{value}`"


def _fmt_hash_mapping(values: Mapping[str, str | None]) -> str:
    if not values:
        return "不可用"
    return "<br>".join(
        f"{name}={_fmt_hash(value)}" for name, value in sorted(values.items())
    )


def _fmt_aggregate(metric: Mapping[str, Any]) -> str:
    if metric.get("availability") != "available":
        return f"不可用（{metric.get('unavailable_reason')}）"
    mean = _fmt_number(metric.get("mean"))
    low = metric.get("bootstrap_ci95_low")
    high = metric.get("bootstrap_ci95_high")
    if low is None or high is None:
        return f"{mean}（描述统计）"
    return f"{mean}（95% CI {_fmt_number(low)}～{_fmt_number(high)}）"


def _fmt_partial_coverage_total(metric: Mapping[str, Any]) -> str:
    if metric.get("availability") != "available":
        return f"不可用（{metric.get('unavailable_reason')}）"
    return "{}（{}/{}）".format(
        _fmt_number(metric.get("value")),
        metric.get("numerator"),
        metric.get("denominator"),
    )


def _fmt_partial_total(metric: Mapping[str, Any]) -> str:
    if metric.get("availability") != "available":
        reasons = _fmt_count_mapping(
            metric.get("unavailability_reason_distribution", {})
        )
        return f"不可用（{reasons}）"
    return _fmt_number(metric.get("value"))


def _fmt_metric_triplet(
    metrics: Mapping[str, PublicMetricEvidence],
    prefix: str,
) -> str:
    return "/".join(
        _fmt_metric(metrics[f"{prefix}_{suffix}"])
        for suffix in ("min", "mean", "max")
    )


def _fmt_commitment_aggregate_coverage(
    payload: Mapping[str, Any],
) -> str:
    if payload.get("availability") != "available":
        return f"不可用（{payload.get('unavailable_reason')}）"
    return _fmt_number(payload.get("coverage"))


def _fmt_summary_mapping(payload: Mapping[str, Any]) -> str:
    return "/".join(
        _fmt_number(payload.get(name)) for name in ("min", "mean", "max")
    )


def _fmt_count_mapping(values: Mapping[str, int]) -> str:
    if not values:
        return "无"
    return "<br>".join(
        f"{name}={count}" for name, count in sorted(values.items())
    )


def _fmt_number(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.4f}"


__all__ = [
    "D1ConsistencyEvaluationRecord",
    "D1SensorRangeConsistencyRecord",
    "D6_D1_CONSISTENCY_ADAPTER_SCHEMA_VERSION",
    "D6_D1_SENSOR_RANGE_RECORD_SCHEMA_VERSION",
    "D6_D2_IDENTITY_ADAPTER_SCHEMA_VERSION",
    "D6_D2_IDENTITY_COMMITMENT_ADAPTER_SCHEMA_VERSION",
    "D6_D2_IDENTITY_RECOVERY_CONFIG_PROVENANCE_SCHEMA_VERSION",
    "D6_D2_PARTIAL_IDENTITY_ADAPTER_SCHEMA_VERSION",
    "D6_TRUTH_ISOLATED_BATCH_SCHEMA_VERSION",
    "D6_TRUTH_ISOLATED_EPISODE_SCHEMA_VERSION",
    "D6_TRUTH_ISOLATED_EVALUATION_DATE",
    "D2_PARTIAL_IDENTITY_DENOMINATOR_DEFINITIONS",
    "D2_IDENTITY_COMMITMENT_DENOMINATOR_POLICY",
    "D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SCHEMA_VERSION",
    "D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V1",
    "D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2",
    "D2_SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION",
    "D2IdentityEvaluationRecord",
    "D2IdentityCommitmentEvidenceRecord",
    "D2IdentityRecoveryConfigProvenanceRecord",
    "D2PartialIdentityDiagnosticsRecord",
    "DEFAULT_TRUTH_ISOLATED_BOOTSTRAP_RESAMPLES",
    "DEFAULT_TRUTH_ISOLATED_BOOTSTRAP_RNG_SEED",
    "PublicMetricEvidence",
    "REFERENCE_SCALABLE_3D_SCALES",
    "TruthIsolatedBatchSummary",
    "TruthIsolatedEpisodeContext",
    "TruthIsolatedEpisodeEvaluationRecord",
    "TruthIsolatedEvaluationError",
    "TruthIsolatedOfflineReportGenerator",
    "adapt_d1_offline_consistency",
    "adapt_d2_scalable_3d_identity",
    "adapt_d2_identity_recovery_config_provenance",
    "aggregate_truth_isolated_episode_records",
    "build_truth_isolated_episode_record",
    "render_truth_isolated_markdown",
    "validate_d2_identity_commitment_evaluation",
]
