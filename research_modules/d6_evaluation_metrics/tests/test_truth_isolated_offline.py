from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.truth_isolated_offline import (
    D2_PARTIAL_IDENTITY_DENOMINATOR_DEFINITIONS,
    REFERENCE_SCALABLE_3D_SCALES,
    TruthIsolatedEpisodeContext,
    TruthIsolatedEvaluationError,
    TruthIsolatedOfflineReportGenerator,
    adapt_d1_offline_consistency,
    adapt_d2_scalable_3d_identity,
    aggregate_truth_isolated_episode_records,
    build_truth_isolated_episode_record,
)


def _sha(character: str) -> str:
    return f"sha256:{character * 64}"


def _canonical_sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _canonical_sha_with_newline(payload: object) -> str:
    encoded = (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _file_sha(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _resign_d1(payload: dict[str, object]) -> None:
    payload.pop("content_digest", None)
    payload["content_digest"] = _canonical_sha(payload)


def _available_metric(value: float, sample_count: int = 2) -> dict[str, object]:
    return {
        "available": True,
        "value": value,
        "sample_count": sample_count,
        "reason": None,
    }


def _unavailable_metric(reason: str) -> dict[str, object]:
    return {
        "available": False,
        "value": None,
        "sample_count": 0,
        "reason": reason,
    }


def _d1_payload(
    *,
    seed: int = 7,
    scenario_id: str = "dense-crossing",
    scenario_version: str = "dense-crossing-v1",
    run_id: str = "episode-007",
    available: bool = True,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    if available:
        for index, (position_error, velocity_error, nees, nis, within) in enumerate(
            (
                (1.0, 0.5, 6.0, 2.0, True),
                (3.0, 1.5, 8.0, 4.0, False),
            )
        ):
            records.append(
                {
                    "schema_version": "d1.consistency.offline_result_record.v1",
                    "evidence_id": f"EV-{index}",
                    "observation_id": f"OBS-{index}",
                    "sensor_id": "RADAR-01",
                    "sensor_type": "radar",
                    "source_sensor_type": "radar",
                    "measurement_timestamp": float(index),
                    "arrival_timestamp": float(index) + 0.2,
                    "global_track_id": "GT-0001",
                    "truth_id": "T-0001",
                    "range_m": 750.0,
                    "range_bin": "mid",
                    "range_bin_schema_version": "d1.consistency.range_bins.v1",
                    "accepted": True,
                    "gate_decision": "accepted",
                    "innovation_dimension": 2,
                    "nis": nis,
                    "normalized_nis": nis / 2.0,
                    "nis_within_gate": within,
                    "position_error_m": position_error,
                    "velocity_error_mps": velocity_error,
                    "nees": nees,
                    "normalized_nees": nees / 6.0,
                    "availability": {
                        "truth_alignment": {"available": True, "reason": None},
                        "nees": {"available": True, "reason": None},
                        "nis_coverage": {"available": True, "reason": None},
                    },
                }
            )
        metrics = {
            "position_rmse_m": _available_metric(5.0**0.5),
            "velocity_rmse_mps": _available_metric(1.25**0.5),
            "mean_nees": _available_metric(7.0),
            "mean_normalized_nees": _available_metric(7.0 / 6.0),
            "mean_nis": _available_metric(3.0),
            "mean_normalized_nis": _available_metric(1.5),
            "nis_gate_coverage": _available_metric(0.5),
        }
        status = "available"
        failure_reasons: list[str] = []
    else:
        reason = "truth_alignment_unavailable"
        metrics = {
            name: _unavailable_metric(reason)
            for name in (
                "position_rmse_m",
                "velocity_rmse_mps",
                "mean_nees",
                "mean_normalized_nees",
                "mean_nis",
                "mean_normalized_nis",
                "nis_gate_coverage",
            )
        }
        status = "unavailable"
        failure_reasons = [reason]
    payload: dict[str, object] = {
        "schema_version": "d1.consistency.offline_result.v1",
        "record_schema_version": "d1.consistency.offline_result_record.v1",
        "scenario_id": scenario_id,
        "scenario_version": scenario_version,
        "run_id": run_id,
        "seed": seed,
        "status": status,
        "input_digests": {
            "online_evidence": _sha("a"),
            "truth_sidecar": _sha("b"),
            "d2_lineage_mapping": _sha("c"),
        },
        "record_count": len(records),
        "records": records,
        "metrics": metrics,
        "failure_reasons": failure_reasons,
        "truth_usage": "offline_evaluation_only",
    }
    payload["content_digest"] = _canonical_sha(payload)
    return payload


def _d2_payload(
    *,
    episode_id: str = "episode-007",
    available: bool = True,
    truth_isolation_verified: bool = True,
    id_switch_count: int = 1,
) -> dict[str, object]:
    reason = None if available else "identity_lineage_unavailable"
    metric_values: dict[str, int | float | None] = {
        "id_switch_count": id_switch_count if available else None,
        "track_continuity": 0.8 if available else None,
        "identity_continuity": 0.8 if available else None,
        "coverage_continuity": 0.9 if available else None,
        "duplicate_truth_to_track_count": 2 if available else None,
    }
    metrics: dict[str, object] = {
        "schema_version": "d2.scalable3d_identity_metrics.v1",
        "evaluated_frame_count": 10,
        "truth_metrics_available": available,
        "truth_metrics_reason": reason,
        "continuity_available": available,
        "continuity_reason": reason,
        "confusion_matrix": (
            {"T-0001": {"GT-0001": 8, "GT-0002": 2}}
            if available
            else None
        ),
        "truth_frame_count": {"T-0001": 10} if available else {},
        "truth_assigned_frame_count": {"T-0001": 9} if available else {},
        "truth_identity_stable_frame_count": {"T-0001": 8} if available else {},
    }
    for name, value in metric_values.items():
        metrics[name] = value
        metrics[f"{name}_available"] = available
        metrics[f"{name}_reason"] = reason
    metrics["duplicate_assignment_count"] = metric_values[
        "duplicate_truth_to_track_count"
    ]
    metrics["duplicate_assignment_count_available"] = available
    metrics["duplicate_assignment_count_reason"] = reason
    return {
        "schema_version": "d2.scalable3d_identity_evaluation.v1",
        "policy_version": "d2.scalable3d_identity_policy.v1",
        "hash_algorithm": "sha256",
        "episode_id": episode_id,
        "source_hashes": {
            "online_d1_records": _sha("d"),
            "online_d2_records": _sha("e"),
            "observation_truth_labels": _sha("f"),
            "identity_evidence_bundle": _sha("0"),
        },
        "configuration": {
            "metric_contract": "MetricsRecorder-compatible-v1"
        },
        "frames": [],
        "metrics": metrics,
        "audit": {
            "source_verification": (
                "raw_source_hashes_and_record_sequences_verified"
                if truth_isolation_verified
                else "canonical_dto_hashes_verified"
            ),
            "online_truth_isolation_verified": truth_isolation_verified,
            "identity_heuristics_used": False,
            "available_mapping_count": 8,
            "ambiguous_mapping_count": 1,
            "unavailable_mapping_count": 1,
        },
    }


def _v2_commitment(
    *,
    track_id: str,
    association_state: str,
    timestamp: float,
    committed: bool,
    observation_id: str | None,
) -> dict[str, object]:
    state = (
        "committed"
        if committed
        else "identity_uncommitted_after_hold"
    )
    return {
        "schema_version": "d2.identity-evidence-commitment.v2",
        "policy_version": "d2-structural-ambiguity-commitment-v2",
        "global_track_id": track_id,
        "association_state": association_state,
        "identity_commitment_state": state,
        "reason": (
            "fresh_original_observation_accepted"
            if committed
            else "identity_recovery_blocked_measurement_not_newer_than_hold"
        ),
        "state_timestamp": timestamp,
        "commitment_generation": 2 if committed else 1,
        "measurement_timestamp": max(timestamp - 0.1, 0.0),
        "arrival_timestamp": max(timestamp - 0.1, 0.0) + 0.01,
        "source_observation_evidence_key": (
            f"evidence:{observation_id}" if committed else None
        ),
        "source_observation_evidence_generation": (
            0 if committed else None
        ),
        "source_observation_disposition": (
            "target_candidate" if committed else None
        ),
        "ambiguity_component_key": None if committed else "component-1",
        "ambiguity_evidence_id": None if committed else "ambiguity-1",
        "ambiguity_component_generation": None if committed else 1,
        "publisher_node_id": None if committed else "D1_FUSION",
        "publisher_epoch": None if committed else "epoch-1",
        "active_lease_count": 0,
        "active_lease_keys": [],
        "lease_first_seen_timestamp": None if committed else timestamp - 0.2,
        "lease_soft_deadline": None if committed else timestamp - 0.1,
        "lease_hard_deadline": None if committed else timestamp + 0.1,
        "lease_expired_timestamp": None if committed else timestamp - 0.1,
        "lease_expiration_reason": (
            None if committed else "soft_deadline_reached"
        ),
        "recovery_blocker_count": 0 if committed else 2,
        "recovery_not_before_measurement_timestamp": (
            None if committed else timestamp - 0.5
        ),
        "recovery_blocker_overflow": not committed,
        "online_truth_used": False,
    }


def _v2_evidence_record(
    *,
    episode_id: str,
    frame_index: int,
    track_id: str,
    association_state: str,
    committed: bool,
    observation_id: str | None,
) -> dict[str, object]:
    timestamp = float(frame_index)
    observations = (
        []
        if observation_id is None
        else [
            {
                "observation_id": observation_id,
                "measurement_timestamp": timestamp,
                "source_lineage": [observation_id],
                "replay_generation": 0,
            }
        ]
    )
    return {
        "schema_version": "d2.scalable3d_identity_evidence.v2",
        "episode_id": episode_id,
        "frame_index": frame_index,
        "frame_timestamp": timestamp,
        "global_track_id": track_id,
        "lifecycle_state": "confirmed",
        "association_state": association_state,
        "identity_commitment": _v2_commitment(
            track_id=track_id,
            association_state=association_state,
            timestamp=timestamp,
            committed=committed,
            observation_id=observation_id,
        ),
        "source_observations": observations,
        "d1_record_sequences": [],
        "d2_record_sequence": None,
    }


def _v2_mapping(
    *,
    track_id: str,
    status: str,
    truth_id: str | None,
) -> dict[str, object]:
    available = status == "available"
    return {
        "global_track_id": track_id,
        "lifecycle_state": "confirmed",
        "association_state": "matched" if available else "unmatched",
        "status": status,
        "truth_target_id": truth_id if available else None,
        "reason": None if available else "identity_uncommitted_after_hold",
        "unavailable_reasons": (
            [] if available else ["identity_uncommitted_after_hold"]
        ),
        "candidate_truth_target_ids": [truth_id] if available else [],
        "source_observation_ids": (
            [f"OBS-{track_id}"] if available else []
        ),
        "source_lineage_hashes": (
            [_sha("9")] if available else []
        ),
        "evidence_count": 1 if available else 0,
        "unique_lineage_count": 1 if available else 0,
        "labeled_evidence_count": 1 if available else 0,
        "replayed_lineage_count": 0,
    }


def _resign_v2_evidence(payload: dict[str, object]) -> None:
    source_hashes = payload["source_hashes"]
    records = payload["identity_evidence_records"]
    assert isinstance(source_hashes, dict)
    assert isinstance(records, list)
    bundle = {
        "schema_version": "d2.scalable3d_identity_evidence.v2",
        "policy_version": "d2.scalable3d_identity_commitment_policy.v2",
        "hash_algorithm": "sha256",
        "episode_id": payload["episode_id"],
        "source_hashes": {
            name: source_hashes[name]
            for name in (
                "online_d1_records",
                "online_d2_records",
                "observation_truth_labels",
            )
        },
        "records": records,
    }
    source_hashes["identity_evidence_bundle"] = (
        _canonical_sha_with_newline(bundle)
    )


def _d2_v2_payload(
    *,
    episode_id: str = "episode-007",
    strict_available: bool = True,
) -> dict[str, object]:
    payload = _d2_payload(
        episode_id=episode_id,
        available=strict_available,
        id_switch_count=1,
    )
    payload["schema_version"] = "d2.scalable3d_identity_evaluation.v2"
    payload["policy_version"] = (
        "d2.scalable3d_identity_commitment_policy.v2"
    )
    records = [
        _v2_evidence_record(
            episode_id=episode_id,
            frame_index=0,
            track_id="GT-0001",
            association_state="created",
            committed=True,
            observation_id="OBS-0",
        ),
        _v2_evidence_record(
            episode_id=episode_id,
            frame_index=1,
            track_id="GT-0001",
            association_state="unmatched",
            committed=False,
            observation_id=None,
        ),
        _v2_evidence_record(
            episode_id=episode_id,
            frame_index=2,
            track_id="GT-0002",
            association_state="created",
            committed=True,
            observation_id="OBS-2",
        ),
    ]
    payload["identity_evidence_records"] = records
    payload["frames"] = [
        {
            "schema_version": "d2.scalable3d_global_track_truth_mapping.v1",
            "frame_index": 0,
            "frame_timestamp": 0.0,
            "mappings": [
                _v2_mapping(
                    track_id="GT-0001",
                    status="available",
                    truth_id="T-0001",
                )
            ],
        },
        {
            "schema_version": "d2.scalable3d_global_track_truth_mapping.v1",
            "frame_index": 1,
            "frame_timestamp": 1.0,
            "mappings": [
                _v2_mapping(
                    track_id="GT-0001",
                    status="uncommitted",
                    truth_id=None,
                )
            ],
        },
        {
            "schema_version": "d2.scalable3d_global_track_truth_mapping.v1",
            "frame_index": 2,
            "frame_timestamp": 2.0,
            "mappings": [
                _v2_mapping(
                    track_id="GT-0002",
                    status="available",
                    truth_id="T-0001",
                )
            ],
        },
    ]
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["evaluated_frame_count"] = 3
    if strict_available:
        metrics.update(
            {
                "id_switch_count": 1,
                "track_continuity": 1.0 / 3.0,
                "identity_continuity": 1.0 / 3.0,
                "coverage_continuity": 2.0 / 3.0,
                "duplicate_truth_to_track_count": 0,
                "duplicate_assignment_count": 0,
                "confusion_matrix": {
                    "T-0001": {"GT-0001": 1, "GT-0002": 1}
                },
                "truth_frame_count": {"T-0001": 3},
                "truth_assigned_frame_count": {"T-0001": 2},
                "truth_identity_stable_frame_count": {"T-0001": 1},
            }
        )
    audit = payload["audit"]
    assert isinstance(audit, dict)
    audit.update(
        {
            "evaluated_frame_count": 3,
            "available_mapping_count": 2,
            "ambiguous_mapping_count": 0,
            "unavailable_mapping_count": 1,
            "identity_commitment_contract_available": True,
            "identity_commitment_schema_version": (
                "d2.identity-evidence-commitment.v2"
            ),
            "identity_commitment_policy_version": (
                "d2-structural-ambiguity-commitment-v2"
            ),
            "identity_commitment_audit_schema_version": (
                "d2.scalable3d_identity_commitment_audit.v2"
            ),
            "identity_commitment_denominator_policy": {
                "all_records": (
                    "all_persisted_v2_identity_evidence_records"
                ),
                "observed_records": (
                    "v2_identity_evidence_records_with_association_state_"
                    "created_or_matched"
                ),
                "committed": "identity_commitment_state_equals_committed",
                "uncommitted": "all_other_v2_identity_commitment_states",
                "recovery_blocker_count": (
                    "all_v2_identity_evidence_records_including_zero"
                ),
                "watermark_age": (
                    "frame_timestamp_minus_recovery_not_before_measurement_"
                    "timestamp_for_records_with_watermark"
                ),
            },
            "identity_commitment_record_count": 3,
            "identity_commitment_state_counts": {
                "committed": 2,
                "identity_uncommitted_after_hold": 1,
            },
            "identity_commitment_coverage": 2.0 / 3.0,
            "identity_commitment_all_records": {
                "denominator": 3,
                "committed_count": 2,
                "uncommitted_count": 1,
                "coverage": 2.0 / 3.0,
                "coverage_available": True,
                "coverage_reason": None,
            },
            "identity_commitment_observed_records": {
                "denominator": 2,
                "committed_count": 2,
                "uncommitted_count": 0,
                "coverage": 1.0,
                "coverage_available": True,
                "coverage_reason": None,
            },
            "identity_commitment_reason_counts": {
                "fresh_original_observation_accepted": 2,
                (
                    "identity_recovery_blocked_"
                    "measurement_not_newer_than_hold"
                ): 1,
            },
            "identity_recovery_blocked_reason_counts": {
                (
                    "identity_recovery_blocked_"
                    "measurement_not_newer_than_hold"
                ): 1,
            },
            "identity_recovery_blocker_count_summary": {
                "record_count": 3,
                "positive_record_count": 1,
                "sum": 2,
                "min": 0,
                "mean": 2.0 / 3.0,
                "max": 2,
            },
            "identity_recovery_watermark_age_seconds_summary": {
                "count": 1,
                "min": 0.5,
                "mean": 0.5,
                "max": 0.5,
            },
            "identity_recovery_blocker_overflow_record_count": 1,
            "identity_recovery_blocker_overflow_track_count": 1,
            "uncommitted_mapping_count": 1,
            "uncommitted_candidate_binding_count": 0,
            "uncommitted_candidate_binding_violation_count": 0,
            "uncommitted_source_binding_violation_count": 0,
            "uncommitted_binding_violation_policy": {
                "candidate": (
                    "uncommitted_frame_mapping_carries_truth_target_or_candidate"
                ),
                "source": (
                    "uncommitted_v2_evidence_or_frame_mapping_carries_source_"
                    "observation_lineage"
                ),
                "required_value": 0,
            },
            "identity_switch_anchor_policy": (
                "compare_consecutive_committed_truth_anchors_across_"
                "uncommitted_gaps"
            ),
            "committed_anchor_across_uncommitted_gap_policy": (
                "compare_consecutive_committed_truth_anchors_across_"
                "uncommitted_gaps"
            ),
        }
    )
    _resign_v2_evidence(payload)
    return payload


def _attach_partial_identity(
    payload: dict[str, object],
    *,
    lower_bound: int = 1,
) -> dict[str, object]:
    partial: dict[str, object] = {
        "schema_version": "d2.scalable3d_partial_identity_diagnostics.v1",
        "scope": "offline_lineage_truth_sidecar_only",
        "denominator_definitions": dict(
            D2_PARTIAL_IDENTITY_DENOMINATOR_DEFINITIONS
        ),
        "total_mapping_count": 12,
        "available_mapping_count": 9,
        "ambiguous_mapping_count": 1,
        "unavailable_mapping_count": 2,
        "scored_mapping_count": 10,
        "non_scored_mapping_count": 2,
        "evaluable_mapping_count": 8,
        "ambiguous_scored_mapping_count": 1,
        "unavailable_scored_mapping_count": 1,
        "mapped_truth_not_present_mapping_count": 0,
        "missing_identity_evidence_mapping_count": 1,
        "evaluable_mapping_coverage": 0.8,
        "evaluable_mapping_coverage_available": True,
        "evaluable_mapping_coverage_reason": None,
        "evaluated_frame_count": 10,
        "evaluable_frame_count": 4,
        "evaluable_frame_coverage": 0.4,
        "evaluable_frame_coverage_available": True,
        "evaluable_frame_coverage_reason": None,
        "transition_opportunity_count": 5,
        "evaluable_transition_count": 3,
        "evaluable_transition_coverage": 0.6,
        "evaluable_transition_coverage_available": True,
        "evaluable_transition_coverage_reason": None,
        "lower_bound_anchor_excluded_truth_frame_count": 1,
        "lower_bound_anchor_exclusion_reason_counts": {
            "multiple_evaluable_global_tracks_for_truth_frame": 1
        },
        "lower_bound_anchor_transition_count": 4,
        "id_switch_lower_bound": lower_bound,
        "id_switch_lower_bound_available": True,
        "id_switch_lower_bound_reason": None,
        "id_switch_upper_bound": None,
        "id_switch_upper_bound_available": False,
        "id_switch_upper_bound_reason": (
            "not_provided_incomplete_identity_evidence"
        ),
        "excluded_scored_mapping_reason_counts": {
            "truth_label_missing": 1
        },
    }
    payload["partial_identity_diagnostics"] = partial
    configuration = payload["configuration"]
    assert isinstance(configuration, dict)
    configuration["partial_identity_diagnostic_contract"] = (
        "d2.scalable3d_partial_identity_diagnostics.v1"
    )
    audit = payload["audit"]
    assert isinstance(audit, dict)
    audit.update(
        {
            "evaluated_frame_count": 10,
            "available_mapping_count": 9,
            "ambiguous_mapping_count": 1,
            "unavailable_mapping_count": 2,
            "partial_identity_diagnostics_available": True,
            "partial_identity_diagnostics_schema_version": (
                "d2.scalable3d_partial_identity_diagnostics.v1"
            ),
        }
    )
    return partial


def _write_d2_identity_with_manifest(
    root: Path,
    payload: dict[str, object],
    *,
    manifest_schema_version: str = (
        "scalable3d-offline-identity-evaluation-manifest-v1"
    ),
    evaluation_sha_override: str | None = None,
    source_hash_override: tuple[str, str] | None = None,
) -> tuple[Path, str, dict[str, str], Path]:
    root.mkdir(parents=True, exist_ok=True)
    evaluation_path = root / "identity_evaluation.json"
    evaluation_path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evaluation_sha = _file_sha(evaluation_path)
    source_hashes = payload["source_hashes"]
    assert isinstance(source_hashes, dict)
    normalized_sources = {
        str(name): str(value) for name, value in source_hashes.items()
    }
    manifest_sources = {
        "online_d1_records": normalized_sources["online_d1_records"],
        "online_d2_records": normalized_sources["online_d2_records"],
        "observation_truth_labels": normalized_sources[
            "observation_truth_labels"
        ],
        "identity_evidence": normalized_sources["identity_evidence_bundle"],
        "identity_evaluation": evaluation_sha_override or evaluation_sha,
    }
    if source_hash_override is not None:
        name, value = source_hash_override
        manifest_sources[name] = value
    metrics = payload["metrics"]
    audit = payload["audit"]
    assert isinstance(metrics, dict)
    assert isinstance(audit, dict)
    manifest = {
        "schema_version": manifest_schema_version,
        "available": True,
        "reason": None,
        "episode_id": payload["episode_id"],
        "source_hashes": manifest_sources,
        "online_truth_isolation_verified": audit[
            "online_truth_isolation_verified"
        ],
        "identity_metrics_available": metrics["truth_metrics_available"],
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evaluation_path, evaluation_sha, normalized_sources, manifest_path


class _D1PublicDTO:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, object]:
        return json.loads(json.dumps(self.payload))

    def aggregation_records(self) -> tuple[dict[str, object], ...]:
        input_digests = self.payload["input_digests"]
        assert isinstance(input_digests, dict)
        context = {
            "schema_version": "d1.consistency.offline_aggregation_record.v1",
            "result_record_schema_version": (
                "d1.consistency.offline_result_record.v1"
            ),
            "scenario_id": self.payload["scenario_id"],
            "scenario_version": self.payload["scenario_version"],
            "run_id": self.payload["run_id"],
            "seed": self.payload["seed"],
            "offline_result_digest": self.payload["content_digest"],
            "online_evidence_digest": input_digests["online_evidence"],
            "truth_sidecar_digest": input_digests["truth_sidecar"],
        }
        if "d2_lineage_mapping" in input_digests:
            context["d2_lineage_mapping_digest"] = input_digests[
                "d2_lineage_mapping"
            ]
        if "canonical_mapping" in input_digests:
            context["canonical_mapping_digest"] = input_digests[
                "canonical_mapping"
            ]
        records = self.payload["records"]
        assert isinstance(records, list)
        return tuple({**record, **context} for record in records)


class _D2PublicDTO:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, object]:
        return json.loads(json.dumps(self.payload))


def _context(
    *,
    episode_id: str = "episode-007",
    run_id: str = "episode-007",
    seed: int = 7,
    scale: int = 20,
) -> TruthIsolatedEpisodeContext:
    return TruthIsolatedEpisodeContext(
        episode_id=episode_id,
        scenario_id="dense-crossing",
        scenario_version="dense-crossing-v1",
        run_id=run_id,
        seed=seed,
        target_count=scale,
        resource_count=scale,
        recon_count=max(1, scale // 20),
        camera_count=scale + max(1, scale // 20),
    )


def test_public_dto_adapters_preserve_d1_d2_metrics() -> None:
    d1 = adapt_d1_offline_consistency(_D1PublicDTO(_d1_payload()))
    d2 = adapt_d2_scalable_3d_identity(_D2PublicDTO(_d2_payload()))

    assert d1.verification_mode == "public_dto_validated"
    assert d1.metrics["position_rmse_m"].value == pytest.approx(5.0**0.5)
    assert len(d1.sensor_range_records) == 1
    group = d1.sensor_range_records[0]
    assert group.metrics["position_rmse_m"].value == pytest.approx(5.0**0.5)
    assert group.metrics["position_rmse_m"].sample_count == 2
    assert group.metrics["nis_gate_coverage"].value == pytest.approx(0.5)
    assert group.input_digests["d2_lineage_mapping"] == _sha("c")
    assert set(d1.to_dict()["input_digests"]) == {
        "online_evidence",
        "truth_sidecar",
        "d2_lineage_mapping",
    }

    assert d2.truth_isolation_verified is True
    assert d2.metrics["id_switch_count"].value == 1
    assert d2.metrics["id_switch_count"].available is True
    assert d2.confusion_matrix == {"T-0001": {"GT-0001": 8, "GT-0002": 2}}
    assert d2.truth_assigned_frame_count == {"T-0001": 9}
    assert d2.configuration["metric_contract"] == "MetricsRecorder-compatible-v1"
    assert d2.partial_identity_diagnostics.available is False
    assert (
        d2.partial_identity_diagnostics.unavailable_reason
        == "partial_identity_diagnostics_missing"
    )
    assert d2.identity_commitment.available is False
    assert (
        d2.identity_commitment.unavailable_reason
        == "identity_commitment_unavailable_for_d2_evaluation_v1"
    )
    assert (
        d2.identity_commitment.metrics["all_commitment_coverage"].value
        is None
    )
    assert (
        d2.identity_commitment.metrics["all_committed_count"].available
        is False
    )


def test_d2_identity_commitment_v2_is_sha_bound_and_keeps_strict_gap_idsw() -> None:
    record = adapt_d2_scalable_3d_identity(_d2_v2_payload())

    assert record.producer_schema_version == (
        "d2.scalable3d_identity_evaluation.v2"
    )
    assert record.metrics["id_switch_count"].available is True
    assert record.metrics["id_switch_count"].value == 1
    commitment = record.identity_commitment
    assert commitment.available is True
    assert commitment.evidence_bundle_sha256_verified is True
    assert commitment.metrics["all_commitment_coverage"].value == pytest.approx(
        2.0 / 3.0
    )
    assert commitment.metrics["observed_commitment_coverage"].value == 1.0
    assert commitment.metrics["all_committed_count"].value == 2
    assert commitment.metrics["all_uncommitted_count"].value == 1
    assert commitment.metrics["uncommitted_mapping_count"].value == 1
    assert commitment.metrics["recovery_blocker_count_sum"].value == 2
    assert (
        commitment.metrics[
            "recovery_watermark_age_seconds_mean"
        ].value
        == pytest.approx(0.5)
    )
    assert commitment.metrics[
        "recovery_blocker_overflow_record_count"
    ].value == 1
    assert commitment.metrics[
        "recovery_blocker_overflow_track_count"
    ].value == 1
    assert commitment.metrics[
        "uncommitted_candidate_binding_violation_count"
    ].value == 0
    assert commitment.metrics[
        "uncommitted_source_binding_violation_count"
    ].value == 0
    assert commitment.to_dict()["strict_id_switch_count_backfilled"] is False
    assert (
        commitment.to_dict()["uncommitted_gap_treated_as_zero_id_switch"]
        is False
    )


def test_d2_identity_commitment_v2_missing_audit_field_fails_closed() -> None:
    payload = _d2_v2_payload()
    audit = payload["audit"]
    assert isinstance(audit, dict)
    del audit["identity_commitment_denominator_policy"]

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="missing required field",
    ):
        adapt_d2_scalable_3d_identity(payload)


@pytest.mark.parametrize(
    ("field", "nested_field", "tampered_value"),
    [
        ("identity_commitment_all_records", "committed_count", 99),
        ("identity_commitment_all_records", "coverage", 0.5),
        ("identity_commitment_observed_records", "denominator", 3),
    ],
)
def test_d2_identity_commitment_v2_denominator_or_coverage_tamper_fails_closed(
    field: str,
    nested_field: str,
    tampered_value: int | float,
) -> None:
    payload = _d2_v2_payload()
    audit = payload["audit"]
    assert isinstance(audit, dict)
    summary = audit[field]
    assert isinstance(summary, dict)
    summary[nested_field] = tampered_value

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="contradicts embedded v2 evidence",
    ):
        adapt_d2_scalable_3d_identity(payload)


def test_d2_identity_commitment_v2_negative_watermark_age_fails_closed() -> None:
    payload = _d2_v2_payload()
    records = payload["identity_evidence_records"]
    assert isinstance(records, list)
    commitment = records[1]["identity_commitment"]
    assert isinstance(commitment, dict)
    commitment["recovery_not_before_measurement_timestamp"] = 1.1
    _resign_v2_evidence(payload)

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="watermark age must be finite and non-negative",
    ):
        adapt_d2_scalable_3d_identity(payload)


def test_d2_identity_commitment_v2_overflow_contradiction_fails_closed() -> None:
    payload = _d2_v2_payload()
    audit = payload["audit"]
    assert isinstance(audit, dict)
    audit["identity_recovery_blocker_overflow_track_count"] = 2

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="contradicts embedded v2 evidence",
    ):
        adapt_d2_scalable_3d_identity(payload)


def test_d2_identity_commitment_v2_uncommitted_binding_violation_fails_closed() -> None:
    payload = _d2_v2_payload()
    frames = payload["frames"]
    audit = payload["audit"]
    assert isinstance(frames, list)
    assert isinstance(audit, dict)
    mapping = frames[1]["mappings"][0]
    assert isinstance(mapping, dict)
    mapping["candidate_truth_target_ids"] = ["T-FORBIDDEN"]
    audit["uncommitted_candidate_binding_count"] = 1
    audit["uncommitted_candidate_binding_violation_count"] = 1

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="binding violation count must be zero",
    ):
        adapt_d2_scalable_3d_identity(payload)


def test_d2_v2_lineage_missing_keeps_strict_idswitch_unavailable() -> None:
    payload = _d2_v2_payload(strict_available=False)
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    for name in (
        "id_switch_count",
        "track_continuity",
        "identity_continuity",
        "coverage_continuity",
        "duplicate_truth_to_track_count",
    ):
        metrics[f"{name}_reason"] = "source_lineage_missing"
    metrics["truth_metrics_reason"] = "source_lineage_missing"
    metrics["continuity_reason"] = "source_lineage_missing"
    metrics["duplicate_assignment_count_reason"] = "source_lineage_missing"

    record = adapt_d2_scalable_3d_identity(payload)

    assert record.identity_commitment.available is True
    assert record.metrics["id_switch_count"].available is False
    assert record.metrics["id_switch_count"].value is None
    assert (
        record.metrics["id_switch_count"].unavailable_reason
        == "source_lineage_missing"
    )
    assert (
        record.identity_commitment.metrics["all_uncommitted_count"].value
        == 1
    )


def test_d2_identity_commitment_v2_report_outputs_separate_evidence_layers(
    tmp_path: Path,
) -> None:
    episode = build_truth_isolated_episode_record(
        _context(),
        d1_result=_D1PublicDTO(_d1_payload()),
        d2_evaluation=_d2_v2_payload(),
    )
    outputs = TruthIsolatedOfflineReportGenerator().write_report_bundle(
        tmp_path / "report",
        records=(episode,),
        bootstrap_resamples=20,
    )

    with outputs["per_seed_csv"].open(
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        row = next(csv.DictReader(handle))
    assert row["d2_id_switch_count"] == "1"
    assert row["d2_identity_commitment_all_commitment_coverage"] == str(
        2.0 / 3.0
    )
    assert row["d2_identity_commitment_observed_commitment_coverage"] == "1.0"
    assert row["d2_identity_commitment_all_uncommitted_count"] == "1"
    assert row["d2_identity_commitment_uncommitted_mapping_count"] == "1"

    aggregate = json.loads(
        outputs["aggregate_json"].read_text(encoding="utf-8")
    )
    group = aggregate["groups"][0]
    commitment = group["d2_identity_commitment"]
    assert commitment["all_records"] == {
        "availability": "available",
        "committed_count": 2,
        "coverage": pytest.approx(2.0 / 3.0),
        "denominator": 3,
        "unavailable_reason": None,
        "uncommitted_count": 1,
    }
    assert commitment["observed_records"]["coverage"] == 1.0
    assert commitment["recovery_blocker_count_summary"]["sum"] == 2
    assert commitment[
        "recovery_watermark_age_seconds_summary"
    ]["mean"] == pytest.approx(0.5)
    assert commitment["uncommitted_mapping_count"] == 1
    assert (
        commitment["uncommitted_candidate_binding_violation_count"] == 0
    )
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "## 身份提交 v2 证据" in markdown
    assert "## Evaluator-only 部分身份诊断" in markdown
    assert "未提交空档降低 coverage，但不等于 `IDSW=0`" in markdown


def test_d2_v2_disposition_audit_is_provenance_bound_and_reported() -> None:
    payload = _d2_payload()
    audit = payload["audit"]
    assert isinstance(audit, dict)
    audit.update(
        {
            "observation_truth_schema_version": (
                "d2.scalable3d_observation_truth.v2"
            ),
            "truth_label_count": 4,
            "observation_truth_disposition_counts": {
                "target": 3,
                "known_false_alarm": 1,
            },
            "known_false_alarm_only_mapping_count": 0,
            "identity_metrics_blocking_reasons": [],
        }
    )

    record = adapt_d2_scalable_3d_identity(payload)
    disposition = record.audit[
        "d6_observation_truth_disposition_acceptance"
    ]

    assert disposition["availability"] == "available"
    assert disposition["source_schema_version"] == (
        "d2.scalable3d_observation_truth.v2"
    )
    assert disposition["source_sha256"] == _sha("f")
    assert disposition["target_label"]["count"] == 3
    assert disposition["known_false_alarm"]["count"] == 1
    assert disposition["unknown"]["count"] == 0
    assert disposition["missing_disposition"]["count"] == 0
    assert disposition["known_false_alarm_treated_as_target"] is False
    assert disposition["strict_id_switch_backfilled"] is False


def test_d2_v2_unknown_disposition_keeps_strict_id_switch_unavailable() -> None:
    payload = _d2_payload(available=False)
    audit = payload["audit"]
    assert isinstance(audit, dict)
    audit.update(
        {
            "observation_truth_schema_version": (
                "d2.scalable3d_observation_truth.v2"
            ),
            "truth_label_count": 4,
            "observation_truth_disposition_counts": {
                "target": 3,
                "unknown": 1,
            },
            "known_false_alarm_only_mapping_count": 0,
            "identity_metrics_blocking_reasons": ["truth_label_unknown"],
        }
    )

    record = adapt_d2_scalable_3d_identity(payload)
    disposition = record.audit[
        "d6_observation_truth_disposition_acceptance"
    ]

    assert disposition["unknown"]["count"] == 1
    assert record.metrics["id_switch_count"].available is False
    assert record.metrics["id_switch_count"].value is None
    assert disposition["strict_id_switch_backfilled"] is False


def test_d2_v2_disposition_count_tampering_is_rejected() -> None:
    payload = _d2_payload()
    audit = payload["audit"]
    assert isinstance(audit, dict)
    audit.update(
        {
            "observation_truth_schema_version": (
                "d2.scalable3d_observation_truth.v2"
            ),
            "truth_label_count": 4,
            "observation_truth_disposition_counts": {
                "target": 4,
                "known_false_alarm": 1,
            },
            "known_false_alarm_only_mapping_count": 0,
        }
    )

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="disposition counts do not cover",
    ):
        adapt_d2_scalable_3d_identity(payload)


def test_d2_unverified_truth_isolation_fails_metrics_closed() -> None:
    d2 = adapt_d2_scalable_3d_identity(
        _d2_payload(truth_isolation_verified=False)
    )

    assert d2.truth_isolation_verified is False
    assert d2.metrics["id_switch_count"].value is None
    assert d2.metrics["id_switch_count"].available is False
    assert (
        d2.metrics["id_switch_count"].unavailable_reason
        == "d2_online_truth_isolation_not_verified"
    )
    assert d2.confusion_matrix is None
    assert d2.truth_frame_count == {}
    assert d2.truth_assigned_frame_count == {}


def test_d2_unavailable_metric_cannot_smuggle_zero() -> None:
    payload = _d2_payload(available=False)
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["id_switch_count"] = 0

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="unavailable D2 identity metric must be null",
    ):
        adapt_d2_scalable_3d_identity(payload)


def test_hash_verified_artifacts_and_tamper_rejection(tmp_path: Path) -> None:
    payload = _d2_payload()
    path = tmp_path / "d2_identity.json"
    path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    expected = _file_sha(path)
    source_hashes = payload["source_hashes"]
    assert isinstance(source_hashes, dict)

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="path requires expected_source_hashes",
    ):
        adapt_d2_scalable_3d_identity(path, expected_sha256=expected)

    record = adapt_d2_scalable_3d_identity(
        path,
        expected_sha256=expected,
        expected_source_hashes=source_hashes,
    )
    assert record.verification_mode == "sha256_verified_artifact"
    assert record.external_file_sha256 == expected

    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(TruthIsolatedEvaluationError, match="sha256 mismatch"):
        adapt_d2_scalable_3d_identity(path, expected_sha256=expected)


def test_partial_identity_remains_available_when_strict_idsw_is_unavailable(
    tmp_path: Path,
) -> None:
    payload = _d2_payload(available=False)
    _attach_partial_identity(payload, lower_bound=2)
    path, expected, source_hashes, _ = _write_d2_identity_with_manifest(
        tmp_path,
        payload,
    )

    record = adapt_d2_scalable_3d_identity(
        path,
        expected_sha256=expected,
        expected_source_hashes=source_hashes,
    )

    assert record.metrics["id_switch_count"].available is False
    assert record.metrics["id_switch_count"].value is None
    partial = record.partial_identity_diagnostics
    assert partial.available is True
    assert partial.provenance_verified is True
    assert partial.metrics["evaluable_mapping_coverage"].value == pytest.approx(
        0.8
    )
    assert partial.metrics["evaluable_frame_coverage"].value == pytest.approx(
        0.4
    )
    assert partial.metrics["adjacent_transition_coverage"].value == pytest.approx(
        0.6
    )
    assert partial.metrics["id_switch_lower_bound"].value == 2
    assert partial.metrics["anchor_interval_count"].value == 4
    assert partial.lower_bound_anchor_exclusion_reason_counts == {
        "multiple_evaluable_global_tracks_for_truth_frame": 1
    }
    normalized = partial.to_dict()
    assert normalized["strict_id_switch_count_backfilled"] is False
    assert normalized["id_switch_upper_bound_reported"] is False
    assert "id_switch_upper_bound" not in normalized["metrics"]

    episode = build_truth_isolated_episode_record(
        _context(),
        d1_result=_d1_payload(),
        d2_evaluation=path,
        d2_expected_sha256=expected,
        d2_expected_source_hashes=source_hashes,
    )
    group = aggregate_truth_isolated_episode_records(
        (episode,),
        bootstrap_resamples=20,
    ).groups[0]
    assert group["metrics"]["d2.id_switch_count"]["availability"] == (
        "unavailable"
    )
    assert (
        group["metrics"]["d2.partial_identity.id_switch_lower_bound"][
            "availability"
        ]
        == "available"
    )
    assert (
        group["d2_partial_identity_diagnostics"][
            "id_switch_lower_bound"
        ]["value"]
        == 2
    )


def test_strict_idsw_and_partial_lower_bound_coexist_in_separate_report_columns(
    tmp_path: Path,
) -> None:
    payload = _d2_payload(id_switch_count=3)
    _attach_partial_identity(payload, lower_bound=2)
    identity_dir = tmp_path / "identity"
    path, expected, source_hashes, _ = _write_d2_identity_with_manifest(
        identity_dir,
        payload,
    )
    record = build_truth_isolated_episode_record(
        _context(),
        d1_result=_d1_payload(),
        d2_evaluation=path,
        d2_expected_sha256=expected,
        d2_expected_source_hashes=source_hashes,
    )

    assert record.d2.metrics["id_switch_count"].value == 3
    assert (
        record.d2.partial_identity_diagnostics.metrics[
            "id_switch_lower_bound"
        ].value
        == 2
    )
    outputs = TruthIsolatedOfflineReportGenerator().write_report_bundle(
        tmp_path / "report",
        records=(record,),
        bootstrap_resamples=20,
    )
    with outputs["per_seed_csv"].open(
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        row = next(csv.DictReader(handle))
    assert row["d2_id_switch_count"] == "3"
    assert row["d2_partial_identity_id_switch_lower_bound"] == "2"
    assert row["d2_partial_identity_anchor_interval_count"] == "4"

    aggregate = json.loads(
        outputs["aggregate_json"].read_text(encoding="utf-8")
    )
    group = aggregate["groups"][0]
    assert group["metrics"]["d2.id_switch_count"]["mean"] == 3.0
    assert (
        group["metrics"]["d2.partial_identity.id_switch_lower_bound"][
            "mean"
        ]
        == 2.0
    )
    partial = group["d2_partial_identity_diagnostics"]
    assert partial["coverage_totals"]["mapping"]["value"] == pytest.approx(
        0.8
    )
    assert partial["id_switch_lower_bound"]["value"] == 2
    assert partial["anchor_interval_count"] == 4
    assert partial["strict_id_switch_count_backfilled"] is False
    assert partial["id_switch_upper_bound_reported"] is False
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "Evaluator-only 部分身份诊断" in markdown
    assert "lower bound 与 strict `id_switch_count` 始终分栏" in markdown


def test_partial_identity_accepts_partitioned_unavailable_audit_counts(
    tmp_path: Path,
) -> None:
    payload = _d2_v2_payload()
    partial = _attach_partial_identity(payload, lower_bound=1)
    partial.update(
        {
            "total_mapping_count": 3,
            "available_mapping_count": 2,
            "ambiguous_mapping_count": 0,
            "unavailable_mapping_count": 1,
            "scored_mapping_count": 2,
            "non_scored_mapping_count": 1,
            "evaluable_mapping_count": 2,
            "ambiguous_scored_mapping_count": 0,
            "unavailable_scored_mapping_count": 0,
            "mapped_truth_not_present_mapping_count": 0,
            "missing_identity_evidence_mapping_count": 0,
            "evaluable_mapping_coverage": 1.0,
            "evaluated_frame_count": 3,
            "evaluable_frame_count": 3,
            "evaluable_frame_coverage": 1.0,
            "transition_opportunity_count": 2,
            "evaluable_transition_count": 1,
            "evaluable_transition_coverage": 0.5,
            "lower_bound_anchor_excluded_truth_frame_count": 0,
            "lower_bound_anchor_exclusion_reason_counts": {},
            "lower_bound_anchor_transition_count": 1,
            "id_switch_lower_bound": 1,
            "excluded_scored_mapping_reason_counts": {},
        }
    )
    audit = payload["audit"]
    assert isinstance(audit, dict)
    audit["evaluated_frame_count"] = 3
    audit["available_mapping_count"] = 2
    audit["ambiguous_mapping_count"] = 0
    audit["unavailable_mapping_count"] = 0
    audit["excluded_mapping_count"] = 0
    audit["uncommitted_mapping_count"] = 1
    path, expected, source_hashes, _ = _write_d2_identity_with_manifest(
        tmp_path,
        payload,
    )

    record = adapt_d2_scalable_3d_identity(
        path,
        expected_sha256=expected,
        expected_source_hashes=source_hashes,
    )

    partial = record.partial_identity_diagnostics
    assert partial.available is True
    assert partial.provenance_verified is True
    assert partial.counts["unavailable_mapping_count"] == 1
    assert partial.metrics["id_switch_lower_bound"].value == 1


def test_partial_identity_rejects_incomplete_unavailable_audit_partition(
    tmp_path: Path,
) -> None:
    payload = _d2_payload(id_switch_count=3)
    _attach_partial_identity(payload, lower_bound=2)
    audit = payload["audit"]
    assert isinstance(audit, dict)
    audit["unavailable_mapping_count"] = 0
    audit["excluded_mapping_count"] = 1
    path, expected, source_hashes, _ = _write_d2_identity_with_manifest(
        tmp_path,
        payload,
    )

    record = adapt_d2_scalable_3d_identity(
        path,
        expected_sha256=expected,
        expected_source_hashes=source_hashes,
    )

    partial = record.partial_identity_diagnostics
    assert partial.available is False
    assert (
        partial.unavailable_reason
        == "partial_identity_audit_binding_mismatch"
    )
    assert partial.metrics["id_switch_lower_bound"].value is None


def test_partial_identity_missing_manifest_fails_closed_without_hiding_strict(
    tmp_path: Path,
) -> None:
    payload = _d2_payload(id_switch_count=1)
    _attach_partial_identity(payload)
    path = tmp_path / "identity_evaluation.json"
    path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source_hashes = payload["source_hashes"]
    assert isinstance(source_hashes, dict)

    record = adapt_d2_scalable_3d_identity(
        path,
        expected_sha256=_file_sha(path),
        expected_source_hashes=source_hashes,
    )

    assert record.metrics["id_switch_count"].value == 1
    assert record.partial_identity_diagnostics.available is False
    assert (
        record.partial_identity_diagnostics.unavailable_reason
        == "d2_identity_manifest_missing"
    )


@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    (
        (
            "wrong_partial_schema",
            "unsupported_partial_identity_diagnostics_schema",
        ),
        (
            "count_conservation",
            "partial_identity_count_conservation_failed",
        ),
        (
            "non_finite_coverage",
            "partial_identity_diagnostics_non_finite_value",
        ),
        (
            "wrong_manifest_schema",
            "unsupported_d2_identity_manifest_schema",
        ),
        (
            "manifest_evaluation_hash",
            "d2_identity_manifest_evaluation_sha256_mismatch",
        ),
        (
            "manifest_source_hash",
            "d2_identity_manifest_source_hash_mismatch",
        ),
        (
            "manifest_file_hash",
            "d2_identity_manifest_sha256_mismatch",
        ),
        (
            "upper_bound",
            "partial_identity_upper_bound_forbidden",
        ),
        (
            "lower_bound_exceeds_strict",
            "partial_identity_lower_bound_exceeds_strict_id_switch_count",
        ),
    ),
)
def test_partial_identity_tampering_fails_closed_with_explicit_reason(
    tmp_path: Path,
    failure: str,
    expected_reason: str,
) -> None:
    payload = _d2_payload(id_switch_count=3)
    partial = _attach_partial_identity(payload, lower_bound=2)
    manifest_schema = "scalable3d-offline-identity-evaluation-manifest-v1"
    evaluation_sha_override = None
    source_hash_override = None
    expected_manifest_sha = None
    if failure == "wrong_partial_schema":
        partial["schema_version"] = "d2.partial.unsupported.v9"
    elif failure == "count_conservation":
        partial["evaluable_mapping_count"] = 7
    elif failure == "non_finite_coverage":
        partial["evaluable_mapping_coverage"] = float("nan")
    elif failure == "wrong_manifest_schema":
        manifest_schema = "scalable3d-offline-identity-manifest-v9"
    elif failure == "manifest_evaluation_hash":
        evaluation_sha_override = _sha("9")
    elif failure == "manifest_source_hash":
        source_hash_override = ("identity_evidence", _sha("9"))
    elif failure == "manifest_file_hash":
        expected_manifest_sha = _sha("9")
    elif failure == "upper_bound":
        partial["id_switch_upper_bound"] = 4
        partial["id_switch_upper_bound_available"] = True
        partial["id_switch_upper_bound_reason"] = None
    elif failure == "lower_bound_exceeds_strict":
        partial["id_switch_lower_bound"] = 4

    path, expected, source_hashes, manifest_path = (
        _write_d2_identity_with_manifest(
            tmp_path / failure,
            payload,
            manifest_schema_version=manifest_schema,
            evaluation_sha_override=evaluation_sha_override,
            source_hash_override=source_hash_override,
        )
    )
    record = adapt_d2_scalable_3d_identity(
        path,
        expected_sha256=expected,
        expected_source_hashes=source_hashes,
        identity_manifest=manifest_path,
        expected_identity_manifest_sha256=expected_manifest_sha,
    )

    assert record.metrics["id_switch_count"].value == 3
    assert record.partial_identity_diagnostics.available is False
    assert (
        record.partial_identity_diagnostics.unavailable_reason
        == expected_reason
    )
    assert (
        record.partial_identity_diagnostics.metrics[
            "id_switch_lower_bound"
        ].value
        is None
    )


def test_d2_zero_without_frame_evidence_is_unavailable_not_zero() -> None:
    payload = _d2_payload(id_switch_count=0)
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["evaluated_frame_count"] = 0
    metrics["truth_frame_count"] = {}
    metrics["truth_assigned_frame_count"] = {}
    metrics["truth_identity_stable_frame_count"] = {}
    metrics["confusion_matrix"] = {}

    record = adapt_d2_scalable_3d_identity(payload)

    assert record.metrics["id_switch_count"].value is None
    assert record.metrics["id_switch_count"].available is False
    assert (
        record.metrics["id_switch_count"].unavailable_reason
        == "d2_evaluated_frames_unavailable"
    )
    assert record.truth_frame_count == {}


def test_d1_record_availability_cannot_be_overridden_by_a_value() -> None:
    payload = _d1_payload()
    records = payload["records"]
    assert isinstance(records, list)
    availability = records[0]["availability"]
    assert isinstance(availability, dict)
    availability["truth_alignment"] = {
        "available": False,
        "reason": "truth_alignment_unavailable",
    }
    _resign_d1(payload)

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="unavailable D1 record field must be null",
    ):
        adapt_d1_offline_consistency(payload)


def test_d1_legacy_canonical_mapping_digest_is_normalized() -> None:
    payload = _d1_payload()
    input_digests = payload["input_digests"]
    assert isinstance(input_digests, dict)
    digest = input_digests.pop("d2_lineage_mapping")
    input_digests["canonical_mapping"] = digest
    _resign_d1(payload)

    record = adapt_d1_offline_consistency(_D1PublicDTO(payload))

    assert record.input_digests["d2_lineage_mapping"] == _sha("c")
    assert "canonical_mapping" not in record.input_digests
    assert (
        record.sensor_range_records[0].input_digests["d2_lineage_mapping"]
        == _sha("c")
    )


def test_d1_mapping_digest_alias_conflict_fails_closed() -> None:
    payload = _d1_payload()
    input_digests = payload["input_digests"]
    assert isinstance(input_digests, dict)
    input_digests["canonical_mapping"] = _sha("9")
    _resign_d1(payload)

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="conflicting d2_lineage_mapping and canonical_mapping",
    ):
        adapt_d1_offline_consistency(payload)


def test_d1_available_truth_metrics_require_lineage_mapping_digest() -> None:
    payload = _d1_payload()
    input_digests = payload["input_digests"]
    assert isinstance(input_digests, dict)
    input_digests.pop("d2_lineage_mapping")
    _resign_d1(payload)

    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="source digests: d2_lineage_mapping",
    ):
        adapt_d1_offline_consistency(payload)


def test_d1_internal_digest_tamper_rejected() -> None:
    payload = _d1_payload()
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    position = metrics["position_rmse_m"]
    assert isinstance(position, dict)
    position["value"] = 999.0

    with pytest.raises(TruthIsolatedEvaluationError, match="content digest mismatch"):
        adapt_d1_offline_consistency(payload)


def test_missing_artifacts_keep_explicit_id_switch_unavailable() -> None:
    record = build_truth_isolated_episode_record(
        _context(),
        d1_result=None,
        d2_evaluation=None,
    )

    payload = record.to_dict()
    assert payload["d2_identity"]["id_switch_count"] is None
    assert (
        payload["d2_identity"]["id_switch_count_availability"]
        == "unavailable"
    )
    assert (
        payload["d2_identity"]["id_switch_count_unavailable_reason"]
        == "d2_identity_evaluation_artifact_missing"
    )
    assert (
        payload["d2_identity"]["partial_identity_diagnostics"][
            "unavailable_reason"
        ]
        == "d2_identity_evaluation_artifact_missing"
    )


def test_context_alignment_rejects_cross_episode_mix() -> None:
    with pytest.raises(
        TruthIsolatedEvaluationError,
        match="D2 identity episode_id",
    ):
        build_truth_isolated_episode_record(
            _context(),
            d1_result=_d1_payload(),
            d2_evaluation=_d2_payload(episode_id="different-episode"),
        )


def test_reference_scales_are_dynamic_and_all_supported() -> None:
    records = []
    for seed, scale in enumerate(REFERENCE_SCALABLE_3D_SCALES, start=1):
        episode_id = f"episode-{scale}"
        context = _context(
            episode_id=episode_id,
            run_id=episode_id,
            seed=seed,
            scale=scale,
        )
        records.append(
            build_truth_isolated_episode_record(
                context,
                d1_result=_d1_payload(
                    seed=seed,
                    run_id=episode_id,
                ),
                d2_evaluation=_d2_payload(episode_id=episode_id),
            )
        )

    summary = aggregate_truth_isolated_episode_records(
        records,
        bootstrap_resamples=50,
    )

    assert summary.scale_values == REFERENCE_SCALABLE_3D_SCALES
    assert all(summary.reference_scale_coverage.values())
    assert len(summary.groups) == len(REFERENCE_SCALABLE_3D_SCALES)
    assert all(
        "d2.id_switch_count" in group["metrics"] for group in summary.groups
    )


def test_report_bundle_writes_csv_json_and_chinese_markdown(tmp_path: Path) -> None:
    available = build_truth_isolated_episode_record(
        _context(),
        d1_result=_D1PublicDTO(_d1_payload()),
        d2_evaluation=_D2PublicDTO(_d2_payload(id_switch_count=0)),
    )
    missing_context = _context(
        episode_id="episode-008",
        run_id="episode-008",
        seed=8,
    )
    missing = build_truth_isolated_episode_record(
        missing_context,
        d1_result=None,
        d2_evaluation=None,
    )

    paths = TruthIsolatedOfflineReportGenerator().write_report_bundle(
        tmp_path,
        records=(available, missing),
        bootstrap_resamples=50,
    )

    assert set(paths) == {
        "per_seed_csv",
        "d1_sensor_range_per_seed_csv",
        "aggregate_json",
        "markdown",
    }
    with paths["per_seed_csv"].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["d2_id_switch_count"] == "0"
    assert rows[1]["d2_id_switch_count"] == ""
    assert rows[1]["d2_id_switch_count_availability"] == "unavailable"
    d1_input_digests = json.loads(rows[0]["d1_input_digests_json"])
    assert d1_input_digests["d2_lineage_mapping"] == _sha("c")
    assert "canonical_mapping" not in d1_input_digests

    with paths["d1_sensor_range_per_seed_csv"].open(
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        d1_rows = list(csv.DictReader(handle))
    assert json.loads(d1_rows[0]["input_digests_json"])[
        "d2_lineage_mapping"
    ] == _sha("c")

    aggregate = json.loads(paths["aggregate_json"].read_text(encoding="utf-8"))
    idsw = aggregate["groups"][0]["metrics"]["d2.id_switch_count"]
    assert idsw["availability"] == "available"
    assert idsw["mean"] == 0.0
    assert idsw["unavailability_reason_distribution"] == {
        "d2_identity_evaluation_artifact_missing": 1
    }
    assert aggregate["groups"][0]["d2_confusion_matrices_by_episode"] == [
        {
            "episode_id": "episode-007",
            "confusion_matrix": {"T-0001": {"GT-0001": 8, "GT-0002": 2}},
        }
    ]
    partial = aggregate["groups"][0]["d2_partial_identity_diagnostics"]
    assert partial["availability"] == "unavailable"
    assert partial["count_totals"] == {}
    assert partial["anchor_interval_count"] is None
    assert partial["unavailability_reason_distribution"] == {
        "d2_identity_evaluation_artifact_missing": 1,
        "partial_identity_diagnostics_missing": 1,
    }
    provenance = aggregate["groups"][0]["source_provenance_by_episode"]
    assert provenance[0]["d1_input_digests"]["d2_lineage_mapping"] == _sha("c")
    assert "canonical_mapping" not in provenance[0]["d1_input_digests"]
    assert provenance[0]["d2_source_hashes"]["online_d1_records"] == _sha("d")
    assert provenance[1]["d2_truth_metric_evidence_verified"] is False
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "D6 未重新构造航迹与真值映射" in markdown
    assert "缺证据时不会写成零" in markdown
    assert "单 seed 分组只给描述统计" in markdown
    assert "## 来源摘要" in markdown
    assert "d2_lineage_mapping=`sha256:" in markdown
    assert "canonical_mapping" not in markdown
    assert "online_d1_records=`sha256:" in markdown
