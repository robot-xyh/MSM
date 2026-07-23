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
D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION = (
    "d2.scalable3d_identity_evaluation.v1"
)
D2_SCALABLE_3D_IDENTITY_METRICS_SCHEMA_VERSION = (
    "d2.scalable3d_identity_metrics.v1"
)
D2_SCALABLE_3D_IDENTITY_POLICY_VERSION = (
    "d2.scalable3d_identity_policy.v1"
)
D2_SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION = (
    "d2.scalable3d_partial_identity_diagnostics.v1"
)
D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-offline-identity-evaluation-manifest-v1"
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
_SHA256_PREFIX = "sha256:"


class TruthIsolatedEvaluationError(ValueError):
    """Raised when a public evaluator artifact violates its frozen contract."""


class _PartialIdentityValidationError(ValueError):
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
                != D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION
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
            "producer_schema_version": (
                D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION
            ),
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
) -> D2IdentityEvaluationRecord:
    """Adapt a public D2 identity DTO without reconstructing identity mappings."""

    payload, external_hash, verification_mode = _public_payload(
        source,
        expected_sha256=expected_sha256,
        artifact_name="D2 scalable 3D identity evaluation",
    )
    if (
        payload.get("schema_version")
        != D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION
    ):
        raise TruthIsolatedEvaluationError(
            "unsupported D2 identity evaluation schema"
        )
    if payload.get("policy_version") != D2_SCALABLE_3D_IDENTITY_POLICY_VERSION:
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
    return D2IdentityEvaluationRecord(
        episode_id=_identifier(payload.get("episode_id"), "D2 episode_id"),
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
        partial_identity_diagnostics=partial_identity_diagnostics,
        verification_mode=verification_mode,
    )


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
    audit_count_bindings = {
        "evaluated_frame_count": "evaluated_frame_count",
        "available_mapping_count": "available_mapping_count",
        "ambiguous_mapping_count": "ambiguous_mapping_count",
        "unavailable_mapping_count": "unavailable_mapping_count",
    }
    for audit_name, count_name in audit_count_bindings.items():
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
        != D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION
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
    "D6_D2_PARTIAL_IDENTITY_ADAPTER_SCHEMA_VERSION",
    "D6_TRUTH_ISOLATED_BATCH_SCHEMA_VERSION",
    "D6_TRUTH_ISOLATED_EPISODE_SCHEMA_VERSION",
    "D6_TRUTH_ISOLATED_EVALUATION_DATE",
    "D2_PARTIAL_IDENTITY_DENOMINATOR_DEFINITIONS",
    "D2_SCALABLE_3D_PARTIAL_IDENTITY_DIAGNOSTICS_SCHEMA_VERSION",
    "D2IdentityEvaluationRecord",
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
    "aggregate_truth_isolated_episode_records",
    "build_truth_isolated_episode_record",
    "render_truth_isolated_markdown",
]
