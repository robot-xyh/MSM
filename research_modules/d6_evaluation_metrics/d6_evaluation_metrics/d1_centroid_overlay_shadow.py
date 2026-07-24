"""Read-only D6 audit for the D1 centroid publication-overlay shadow.

The adapter consumes persisted main-bus envelopes, final diagnostics, and
stage-timing summaries.  It never imports the scalable runtime or D1 code and
never writes to a control path.  Missing or contradictory evidence remains
unavailable instead of being backfilled with zero.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence


D1_CENTROID_OVERLAY_SHADOW_TOPIC = (
    "audit.d1.centroid_publication_overlay_shadow"
)
D1_CENTROID_OVERLAY_SHADOW_RUNTIME_SCHEMA = (
    "scalable3d-d1-centroid-overlay-shadow-v1"
)
D1_CENTROID_OVERLAY_SHADOW_EVALUATION_SCHEMA = (
    "d6.d1-centroid-overlay-shadow-readonly.v1"
)
D1_CENTROID_OVERLAY_SHADOW_TIMING_STAGE = (
    "module.d1_centroid_publication_overlay_shadow"
)
D1_CENTROID_OVERLAY_SHADOW_MAX_WALL_TIME_OVERHEAD_RATIO = 0.05
D1_CENTROID_OVERLAY_SHADOW_DIGEST_SEMANTICS = (
    "sha256_of_canonical_track_and_evidence_digest_manifest_v1"
)
D1_CENTROID_OVERLAY_SHADOW_PREPARATION_AUDIT_SCHEMA = (
    "d6.d1-centroid-overlay-preparation-readonly.v1"
)
D1_CENTROID_OVERLAY_SHADOW_EXECUTION_MODE_FIELD = (
    "overlay_execution_mode"
)
D1_CENTROID_OVERLAY_SHADOW_ATOMIC_EXECUTION_MODE = (
    "atomic_experimental_offline_v1"
)
D1_CENTROID_OVERLAY_SHADOW_LEGACY_EXECUTION_MODE = (
    "legacy_prepared_handle_v1"
)
D1_CENTROID_OVERLAY_SHADOW_LEGACY_UNINSTRUMENTED_EXECUTION_MODE = (
    "legacy_uninstrumented_runtime_v1"
)
_D1_CENTROID_OVERLAY_PROTOTYPE_STATUS = (
    "experimental_design_prototype_not_online_schema"
)
_D1_CENTROID_OVERLAY_ATOMIC_USAGE_SCOPE = (
    "experimental_offline_atomic_only"
)

D1_CENTROID_OVERLAY_SHADOW_NUMERIC_METRIC_FIELDS = (
    "d1_centroid_overlay_shadow_enabled",
    "d1_centroid_overlay_shadow_publication_count",
    "d1_centroid_overlay_shadow_evaluation_count",
    "d1_centroid_overlay_shadow_decision_count",
    "d1_centroid_overlay_shadow_accepted_count",
    "d1_centroid_overlay_shadow_rejected_count",
    "d1_centroid_overlay_shadow_error_count",
    "d1_centroid_overlay_shadow_hash_pair_evaluable_count",
    "d1_centroid_overlay_shadow_sha_equal_count",
    "d1_centroid_overlay_shadow_sha_different_count",
    "d1_centroid_overlay_shadow_global_track_id_evaluable_count",
    "d1_centroid_overlay_shadow_global_track_id_unchanged_count",
    "d1_centroid_overlay_shadow_global_track_id_changed_count",
    "d1_centroid_overlay_shadow_forbidden_mutation_count",
    "d1_centroid_overlay_shadow_forbidden_surface_violation_count",
    "d1_centroid_overlay_shadow_measurement_timestamp_publication_count",
    "d1_centroid_overlay_shadow_arrival_timestamp_publication_count",
    "d1_centroid_overlay_shadow_dual_timestamp_publication_count",
    "d1_centroid_overlay_shadow_measurement_timestamp_value_count",
    "d1_centroid_overlay_shadow_arrival_timestamp_value_count",
    "d1_centroid_overlay_shadow_overhead_p50_ms",
    "d1_centroid_overlay_shadow_overhead_p95_ms",
    "d1_centroid_overlay_shadow_overhead_max_ms",
    "d1_centroid_overlay_shadow_overhead_stage_consistent",
    "d1_centroid_overlay_shadow_generation_watermark_current",
    "d1_centroid_overlay_shadow_generation_watermark_peak",
    "d1_centroid_overlay_shadow_generation_watermark_capacity",
    "d1_centroid_overlay_shadow_payload_bytes_peak",
    "d1_centroid_overlay_shadow_d2_consumption_count",
    "d1_centroid_overlay_shadow_d3_consumption_count",
    "d1_centroid_overlay_shadow_online_truth_use_count",
    "d1_centroid_overlay_shadow_summary_counter_consistent",
    "d1_centroid_overlay_shadow_business_nonintervention_passed",
    "d1_centroid_overlay_shadow_preparation_audit_evaluable_count",
    "d1_centroid_overlay_shadow_preparation_audit_unavailable_count",
    "d1_centroid_overlay_shadow_integrity_check_evaluable_count",
    "d1_centroid_overlay_shadow_integrity_check_passed_count",
    "d1_centroid_overlay_shadow_integrity_check_failed_count",
    "d1_centroid_overlay_shadow_legacy_uninstrumented_count",
    "d1_centroid_overlay_shadow_legacy_prepared_handle_count",
    "d1_centroid_overlay_shadow_atomic_count",
    "d1_centroid_overlay_shadow_atomic_failure_count",
    "d1_centroid_overlay_shadow_atomic_shadow_materialized_count",
    "d1_centroid_overlay_shadow_atomic_canonical_description_pass_count",
    "d1_centroid_overlay_shadow_atomic_canonical_description_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_post_integrity_pass_count",
    "d1_centroid_overlay_shadow_atomic_post_integrity_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_shadow_track_copy_count",
    "d1_centroid_overlay_shadow_atomic_shadow_full_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_shadow_publication_digest_count",
)

_SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_SUMMARY_PREFIX = "d1_centroid_overlay_shadow_"
_SUMMARY_FIELDS = {
    "evaluation_count": f"{_SUMMARY_PREFIX}evaluation_count",
    "decision_count": f"{_SUMMARY_PREFIX}decision_count",
    "accepted_count": f"{_SUMMARY_PREFIX}accepted_count",
    "rejected_count": f"{_SUMMARY_PREFIX}rejected_count",
    "error_count": f"{_SUMMARY_PREFIX}error_count",
    "rejection_reason_counts": (
        f"{_SUMMARY_PREFIX}rejection_reason_counts"
    ),
    "forbidden_mutation_count": (
        f"{_SUMMARY_PREFIX}forbidden_mutation_count"
    ),
    "generation_watermark_current": (
        f"{_SUMMARY_PREFIX}watermark_count"
    ),
    "generation_watermark_peak": (
        f"{_SUMMARY_PREFIX}max_watermark_count"
    ),
    "generation_watermark_capacity": (
        f"{_SUMMARY_PREFIX}watermark_capacity"
    ),
    "payload_bytes_peak": f"{_SUMMARY_PREFIX}max_payload_bytes",
    "d2_consumption_count": f"{_SUMMARY_PREFIX}d2_consumption_count",
    "d3_consumption_count": f"{_SUMMARY_PREFIX}d3_consumption_count",
}

_RECORD_METRIC_FIELDS = (
    "d1_centroid_overlay_shadow_evaluation_count",
    "d1_centroid_overlay_shadow_decision_count",
    "d1_centroid_overlay_shadow_accepted_count",
    "d1_centroid_overlay_shadow_rejected_count",
    "d1_centroid_overlay_shadow_error_count",
    "d1_centroid_overlay_shadow_rejection_reason_distribution_json",
    "d1_centroid_overlay_shadow_hash_pair_evaluable_count",
    "d1_centroid_overlay_shadow_sha_equal_count",
    "d1_centroid_overlay_shadow_sha_different_count",
    "d1_centroid_overlay_shadow_global_track_id_evaluable_count",
    "d1_centroid_overlay_shadow_global_track_id_unchanged_count",
    "d1_centroid_overlay_shadow_global_track_id_changed_count",
    "d1_centroid_overlay_shadow_forbidden_mutation_count",
    "d1_centroid_overlay_shadow_forbidden_surface_violation_count",
    "d1_centroid_overlay_shadow_measurement_timestamp_publication_count",
    "d1_centroid_overlay_shadow_arrival_timestamp_publication_count",
    "d1_centroid_overlay_shadow_dual_timestamp_publication_count",
    "d1_centroid_overlay_shadow_measurement_timestamp_value_count",
    "d1_centroid_overlay_shadow_arrival_timestamp_value_count",
    "d1_centroid_overlay_shadow_generation_watermark_peak",
    "d1_centroid_overlay_shadow_generation_watermark_capacity",
    "d1_centroid_overlay_shadow_payload_bytes_peak",
    "d1_centroid_overlay_shadow_d2_consumption_count",
    "d1_centroid_overlay_shadow_d3_consumption_count",
    "d1_centroid_overlay_shadow_online_truth_use_count",
)

_OVERHEAD_FIELDS = (
    "d1_centroid_overlay_shadow_overhead_p50_ms",
    "d1_centroid_overlay_shadow_overhead_p95_ms",
    "d1_centroid_overlay_shadow_overhead_max_ms",
)

_PREPARATION_RECORD_METRIC_FIELDS = (
    "d1_centroid_overlay_shadow_execution_mode_distribution_json",
    "d1_centroid_overlay_shadow_preparation_audit_evaluable_count",
    "d1_centroid_overlay_shadow_preparation_audit_unavailable_count",
    "d1_centroid_overlay_shadow_integrity_check_evaluable_count",
    "d1_centroid_overlay_shadow_integrity_check_passed_count",
    "d1_centroid_overlay_shadow_integrity_check_failed_count",
    "d1_centroid_overlay_shadow_legacy_uninstrumented_count",
    "d1_centroid_overlay_shadow_legacy_prepared_handle_count",
    "d1_centroid_overlay_shadow_atomic_count",
    "d1_centroid_overlay_shadow_atomic_failure_count",
    "d1_centroid_overlay_shadow_atomic_failure_reason_distribution_json",
    "d1_centroid_overlay_shadow_atomic_shadow_materialized_count",
    "d1_centroid_overlay_shadow_atomic_canonical_description_pass_count",
    "d1_centroid_overlay_shadow_atomic_canonical_description_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_post_integrity_pass_count",
    "d1_centroid_overlay_shadow_atomic_post_integrity_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_shadow_track_copy_count",
    "d1_centroid_overlay_shadow_atomic_shadow_full_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_shadow_publication_digest_count",
)

_ATOMIC_ONLY_METRIC_FIELDS = (
    "d1_centroid_overlay_shadow_atomic_failure_count",
    "d1_centroid_overlay_shadow_atomic_failure_reason_distribution_json",
    "d1_centroid_overlay_shadow_atomic_shadow_materialized_count",
    "d1_centroid_overlay_shadow_atomic_canonical_description_pass_count",
    "d1_centroid_overlay_shadow_atomic_canonical_description_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_post_integrity_pass_count",
    "d1_centroid_overlay_shadow_atomic_post_integrity_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_shadow_track_copy_count",
    "d1_centroid_overlay_shadow_atomic_shadow_full_track_digest_count",
    "d1_centroid_overlay_shadow_atomic_shadow_publication_digest_count",
)

_LEGACY_PREPARATION_FIELDS = frozenset(
    {
        "explicit_prepared_handle_used",
        "base_publication_digest",
        "validation_error",
        "work",
        "evaluation_integrity_check",
    }
)
_ATOMIC_PREPARATION_FIELDS = frozenset(
    {
        "prepared_publication",
        "post_integrity_check",
        "canonical_publication_digest",
        "shadow_publication_digest",
        "shadow_materialized",
        "work",
        "atomic_failure_reason",
    }
)
_PREPARATION_WORK_FIELDS = frozenset(
    {
        "full_description_pass_count",
        "track_count",
        "validated_track_count",
        "full_track_digest_count",
        "state_digest_count",
        "covariance_digest_count",
        "publication_digest_count",
    }
)
_INTEGRITY_CHECK_FIELDS = frozenset(
    {
        "matches",
        "mismatch_reason",
        "object_binding_pass_count",
        "full_content_digest_pass_count",
        "track_digest_count",
    }
)
_ATOMIC_PREPARED_PUBLICATION_FIELDS = frozenset(
    {
        "prototype_status",
        "usage_scope",
        "base_publication_digest",
        "validation_error",
        "track_count",
        "work",
    }
)
_ATOMIC_WORK_FIELDS = frozenset(
    {
        "canonical_full_description_pass_count",
        "canonical_description_track_digest_count",
        "canonical_post_integrity_pass_count",
        "canonical_post_integrity_track_digest_count",
        "shadow_track_copy_count",
        "shadow_full_track_digest_count",
        "shadow_publication_digest_count",
    }
)


@dataclass(frozen=True)
class D1CentroidOverlayShadowEvidence:
    """Availability-aware metrics and fail-closed audit reasons."""

    metrics: dict[str, Any]
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class D1CentroidOverlayShadowPairPerformanceEvidence:
    """Explicit paired wall-time gate kept separate from safety evidence."""

    metrics: dict[str, Any]
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _ParsedPreparationAudit:
    execution_mode: str
    preparation_instrumented: bool
    integrity_matches: bool | None
    atomic_failure_reason: str | None
    atomic_shadow_materialized: bool | None
    atomic_work: Mapping[str, int] | None


@dataclass(frozen=True)
class _ParsedShadowRecord:
    decision_count: int
    accepted_count: int
    rejected_count: int
    rejection_reasons: Counter[str]
    error_count: int
    hashes_equal: bool
    global_track_ids_unchanged: bool
    forbidden_mutation: bool
    forbidden_surface_violation: bool
    canonical_business_tracks_replaced: bool
    d2_consumption_count: int
    d3_consumption_count: int
    online_truth_use_count: int
    measurement_timestamp_count: int
    arrival_timestamp_count: int
    watermark_count: int
    watermark_capacity: int
    payload_bytes: int
    evaluation_wall_time_ms: float
    status_is_nonconsumed_shadow: bool
    preparation_audit: _ParsedPreparationAudit


def evaluate_d1_centroid_overlay_shadow_evidence(
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any] | None,
    stage_timings: Mapping[str, Mapping[str, Any]] | None,
    *,
    online_unavailable_reason: str | None,
    stage_unavailable_reason: str | None,
) -> D1CentroidOverlayShadowEvidence:
    """Evaluate A2 shadow evidence without importing or changing runtime state."""

    metrics: dict[str, Any] = {}
    failures: list[str] = []
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_evaluation_schema_version",
        D1_CENTROID_OVERLAY_SHADOW_EVALUATION_SCHEMA,
    )
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_preparation_audit_schema_version",
        D1_CENTROID_OVERLAY_SHADOW_PREPARATION_AUDIT_SCHEMA,
    )
    shadow_records = [
        record
        for record in records
        if record.get("topic") == D1_CENTROID_OVERLAY_SHADOW_TOPIC
    ]

    if online_unavailable_reason is not None:
        _mark_all_unavailable(metrics, online_unavailable_reason)
        return D1CentroidOverlayShadowEvidence(metrics, ())

    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_publication_count",
        len(shadow_records),
    )
    summary_values, summary_reason = _parse_summary(summary)
    if summary_values is None:
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_enabled",
            summary_reason,
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_status",
            summary_reason,
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_generation_watermark_current",
            summary_reason,
        )
    else:
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_enabled",
            summary_values["enabled"],
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_status",
            summary_values["status"],
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_generation_watermark_current",
            summary_values["generation_watermark_current"],
        )

    if not shadow_records:
        _evaluate_without_publications(
            metrics,
            summary_values=summary_values,
            summary_reason=summary_reason,
        )
        _mark_overhead_unavailable(
            metrics,
            "no_d1_centroid_overlay_shadow_evaluations",
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_business_nonintervention_passed",
            "no_d1_centroid_overlay_shadow_evaluations",
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_semantics_json",
            _semantics(),
        )
        if (
            summary_values is not None
            and summary_values["evaluation_count"] > 0
        ):
            failures.append(
                "d1_centroid_overlay_shadow_publication_missing"
            )
        return D1CentroidOverlayShadowEvidence(
            metrics,
            tuple(dict.fromkeys(failures)),
        )

    parsed: list[_ParsedShadowRecord] = []
    parse_error: str | None = None
    for index, record in enumerate(shadow_records):
        try:
            parsed.append(_parse_record(record))
        except ValueError as exc:
            parse_error = (
                "d1_centroid_overlay_shadow_record_invalid:"
                f"index={index}:{exc}"
            )
            break

    if parse_error is not None:
        _mark_record_metrics_unavailable(metrics, parse_error)
        _mark_overhead_unavailable(metrics, parse_error)
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_summary_counter_consistent",
            parse_error,
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_business_nonintervention_passed",
            parse_error,
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_semantics_json",
            _semantics(),
        )
        failures.append(parse_error)
        return D1CentroidOverlayShadowEvidence(metrics, tuple(failures))

    try:
        aggregates = _aggregate_records(parsed)
    except ValueError as exc:
        aggregate_error = (
            f"d1_centroid_overlay_shadow_record_set_invalid:{exc}"
        )
        _mark_record_metrics_unavailable(metrics, aggregate_error)
        _mark_overhead_unavailable(metrics, aggregate_error)
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_summary_counter_consistent",
            aggregate_error,
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_business_nonintervention_passed",
            aggregate_error,
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_semantics_json",
            _semantics(),
        )
        failures.append(aggregate_error)
        return D1CentroidOverlayShadowEvidence(metrics, tuple(failures))
    for field, value in aggregates.items():
        _put_available(metrics, field, value)
    _mark_absent_preparation_metrics_unavailable(metrics, parsed)

    summary_consistent: bool | None
    if summary_values is None:
        summary_consistent = None
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_summary_counter_consistent",
            summary_reason,
        )
        failures.append(
            "d1_centroid_overlay_shadow_summary_evidence_missing"
        )
    else:
        summary_consistent = _summary_matches_records(
            summary_values,
            aggregates,
            parsed,
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_summary_counter_consistent",
            summary_consistent,
        )
        if not summary_consistent:
            failures.append(
                "d1_centroid_overlay_shadow_summary_counter_mismatch"
            )

    overhead_reason = _extract_overhead_metrics(
        metrics,
        stage_timings,
        publication_count=len(parsed),
        stage_unavailable_reason=stage_unavailable_reason,
    )
    if overhead_reason is not None:
        failures.append(
            "d1_centroid_overlay_shadow_overhead_unavailable:"
            f"{overhead_reason}"
        )

    criteria = {
        "summary_counter_consistent": summary_consistent,
        "status_offline_shadow_not_consumed": all(
            item.status_is_nonconsumed_shadow for item in parsed
        ),
        "canonical_business_tracks_replaced": any(
            item.canonical_business_tracks_replaced for item in parsed
        ),
        "forbidden_surface_violation_count": aggregates[
            "d1_centroid_overlay_shadow_forbidden_surface_violation_count"
        ],
        "global_track_id_changed_count": aggregates[
            "d1_centroid_overlay_shadow_global_track_id_changed_count"
        ],
        "d2_consumption_count": aggregates[
            "d1_centroid_overlay_shadow_d2_consumption_count"
        ],
        "d3_consumption_count": aggregates[
            "d1_centroid_overlay_shadow_d3_consumption_count"
        ],
        "online_truth_use_count": aggregates[
            "d1_centroid_overlay_shadow_online_truth_use_count"
        ],
        "shadow_sha_difference_is_not_business_output_change": True,
    }
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_business_nonintervention_criteria_json",
        criteria,
    )
    if summary_consistent is None:
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_business_nonintervention_passed",
            "d1_centroid_overlay_shadow_summary_evidence_missing",
        )
    else:
        nonintervention = bool(
            summary_consistent
            and criteria["status_offline_shadow_not_consumed"]
            and not criteria["canonical_business_tracks_replaced"]
            and criteria["forbidden_surface_violation_count"] == 0
            and criteria["global_track_id_changed_count"] == 0
            and criteria["d2_consumption_count"] == 0
            and criteria["d3_consumption_count"] == 0
            and criteria["online_truth_use_count"] == 0
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_business_nonintervention_passed",
            nonintervention,
        )
        if not nonintervention:
            failures.append(
                "d1_centroid_overlay_shadow_business_nonintervention_failed"
            )

    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_semantics_json",
        _semantics(),
    )
    if aggregates[
        "d1_centroid_overlay_shadow_forbidden_surface_violation_count"
    ] > 0:
        failures.append(
            "d1_centroid_overlay_shadow_forbidden_surface_violation"
        )
    if aggregates[
        "d1_centroid_overlay_shadow_global_track_id_changed_count"
    ] > 0:
        failures.append(
            "d1_centroid_overlay_shadow_global_track_id_changed"
        )
    if aggregates["d1_centroid_overlay_shadow_d2_consumption_count"] > 0:
        failures.append(
            "d1_centroid_overlay_shadow_d2_consumption_nonzero"
        )
    if aggregates["d1_centroid_overlay_shadow_d3_consumption_count"] > 0:
        failures.append(
            "d1_centroid_overlay_shadow_d3_consumption_nonzero"
        )
    if aggregates["d1_centroid_overlay_shadow_online_truth_use_count"] > 0:
        failures.append(
            "d1_centroid_overlay_shadow_online_truth_use_nonzero"
        )
    if aggregates["d1_centroid_overlay_shadow_error_count"] > 0:
        failures.append(
            "d1_centroid_overlay_shadow_evaluation_error_nonzero"
        )
    if (
        aggregates.get(
            "d1_centroid_overlay_shadow_integrity_check_failed_count",
            0,
        )
        > 0
    ):
        failures.append(
            "d1_centroid_overlay_shadow_preparation_integrity_failed"
        )
    if (
        aggregates.get(
            "d1_centroid_overlay_shadow_atomic_failure_count",
            0,
        )
        > 0
    ):
        failures.append(
            "d1_centroid_overlay_shadow_atomic_failure_reported"
        )
    return D1CentroidOverlayShadowEvidence(
        metrics,
        tuple(dict.fromkeys(failures)),
    )


def evaluate_d1_centroid_overlay_shadow_pair_performance(
    control_summary: Mapping[str, Any],
    shadow_summary: Mapping[str, Any],
    shadow_metrics: Mapping[str, Any],
    *,
    maximum_wall_time_overhead_ratio: float = (
        D1_CENTROID_OVERLAY_SHADOW_MAX_WALL_TIME_OVERHEAD_RATIO
    ),
) -> D1CentroidOverlayShadowPairPerformanceEvidence:
    """Evaluate an explicit same-scenario control/shadow wall-time pair.

    This is a descriptive performance gate.  Even a passing result cannot
    admit A2 because outcome-effect evidence is outside this adapter.
    """

    limit = float(maximum_wall_time_overhead_ratio)
    if not math.isfinite(limit) or limit < 0.0:
        raise ValueError(
            "maximum_wall_time_overhead_ratio must be finite and nonnegative"
        )
    metrics: dict[str, Any] = {}
    failures: list[str] = []
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_pair_evaluation_schema_version",
        D1_CENTROID_OVERLAY_SHADOW_EVALUATION_SCHEMA,
    )
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_wall_time_overhead_limit_ratio",
        limit,
    )

    identity_fields = (
        "scenario_name",
        "scenario_version",
        "seed",
        "target_count",
        "resource_count",
        "recon_count",
    )
    identity_values: dict[str, Any] = {}
    identity_reason: str | None = None
    for field in identity_fields:
        control_value = control_summary.get(field)
        shadow_value = shadow_summary.get(field)
        if control_value is None or shadow_value is None:
            identity_reason = f"paired_summary_field_missing:{field}"
            break
        if control_value != shadow_value:
            identity_reason = f"paired_summary_field_mismatch:{field}"
            break
        identity_values[field] = control_value
    if identity_reason is None:
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_pair_identity_consistent",
            True,
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_pair_identity_json",
            identity_values,
        )
    else:
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_pair_identity_consistent",
            False,
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_pair_identity_json",
            identity_reason,
        )
        failures.append(identity_reason)

    control_wall = control_summary.get("wall_time_s")
    shadow_wall = shadow_summary.get("wall_time_s")
    if (
        identity_reason is not None
        or not _is_positive_finite(control_wall)
        or not _is_positive_finite(shadow_wall)
    ):
        reason = identity_reason or "paired_wall_time_missing_or_invalid"
        for field in (
            "d1_centroid_overlay_shadow_control_wall_time_s",
            "d1_centroid_overlay_shadow_treatment_wall_time_s",
            "d1_centroid_overlay_shadow_wall_time_overhead_ratio",
            "d1_centroid_overlay_shadow_performance_gate_passed",
        ):
            _put_unavailable(metrics, field, reason)
        failures.append(reason)
    else:
        control_value = float(control_wall)
        shadow_value = float(shadow_wall)
        overhead_ratio = (shadow_value - control_value) / control_value
        performance_passed = overhead_ratio <= limit + 1.0e-12
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_control_wall_time_s",
            control_value,
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_treatment_wall_time_s",
            shadow_value,
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_wall_time_overhead_ratio",
            overhead_ratio,
        )
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_performance_gate_passed",
            performance_passed,
        )
        if not performance_passed:
            failures.append(
                "d1_centroid_overlay_shadow_performance_gate_failed"
            )

    for source, target in (
        (
            "d1_centroid_overlay_shadow_business_nonintervention_passed",
            "d1_centroid_overlay_shadow_pair_business_nonintervention_passed",
        ),
        (
            "d1_centroid_overlay_shadow_accepted_count",
            "d1_centroid_overlay_shadow_pair_accepted_treatment_count",
        ),
        (
            "d1_centroid_overlay_shadow_overhead_p95_ms",
            "d1_centroid_overlay_shadow_pair_evaluation_p95_ms",
        ),
        (
            "d1_centroid_overlay_shadow_payload_bytes_peak",
            "d1_centroid_overlay_shadow_pair_payload_bytes_peak",
        ),
    ):
        availability = shadow_metrics.get(f"{source}_availability")
        if availability == "available":
            _put_available(metrics, target, shadow_metrics.get(source))
        else:
            _put_unavailable(
                metrics,
                target,
                str(
                    shadow_metrics.get(f"{source}_unavailable_reason")
                    or f"{source}_unavailable"
                ),
            )

    blockers = list(dict.fromkeys(failures))
    business_available = (
        metrics.get(
            "d1_centroid_overlay_shadow_pair_business_nonintervention_passed_availability"
        )
        == "available"
    )
    if not business_available:
        blockers.append("business_nonintervention_evidence_unavailable")
    elif not metrics[
        "d1_centroid_overlay_shadow_pair_business_nonintervention_passed"
    ]:
        blockers.append("business_nonintervention_gate_failed")
    accepted_available = (
        metrics.get(
            "d1_centroid_overlay_shadow_pair_accepted_treatment_count_availability"
        )
        == "available"
    )
    if not accepted_available:
        blockers.append("accepted_treatment_count_unavailable")
    elif int(
        metrics["d1_centroid_overlay_shadow_pair_accepted_treatment_count"]
    ) <= 0:
        blockers.append("no_accepted_treatment")
    blockers.append("outcome_effect_evidence_not_provided")
    blockers = list(dict.fromkeys(blockers))
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_effect_evidence_available",
        False,
    )
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_overall_admitted",
        False,
    )
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_admission_status",
        "not_admitted",
    )
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_admission_blockers_json",
        blockers,
    )
    return D1CentroidOverlayShadowPairPerformanceEvidence(
        metrics,
        tuple(dict.fromkeys(failures)),
    )


def _parse_record(record: Mapping[str, Any]) -> _ParsedShadowRecord:
    if record.get("schema_version") != D1_CENTROID_OVERLAY_SHADOW_RUNTIME_SCHEMA:
        raise ValueError("unsupported_schema")
    if record.get("source") != "main":
        raise ValueError("unexpected_source")
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("payload_missing_or_invalid")
    if payload.get("status") != "offline_shadow_not_consumed":
        raise ValueError("status_not_offline_shadow_not_consumed")

    _required_nonnegative_float(payload, "timestamp")
    _required_positive_int(payload, "posterior_generation")
    for field in (
        "canonical_track_count",
        "shadow_track_count",
        "evidence_count",
        "decision_count",
        "accepted_count",
        "rejected_count",
    ):
        _required_nonnegative_int(payload, field)

    canonical_hash = _required_sha256(payload, "canonical_tracks_sha256")
    shadow_hash = _required_sha256(payload, "shadow_tracks_sha256")
    differs = _required_bool(payload, "shadow_differs_from_canonical")
    if differs != (canonical_hash != shadow_hash):
        raise ValueError("shadow_hash_difference_flag_mismatch")

    canonical_ids_hash = _required_sha256(
        payload,
        "canonical_global_track_ids_sha256",
    )
    shadow_ids_hash = _required_sha256(
        payload,
        "shadow_global_track_ids_sha256",
    )
    ids_unchanged = _required_bool(
        payload,
        "global_track_id_sequence_unchanged",
    )
    if ids_unchanged != (canonical_ids_hash == shadow_ids_hash):
        raise ValueError("global_track_id_sequence_flag_mismatch")
    if ids_unchanged and int(payload["canonical_track_count"]) != int(
        payload["shadow_track_count"]
    ):
        raise ValueError("unchanged_global_track_ids_have_count_mismatch")

    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("decisions_missing_or_invalid")
    if len(decisions) != int(payload["decision_count"]):
        raise ValueError("decision_count_mismatch")
    decision_counter: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    measurement_timestamps: list[float] = []
    arrival_timestamps: list[float] = []
    for decision in decisions:
        if not isinstance(decision, Mapping):
            raise ValueError("decision_not_object")
        disposition = decision.get("decision")
        if disposition not in {"accepted", "rejected"}:
            raise ValueError("decision_disposition_invalid")
        decision_counter[str(disposition)] += 1
        reason = decision.get("reject_reason")
        if disposition == "accepted":
            if reason is not None:
                raise ValueError("accepted_decision_has_reject_reason")
        elif not isinstance(reason, str) or not reason.strip():
            raise ValueError("rejected_decision_reason_missing")
        else:
            rejection_reasons[reason.strip()] += 1
        measurement_timestamps.append(
            _required_nonnegative_float(decision, "measurement_timestamp")
        )
        arrival_timestamps.append(
            _required_nonnegative_float(decision, "arrival_timestamp")
        )

    if decision_counter["accepted"] != int(payload["accepted_count"]):
        raise ValueError("accepted_count_mismatch")
    if decision_counter["rejected"] != int(payload["rejected_count"]):
        raise ValueError("rejected_count_mismatch")
    declared_reasons = _required_counter(
        payload,
        "rejection_reason_counts",
    )
    if declared_reasons != rejection_reasons:
        raise ValueError("rejection_reason_counts_mismatch")

    error = payload.get("evaluation_error")
    if error is not None and (
        not isinstance(error, str) or not error.strip()
    ):
        raise ValueError("evaluation_error_invalid")
    preparation_audit = _parse_preparation_audit(
        payload,
        canonical_track_count=int(payload["canonical_track_count"]),
        shadow_track_count=int(payload["shadow_track_count"]),
        accepted_count=int(payload["accepted_count"]),
        canonical_hash=canonical_hash,
        shadow_hash=shadow_hash,
        evaluation_error=error,
    )

    declared_measurement = _required_timestamp_array(
        payload,
        "measurement_timestamps",
    )
    declared_arrival = _required_timestamp_array(
        payload,
        "arrival_timestamps",
    )
    if error is None and declared_measurement != sorted(
        set(measurement_timestamps)
    ):
        raise ValueError("measurement_timestamp_summary_mismatch")
    if error is None and declared_arrival != sorted(set(arrival_timestamps)):
        raise ValueError("arrival_timestamp_summary_mismatch")
    if int(payload["evidence_count"]) > 0 and (
        not declared_measurement or not declared_arrival
    ):
        raise ValueError("dual_timestamp_evidence_missing")

    forbidden = payload.get("forbidden_mutation_audit")
    if not isinstance(forbidden, Mapping):
        raise ValueError("forbidden_mutation_audit_missing_or_invalid")
    digest_semantics = _required_nonempty_string(
        forbidden,
        "digest_semantics",
    )
    if digest_semantics != D1_CENTROID_OVERLAY_SHADOW_DIGEST_SEMANTICS:
        raise ValueError("forbidden_digest_semantics_unsupported")
    before_hash = _required_sha256(forbidden, "before_sha256")
    after_hash = _required_sha256(forbidden, "after_sha256")
    canonical_before_hash = _required_sha256(
        forbidden,
        "canonical_tracks_before_sha256",
    )
    canonical_after_hash = _required_sha256(
        forbidden,
        "canonical_tracks_after_sha256",
    )
    evidence_before_hash = _required_sha256(
        forbidden,
        "structural_ambiguity_evidence_before_sha256",
    )
    evidence_after_hash = _required_sha256(
        forbidden,
        "structural_ambiguity_evidence_after_sha256",
    )
    expected_before_hash = _digest_manifest_sha256(
        canonical_before_hash,
        evidence_before_hash,
    )
    expected_after_hash = _digest_manifest_sha256(
        canonical_after_hash,
        evidence_after_hash,
    )
    if before_hash != expected_before_hash or after_hash != expected_after_hash:
        raise ValueError("forbidden_digest_manifest_mismatch")
    if canonical_hash != canonical_before_hash:
        raise ValueError("canonical_track_digest_binding_mismatch")
    passed = _required_bool(forbidden, "passed")
    digest_pairs_unchanged = bool(
        canonical_before_hash == canonical_after_hash
        and evidence_before_hash == evidence_after_hash
    )
    if passed != digest_pairs_unchanged:
        raise ValueError("forbidden_mutation_pass_flag_mismatch")
    reference_fields = (
        "filter_adapter_reference_passed_to_prototype",
        "history_reference_passed_to_prototype",
        "checkpoint_reference_passed_to_prototype",
        "replay_cache_reference_passed_to_prototype",
        "scan_watermark_reference_passed_to_prototype",
    )
    forbidden_reference = any(
        _required_bool(forbidden, field) for field in reference_fields
    )
    canonical_replaced = _required_bool(
        forbidden,
        "canonical_business_tracks_replaced",
    )
    d2_consumption = _required_nonnegative_int(
        forbidden,
        "d2_consumption_count",
    )
    d3_consumption = _required_nonnegative_int(
        forbidden,
        "d3_consumption_count",
    )

    bounded = payload.get("bounded_memory_audit")
    if not isinstance(bounded, Mapping):
        raise ValueError("bounded_memory_audit_missing_or_invalid")
    watermark_count = _required_nonnegative_int(
        bounded,
        "generation_watermark_count",
    )
    watermark_capacity = _required_positive_int(
        bounded,
        "generation_watermark_capacity",
    )
    if watermark_count > watermark_capacity:
        raise ValueError("generation_watermark_capacity_exceeded")
    payload_bytes = _required_nonnegative_int(
        bounded,
        "shadow_track_payload_bytes",
    )
    online_truth_use = _required_nonnegative_int(
        payload,
        "online_truth_use_count",
    )
    evaluation_wall_time_ms = _required_nonnegative_float(
        payload,
        "evaluation_wall_time_ms",
    )

    return _ParsedShadowRecord(
        decision_count=len(decisions),
        accepted_count=decision_counter["accepted"],
        rejected_count=decision_counter["rejected"],
        rejection_reasons=rejection_reasons,
        error_count=1 if error is not None else 0,
        hashes_equal=canonical_hash == shadow_hash,
        global_track_ids_unchanged=ids_unchanged,
        forbidden_mutation=not passed,
        forbidden_surface_violation=bool(
            not passed or forbidden_reference or canonical_replaced
        ),
        canonical_business_tracks_replaced=canonical_replaced,
        d2_consumption_count=d2_consumption,
        d3_consumption_count=d3_consumption,
        online_truth_use_count=online_truth_use,
        measurement_timestamp_count=len(declared_measurement),
        arrival_timestamp_count=len(declared_arrival),
        watermark_count=watermark_count,
        watermark_capacity=watermark_capacity,
        payload_bytes=payload_bytes,
        evaluation_wall_time_ms=evaluation_wall_time_ms,
        status_is_nonconsumed_shadow=True,
        preparation_audit=preparation_audit,
    )


def _parse_preparation_audit(
    payload: Mapping[str, Any],
    *,
    canonical_track_count: int,
    shadow_track_count: int,
    accepted_count: int,
    canonical_hash: str,
    shadow_hash: str,
    evaluation_error: object,
) -> _ParsedPreparationAudit:
    mode_present = D1_CENTROID_OVERLAY_SHADOW_EXECUTION_MODE_FIELD in payload
    mode = payload.get(D1_CENTROID_OVERLAY_SHADOW_EXECUTION_MODE_FIELD)
    preparation_present = "canonical_preparation" in payload
    preparation = payload.get("canonical_preparation")

    if not mode_present:
        if not preparation_present:
            return _ParsedPreparationAudit(
                execution_mode=(
                    D1_CENTROID_OVERLAY_SHADOW_LEGACY_UNINSTRUMENTED_EXECUTION_MODE
                ),
                preparation_instrumented=False,
                integrity_matches=None,
                atomic_failure_reason=None,
                atomic_shadow_materialized=None,
                atomic_work=None,
            )
        if not isinstance(preparation, Mapping):
            raise ValueError("canonical_preparation_missing_or_invalid")
        if set(preparation) != _LEGACY_PREPARATION_FIELDS:
            if set(preparation) & _ATOMIC_PREPARATION_FIELDS:
                raise ValueError("atomic_execution_mode_marker_missing")
            raise ValueError("legacy_canonical_preparation_fields_invalid")
        return _parse_legacy_preparation_audit(
            preparation,
            canonical_track_count=canonical_track_count,
            accepted_count=accepted_count,
            evaluation_error=evaluation_error,
        )

    if mode == D1_CENTROID_OVERLAY_SHADOW_LEGACY_UNINSTRUMENTED_EXECUTION_MODE:
        if preparation_present:
            raise ValueError(
                "legacy_uninstrumented_mode_has_canonical_preparation"
            )
        return _ParsedPreparationAudit(
            execution_mode=(
                D1_CENTROID_OVERLAY_SHADOW_LEGACY_UNINSTRUMENTED_EXECUTION_MODE
            ),
            preparation_instrumented=False,
            integrity_matches=None,
            atomic_failure_reason=None,
            atomic_shadow_materialized=None,
            atomic_work=None,
        )
    if mode == D1_CENTROID_OVERLAY_SHADOW_LEGACY_EXECUTION_MODE:
        if not isinstance(preparation, Mapping):
            raise ValueError("legacy_canonical_preparation_missing_or_invalid")
        return _parse_legacy_preparation_audit(
            preparation,
            canonical_track_count=canonical_track_count,
            accepted_count=accepted_count,
            evaluation_error=evaluation_error,
        )
    if mode != D1_CENTROID_OVERLAY_SHADOW_ATOMIC_EXECUTION_MODE:
        raise ValueError("overlay_execution_mode_unsupported")
    if not isinstance(preparation, Mapping):
        raise ValueError("atomic_canonical_preparation_missing_or_invalid")
    return _parse_atomic_preparation_audit(
        preparation,
        canonical_track_count=canonical_track_count,
        shadow_track_count=shadow_track_count,
        accepted_count=accepted_count,
        canonical_hash=canonical_hash,
        shadow_hash=shadow_hash,
    )


def _parse_legacy_preparation_audit(
    preparation: Mapping[str, Any],
    *,
    canonical_track_count: int,
    accepted_count: int,
    evaluation_error: object,
) -> _ParsedPreparationAudit:
    _require_exact_fields(
        preparation,
        _LEGACY_PREPARATION_FIELDS,
        "legacy_canonical_preparation",
    )
    explicitly_prepared = _required_bool(
        preparation,
        "explicit_prepared_handle_used",
    )
    if not explicitly_prepared:
        if any(
            preparation[field] is not None
            for field in (
                "base_publication_digest",
                "validation_error",
                "work",
                "evaluation_integrity_check",
            )
        ):
            raise ValueError("legacy_unprepared_fields_must_be_null")
        return _ParsedPreparationAudit(
            execution_mode=D1_CENTROID_OVERLAY_SHADOW_LEGACY_EXECUTION_MODE,
            preparation_instrumented=False,
            integrity_matches=None,
            atomic_failure_reason=None,
            atomic_shadow_materialized=None,
            atomic_work=None,
        )

    _required_sha256(preparation, "base_publication_digest")
    validation_error = _optional_nonempty_string(
        preparation,
        "validation_error",
    )
    work = _parse_preparation_work(
        preparation.get("work"),
        context="legacy_preparation_work",
        canonical_track_count=canonical_track_count,
        validation_error=validation_error,
    )
    integrity_value = preparation.get("evaluation_integrity_check")
    if integrity_value is None:
        if evaluation_error is None:
            raise ValueError(
                "legacy_evaluation_integrity_check_missing_without_error"
            )
        integrity_matches = None
    else:
        integrity = _parse_integrity_check(
            integrity_value,
            context="legacy_evaluation_integrity_check",
            canonical_track_count=canonical_track_count,
            validation_error=validation_error,
        )
        integrity_matches = bool(integrity["matches"])
        if not integrity_matches and accepted_count > 0:
            raise ValueError("legacy_integrity_failure_has_accepted_decision")
        if (
            int(work["full_track_digest_count"])
            != int(work["validated_track_count"])
        ):
            raise ValueError("legacy_preparation_work_digest_count_mismatch")
    return _ParsedPreparationAudit(
        execution_mode=D1_CENTROID_OVERLAY_SHADOW_LEGACY_EXECUTION_MODE,
        preparation_instrumented=True,
        integrity_matches=integrity_matches,
        atomic_failure_reason=None,
        atomic_shadow_materialized=None,
        atomic_work=None,
    )


def _parse_atomic_preparation_audit(
    preparation: Mapping[str, Any],
    *,
    canonical_track_count: int,
    shadow_track_count: int,
    accepted_count: int,
    canonical_hash: str,
    shadow_hash: str,
) -> _ParsedPreparationAudit:
    _require_exact_fields(
        preparation,
        _ATOMIC_PREPARATION_FIELDS,
        "atomic_canonical_preparation",
    )
    prepared = preparation.get("prepared_publication")
    if not isinstance(prepared, Mapping):
        raise ValueError("atomic_prepared_publication_missing_or_invalid")
    _require_exact_fields(
        prepared,
        _ATOMIC_PREPARED_PUBLICATION_FIELDS,
        "atomic_prepared_publication",
    )
    if (
        _required_nonempty_string(prepared, "prototype_status")
        != _D1_CENTROID_OVERLAY_PROTOTYPE_STATUS
    ):
        raise ValueError("atomic_prepared_publication_status_unsupported")
    if (
        _required_nonempty_string(prepared, "usage_scope")
        != _D1_CENTROID_OVERLAY_ATOMIC_USAGE_SCOPE
    ):
        raise ValueError("atomic_prepared_publication_scope_unsupported")
    base_digest = _required_sha256(prepared, "base_publication_digest")
    validation_error = _optional_nonempty_string(
        prepared,
        "validation_error",
    )
    prepared_track_count = _required_nonnegative_int(
        prepared,
        "track_count",
    )
    if prepared_track_count != canonical_track_count:
        raise ValueError("atomic_prepared_track_count_mismatch")
    preparation_work = _parse_preparation_work(
        prepared.get("work"),
        context="atomic_preparation_work",
        canonical_track_count=canonical_track_count,
        validation_error=validation_error,
    )

    canonical_publication_digest = _required_sha256(
        preparation,
        "canonical_publication_digest",
    )
    if canonical_publication_digest != base_digest:
        raise ValueError("atomic_canonical_publication_digest_mismatch")
    integrity = _parse_integrity_check(
        preparation.get("post_integrity_check"),
        context="atomic_post_integrity_check",
        canonical_track_count=canonical_track_count,
        validation_error=validation_error,
    )
    atomic_work = _parse_atomic_work(preparation.get("work"))
    if (
        atomic_work["canonical_full_description_pass_count"]
        != preparation_work["full_description_pass_count"]
    ):
        raise ValueError("atomic_description_pass_count_mismatch")
    if (
        atomic_work["canonical_description_track_digest_count"]
        != preparation_work["full_track_digest_count"]
    ):
        raise ValueError("atomic_description_track_digest_count_mismatch")
    if (
        atomic_work["canonical_post_integrity_pass_count"]
        != integrity["full_content_digest_pass_count"]
    ):
        raise ValueError("atomic_post_integrity_pass_count_mismatch")
    if (
        atomic_work["canonical_post_integrity_track_digest_count"]
        != integrity["track_digest_count"]
    ):
        raise ValueError("atomic_post_integrity_track_digest_count_mismatch")

    shadow_materialized = _required_bool(
        preparation,
        "shadow_materialized",
    )
    shadow_digest = _optional_sha256(
        preparation,
        "shadow_publication_digest",
    )
    if shadow_materialized != (shadow_digest is not None):
        raise ValueError("atomic_shadow_digest_materialization_mismatch")
    failure_reason = _optional_nonempty_string(
        preparation,
        "atomic_failure_reason",
    )
    integrity_matches = bool(integrity["matches"])
    if not integrity_matches:
        if failure_reason is None:
            raise ValueError("atomic_integrity_failure_reason_missing")
        expected_failure = (
            "post_integrity_mismatch:"
            f"{integrity['mismatch_reason']}"
        )
        if failure_reason != expected_failure:
            raise ValueError("atomic_integrity_failure_reason_mismatch")
    elif failure_reason is not None:
        # A detached shadow assembly failure may follow a valid post-check.
        if not failure_reason.startswith("shadow_assembly_failed:"):
            raise ValueError("atomic_failure_reason_inconsistent")

    if validation_error is not None and accepted_count > 0:
        raise ValueError("atomic_invalid_preparation_has_accepted_decision")
    if failure_reason is not None:
        if accepted_count > 0:
            raise ValueError("atomic_failure_has_accepted_decision")
        if shadow_materialized:
            raise ValueError("atomic_failure_exposes_shadow")
    elif shadow_materialized != (accepted_count > 0):
        raise ValueError("atomic_accepted_materialization_mismatch")

    if shadow_materialized:
        if shadow_track_count != canonical_track_count:
            raise ValueError("atomic_materialized_track_count_mismatch")
        if (
            atomic_work["shadow_track_copy_count"] != canonical_track_count
            or atomic_work["shadow_full_track_digest_count"]
            != canonical_track_count
            or atomic_work["shadow_publication_digest_count"] != 1
        ):
            raise ValueError("atomic_materialized_shadow_work_mismatch")
    elif failure_reason is None:
        if canonical_hash != shadow_hash:
            raise ValueError("atomic_rejected_shadow_hash_mismatch")
        if shadow_track_count != canonical_track_count:
            raise ValueError("atomic_rejected_shadow_track_count_mismatch")
        if any(
            atomic_work[field] != 0
            for field in (
                "shadow_track_copy_count",
                "shadow_full_track_digest_count",
                "shadow_publication_digest_count",
            )
        ):
            raise ValueError("atomic_rejected_shadow_work_nonzero")
    else:
        if canonical_hash != shadow_hash:
            raise ValueError("atomic_failure_shadow_hash_mismatch")
        if shadow_track_count != canonical_track_count:
            raise ValueError("atomic_failure_shadow_track_count_mismatch")
        if atomic_work["shadow_track_copy_count"] > canonical_track_count:
            raise ValueError("atomic_failure_shadow_copy_count_invalid")
        if (
            atomic_work["shadow_full_track_digest_count"]
            > atomic_work["shadow_track_copy_count"]
        ):
            raise ValueError("atomic_failure_shadow_digest_count_invalid")
        if atomic_work["shadow_publication_digest_count"] > 1:
            raise ValueError("atomic_failure_publication_digest_count_invalid")

    return _ParsedPreparationAudit(
        execution_mode=D1_CENTROID_OVERLAY_SHADOW_ATOMIC_EXECUTION_MODE,
        preparation_instrumented=True,
        integrity_matches=integrity_matches,
        atomic_failure_reason=failure_reason,
        atomic_shadow_materialized=shadow_materialized,
        atomic_work=dict(atomic_work),
    )


def _parse_preparation_work(
    value: object,
    *,
    context: str,
    canonical_track_count: int,
    validation_error: str | None,
) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}_missing_or_invalid")
    _require_exact_fields(value, _PREPARATION_WORK_FIELDS, context)
    work = {
        field: _required_nonnegative_int(value, field)
        for field in _PREPARATION_WORK_FIELDS
    }
    if work["full_description_pass_count"] != 1:
        raise ValueError(f"{context}_description_pass_count_invalid")
    if work["track_count"] != canonical_track_count:
        raise ValueError(f"{context}_track_count_mismatch")
    validated = work["validated_track_count"]
    if validated > canonical_track_count:
        raise ValueError(f"{context}_validated_track_count_invalid")
    for field in (
        "full_track_digest_count",
        "state_digest_count",
        "covariance_digest_count",
    ):
        if work[field] != validated:
            raise ValueError(f"{context}_{field}_mismatch")
    if work["publication_digest_count"] != 1:
        raise ValueError(f"{context}_publication_digest_count_invalid")
    if validation_error is None and validated != canonical_track_count:
        raise ValueError(f"{context}_valid_publication_not_fully_described")
    return work


def _parse_integrity_check(
    value: object,
    *,
    context: str,
    canonical_track_count: int,
    validation_error: str | None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}_missing_or_invalid")
    _require_exact_fields(value, _INTEGRITY_CHECK_FIELDS, context)
    matches = _required_bool(value, "matches")
    mismatch_reason = _optional_nonempty_string(value, "mismatch_reason")
    if matches == (mismatch_reason is not None):
        raise ValueError(f"{context}_match_reason_inconsistent")
    object_passes = _required_nonnegative_int(
        value,
        "object_binding_pass_count",
    )
    full_passes = _required_nonnegative_int(
        value,
        "full_content_digest_pass_count",
    )
    track_digests = _required_nonnegative_int(value, "track_digest_count")
    if object_passes != 1:
        raise ValueError(f"{context}_object_binding_pass_count_invalid")
    if full_passes > 1:
        raise ValueError(f"{context}_full_content_pass_count_invalid")
    if track_digests > canonical_track_count:
        raise ValueError(f"{context}_track_digest_count_invalid")
    if full_passes == 0 and track_digests != 0:
        raise ValueError(f"{context}_track_digest_without_full_pass")
    if matches:
        if validation_error is None and (
            full_passes != 1 or track_digests != canonical_track_count
        ):
            raise ValueError(f"{context}_valid_content_not_fully_checked")
        if validation_error is not None and (
            full_passes != 0 or track_digests != 0
        ):
            raise ValueError(f"{context}_invalid_content_rehashed")
    elif validation_error is not None:
        raise ValueError(f"{context}_invalid_preparation_mismatch_impossible")
    return {
        "matches": matches,
        "mismatch_reason": mismatch_reason,
        "object_binding_pass_count": object_passes,
        "full_content_digest_pass_count": full_passes,
        "track_digest_count": track_digests,
    }


def _parse_atomic_work(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError("atomic_work_missing_or_invalid")
    _require_exact_fields(value, _ATOMIC_WORK_FIELDS, "atomic_work")
    return {
        field: _required_nonnegative_int(value, field)
        for field in _ATOMIC_WORK_FIELDS
    }


def _aggregate_records(
    records: Sequence[_ParsedShadowRecord],
) -> dict[str, Any]:
    reasons: Counter[str] = Counter()
    for record in records:
        reasons.update(record.rejection_reasons)
    capacities = {record.watermark_capacity for record in records}
    if len(capacities) != 1:
        raise ValueError("generation_watermark_capacity_changed")
    overhead_samples = sorted(
        item.evaluation_wall_time_ms for item in records
    )
    aggregates: dict[str, Any] = {
        "d1_centroid_overlay_shadow_evaluation_count": len(records),
        "d1_centroid_overlay_shadow_decision_count": sum(
            item.decision_count for item in records
        ),
        "d1_centroid_overlay_shadow_accepted_count": sum(
            item.accepted_count for item in records
        ),
        "d1_centroid_overlay_shadow_rejected_count": sum(
            item.rejected_count for item in records
        ),
        "d1_centroid_overlay_shadow_error_count": sum(
            item.error_count for item in records
        ),
        "d1_centroid_overlay_shadow_rejection_reason_distribution_json": dict(
            sorted(reasons.items())
        ),
        "d1_centroid_overlay_shadow_hash_pair_evaluable_count": len(records),
        "d1_centroid_overlay_shadow_sha_equal_count": sum(
            item.hashes_equal for item in records
        ),
        "d1_centroid_overlay_shadow_sha_different_count": sum(
            not item.hashes_equal for item in records
        ),
        "d1_centroid_overlay_shadow_global_track_id_evaluable_count": len(
            records
        ),
        "d1_centroid_overlay_shadow_global_track_id_unchanged_count": sum(
            item.global_track_ids_unchanged for item in records
        ),
        "d1_centroid_overlay_shadow_global_track_id_changed_count": sum(
            not item.global_track_ids_unchanged for item in records
        ),
        "d1_centroid_overlay_shadow_forbidden_mutation_count": sum(
            item.forbidden_mutation for item in records
        ),
        "d1_centroid_overlay_shadow_forbidden_surface_violation_count": sum(
            item.forbidden_surface_violation for item in records
        ),
        "d1_centroid_overlay_shadow_measurement_timestamp_publication_count": len(
            records
        ),
        "d1_centroid_overlay_shadow_arrival_timestamp_publication_count": len(
            records
        ),
        "d1_centroid_overlay_shadow_dual_timestamp_publication_count": len(
            records
        ),
        "d1_centroid_overlay_shadow_measurement_timestamp_value_count": sum(
            item.measurement_timestamp_count for item in records
        ),
        "d1_centroid_overlay_shadow_arrival_timestamp_value_count": sum(
            item.arrival_timestamp_count for item in records
        ),
        "d1_centroid_overlay_shadow_generation_watermark_peak": max(
            item.watermark_count for item in records
        ),
        "d1_centroid_overlay_shadow_generation_watermark_capacity": next(
            iter(capacities)
        ),
        "d1_centroid_overlay_shadow_payload_bytes_peak": max(
            item.payload_bytes for item in records
        ),
        "d1_centroid_overlay_shadow_d2_consumption_count": sum(
            item.d2_consumption_count for item in records
        ),
        "d1_centroid_overlay_shadow_d3_consumption_count": sum(
            item.d3_consumption_count for item in records
        ),
        "d1_centroid_overlay_shadow_online_truth_use_count": sum(
            item.online_truth_use_count for item in records
        ),
        "d1_centroid_overlay_shadow_overhead_p50_ms": _percentile(
            overhead_samples,
            50.0,
        ),
        "d1_centroid_overlay_shadow_overhead_p95_ms": _percentile(
            overhead_samples,
            95.0,
        ),
        "d1_centroid_overlay_shadow_overhead_max_ms": max(
            overhead_samples
        ),
    }
    mode_counts = Counter(
        item.preparation_audit.execution_mode for item in records
    )
    preparation_evaluable_count = sum(
        item.preparation_audit.preparation_instrumented
        for item in records
    )
    integrity_values = [
        item.preparation_audit.integrity_matches
        for item in records
        if item.preparation_audit.integrity_matches is not None
    ]
    atomic = [
        item.preparation_audit
        for item in records
        if item.preparation_audit.execution_mode
        == D1_CENTROID_OVERLAY_SHADOW_ATOMIC_EXECUTION_MODE
    ]
    aggregates.update(
        {
            "d1_centroid_overlay_shadow_execution_mode_distribution_json": dict(
                sorted(mode_counts.items())
            ),
            "d1_centroid_overlay_shadow_preparation_audit_evaluable_count": (
                preparation_evaluable_count
            ),
            "d1_centroid_overlay_shadow_preparation_audit_unavailable_count": (
                len(records) - preparation_evaluable_count
            ),
            "d1_centroid_overlay_shadow_integrity_check_evaluable_count": len(
                integrity_values
            ),
            "d1_centroid_overlay_shadow_legacy_uninstrumented_count": (
                mode_counts[
                    D1_CENTROID_OVERLAY_SHADOW_LEGACY_UNINSTRUMENTED_EXECUTION_MODE
                ]
            ),
            "d1_centroid_overlay_shadow_legacy_prepared_handle_count": (
                mode_counts[D1_CENTROID_OVERLAY_SHADOW_LEGACY_EXECUTION_MODE]
            ),
            "d1_centroid_overlay_shadow_atomic_count": len(atomic),
        }
    )
    if integrity_values:
        aggregates.update(
            {
                "d1_centroid_overlay_shadow_integrity_check_passed_count": sum(
                    value is True for value in integrity_values
                ),
                "d1_centroid_overlay_shadow_integrity_check_failed_count": sum(
                    value is False for value in integrity_values
                ),
            }
        )
    if atomic:
        atomic_failure_reasons = Counter(
            item.atomic_failure_reason
            for item in atomic
            if item.atomic_failure_reason is not None
        )
        atomic_work = [
            item.atomic_work
            for item in atomic
            if item.atomic_work is not None
        ]
        if len(atomic_work) != len(atomic):
            raise ValueError("atomic_work_internal_parse_mismatch")
        aggregates.update(
            {
                "d1_centroid_overlay_shadow_atomic_failure_count": sum(
                    item.atomic_failure_reason is not None for item in atomic
                ),
                "d1_centroid_overlay_shadow_atomic_failure_reason_distribution_json": dict(
                    sorted(atomic_failure_reasons.items())
                ),
                "d1_centroid_overlay_shadow_atomic_shadow_materialized_count": sum(
                    item.atomic_shadow_materialized is True for item in atomic
                ),
                "d1_centroid_overlay_shadow_atomic_canonical_description_pass_count": sum(
                    item["canonical_full_description_pass_count"]
                    for item in atomic_work
                ),
                "d1_centroid_overlay_shadow_atomic_canonical_description_track_digest_count": sum(
                    item["canonical_description_track_digest_count"]
                    for item in atomic_work
                ),
                "d1_centroid_overlay_shadow_atomic_post_integrity_pass_count": sum(
                    item["canonical_post_integrity_pass_count"]
                    for item in atomic_work
                ),
                "d1_centroid_overlay_shadow_atomic_post_integrity_track_digest_count": sum(
                    item["canonical_post_integrity_track_digest_count"]
                    for item in atomic_work
                ),
                "d1_centroid_overlay_shadow_atomic_shadow_track_copy_count": sum(
                    item["shadow_track_copy_count"] for item in atomic_work
                ),
                "d1_centroid_overlay_shadow_atomic_shadow_full_track_digest_count": sum(
                    item["shadow_full_track_digest_count"]
                    for item in atomic_work
                ),
                "d1_centroid_overlay_shadow_atomic_shadow_publication_digest_count": sum(
                    item["shadow_publication_digest_count"]
                    for item in atomic_work
                ),
            }
        )
    return aggregates


def _parse_summary(
    summary: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(summary, Mapping):
        return None, "summary_json_missing"
    diagnostics = summary.get("module_final_diagnostics")
    if not isinstance(diagnostics, Mapping):
        return None, "module_final_diagnostics_missing"
    governance = diagnostics.get("observation_governance")
    candidate_surfaces = [
        surface
        for surface in (
            governance if isinstance(governance, Mapping) else None,
            diagnostics,
        )
        if isinstance(surface, Mapping)
        and (
            "d1_centroid_publication_overlay_shadow_enabled" in surface
            or any(field in surface for field in _SUMMARY_FIELDS.values())
        )
    ]
    if not candidate_surfaces:
        return None, "d1_centroid_overlay_shadow_capability_not_recorded"
    try:
        parsed = [
            _parse_summary_surface(surface)
            for surface in candidate_surfaces
        ]
    except ValueError as exc:
        return None, f"d1_centroid_overlay_shadow_summary_invalid:{exc}"
    if any(value != parsed[0] for value in parsed[1:]):
        return None, "d1_centroid_overlay_shadow_summary_invalid:duplicate_surface_mismatch"
    return parsed[0], ""


def _parse_summary_surface(
    diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    enabled_field = "d1_centroid_publication_overlay_shadow_enabled"
    status_field = "d1_centroid_publication_overlay_shadow_status"
    enabled = _required_bool(diagnostics, enabled_field)
    status = _required_nonempty_string(diagnostics, status_field)
    if status not in {"disabled", "offline_shadow_not_consumed"}:
        raise ValueError("summary_status_invalid")
    if enabled != (status == "offline_shadow_not_consumed"):
        raise ValueError("summary_enabled_status_mismatch")
    values: dict[str, Any] = {
        "enabled": enabled,
        "status": status,
    }
    for key, field in _SUMMARY_FIELDS.items():
        if key == "rejection_reason_counts":
            values[key] = _required_counter(diagnostics, field)
        else:
            values[key] = _required_nonnegative_int(
                diagnostics,
                field,
            )
    if values["generation_watermark_current"] > values[
        "generation_watermark_capacity"
    ]:
        raise ValueError("summary_watermark_capacity_exceeded")
    if values["generation_watermark_peak"] > values[
        "generation_watermark_capacity"
    ]:
        raise ValueError("summary_peak_watermark_capacity_exceeded")
    return values


def _evaluate_without_publications(
    metrics: dict[str, Any],
    *,
    summary_values: Mapping[str, Any] | None,
    summary_reason: str,
) -> None:
    record_reason = (
        "d1_centroid_overlay_shadow_capability_not_recorded"
        if summary_values is None
        else (
            "d1_centroid_overlay_shadow_disabled"
            if summary_values["enabled"] is False
            else "no_d1_centroid_overlay_shadow_evaluations"
        )
    )
    if summary_values is None:
        _mark_record_metrics_unavailable(
            metrics,
            summary_reason or record_reason,
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_summary_counter_consistent",
            summary_reason or record_reason,
        )
        return

    for source, field in (
        ("evaluation_count", "d1_centroid_overlay_shadow_evaluation_count"),
        ("decision_count", "d1_centroid_overlay_shadow_decision_count"),
        ("accepted_count", "d1_centroid_overlay_shadow_accepted_count"),
        ("rejected_count", "d1_centroid_overlay_shadow_rejected_count"),
        ("error_count", "d1_centroid_overlay_shadow_error_count"),
        (
            "rejection_reason_counts",
            "d1_centroid_overlay_shadow_rejection_reason_distribution_json",
        ),
        (
            "forbidden_mutation_count",
            "d1_centroid_overlay_shadow_forbidden_mutation_count",
        ),
        (
            "generation_watermark_peak",
            "d1_centroid_overlay_shadow_generation_watermark_peak",
        ),
        (
            "generation_watermark_capacity",
            "d1_centroid_overlay_shadow_generation_watermark_capacity",
        ),
        (
            "payload_bytes_peak",
            "d1_centroid_overlay_shadow_payload_bytes_peak",
        ),
        (
            "d2_consumption_count",
            "d1_centroid_overlay_shadow_d2_consumption_count",
        ),
        (
            "d3_consumption_count",
            "d1_centroid_overlay_shadow_d3_consumption_count",
        ),
    ):
        _put_available(metrics, field, summary_values[source])
    for field in (
        "d1_centroid_overlay_shadow_hash_pair_evaluable_count",
        "d1_centroid_overlay_shadow_sha_equal_count",
        "d1_centroid_overlay_shadow_sha_different_count",
        "d1_centroid_overlay_shadow_global_track_id_evaluable_count",
        "d1_centroid_overlay_shadow_global_track_id_unchanged_count",
        "d1_centroid_overlay_shadow_global_track_id_changed_count",
        "d1_centroid_overlay_shadow_forbidden_surface_violation_count",
        "d1_centroid_overlay_shadow_measurement_timestamp_publication_count",
        "d1_centroid_overlay_shadow_arrival_timestamp_publication_count",
        "d1_centroid_overlay_shadow_dual_timestamp_publication_count",
        "d1_centroid_overlay_shadow_measurement_timestamp_value_count",
        "d1_centroid_overlay_shadow_arrival_timestamp_value_count",
        "d1_centroid_overlay_shadow_online_truth_use_count",
    ):
        _put_unavailable(metrics, field, record_reason)
    for field in _PREPARATION_RECORD_METRIC_FIELDS:
        _put_unavailable(metrics, field, record_reason)
    summary_consistent = bool(
        summary_values["evaluation_count"] == 0
        and summary_values["decision_count"] == 0
        and summary_values["accepted_count"] == 0
        and summary_values["rejected_count"] == 0
        and summary_values["error_count"] == 0
        and not summary_values["rejection_reason_counts"]
        and summary_values["forbidden_mutation_count"] == 0
        and summary_values["generation_watermark_current"] == 0
        and summary_values["generation_watermark_peak"] == 0
        and summary_values["payload_bytes_peak"] == 0
        and summary_values["d2_consumption_count"] == 0
        and summary_values["d3_consumption_count"] == 0
    )
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_summary_counter_consistent",
        summary_consistent,
    )


def _summary_matches_records(
    summary: Mapping[str, Any],
    aggregates: Mapping[str, Any],
    records: Sequence[_ParsedShadowRecord],
) -> bool:
    expected = {
        "evaluation_count": len(records),
        "decision_count": aggregates[
            "d1_centroid_overlay_shadow_decision_count"
        ],
        "accepted_count": aggregates[
            "d1_centroid_overlay_shadow_accepted_count"
        ],
        "rejected_count": aggregates[
            "d1_centroid_overlay_shadow_rejected_count"
        ],
        "error_count": aggregates[
            "d1_centroid_overlay_shadow_error_count"
        ],
        "rejection_reason_counts": Counter(
            aggregates[
                "d1_centroid_overlay_shadow_rejection_reason_distribution_json"
            ]
        ),
        "forbidden_mutation_count": aggregates[
            "d1_centroid_overlay_shadow_forbidden_mutation_count"
        ],
        "generation_watermark_current": records[-1].watermark_count,
        "generation_watermark_peak": aggregates[
            "d1_centroid_overlay_shadow_generation_watermark_peak"
        ],
        "generation_watermark_capacity": aggregates[
            "d1_centroid_overlay_shadow_generation_watermark_capacity"
        ],
        "payload_bytes_peak": aggregates[
            "d1_centroid_overlay_shadow_payload_bytes_peak"
        ],
        "d2_consumption_count": aggregates[
            "d1_centroid_overlay_shadow_d2_consumption_count"
        ],
        "d3_consumption_count": aggregates[
            "d1_centroid_overlay_shadow_d3_consumption_count"
        ],
    }
    if summary["enabled"] is not True:
        return False
    if summary["status"] != "offline_shadow_not_consumed":
        return False
    for key, value in expected.items():
        if key == "rejection_reason_counts":
            if Counter(summary[key]) != value:
                return False
        elif summary[key] != value:
            return False
    return True


def _extract_overhead_metrics(
    metrics: dict[str, Any],
    stage_timings: Mapping[str, Mapping[str, Any]] | None,
    *,
    publication_count: int,
    stage_unavailable_reason: str | None,
) -> str | None:
    if not isinstance(stage_timings, Mapping):
        reason = stage_unavailable_reason or "stage_timings_missing"
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_overhead_stage_consistent",
            reason,
        )
        return reason
    stage = stage_timings.get(D1_CENTROID_OVERLAY_SHADOW_TIMING_STAGE)
    if not isinstance(stage, Mapping):
        reason = (
            f"stage_not_reported:{D1_CENTROID_OVERLAY_SHADOW_TIMING_STAGE}"
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_overhead_stage_consistent",
            reason,
        )
        return reason
    call_count = stage.get("call_count")
    if not _is_nonnegative_int(call_count) or int(call_count) != int(
        publication_count
    ):
        reason = "shadow_stage_call_count_mismatch"
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_overhead_stage_consistent",
            False,
        )
        return reason
    if stage.get("distribution_available") is not True:
        reason = str(
            stage.get("distribution_unavailable_reason")
            or "shadow_stage_distribution_unavailable"
        )
        _put_unavailable(
            metrics,
            "d1_centroid_overlay_shadow_overhead_stage_consistent",
            reason,
        )
        return reason
    values = (
        stage.get("p50_wall_time_ms"),
        stage.get("p95_wall_time_ms"),
        stage.get("max_wall_time_ms"),
    )
    if not all(_is_nonnegative_finite(value) for value in values):
        reason = "shadow_stage_quantile_missing_or_invalid"
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_overhead_stage_consistent",
            False,
        )
        return reason
    p50, p95, maximum = (float(value) for value in values)
    if p50 > p95 or p95 > maximum:
        reason = "shadow_stage_quantile_order_invalid"
        _put_available(
            metrics,
            "d1_centroid_overlay_shadow_overhead_stage_consistent",
            False,
        )
        return reason
    expected = tuple(float(metrics[field]) for field in _OVERHEAD_FIELDS)
    consistent = all(
        math.isclose(observed, expected_value, rel_tol=1.0e-9, abs_tol=1.0e-6)
        for observed, expected_value in zip((p50, p95, maximum), expected)
    )
    _put_available(
        metrics,
        "d1_centroid_overlay_shadow_overhead_stage_consistent",
        consistent,
    )
    return None if consistent else "shadow_stage_quantile_mismatch"


def _mark_all_unavailable(metrics: dict[str, Any], reason: str) -> None:
    for field in (
        "d1_centroid_overlay_shadow_enabled",
        "d1_centroid_overlay_shadow_status",
        "d1_centroid_overlay_shadow_publication_count",
        *_RECORD_METRIC_FIELDS,
        *_PREPARATION_RECORD_METRIC_FIELDS,
        "d1_centroid_overlay_shadow_generation_watermark_current",
        *_OVERHEAD_FIELDS,
        "d1_centroid_overlay_shadow_overhead_stage_consistent",
        "d1_centroid_overlay_shadow_summary_counter_consistent",
        "d1_centroid_overlay_shadow_business_nonintervention_criteria_json",
        "d1_centroid_overlay_shadow_business_nonintervention_passed",
        "d1_centroid_overlay_shadow_semantics_json",
    ):
        _put_unavailable(metrics, field, reason)


def _mark_record_metrics_unavailable(
    metrics: dict[str, Any],
    reason: str,
) -> None:
    for field in (*_RECORD_METRIC_FIELDS, *_PREPARATION_RECORD_METRIC_FIELDS):
        _put_unavailable(metrics, field, reason)


def _mark_absent_preparation_metrics_unavailable(
    metrics: dict[str, Any],
    records: Sequence[_ParsedShadowRecord],
) -> None:
    integrity_present = any(
        item.preparation_audit.integrity_matches is not None
        for item in records
    )
    atomic_present = any(
        item.preparation_audit.execution_mode
        == D1_CENTROID_OVERLAY_SHADOW_ATOMIC_EXECUTION_MODE
        for item in records
    )
    for field in _PREPARATION_RECORD_METRIC_FIELDS:
        if field in metrics:
            continue
        reason = (
            "atomic_overlay_records_not_present"
            if field in _ATOMIC_ONLY_METRIC_FIELDS and not atomic_present
            else "preparation_integrity_evidence_not_present"
            if field
            in {
                "d1_centroid_overlay_shadow_integrity_check_passed_count",
                "d1_centroid_overlay_shadow_integrity_check_failed_count",
            }
            and not integrity_present
            else "preparation_audit_metric_not_evaluable"
        )
        _put_unavailable(metrics, field, reason)


def _mark_overhead_unavailable(
    metrics: dict[str, Any],
    reason: str,
) -> None:
    for field in _OVERHEAD_FIELDS:
        _put_unavailable(metrics, field, reason)
    _put_unavailable(
        metrics,
        "d1_centroid_overlay_shadow_overhead_stage_consistent",
        reason,
    )


def _semantics() -> dict[str, str]:
    return {
        "canonical_shadow_sha_relation": (
            "describes whether the detached experimental shadow DTO differs "
            "from the canonical publication DTO"
        ),
        "shadow_difference_business_effect": (
            "a different shadow SHA is not evidence that the canonical D1 "
            "publication or any D2/D3 input changed"
        ),
        "business_nonintervention": (
            "requires summary/log agreement, unchanged global-track identity "
            "sequence, no forbidden canonical-surface violation, no canonical "
            "business-track replacement, zero D2/D3 consumption, and zero "
            "online truth use"
        ),
        "control_authority": "none; metrics consume persisted logs only",
        "preparation_compatibility": (
            "runtime v1 records without preparation evidence remain explicit "
            "legacy-uninstrumented evidence; legacy prepared-handle records "
            "retain their exact five-field contract"
        ),
        "atomic_execution_mode": (
            "atomic preparation, post-integrity, work, materialization, and "
            "failure evidence is accepted only with the explicit "
            "atomic_experimental_offline_v1 mode marker"
        ),
        "missing_atomic_evidence": (
            "atomic metrics are unavailable when atomic records are absent; "
            "missing evidence is never backfilled with zero"
        ),
        "atomic_failure_authority": (
            "D6 reports valid fail-closed atomic failures but cannot alter "
            "D1 state, publication, assignment, or guidance"
        ),
        "performance_admission": (
            "requires an explicitly paired control episode and is independent "
            "from business nonintervention"
        ),
        "overall_admission": (
            "D6 does not admit A2 from mutation, identity, or timing evidence "
            "alone; accepted treatment and outcome evidence remain separate"
        ),
    }


def _digest_manifest_sha256(
    canonical_tracks_sha256: str,
    evidence_sha256: str,
) -> str:
    prefixes = {
        value.startswith("sha256:")
        for value in (canonical_tracks_sha256, evidence_sha256)
    }
    if len(prefixes) != 1:
        raise ValueError("digest_manifest_hash_prefix_mismatch")
    payload = {
        "canonical_tracks_sha256": canonical_tracks_sha256,
        "structural_ambiguity_evidence_sha256": evidence_sha256,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return f"sha256:{digest}" if True in prefixes else digest


def _percentile(ordered: Sequence[float], percentile: float) -> float:
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * float(percentile) / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(
        ordered[lower] * (1.0 - fraction)
        + ordered[upper] * fraction
    )


def _required_sha256(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field}_missing_or_invalid")
    return value


def _optional_sha256(
    payload: Mapping[str, Any],
    field: str,
) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field}_invalid")
    return value


def _required_bool(payload: Mapping[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field}_missing_or_invalid")
    return value


def _required_nonnegative_int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if not _is_nonnegative_int(value):
        raise ValueError(f"{field}_missing_or_invalid")
    return int(value)


def _required_positive_int(payload: Mapping[str, Any], field: str) -> int:
    value = _required_nonnegative_int(payload, field)
    if value <= 0:
        raise ValueError(f"{field}_missing_or_invalid")
    return value


def _required_nonnegative_float(
    payload: Mapping[str, Any],
    field: str,
) -> float:
    value = payload.get(field)
    if not _is_nonnegative_finite(value):
        raise ValueError(f"{field}_missing_or_invalid")
    return float(value)


def _required_nonempty_string(
    payload: Mapping[str, Any],
    field: str,
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_missing_or_invalid")
    return value.strip()


def _optional_nonempty_string(
    payload: Mapping[str, Any],
    field: str,
) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_invalid")
    return value.strip()


def _require_exact_fields(
    payload: Mapping[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(str(item) for item in actual - expected)
        detail = []
        if missing:
            detail.append(f"missing={','.join(missing)}")
        if unexpected:
            detail.append(f"unexpected={','.join(unexpected)}")
        raise ValueError(
            f"{context}_fields_invalid"
            + (f":{';'.join(detail)}" if detail else "")
        )


def _required_counter(
    payload: Mapping[str, Any],
    field: str,
) -> Counter[str]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field}_missing_or_invalid")
    counter: Counter[str] = Counter()
    for key, count in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field}_key_invalid")
        if not _is_nonnegative_int(count):
            raise ValueError(f"{field}_count_invalid")
        counter[key.strip()] = int(count)
    return counter


def _required_timestamp_array(
    payload: Mapping[str, Any],
    field: str,
) -> list[float]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ValueError(f"{field}_missing_or_invalid")
    parsed: list[float] = []
    for item in value:
        if not _is_nonnegative_finite(item):
            raise ValueError(f"{field}_value_invalid")
        parsed.append(float(item))
    if parsed != sorted(set(parsed)):
        raise ValueError(f"{field}_not_sorted_unique")
    return parsed


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_nonnegative_finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _is_positive_finite(value: Any) -> bool:
    return _is_nonnegative_finite(value) and float(value) > 0.0


def _put_available(metrics: dict[str, Any], field: str, value: Any) -> None:
    metrics[field] = value
    metrics[f"{field}_availability"] = "available"
    metrics[f"{field}_unavailable_reason"] = None


def _put_unavailable(
    metrics: dict[str, Any],
    field: str,
    reason: str,
) -> None:
    metrics[field] = None
    metrics[f"{field}_availability"] = "unavailable"
    metrics[f"{field}_unavailable_reason"] = str(reason)


__all__ = [
    "D1_CENTROID_OVERLAY_SHADOW_ATOMIC_EXECUTION_MODE",
    "D1_CENTROID_OVERLAY_SHADOW_DIGEST_SEMANTICS",
    "D1_CENTROID_OVERLAY_SHADOW_EVALUATION_SCHEMA",
    "D1_CENTROID_OVERLAY_SHADOW_EXECUTION_MODE_FIELD",
    "D1_CENTROID_OVERLAY_SHADOW_LEGACY_EXECUTION_MODE",
    "D1_CENTROID_OVERLAY_SHADOW_LEGACY_UNINSTRUMENTED_EXECUTION_MODE",
    "D1_CENTROID_OVERLAY_SHADOW_MAX_WALL_TIME_OVERHEAD_RATIO",
    "D1_CENTROID_OVERLAY_SHADOW_NUMERIC_METRIC_FIELDS",
    "D1_CENTROID_OVERLAY_SHADOW_PREPARATION_AUDIT_SCHEMA",
    "D1_CENTROID_OVERLAY_SHADOW_RUNTIME_SCHEMA",
    "D1_CENTROID_OVERLAY_SHADOW_TIMING_STAGE",
    "D1_CENTROID_OVERLAY_SHADOW_TOPIC",
    "D1CentroidOverlayShadowEvidence",
    "D1CentroidOverlayShadowPairPerformanceEvidence",
    "evaluate_d1_centroid_overlay_shadow_evidence",
    "evaluate_d1_centroid_overlay_shadow_pair_performance",
]
