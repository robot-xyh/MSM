from __future__ import annotations

import copy
import hashlib
import json

import pytest

from d6_evaluation_metrics.d1_centroid_overlay_shadow import (
    D1_CENTROID_OVERLAY_SHADOW_ATOMIC_EXECUTION_MODE,
    D1_CENTROID_OVERLAY_SHADOW_EXECUTION_MODE_FIELD,
    D1_CENTROID_OVERLAY_SHADOW_LEGACY_EXECUTION_MODE,
    D1_CENTROID_OVERLAY_SHADOW_LEGACY_UNINSTRUMENTED_EXECUTION_MODE,
    D1_CENTROID_OVERLAY_SHADOW_RUNTIME_SCHEMA,
    D1_CENTROID_OVERLAY_SHADOW_TIMING_STAGE,
    D1_CENTROID_OVERLAY_SHADOW_TOPIC,
    evaluate_d1_centroid_overlay_shadow_evidence,
    evaluate_d1_centroid_overlay_shadow_pair_performance,
)


def _record(
    sequence: int,
    *,
    accepted: bool,
    watermark_count: int,
    payload_bytes: int,
    d2_consumption_count: int = 0,
    d3_consumption_count: int = 0,
    online_truth_use_count: int = 0,
) -> dict[str, object]:
    measurement = 0.4 + sequence * 0.1
    arrival = measurement + 0.2
    reason = None if accepted else "oosm_scan"
    decision = {
        "decision": "accepted" if accepted else "rejected",
        "reject_reason": reason,
        "measurement_timestamp": measurement,
        "arrival_timestamp": arrival,
    }
    canonical_hash = "a" * 64 if accepted else "b" * 64
    shadow_hash = "c" * 64 if accepted else canonical_hash
    identity_hash = "d" * 64
    evidence_hash = "e" * 64
    forbidden_hash = _digest_manifest(canonical_hash, evidence_hash)
    return {
        "sequence": sequence,
        "topic": D1_CENTROID_OVERLAY_SHADOW_TOPIC,
        "source": "main",
        "timestamp": arrival,
        "schema_version": D1_CENTROID_OVERLAY_SHADOW_RUNTIME_SCHEMA,
        "payload": {
            "timestamp": arrival,
            "posterior_generation": sequence,
            "status": "offline_shadow_not_consumed",
            "base_publication_revision": f"epoch:posterior:{sequence:08d}",
            "overlay_valid_for_publication_id": f"shadow:{sequence:08d}",
            "canonical_track_count": 2,
            "shadow_track_count": 2,
            "evidence_count": 1,
            "decision_count": 1,
            "accepted_count": int(accepted),
            "rejected_count": int(not accepted),
            "rejection_reason_counts": (
                {} if accepted else {"oosm_scan": 1}
            ),
            "evaluation_error": None,
            "canonical_tracks_sha256": canonical_hash,
            "shadow_tracks_sha256": shadow_hash,
            "shadow_differs_from_canonical": accepted,
            "canonical_global_track_ids_sha256": identity_hash,
            "shadow_global_track_ids_sha256": identity_hash,
            "global_track_id_sequence_unchanged": True,
            "decisions": [decision],
            "forbidden_mutation_audit": {
                "digest_semantics": (
                    "sha256_of_canonical_track_and_evidence_digest_manifest_v1"
                ),
                "before_sha256": forbidden_hash,
                "after_sha256": forbidden_hash,
                "canonical_tracks_before_sha256": canonical_hash,
                "canonical_tracks_after_sha256": canonical_hash,
                "structural_ambiguity_evidence_before_sha256": evidence_hash,
                "structural_ambiguity_evidence_after_sha256": evidence_hash,
                "passed": True,
                "filter_adapter_reference_passed_to_prototype": False,
                "history_reference_passed_to_prototype": False,
                "checkpoint_reference_passed_to_prototype": False,
                "replay_cache_reference_passed_to_prototype": False,
                "scan_watermark_reference_passed_to_prototype": False,
                "canonical_business_tracks_replaced": False,
                "d2_consumption_count": d2_consumption_count,
                "d3_consumption_count": d3_consumption_count,
            },
            "bounded_memory_audit": {
                "generation_watermark_count": watermark_count,
                "generation_watermark_capacity": 8,
                "shadow_track_payload_bytes": payload_bytes,
            },
            "measurement_timestamps": [measurement],
            "arrival_timestamps": [arrival],
            "evaluation_wall_time_ms": float(sequence),
            "online_truth_use_count": online_truth_use_count,
        },
    }


def _digest_manifest(canonical_hash: str, evidence_hash: str) -> str:
    canonical = json.dumps(
        {
            "canonical_tracks_sha256": canonical_hash,
            "structural_ambiguity_evidence_sha256": evidence_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _summary(
    *,
    evaluation_count: int = 2,
    decision_count: int = 2,
    accepted_count: int = 1,
    rejected_count: int = 1,
    error_count: int = 0,
    rejection_reason_counts: dict[str, int] | None = None,
    current_watermark: int = 2,
    peak_watermark: int = 2,
    payload_bytes_peak: int = 480,
    d2_consumption_count: int = 0,
    d3_consumption_count: int = 0,
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "module_final_diagnostics": {
            "observation_governance": {
                "d1_centroid_publication_overlay_shadow_enabled": enabled,
                "d1_centroid_publication_overlay_shadow_status": (
                    "offline_shadow_not_consumed" if enabled else "disabled"
                ),
                "d1_centroid_overlay_shadow_evaluation_count": evaluation_count,
                "d1_centroid_overlay_shadow_decision_count": decision_count,
                "d1_centroid_overlay_shadow_accepted_count": accepted_count,
                "d1_centroid_overlay_shadow_rejected_count": rejected_count,
                "d1_centroid_overlay_shadow_error_count": error_count,
                "d1_centroid_overlay_shadow_rejection_reason_counts": (
                    {"oosm_scan": 1}
                    if rejection_reason_counts is None
                    else rejection_reason_counts
                ),
                "d1_centroid_overlay_shadow_forbidden_mutation_count": 0,
                "d1_centroid_overlay_shadow_watermark_count": (
                    current_watermark
                ),
                "d1_centroid_overlay_shadow_max_watermark_count": (
                    peak_watermark
                ),
                "d1_centroid_overlay_shadow_watermark_capacity": 8,
                "d1_centroid_overlay_shadow_max_payload_bytes": (
                    payload_bytes_peak
                ),
                "d1_centroid_overlay_shadow_d2_consumption_count": (
                    d2_consumption_count
                ),
                "d1_centroid_overlay_shadow_d3_consumption_count": (
                    d3_consumption_count
                ),
            }
        }
    }


def _timings(
    *,
    call_count: int = 2,
    distribution_available: bool = True,
) -> dict[str, dict[str, object]]:
    if call_count == 2:
        p50, p95, maximum = 1.5, 1.95, 2.0
    elif call_count == 3:
        p50, p95, maximum = 2.0, 2.9, 3.0
    else:
        p50 = p95 = maximum = 1.0
    return {
        D1_CENTROID_OVERLAY_SHADOW_TIMING_STAGE: {
            "call_count": call_count,
            "wall_time_s": 0.004,
            "mean_wall_time_ms": 2.0,
            "p50_wall_time_ms": p50 if distribution_available else None,
            "p95_wall_time_ms": p95 if distribution_available else None,
            "max_wall_time_ms": maximum if distribution_available else None,
            "distribution_available": distribution_available,
            "distribution_unavailable_reason": (
                None
                if distribution_available
                else "legacy_stage_timing_distribution_values_absent"
            ),
        }
    }


def _evaluate(
    records: list[dict[str, object]],
    *,
    summary: dict[str, object] | None = None,
    timings: dict[str, dict[str, object]] | None = None,
):
    return evaluate_d1_centroid_overlay_shadow_evidence(
        records,
        _summary() if summary is None else summary,
        _timings() if timings is None else timings,
        online_unavailable_reason=None,
        stage_unavailable_reason=None,
    )


def _with_legacy_preparation(
    record: dict[str, object],
) -> dict[str, object]:
    payload = record["payload"]
    assert isinstance(payload, dict)
    track_count = int(payload["canonical_track_count"])
    payload["canonical_preparation"] = {
        "explicit_prepared_handle_used": True,
        "base_publication_digest": f"sha256:{'1' * 64}",
        "validation_error": None,
        "work": {
            "full_description_pass_count": 1,
            "track_count": track_count,
            "validated_track_count": track_count,
            "full_track_digest_count": track_count,
            "state_digest_count": track_count,
            "covariance_digest_count": track_count,
            "publication_digest_count": 1,
        },
        "evaluation_integrity_check": {
            "matches": True,
            "mismatch_reason": None,
            "object_binding_pass_count": 1,
            "full_content_digest_pass_count": 1,
            "track_digest_count": track_count,
        },
    }
    return record


def _with_atomic_preparation(
    record: dict[str, object],
    *,
    integrity_matches: bool = True,
    atomic_failure_reason: str | None = None,
    provisional_shadow_work: bool = False,
) -> dict[str, object]:
    payload = record["payload"]
    assert isinstance(payload, dict)
    track_count = int(payload["canonical_track_count"])
    accepted_count = int(payload["accepted_count"])
    materialized = accepted_count > 0 and atomic_failure_reason is None
    if atomic_failure_reason is not None:
        assert accepted_count == 0
    if materialized or provisional_shadow_work:
        shadow_copies = track_count
        shadow_digests = track_count
        shadow_publication_digests = 1
    else:
        shadow_copies = 0
        shadow_digests = 0
        shadow_publication_digests = 0
    post_track_digests = track_count if integrity_matches else 1
    base_digest = f"sha256:{'2' * 64}"
    payload[D1_CENTROID_OVERLAY_SHADOW_EXECUTION_MODE_FIELD] = (
        D1_CENTROID_OVERLAY_SHADOW_ATOMIC_EXECUTION_MODE
    )
    payload["canonical_preparation"] = {
        "prepared_publication": {
            "prototype_status": (
                "experimental_design_prototype_not_online_schema"
            ),
            "usage_scope": "experimental_offline_atomic_only",
            "base_publication_digest": base_digest,
            "validation_error": None,
            "track_count": track_count,
            "work": {
                "full_description_pass_count": 1,
                "track_count": track_count,
                "validated_track_count": track_count,
                "full_track_digest_count": track_count,
                "state_digest_count": track_count,
                "covariance_digest_count": track_count,
                "publication_digest_count": 1,
            },
        },
        "post_integrity_check": {
            "matches": integrity_matches,
            "mismatch_reason": (
                None
                if integrity_matches
                else "track_content_digest_mismatch"
            ),
            "object_binding_pass_count": 1,
            "full_content_digest_pass_count": 1,
            "track_digest_count": post_track_digests,
        },
        "canonical_publication_digest": base_digest,
        "shadow_publication_digest": (
            f"sha256:{'3' * 64}" if materialized else None
        ),
        "shadow_materialized": materialized,
        "work": {
            "canonical_full_description_pass_count": 1,
            "canonical_description_track_digest_count": track_count,
            "canonical_post_integrity_pass_count": 1,
            "canonical_post_integrity_track_digest_count": (
                post_track_digests
            ),
            "shadow_track_copy_count": shadow_copies,
            "shadow_full_track_digest_count": shadow_digests,
            "shadow_publication_digest_count": (
                shadow_publication_digests
            ),
        },
        "atomic_failure_reason": atomic_failure_reason,
    }
    return record


def _one_record_summary(
    *,
    accepted: bool,
    rejection_reason_counts: dict[str, int] | None = None,
    error_count: int = 0,
) -> dict[str, object]:
    return _summary(
        evaluation_count=1,
        decision_count=1,
        accepted_count=int(accepted),
        rejected_count=int(not accepted),
        error_count=error_count,
        rejection_reason_counts=(
            {} if accepted else rejection_reason_counts or {"oosm_scan": 1}
        ),
        current_watermark=1,
        peak_watermark=1,
        payload_bytes_peak=420,
    )


def test_shadow_difference_is_separate_from_business_nonintervention() -> None:
    evidence = _evaluate(
        [
            _record(1, accepted=True, watermark_count=1, payload_bytes=420),
            _record(2, accepted=False, watermark_count=2, payload_bytes=480),
        ]
    )
    metrics = evidence.metrics

    assert evidence.failure_reasons == ()
    assert metrics["d1_centroid_overlay_shadow_sha_equal_count"] == 1
    assert metrics["d1_centroid_overlay_shadow_sha_different_count"] == 1
    assert (
        metrics[
            "d1_centroid_overlay_shadow_global_track_id_unchanged_count"
        ]
        == 2
    )
    assert metrics["d1_centroid_overlay_shadow_accepted_count"] == 1
    assert metrics["d1_centroid_overlay_shadow_rejected_count"] == 1
    assert metrics[
        "d1_centroid_overlay_shadow_rejection_reason_distribution_json"
    ] == {"oosm_scan": 1}
    assert (
        metrics["d1_centroid_overlay_shadow_dual_timestamp_publication_count"]
        == 2
    )
    assert metrics["d1_centroid_overlay_shadow_overhead_p50_ms"] == 1.5
    assert metrics["d1_centroid_overlay_shadow_overhead_p95_ms"] == 1.95
    assert metrics["d1_centroid_overlay_shadow_overhead_max_ms"] == 2.0
    assert metrics[
        "d1_centroid_overlay_shadow_overhead_stage_consistent"
    ] is True
    assert (
        metrics[
            "d1_centroid_overlay_shadow_business_nonintervention_passed"
        ]
        is True
    )
    criteria = metrics[
        "d1_centroid_overlay_shadow_business_nonintervention_criteria_json"
    ]
    assert criteria["shadow_sha_difference_is_not_business_output_change"] is True
    assert criteria["d2_consumption_count"] == 0
    assert criteria["d3_consumption_count"] == 0


def test_missing_timestamp_field_is_unavailable_not_zero() -> None:
    records = [
        _record(1, accepted=True, watermark_count=1, payload_bytes=420),
        _record(2, accepted=False, watermark_count=2, payload_bytes=480),
    ]
    del records[0]["payload"]["arrival_timestamps"]  # type: ignore[index]

    evidence = _evaluate(records)

    metric = "d1_centroid_overlay_shadow_dual_timestamp_publication_count"
    assert evidence.metrics[metric] is None
    assert evidence.metrics[f"{metric}_availability"] == "unavailable"
    assert "arrival_timestamps_missing_or_invalid" in evidence.metrics[
        f"{metric}_unavailable_reason"
    ]
    assert any(
        reason.startswith("d1_centroid_overlay_shadow_record_invalid:")
        for reason in evidence.failure_reasons
    )


def test_nonzero_d2_consumption_fails_business_nonintervention() -> None:
    records = [
        _record(
            1,
            accepted=True,
            watermark_count=1,
            payload_bytes=420,
            d2_consumption_count=1,
        ),
        _record(2, accepted=False, watermark_count=2, payload_bytes=480),
    ]
    summary = _summary(d2_consumption_count=1)

    evidence = _evaluate(records, summary=summary)

    assert evidence.metrics[
        "d1_centroid_overlay_shadow_d2_consumption_count"
    ] == 1
    assert evidence.metrics[
        "d1_centroid_overlay_shadow_summary_counter_consistent"
    ] is True
    assert evidence.metrics[
        "d1_centroid_overlay_shadow_business_nonintervention_passed"
    ] is False
    assert "d1_centroid_overlay_shadow_d2_consumption_nonzero" in (
        evidence.failure_reasons
    )


def test_wrong_schema_fails_closed() -> None:
    records = [
        _record(1, accepted=True, watermark_count=1, payload_bytes=420),
        _record(2, accepted=False, watermark_count=2, payload_bytes=480),
    ]
    records[0]["schema_version"] = "unknown-shadow-v9"

    evidence = _evaluate(records)

    metric = "d1_centroid_overlay_shadow_accepted_count"
    assert evidence.metrics[metric] is None
    assert evidence.metrics[f"{metric}_availability"] == "unavailable"
    assert "unsupported_schema" in evidence.metrics[
        f"{metric}_unavailable_reason"
    ]


def test_summary_mismatch_is_explicit_and_blocks_nonintervention() -> None:
    records = [
        _record(1, accepted=True, watermark_count=1, payload_bytes=420),
        _record(2, accepted=False, watermark_count=2, payload_bytes=480),
    ]
    summary = _summary(accepted_count=2)

    evidence = _evaluate(records, summary=summary)

    assert evidence.metrics[
        "d1_centroid_overlay_shadow_summary_counter_consistent"
    ] is False
    assert evidence.metrics[
        "d1_centroid_overlay_shadow_business_nonintervention_passed"
    ] is False
    assert "d1_centroid_overlay_shadow_summary_counter_mismatch" in (
        evidence.failure_reasons
    )


def test_missing_stage_distribution_keeps_record_timing_but_blocks_crosscheck() -> None:
    records = [
        _record(1, accepted=True, watermark_count=1, payload_bytes=420),
        _record(2, accepted=False, watermark_count=2, payload_bytes=480),
    ]

    evidence = _evaluate(
        records,
        timings=_timings(distribution_available=False),
    )

    metric = "d1_centroid_overlay_shadow_overhead_p95_ms"
    assert evidence.metrics[metric] == 1.95
    assert evidence.metrics[f"{metric}_availability"] == "available"
    assert evidence.metrics[
        "d1_centroid_overlay_shadow_overhead_stage_consistent"
    ] is None
    assert any(
        reason.startswith(
            "d1_centroid_overlay_shadow_overhead_unavailable:"
        )
        for reason in evidence.failure_reasons
    )


def test_absent_legacy_capability_remains_unavailable_without_failure() -> None:
    evidence = evaluate_d1_centroid_overlay_shadow_evidence(
        [],
        {"module_final_diagnostics": {"schema_version": "legacy-v1"}},
        {},
        online_unavailable_reason=None,
        stage_unavailable_reason=None,
    )

    metric = "d1_centroid_overlay_shadow_accepted_count"
    assert evidence.metrics[metric] is None
    assert evidence.metrics[f"{metric}_availability"] == "unavailable"
    assert evidence.failure_reasons == ()


def test_explicit_disabled_summary_preserves_observed_zero_counts() -> None:
    summary = _summary(
        evaluation_count=0,
        decision_count=0,
        accepted_count=0,
        rejected_count=0,
        rejection_reason_counts={},
        current_watermark=0,
        peak_watermark=0,
        payload_bytes_peak=0,
        enabled=False,
    )

    evidence = _evaluate([], summary=summary, timings={})

    assert evidence.metrics["d1_centroid_overlay_shadow_enabled"] is False
    assert evidence.metrics[
        "d1_centroid_overlay_shadow_accepted_count"
    ] == 0
    assert evidence.metrics[
        "d1_centroid_overlay_shadow_sha_equal_count"
    ] is None
    assert evidence.metrics[
        "d1_centroid_overlay_shadow_business_nonintervention_passed"
    ] is None
    assert evidence.failure_reasons == ()


def test_evaluation_error_is_counted_without_inventing_decision_timestamps() -> None:
    error_record = _record(
        3,
        accepted=False,
        watermark_count=3,
        payload_bytes=500,
    )
    payload = error_record["payload"]
    assert isinstance(payload, dict)
    payload["decision_count"] = 0
    payload["accepted_count"] = 0
    payload["rejected_count"] = 0
    payload["rejection_reason_counts"] = {}
    payload["decisions"] = []
    payload["evaluation_error"] = "ValueError:fixture"
    summary = _summary(
        evaluation_count=3,
        decision_count=2,
        error_count=1,
        current_watermark=3,
        peak_watermark=3,
        payload_bytes_peak=500,
    )
    records = [
        _record(1, accepted=True, watermark_count=1, payload_bytes=420),
        _record(2, accepted=False, watermark_count=2, payload_bytes=480),
        error_record,
    ]

    evidence = _evaluate(records, summary=summary, timings=_timings(call_count=3))

    assert evidence.metrics["d1_centroid_overlay_shadow_error_count"] == 1
    assert evidence.metrics[
        "d1_centroid_overlay_shadow_dual_timestamp_publication_count"
    ] == 3
    assert "d1_centroid_overlay_shadow_evaluation_error_nonzero" in (
        evidence.failure_reasons
    )


def test_pair_performance_gate_is_separate_from_nonintervention() -> None:
    evidence = _evaluate(
        [
            _record(1, accepted=True, watermark_count=1, payload_bytes=420),
            _record(2, accepted=False, watermark_count=2, payload_bytes=480),
        ]
    )
    identity = {
        "scenario_name": "nominal_200v200",
        "scenario_version": "nominal-v1",
        "seed": 1100,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }

    paired = evaluate_d1_centroid_overlay_shadow_pair_performance(
        {**identity, "wall_time_s": 10.732309815997723},
        {**identity, "wall_time_s": 17.86645007604966},
        evidence.metrics,
    )

    assert paired.metrics[
        "d1_centroid_overlay_shadow_pair_business_nonintervention_passed"
    ] is True
    assert paired.metrics[
        "d1_centroid_overlay_shadow_performance_gate_passed"
    ] is False
    assert paired.metrics[
        "d1_centroid_overlay_shadow_wall_time_overhead_ratio"
    ] > 0.66
    assert paired.metrics[
        "d1_centroid_overlay_shadow_overall_admitted"
    ] is False
    assert (
        "d1_centroid_overlay_shadow_performance_gate_failed"
        in paired.failure_reasons
    )
    assert (
        "outcome_effect_evidence_not_provided"
        in paired.metrics[
            "d1_centroid_overlay_shadow_admission_blockers_json"
        ]
    )
    no_treatment_metrics = dict(evidence.metrics)
    no_treatment_metrics["d1_centroid_overlay_shadow_accepted_count"] = 0
    no_treatment = evaluate_d1_centroid_overlay_shadow_pair_performance(
        {**identity, "wall_time_s": 10.732309815997723},
        {**identity, "wall_time_s": 17.86645007604966},
        no_treatment_metrics,
    )
    assert "no_accepted_treatment" in no_treatment.metrics[
        "d1_centroid_overlay_shadow_admission_blockers_json"
    ]


def test_input_records_are_not_mutated() -> None:
    records = [
        _record(1, accepted=True, watermark_count=1, payload_bytes=420),
        _record(2, accepted=False, watermark_count=2, payload_bytes=480),
    ]
    before = copy.deepcopy(records)

    _evaluate(records)

    assert records == before


def test_historical_prepared_handle_v1_remains_readable() -> None:
    record = _with_legacy_preparation(
        _record(1, accepted=True, watermark_count=1, payload_bytes=420)
    )

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(accepted=True),
        timings=_timings(call_count=1),
    )

    metrics = evidence.metrics
    assert evidence.failure_reasons == ()
    assert metrics[
        "d1_centroid_overlay_shadow_execution_mode_distribution_json"
    ] == {D1_CENTROID_OVERLAY_SHADOW_LEGACY_EXECUTION_MODE: 1}
    assert metrics[
        "d1_centroid_overlay_shadow_legacy_prepared_handle_count"
    ] == 1
    assert metrics[
        "d1_centroid_overlay_shadow_preparation_audit_evaluable_count"
    ] == 1
    assert metrics[
        "d1_centroid_overlay_shadow_integrity_check_passed_count"
    ] == 1
    atomic_metric = "d1_centroid_overlay_shadow_atomic_failure_count"
    assert metrics[atomic_metric] is None
    assert metrics[f"{atomic_metric}_availability"] == "unavailable"
    assert metrics[f"{atomic_metric}_unavailable_reason"] == (
        "atomic_overlay_records_not_present"
    )


def test_historical_uninstrumented_v1_does_not_invent_atomic_zeroes() -> None:
    record = _record(
        1,
        accepted=False,
        watermark_count=1,
        payload_bytes=420,
    )

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(accepted=False),
        timings=_timings(call_count=1),
    )

    metrics = evidence.metrics
    assert evidence.failure_reasons == ()
    assert metrics[
        "d1_centroid_overlay_shadow_execution_mode_distribution_json"
    ] == {
        D1_CENTROID_OVERLAY_SHADOW_LEGACY_UNINSTRUMENTED_EXECUTION_MODE: 1
    }
    assert metrics[
        "d1_centroid_overlay_shadow_preparation_audit_evaluable_count"
    ] == 0
    assert metrics[
        "d1_centroid_overlay_shadow_preparation_audit_unavailable_count"
    ] == 1
    integrity_metric = (
        "d1_centroid_overlay_shadow_integrity_check_passed_count"
    )
    assert metrics[integrity_metric] is None
    assert metrics[f"{integrity_metric}_availability"] == "unavailable"
    atomic_work_metric = (
        "d1_centroid_overlay_shadow_atomic_shadow_track_copy_count"
    )
    assert metrics[atomic_work_metric] is None
    assert metrics[f"{atomic_work_metric}_availability"] == "unavailable"


def test_atomic_accepted_record_reports_strict_work_and_materialization() -> None:
    record = _with_atomic_preparation(
        _record(1, accepted=True, watermark_count=1, payload_bytes=420)
    )

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(accepted=True),
        timings=_timings(call_count=1),
    )

    metrics = evidence.metrics
    assert evidence.failure_reasons == ()
    assert metrics["d1_centroid_overlay_shadow_atomic_count"] == 1
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_materialized_count"
    ] == 1
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_canonical_description_pass_count"
    ] == 1
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_canonical_description_track_digest_count"
    ] == 2
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_post_integrity_pass_count"
    ] == 1
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_post_integrity_track_digest_count"
    ] == 2
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_track_copy_count"
    ] == 2
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_full_track_digest_count"
    ] == 2
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_publication_digest_count"
    ] == 1


def test_atomic_rejected_record_proves_no_shadow_work() -> None:
    record = _with_atomic_preparation(
        _record(1, accepted=False, watermark_count=1, payload_bytes=420)
    )

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(accepted=False),
        timings=_timings(call_count=1),
    )

    metrics = evidence.metrics
    assert evidence.failure_reasons == ()
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_materialized_count"
    ] == 0
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_track_copy_count"
    ] == 0
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_full_track_digest_count"
    ] == 0
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_publication_digest_count"
    ] == 0


def test_atomic_post_integrity_failure_is_readable_and_flagged() -> None:
    record = _record(
        1,
        accepted=False,
        watermark_count=1,
        payload_bytes=420,
    )
    payload = record["payload"]
    assert isinstance(payload, dict)
    decision = payload["decisions"][0]
    assert isinstance(decision, dict)
    decision["reject_reason"] = "prepared_canonical_publication_mismatch"
    payload["rejection_reason_counts"] = {
        "prepared_canonical_publication_mismatch": 1
    }
    payload["evaluation_error"] = (
        "RuntimeError:post_integrity_mismatch:"
        "track_content_digest_mismatch"
    )
    _with_atomic_preparation(
        record,
        integrity_matches=False,
        atomic_failure_reason=(
            "post_integrity_mismatch:track_content_digest_mismatch"
        ),
        provisional_shadow_work=True,
    )

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(
            accepted=False,
            rejection_reason_counts={
                "prepared_canonical_publication_mismatch": 1
            },
            error_count=1,
        ),
        timings=_timings(call_count=1),
    )

    metrics = evidence.metrics
    assert metrics[
        "d1_centroid_overlay_shadow_integrity_check_failed_count"
    ] == 1
    assert metrics["d1_centroid_overlay_shadow_atomic_failure_count"] == 1
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_materialized_count"
    ] == 0
    assert metrics[
        "d1_centroid_overlay_shadow_atomic_shadow_track_copy_count"
    ] == 2
    assert (
        "d1_centroid_overlay_shadow_preparation_integrity_failed"
        in evidence.failure_reasons
    )
    assert (
        "d1_centroid_overlay_shadow_atomic_failure_reported"
        in evidence.failure_reasons
    )


@pytest.mark.parametrize(
    ("surface", "field"),
    [
        ("canonical_preparation", "post_integrity_check"),
        ("prepared_publication", "work"),
        ("post_integrity_check", "track_digest_count"),
        ("work", "canonical_post_integrity_pass_count"),
        ("canonical_preparation", "atomic_failure_reason"),
    ],
)
def test_atomic_missing_required_field_fails_closed(
    surface: str,
    field: str,
) -> None:
    record = _with_atomic_preparation(
        _record(1, accepted=True, watermark_count=1, payload_bytes=420)
    )
    payload = record["payload"]
    assert isinstance(payload, dict)
    preparation = payload["canonical_preparation"]
    assert isinstance(preparation, dict)
    if surface == "canonical_preparation":
        target = preparation
    else:
        target = preparation[surface]
        assert isinstance(target, dict)
    del target[field]

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(accepted=True),
        timings=_timings(call_count=1),
    )

    metric = "d1_centroid_overlay_shadow_atomic_count"
    assert evidence.metrics[metric] is None
    assert evidence.metrics[f"{metric}_availability"] == "unavailable"
    assert any(
        reason.startswith("d1_centroid_overlay_shadow_record_invalid:")
        for reason in evidence.failure_reasons
    )


def test_atomic_shape_without_mode_marker_fails_closed() -> None:
    record = _with_atomic_preparation(
        _record(1, accepted=True, watermark_count=1, payload_bytes=420)
    )
    payload = record["payload"]
    assert isinstance(payload, dict)
    del payload[D1_CENTROID_OVERLAY_SHADOW_EXECUTION_MODE_FIELD]

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(accepted=True),
        timings=_timings(call_count=1),
    )

    assert any(
        "atomic_execution_mode_marker_missing" in reason
        for reason in evidence.failure_reasons
    )


def test_atomic_integrity_failure_reason_must_bind_mismatch() -> None:
    record = _record(
        1,
        accepted=False,
        watermark_count=1,
        payload_bytes=420,
    )
    _with_atomic_preparation(
        record,
        integrity_matches=False,
        atomic_failure_reason="post_integrity_mismatch:wrong_reason",
    )

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(accepted=False),
        timings=_timings(call_count=1),
    )

    assert any(
        "atomic_integrity_failure_reason_mismatch" in reason
        for reason in evidence.failure_reasons
    )


def test_mixed_legacy_and_atomic_preparation_shape_fails_closed() -> None:
    record = _with_atomic_preparation(
        _record(1, accepted=True, watermark_count=1, payload_bytes=420)
    )
    payload = record["payload"]
    assert isinstance(payload, dict)
    preparation = payload["canonical_preparation"]
    assert isinstance(preparation, dict)
    preparation["explicit_prepared_handle_used"] = True

    evidence = _evaluate(
        [record],
        summary=_one_record_summary(accepted=True),
        timings=_timings(call_count=1),
    )

    assert any(
        "atomic_canonical_preparation_fields_invalid" in reason
        for reason in evidence.failure_reasons
    )


def test_atomic_evaluation_does_not_mutate_nested_input() -> None:
    record = _with_atomic_preparation(
        _record(1, accepted=True, watermark_count=1, payload_bytes=420)
    )
    before = copy.deepcopy(record)

    _evaluate(
        [record],
        summary=_one_record_summary(accepted=True),
        timings=_timings(call_count=1),
    )

    assert record == before
