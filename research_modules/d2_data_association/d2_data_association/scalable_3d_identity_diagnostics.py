"""Auditable blocker diagnostics for scalable-3D offline identity metrics.

This module never changes online association state.  It explains why the
strict evaluator stayed unavailable by joining only persisted observation
lineage, measurement timestamps, and the independent offline truth sidecar.
It also checks whether the same evidence is complete enough to publish the
observation-level mapping records consumed by D1 consistency evaluation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from pathlib import Path
from typing import Any

from .scalable_3d_identity import (
    GlobalTrackLineageEvidence,
    OBSERVATION_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
    OBSERVATION_TRUTH_DISPOSITION_TARGET,
    OBSERVATION_TRUTH_DISPOSITION_UNKNOWN,
    Scalable3DIdentityEvaluation,
    Scalable3DIdentityEvidenceBundle,
    Scalable3DObservationTruthLabel,
    hash_scalable_3d_identity_evidence,
    hash_scalable_3d_observation_truth_label_sources,
    hash_scalable_3d_observation_truth_labels,
)


SCALABLE_3D_IDENTITY_BLOCKER_DIAGNOSTICS_SCHEMA_VERSION = (
    "d2.scalable3d_identity_blocker_diagnostics.v2"
)
SCALABLE_3D_D1_LINEAGE_MAPPING_AUDIT_SCHEMA_VERSION = (
    "d2.scalable3d_d1_lineage_mapping_audit.v2"
)
D1_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION = (
    "d1.consistency.d2_lineage_mapping_record.v1"
)
_OBSERVED_ASSOCIATION_STATES = frozenset({"created", "matched"})
_NON_BLOCKING_AUDIT_REASONS = frozenset(
    {
        "known_false_alarm_only",
        "track_not_assigned_in_frame",
    }
)
_D1_REASON_PRIORITY = (
    "d1_estimate_observation_duplicate",
    "truth_label_conflict",
    "truth_label_duplicate",
    "truth_label_timestamp_mismatch",
    "truth_label_unknown",
    "truth_label_missing",
    "d2_lineage_claim_conflict",
    "d2_lineage_claim_timestamp_mismatch",
    "d2_lineage_claim_missing",
)


@dataclass(frozen=True, slots=True)
class Scalable3DIdentityBlockerDiagnostics:
    """Portable, truth-isolated explanation of strict metric blockers."""

    episode_id: str
    source_hashes: Mapping[str, str]
    strict_identity_metrics_available: bool
    strict_identity_metrics_reason: str | None
    online_truth_isolation_verified: bool
    scored_mapping_count: int
    blocking_mapping_count: int
    blocking_reason_counts: Mapping[str, int]
    root_cause_counts: Mapping[str, int]
    blocker_intervals: tuple[Mapping[str, Any], ...]
    truth_label_disposition_counts: Mapping[str, int]
    known_false_alarm_only_mapping_count: int
    target_with_known_false_alarm_mapping_count: int
    lineage_disposition_audit: tuple[Mapping[str, Any], ...]
    d1_lineage_mapping_audit: Mapping[str, Any] | None = None
    schema_version: str = (
        SCALABLE_3D_IDENTITY_BLOCKER_DIAGNOSTICS_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != SCALABLE_3D_IDENTITY_BLOCKER_DIAGNOSTICS_SCHEMA_VERSION
        ):
            raise ValueError("unsupported identity blocker diagnostics schema")
        episode_id = str(self.episode_id).strip()
        if not episode_id:
            raise ValueError("episode_id must be non-empty")
        source_hashes = {
            str(name): _digest(value, f"source hash {name}")
            for name, value in self.source_hashes.items()
        }
        if not source_hashes:
            raise ValueError("identity blocker diagnostics require source hashes")
        scored_mapping_count = _nonnegative_int(
            self.scored_mapping_count,
            "scored_mapping_count",
        )
        blocking_mapping_count = _nonnegative_int(
            self.blocking_mapping_count,
            "blocking_mapping_count",
        )
        if blocking_mapping_count > scored_mapping_count:
            raise ValueError("blocking mappings cannot exceed scored mappings")
        reason_counts = _nonnegative_count_mapping(
            self.blocking_reason_counts,
            "blocking_reason_counts",
        )
        root_counts = _nonnegative_count_mapping(
            self.root_cause_counts,
            "root_cause_counts",
        )
        disposition_counts = _nonnegative_count_mapping(
            self.truth_label_disposition_counts,
            "truth_label_disposition_counts",
        )
        known_false_alarm_only_mapping_count = _nonnegative_int(
            self.known_false_alarm_only_mapping_count,
            "known_false_alarm_only_mapping_count",
        )
        target_with_known_false_alarm_mapping_count = _nonnegative_int(
            self.target_with_known_false_alarm_mapping_count,
            "target_with_known_false_alarm_mapping_count",
        )
        strict_available = bool(self.strict_identity_metrics_available)
        reason = (
            None
            if self.strict_identity_metrics_reason is None
            else str(self.strict_identity_metrics_reason).strip()
        )
        if strict_available != (reason is None):
            raise ValueError(
                "strict identity metric availability contradicts its reason"
            )
        object.__setattr__(self, "episode_id", episode_id)
        object.__setattr__(self, "source_hashes", source_hashes)
        object.__setattr__(self, "scored_mapping_count", scored_mapping_count)
        object.__setattr__(
            self,
            "blocking_mapping_count",
            blocking_mapping_count,
        )
        object.__setattr__(
            self,
            "blocking_reason_counts",
            reason_counts,
        )
        object.__setattr__(self, "root_cause_counts", root_counts)
        object.__setattr__(
            self,
            "truth_label_disposition_counts",
            disposition_counts,
        )
        object.__setattr__(
            self,
            "known_false_alarm_only_mapping_count",
            known_false_alarm_only_mapping_count,
        )
        object.__setattr__(
            self,
            "target_with_known_false_alarm_mapping_count",
            target_with_known_false_alarm_mapping_count,
        )
        object.__setattr__(
            self,
            "lineage_disposition_audit",
            tuple(dict(item) for item in self.lineage_disposition_audit),
        )
        object.__setattr__(
            self,
            "blocker_intervals",
            tuple(dict(item) for item in self.blocker_intervals),
        )
        object.__setattr__(
            self,
            "d1_lineage_mapping_audit",
            (
                None
                if self.d1_lineage_mapping_audit is None
                else dict(self.d1_lineage_mapping_audit)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "source_hashes": dict(sorted(self.source_hashes.items())),
            "identity_boundary": {
                "usage": "offline_evaluation_only",
                "online_truth_isolation_verified": (
                    self.online_truth_isolation_verified
                ),
                "identity_heuristics_used": False,
                "allowed_evidence": [
                    "observation_id",
                    "measurement_timestamp",
                    "d1_d2_source_lineage",
                    "independent_offline_truth_labels",
                ],
                "forbidden_evidence": [
                    "position_or_distance",
                    "target_or_actor_name",
                    "actor_id",
                    "terminal_proximity",
                    "posterior_nearest_neighbor",
                ],
            },
            "strict_identity_metrics": {
                "available": self.strict_identity_metrics_available,
                "reason": self.strict_identity_metrics_reason,
                "unique_full_timeline_mapping_required": True,
                "partial_lower_bound_promoted_to_strict": False,
                "id_switch_upper_bound_emitted": False,
            },
            "scored_mapping_count": self.scored_mapping_count,
            "blocking_mapping_count": self.blocking_mapping_count,
            "blocking_reason_counts": dict(
                sorted(self.blocking_reason_counts.items())
            ),
            "root_cause_counts": dict(sorted(self.root_cause_counts.items())),
            "truth_label_disposition_counts": dict(
                sorted(self.truth_label_disposition_counts.items())
            ),
            "known_false_alarm_only_mapping_count": (
                self.known_false_alarm_only_mapping_count
            ),
            "target_with_known_false_alarm_mapping_count": (
                self.target_with_known_false_alarm_mapping_count
            ),
            "lineage_disposition_audit": [
                dict(item) for item in self.lineage_disposition_audit
            ],
            "blocker_interval_count": len(self.blocker_intervals),
            "blocker_intervals": [
                dict(item) for item in self.blocker_intervals
            ],
            "d1_lineage_mapping_audit": self.d1_lineage_mapping_audit,
        }


def build_scalable_3d_identity_blocker_diagnostics(
    evidence: Scalable3DIdentityEvidenceBundle,
    evaluation: Scalable3DIdentityEvaluation,
    truth_labels: Iterable[Scalable3DObservationTruthLabel],
    *,
    identity_evaluation_sha256: str,
    d1_consistency_evidence: Mapping[str, Any] | None = None,
    d1_consistency_evidence_sha256: str | None = None,
) -> Scalable3DIdentityBlockerDiagnostics:
    """Build fail-closed diagnostics from persisted evaluator inputs.

    D1-compatible mapping records are emitted only when every estimate-bearing
    D1 observation has one exact timestamp, one truth label, and one D2 global
    track claim.  Incomplete evidence remains an audit result and never becomes
    a partial consumer sidecar.
    """

    labels = tuple(truth_labels)
    _validate_source_contract(evidence, evaluation, labels)
    tolerance = _nonnegative_float(
        evaluation.configuration.get("timestamp_tolerance_s", 0.0),
        "timestamp_tolerance_s",
    )
    evidence_by_key: dict[
        tuple[int, str],
        list[GlobalTrackLineageEvidence],
    ] = defaultdict(list)
    for record in evidence.records:
        evidence_by_key[(record.frame_index, record.global_track_id)].append(
            record
        )
    label_index: dict[
        str,
        list[Scalable3DObservationTruthLabel],
    ] = defaultdict(list)
    for label in labels:
        label_index[label.observation_id].append(label)

    frame_timestamp_by_index = {
        frame.frame_index: frame.frame_timestamp for frame in evaluation.frames
    }
    events: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    root_cause_counts: Counter[str] = Counter()
    scored_mapping_count = 0
    blocking_mapping_count = 0
    known_false_alarm_only_mapping_count = 0
    target_with_known_false_alarm_mapping_count = 0
    lineage_disposition_audit: list[dict[str, Any]] = []
    for frame in evaluation.frames:
        for mapping in frame.mappings:
            if mapping.association_state not in _OBSERVED_ASSOCIATION_STATES:
                continue
            observations = _observation_evidence(
                evidence_by_key.get(
                    (frame.frame_index, mapping.global_track_id),
                    (),
                ),
                label_index,
                tolerance=tolerance,
            )
            disposition_counts: Counter[str] = Counter(
                disposition
                for observation in observations
                for disposition in observation[
                    "truth_label_dispositions"
                ]
            )
            has_target = (
                disposition_counts[OBSERVATION_TRUTH_DISPOSITION_TARGET] > 0
            )
            has_known_false_alarm = (
                disposition_counts[
                    OBSERVATION_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM
                ]
                > 0
            )
            has_unknown = (
                disposition_counts[OBSERVATION_TRUTH_DISPOSITION_UNKNOWN] > 0
            )
            if has_known_false_alarm or has_unknown:
                lineage_disposition_audit.append(
                    {
                        "frame_index": frame.frame_index,
                        "frame_timestamp": frame.frame_timestamp,
                        "global_track_id": mapping.global_track_id,
                        "mapping_status": mapping.status,
                        "mapping_reason": mapping.reason,
                        "candidate_truth_target_ids": list(
                            mapping.candidate_truth_target_ids
                        ),
                        "disposition_counts": dict(
                            sorted(disposition_counts.items())
                        ),
                        "source_observations": observations,
                    }
                )
            if has_target and has_known_false_alarm:
                target_with_known_false_alarm_mapping_count += 1
            if (
                mapping.status == "excluded"
                and mapping.reason == "known_false_alarm_only"
            ):
                known_false_alarm_only_mapping_count += 1
                continue
            scored_mapping_count += 1
            reasons = tuple(
                reason
                for reason in mapping.unavailable_reasons
                if reason not in _NON_BLOCKING_AUDIT_REASONS
            )
            if not reasons:
                continue
            blocking_mapping_count += 1
            reason_counts.update(reasons)
            if "multiple_truth_targets_for_global_track" in reasons:
                root_cause_counts["persisted_multi_truth_track_frame"] += 1
            if "truth_label_missing" in reasons:
                root_cause_counts["truth_sidecar_label_absent"] += 1
            if "truth_label_unknown" in reasons:
                root_cause_counts["truth_sidecar_label_unknown"] += 1
            if not (
                set(reasons)
                & {
                    "multiple_truth_targets_for_global_track",
                    "truth_label_missing",
                    "truth_label_unknown",
                }
            ):
                root_cause_counts["other_identity_integrity_blocker"] += 1
            for reason in reasons:
                events.append(
                    {
                        "reason": reason,
                        "global_track_id": mapping.global_track_id,
                        "candidate_truth_target_ids": list(
                            mapping.candidate_truth_target_ids
                        ),
                        "frame_index": frame.frame_index,
                        "frame_timestamp": frame.frame_timestamp,
                        "source_observations": observations,
                    }
                )

    source_hashes = dict(evaluation.source_hashes)
    source_hashes["identity_evaluation"] = _digest(
        identity_evaluation_sha256,
        "identity evaluation SHA-256",
    )
    d1_audit = None
    if d1_consistency_evidence is not None:
        if d1_consistency_evidence_sha256 is None:
            raise ValueError(
                "D1 consistency evidence requires its persisted SHA-256"
            )
        source_hashes["d1_consistency_online_evidence"] = _digest(
            d1_consistency_evidence_sha256,
            "d1 consistency evidence SHA-256",
        )
        d1_audit = _build_d1_lineage_mapping_audit(
            episode_id=evidence.episode_id,
            evidence=evidence,
            labels=labels,
            d1_consistency_evidence=d1_consistency_evidence,
            source_hashes=source_hashes,
            tolerance=tolerance,
        )

    intervals = _coalesce_blocker_intervals(
        events,
        frame_timestamp_by_index=frame_timestamp_by_index,
    )
    return Scalable3DIdentityBlockerDiagnostics(
        episode_id=evidence.episode_id,
        source_hashes=source_hashes,
        strict_identity_metrics_available=evaluation.metrics.available,
        strict_identity_metrics_reason=evaluation.metrics.reason,
        online_truth_isolation_verified=bool(
            evaluation.audit.get(
                "online_truth_isolation_verified",
                False,
            )
        ),
        scored_mapping_count=scored_mapping_count,
        blocking_mapping_count=blocking_mapping_count,
        blocking_reason_counts=reason_counts,
        root_cause_counts=root_cause_counts,
        blocker_intervals=intervals,
        truth_label_disposition_counts=Counter(
            label.disposition for label in labels
        ),
        known_false_alarm_only_mapping_count=(
            known_false_alarm_only_mapping_count
        ),
        target_with_known_false_alarm_mapping_count=(
            target_with_known_false_alarm_mapping_count
        ),
        lineage_disposition_audit=tuple(lineage_disposition_audit),
        d1_lineage_mapping_audit=d1_audit,
    )


def write_scalable_3d_identity_blocker_diagnostics(
    path: str | Path,
    diagnostics: Scalable3DIdentityBlockerDiagnostics,
) -> str:
    """Write deterministic diagnostics JSON and return its SHA-256."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_json_bytes(diagnostics.to_dict()) + b"\n"
    destination.write_bytes(encoded)
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _validate_source_contract(
    evidence: Scalable3DIdentityEvidenceBundle,
    evaluation: Scalable3DIdentityEvaluation,
    labels: Sequence[Scalable3DObservationTruthLabel],
) -> None:
    if evidence.episode_id != evaluation.episode_id:
        raise ValueError("identity evidence/evaluation episode mismatch")
    for name, digest in evidence.source_hashes.items():
        if evaluation.source_hashes.get(name) != digest:
            raise ValueError(
                f"identity evaluation source hash mismatch for {name}"
            )
    if evaluation.source_hashes.get("identity_evidence_bundle") != (
        hash_scalable_3d_identity_evidence(evidence)
    ):
        raise ValueError("identity evaluation evidence bundle hash mismatch")
    normalized_truth_hash = hash_scalable_3d_observation_truth_labels(labels)
    source_truth_hash = hash_scalable_3d_observation_truth_label_sources(
        labels
    )
    persisted_truth_hash = evidence.source_hashes[
        "observation_truth_labels"
    ]
    if persisted_truth_hash not in {
        normalized_truth_hash,
        source_truth_hash,
    }:
        raise ValueError("identity diagnostics truth sidecar hash mismatch")
    audited_normalized_hash = evaluation.audit.get(
        "normalized_observation_truth_labels_sha256"
    )
    if (
        audited_normalized_hash is not None
        and audited_normalized_hash != normalized_truth_hash
    ):
        raise ValueError(
            "identity diagnostics normalized truth sidecar hash mismatch"
        )
    if not bool(
        evaluation.audit.get("online_truth_isolation_verified", False)
    ):
        raise ValueError("identity diagnostics require verified truth isolation")
    if bool(evaluation.audit.get("identity_heuristics_used", True)):
        raise ValueError("identity diagnostics reject heuristic identity input")


def _observation_evidence(
    records: Sequence[GlobalTrackLineageEvidence],
    label_index: Mapping[str, Sequence[Scalable3DObservationTruthLabel]],
    *,
    tolerance: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[
        tuple[int, str, float, tuple[str, ...], int]
    ] = set()
    for record in records:
        for ref in record.source_observations:
            key = (
                record.frame_index,
                ref.observation_id,
                ref.measurement_timestamp,
                ref.source_lineage,
                ref.replay_generation,
            )
            if key in seen:
                continue
            seen.add(key)
            labels = tuple(label_index.get(ref.observation_id, ()))
            matching = tuple(
                label
                for label in labels
                if abs(
                    label.measurement_timestamp - ref.measurement_timestamp
                )
                <= tolerance
            )
            if not labels:
                label_status = "missing"
            elif not matching:
                label_status = "timestamp_mismatch"
            elif len(
                {
                    (
                        item.disposition,
                        item.truth_target_id,
                        item.measurement_timestamp,
                    )
                    for item in labels
                }
            ) > 1:
                label_status = "conflict"
            else:
                label_status = "unique"
            rows.append(
                {
                    "observation_id": ref.observation_id,
                    "measurement_timestamp": ref.measurement_timestamp,
                    "replay_generation": ref.replay_generation,
                    "source_lineage_sha256": _sha256_payload(
                        list(ref.source_lineage)
                    ),
                    "truth_label_status": label_status,
                    "truth_label_dispositions": sorted(
                        {item.disposition for item in matching}
                    ),
                    "truth_target_ids": sorted(
                        {
                            item.truth_target_id
                            for item in matching
                            if (
                                item.disposition
                                == OBSERVATION_TRUTH_DISPOSITION_TARGET
                                and item.truth_target_id is not None
                            )
                        }
                    ),
                }
            )
    rows.sort(
        key=lambda item: (
            item["measurement_timestamp"],
            item["observation_id"],
            item["source_lineage_sha256"],
        )
    )
    return rows


def _coalesce_blocker_intervals(
    events: Sequence[Mapping[str, Any]],
    *,
    frame_timestamp_by_index: Mapping[int, float],
) -> tuple[Mapping[str, Any], ...]:
    grouped: dict[
        tuple[str, str, tuple[str, ...]],
        list[Mapping[str, Any]],
    ] = defaultdict(list)
    for event in events:
        grouped[
            (
                str(event["reason"]),
                str(event["global_track_id"]),
                tuple(event["candidate_truth_target_ids"]),
            )
        ].append(event)

    intervals: list[dict[str, Any]] = []
    for (
        reason,
        global_track_id,
        candidate_truth_ids,
    ), items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: int(item["frame_index"]))
        current: list[Mapping[str, Any]] = []
        for item in ordered:
            if current and int(item["frame_index"]) != (
                int(current[-1]["frame_index"]) + 1
            ):
                intervals.append(
                    _blocker_interval_payload(
                        reason,
                        global_track_id,
                        candidate_truth_ids,
                        current,
                    )
                )
                current = []
            current.append(item)
        if current:
            intervals.append(
                _blocker_interval_payload(
                    reason,
                    global_track_id,
                    candidate_truth_ids,
                    current,
                )
            )

    intervals.sort(
        key=lambda item: (
            item["start_frame_index"],
            item["global_track_id"],
            item["reason"],
        )
    )
    for interval in intervals:
        for frame_index in interval["frame_indices"]:
            if frame_index not in frame_timestamp_by_index:
                raise ValueError(
                    "blocker interval references an unknown evaluation frame"
                )
    return tuple(intervals)


def _blocker_interval_payload(
    reason: str,
    global_track_id: str,
    candidate_truth_ids: Sequence[str],
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    frame_indices = [int(item["frame_index"]) for item in events]
    frame_timestamps = [float(item["frame_timestamp"]) for item in events]
    return {
        "reason": reason,
        "global_track_id": global_track_id,
        "candidate_truth_target_ids": list(candidate_truth_ids),
        "start_frame_index": frame_indices[0],
        "end_frame_index": frame_indices[-1],
        "start_frame_timestamp": frame_timestamps[0],
        "end_frame_timestamp": frame_timestamps[-1],
        "frame_count": len(frame_indices),
        "frame_indices": frame_indices,
        "frames": [
            {
                "frame_index": int(item["frame_index"]),
                "frame_timestamp": float(item["frame_timestamp"]),
                "source_observations": list(item["source_observations"]),
            }
            for item in events
        ],
    }


def _build_d1_lineage_mapping_audit(
    *,
    episode_id: str,
    evidence: Scalable3DIdentityEvidenceBundle,
    labels: Sequence[Scalable3DObservationTruthLabel],
    d1_consistency_evidence: Mapping[str, Any],
    source_hashes: Mapping[str, str],
    tolerance: float,
) -> dict[str, Any]:
    records_value = d1_consistency_evidence.get("records")
    if not isinstance(records_value, Sequence) or isinstance(
        records_value,
        (str, bytes, bytearray),
    ):
        raise ValueError("D1 consistency evidence records must be a sequence")
    records = tuple(
        _mapping(item, "D1 consistency evidence record")
        for item in records_value
    )
    if int(d1_consistency_evidence.get("record_count", -1)) != len(records):
        raise ValueError("D1 consistency evidence record_count mismatch")

    estimate_records = tuple(
        record for record in records if _estimate_available(record)
    )
    records_by_observation: dict[str, list[Mapping[str, Any]]] = defaultdict(
        list
    )
    for record in estimate_records:
        observation_id = _identifier(
            record.get("observation_id"),
            "D1 estimate observation_id",
        )
        records_by_observation[observation_id].append(record)

    label_index: dict[
        str,
        list[Scalable3DObservationTruthLabel],
    ] = defaultdict(list)
    for label in labels:
        label_index[label.observation_id].append(label)
    lineage_claims_by_observation: dict[
        str,
        set[tuple[str, float]],
    ] = defaultdict(set)
    for item in evidence.records:
        if item.association_state not in _OBSERVED_ASSOCIATION_STATES:
            continue
        for ref in item.source_observations:
            lineage_claims_by_observation[ref.observation_id].add(
                (
                    item.global_track_id,
                    ref.measurement_timestamp,
                )
            )

    reason_to_observations: dict[str, list[str]] = defaultdict(list)
    candidate_records: list[dict[str, Any]] = []
    target_observation_ids: list[str] = []
    known_false_alarm_observation_ids: list[str] = []
    for observation_id, observation_records in sorted(
        records_by_observation.items()
    ):
        reasons: set[str] = set()
        if len(observation_records) != 1:
            reasons.add("d1_estimate_observation_duplicate")
        measurement_timestamps = {
            _finite_float(
                record.get("measurement_timestamp"),
                "D1 estimate measurement_timestamp",
            )
            for record in observation_records
        }
        if len(measurement_timestamps) != 1:
            reasons.add("d1_estimate_observation_duplicate")
        measurement_timestamp = min(measurement_timestamps)

        observation_labels = tuple(label_index.get(observation_id, ()))
        matching_labels: tuple[
            Scalable3DObservationTruthLabel,
            ...,
        ] = ()
        if not observation_labels:
            reasons.add("truth_label_missing")
        else:
            if len(observation_labels) != 1:
                reasons.add("truth_label_duplicate")
            matching_labels = tuple(
                label
                for label in observation_labels
                if abs(
                    label.measurement_timestamp - measurement_timestamp
                )
                <= tolerance
            )
            if not matching_labels:
                reasons.add("truth_label_timestamp_mismatch")
            if len(
                {
                    (
                        label.disposition,
                        label.truth_target_id,
                        label.measurement_timestamp,
                    )
                    for label in observation_labels
                }
            ) > 1:
                reasons.add("truth_label_conflict")

        resolved_label = (
            matching_labels[0]
            if len(observation_labels) == 1
            and len(matching_labels) == 1
            else None
        )
        if (
            resolved_label is not None
            and resolved_label.disposition
            == OBSERVATION_TRUTH_DISPOSITION_UNKNOWN
        ):
            reasons.add("truth_label_unknown")

        matching_claims: set[tuple[str, float]] = set()
        if (
            resolved_label is not None
            and resolved_label.disposition
            == OBSERVATION_TRUTH_DISPOSITION_TARGET
        ):
            target_observation_ids.append(observation_id)
            all_claims = lineage_claims_by_observation.get(
                observation_id,
                set(),
            )
            matching_claims = {
                claim
                for claim in all_claims
                if abs(claim[1] - measurement_timestamp) <= tolerance
            }
            if not all_claims:
                reasons.add("d2_lineage_claim_missing")
            elif not matching_claims:
                reasons.add("d2_lineage_claim_timestamp_mismatch")
            elif len(
                {claim[0] for claim in matching_claims}
            ) != 1:
                reasons.add("d2_lineage_claim_conflict")
        elif (
            resolved_label is not None
            and resolved_label.disposition
            == OBSERVATION_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM
        ):
            known_false_alarm_observation_ids.append(observation_id)

        if reasons:
            for reason in reasons:
                reason_to_observations[reason].append(observation_id)
            continue
        if (
            resolved_label is not None
            and resolved_label.disposition
            == OBSERVATION_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM
        ):
            continue
        global_track_id = next(iter({claim[0] for claim in matching_claims}))
        if resolved_label is None or resolved_label.truth_target_id is None:
            raise ValueError("resolved D1 target label lacks truth_target_id")
        truth_id = resolved_label.truth_target_id
        candidate_records.append(
            {
                "schema_version": D1_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION,
                "observation_id": observation_id,
                "measurement_timestamp": measurement_timestamp,
                "global_track_id": global_track_id,
                "truth_id": truth_id,
            }
        )

    reason_counts = {
        reason: len(set(observation_ids))
        for reason, observation_ids in reason_to_observations.items()
    }
    unique_estimate_count = len(records_by_observation)
    consumable = (
        not reason_counts
        and bool(candidate_records)
        and len(candidate_records) == len(target_observation_ids)
        and (
            len(target_observation_ids)
            + len(known_false_alarm_observation_ids)
            == unique_estimate_count
        )
    )
    reason = None
    if not consumable:
        reason = next(
            (
                item
                for item in _D1_REASON_PRIORITY
                if reason_counts.get(item, 0) > 0
            ),
            "d1_lineage_mapping_empty",
        )
    return {
        "schema_version": (
            SCALABLE_3D_D1_LINEAGE_MAPPING_AUDIT_SCHEMA_VERSION
        ),
        "episode_id": episode_id,
        "usage": "offline_evaluation_only",
        "producer_role": "d2_evaluator_only",
        "identity_join": "source_observation_lineage",
        "online_truth_used": False,
        "consumer_record_schema_version": (
            D1_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION
        ),
        "estimate_record_count": len(estimate_records),
        "unique_estimate_observation_count": unique_estimate_count,
        "available_candidate_mapping_count": len(candidate_records),
        "target_observation_count": len(target_observation_ids),
        "known_false_alarm_exclusion_count": len(
            known_false_alarm_observation_ids
        ),
        "known_false_alarm_observation_ids": sorted(
            known_false_alarm_observation_ids
        ),
        "unresolved_observation_count": len(
            set().union(
                *(
                    set(observation_ids)
                    for observation_ids in reason_to_observations.values()
                ),
                set(),
            )
        ),
        "unresolved_reason_counts": dict(sorted(reason_counts.items())),
        "unresolved_observation_ids_by_reason": {
            key: sorted(set(values))
            for key, values in sorted(reason_to_observations.items())
        },
        "d1_consumable": consumable,
        "reason": reason,
        "mapping_records_emitted": consumable,
        "mapping_records": candidate_records if consumable else [],
        "source_hashes": {
            name: value
            for name, value in sorted(source_hashes.items())
            if name
            in {
                "online_d1_records",
                "online_d2_records",
                "observation_truth_labels",
                "identity_evidence_bundle",
                "identity_evaluation",
                "d1_consistency_online_evidence",
            }
        },
    }


def _estimate_available(record: Mapping[str, Any]) -> bool:
    availability = record.get("availability")
    if not isinstance(availability, Mapping):
        raise ValueError("D1 consistency record lacks availability")
    estimate = availability.get("estimate")
    if not isinstance(estimate, Mapping):
        raise ValueError("D1 consistency record lacks estimate availability")
    value = estimate.get("available")
    if type(value) is not bool:
        raise ValueError("D1 estimate availability must be boolean")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _identifier(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must be non-empty")
    return result


def _finite_float(value: Any, name: str) -> float:
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _nonnegative_float(value: Any, name: str) -> float:
    result = _finite_float(value, name)
    if result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _nonnegative_int(value: Any, name: str) -> int:
    result = int(value)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _nonnegative_count_mapping(
    value: Mapping[str, int],
    name: str,
) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return {
        str(key): _nonnegative_int(count, f"{name}.{key}")
        for key, count in value.items()
    }


def _digest(value: Any, name: str) -> str:
    result = str(value).strip().lower()
    if (
        not result.startswith("sha256:")
        or len(result) != 71
        or any(character not in "0123456789abcdef" for character in result[7:])
    ):
        raise ValueError(f"{name} must be a sha256 digest")
    return result


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_payload(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json_bytes(value)).hexdigest()}"
