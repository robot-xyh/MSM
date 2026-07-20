from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .consistency_evidence import (
    CONSISTENCY_RANGE_BIN_SCHEMA_VERSION,
    EvidenceAvailability,
    OnlineConsistencyEvidenceBundle,
    OnlineConsistencyEvidenceRecord,
    ConsistencySourceProvenance,
    consistency_payload_sha256,
)


OFFLINE_TRUTH_STATE_SAMPLE_SCHEMA_VERSION = "d1.consistency.offline_truth_sample.v1"
OFFLINE_TRUTH_STATE_SIDECAR_SCHEMA_VERSION = (
    "d1.consistency.offline_truth_sidecar.v1"
)
D2_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION = (
    "d1.consistency.d2_lineage_mapping_record.v1"
)
D2_LINEAGE_MAPPING_SIDECAR_SCHEMA_VERSION = (
    "d1.consistency.d2_lineage_mapping_sidecar.v1"
)
OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION = "d1.consistency.offline_result_record.v1"
OFFLINE_CONSISTENCY_RESULT_SCHEMA_VERSION = "d1.consistency.offline_result.v1"
OFFLINE_CONSISTENCY_AGGREGATION_RECORD_SCHEMA_VERSION = (
    "d1.consistency.offline_aggregation_record.v1"
)


@dataclass(frozen=True, slots=True)
class OfflineTruthStateSample:
    truth_id: str
    timestamp: float
    state_ned: tuple[float, ...]
    schema_version: str = OFFLINE_TRUTH_STATE_SAMPLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OFFLINE_TRUTH_STATE_SAMPLE_SCHEMA_VERSION:
            raise ValueError("unsupported offline truth sample schema")
        truth_id = str(self.truth_id).strip()
        if not truth_id:
            raise ValueError("offline truth_id must be non-empty")
        timestamp = _finite_float(self.timestamp, "offline truth timestamp")
        state = np.asarray(self.state_ned, dtype=float)
        if state.shape != (6,) or not np.isfinite(state).all():
            raise ValueError("offline truth state_ned must be a finite six-state vector")
        object.__setattr__(self, "truth_id", truth_id)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "state_ned", tuple(float(item) for item in state))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "truth_id": self.truth_id,
            "timestamp": self.timestamp,
            "state_ned": list(self.state_ned),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OfflineTruthStateSample":
        return cls(
            schema_version=str(payload["schema_version"]),
            truth_id=str(payload["truth_id"]),
            timestamp=float(payload["timestamp"]),
            state_ned=tuple(payload["state_ned"]),
        )


@dataclass(frozen=True, slots=True)
class OfflineTruthStateSidecar:
    provenance: ConsistencySourceProvenance
    samples: tuple[OfflineTruthStateSample, ...]
    content_digest: str = ""
    frame_id: str = "ned"
    schema_version: str = OFFLINE_TRUTH_STATE_SIDECAR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OFFLINE_TRUTH_STATE_SIDECAR_SCHEMA_VERSION:
            raise ValueError("unsupported offline truth sidecar schema")
        if str(self.frame_id).lower() != "ned":
            raise ValueError("offline truth sidecar frame_id must be NED")
        samples = tuple(
            sorted(self.samples, key=lambda item: (item.truth_id, item.timestamp))
        )
        if not samples:
            raise ValueError("offline truth sidecar requires at least one state sample")
        keys = [(item.truth_id, item.timestamp) for item in samples]
        if len(set(keys)) != len(keys):
            raise ValueError("offline truth sidecar contains duplicate truth/time samples")
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "frame_id", "ned")
        digest = consistency_payload_sha256(self._unsigned_payload())
        if self.content_digest and self.content_digest != digest:
            raise ValueError("offline truth sidecar digest mismatch")
        object.__setattr__(self, "content_digest", digest)

    def _unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_schema_version": OFFLINE_TRUTH_STATE_SAMPLE_SCHEMA_VERSION,
            "frame_id": self.frame_id,
            "state_dimension": 6,
            "provenance": self.provenance.to_dict(),
            "sample_count": len(self.samples),
            "samples": [item.to_dict() for item in self.samples],
            "usage": "offline_evaluation_only",
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._unsigned_payload(), "content_digest": self.content_digest}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OfflineTruthStateSidecar":
        if payload.get("sample_schema_version") != OFFLINE_TRUTH_STATE_SAMPLE_SCHEMA_VERSION:
            raise ValueError("unsupported offline truth sample schema")
        if int(payload.get("state_dimension", -1)) != 6:
            raise ValueError("offline truth state_dimension must be six")
        if payload.get("usage") != "offline_evaluation_only":
            raise ValueError("offline truth sidecar usage must be evaluator-only")
        samples_payload = payload.get("samples")
        if not isinstance(samples_payload, list):
            raise ValueError("offline truth sidecar samples must be a list")
        samples = tuple(
            OfflineTruthStateSample.from_mapping(_as_mapping(item))
            for item in samples_payload
        )
        if int(payload.get("sample_count", -1)) != len(samples):
            raise ValueError("offline truth sample_count mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            frame_id=str(payload["frame_id"]),
            provenance=ConsistencySourceProvenance.from_mapping(
                _mapping(payload, "provenance")
            ),
            samples=samples,
            content_digest=str(payload["content_digest"]),
        )


def build_offline_truth_state_sidecar(
    provenance: ConsistencySourceProvenance,
    samples: Iterable[OfflineTruthStateSample | Mapping[str, Any]],
) -> OfflineTruthStateSidecar:
    return OfflineTruthStateSidecar(
        provenance=provenance,
        samples=tuple(_coerce_truth_sample(item) for item in samples),
    )


@dataclass(frozen=True, slots=True)
class D2LineageTruthMapping:
    """Evaluator-only identity decision joined through one source observation."""

    observation_id: str
    measurement_timestamp: float
    global_track_id: str
    truth_id: str
    schema_version: str = D2_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D2_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported D2 lineage mapping record schema")
        observation_id = str(self.observation_id).strip()
        track_id = str(self.global_track_id).strip()
        truth_id = str(self.truth_id).strip()
        if not observation_id or not track_id or not truth_id:
            raise ValueError("D2 lineage mapping IDs must be non-empty")
        object.__setattr__(self, "observation_id", observation_id)
        object.__setattr__(
            self,
            "measurement_timestamp",
            _finite_float(self.measurement_timestamp, "mapping measurement_timestamp"),
        )
        object.__setattr__(self, "global_track_id", track_id)
        object.__setattr__(self, "truth_id", truth_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "measurement_timestamp": self.measurement_timestamp,
            "global_track_id": self.global_track_id,
            "truth_id": self.truth_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "D2LineageTruthMapping":
        _reject_unknown_keys(
            payload,
            {
                "schema_version",
                "observation_id",
                "measurement_timestamp",
                "global_track_id",
                "truth_id",
            },
            "D2 lineage mapping record",
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            observation_id=str(payload["observation_id"]),
            measurement_timestamp=float(payload["measurement_timestamp"]),
            global_track_id=str(payload["global_track_id"]),
            truth_id=str(payload["truth_id"]),
        )


@dataclass(frozen=True, slots=True)
class D2LineageMappingSidecar:
    provenance: ConsistencySourceProvenance
    mappings: tuple[D2LineageTruthMapping, ...]
    online_evidence_digest: str
    truth_sidecar_digest: str
    content_digest: str = ""
    producer_role: str = "d2_evaluator_only"
    schema_version: str = D2_LINEAGE_MAPPING_SIDECAR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D2_LINEAGE_MAPPING_SIDECAR_SCHEMA_VERSION:
            raise ValueError("unsupported D2 lineage mapping sidecar schema")
        if self.producer_role != "d2_evaluator_only":
            raise ValueError("canonical mapping must be produced by D2 evaluator-only path")
        _require_digest(self.online_evidence_digest, "online_evidence_digest")
        _require_digest(self.truth_sidecar_digest, "truth_sidecar_digest")
        mappings = tuple(
            sorted(
                self.mappings,
                key=lambda item: (
                    item.measurement_timestamp,
                    item.observation_id,
                    item.global_track_id,
                ),
            )
        )
        if not mappings:
            raise ValueError("D2 lineage mapping sidecar must not be empty")
        observation_ids = [item.observation_id for item in mappings]
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("D2 lineage mapping observation_id values must be unique")
        object.__setattr__(self, "mappings", mappings)
        digest = consistency_payload_sha256(self._unsigned_payload())
        if self.content_digest and self.content_digest != digest:
            raise ValueError("D2 evaluator canonical mapping digest mismatch")
        object.__setattr__(self, "content_digest", digest)

    def _unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_schema_version": D2_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION,
            "producer_role": self.producer_role,
            "usage": "offline_evaluation_only",
            "identity_join": "source_observation_lineage",
            "provenance": self.provenance.to_dict(),
            "online_evidence_digest": self.online_evidence_digest,
            "truth_sidecar_digest": self.truth_sidecar_digest,
            "mapping_count": len(self.mappings),
            "mappings": [item.to_dict() for item in self.mappings],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._unsigned_payload(), "content_digest": self.content_digest}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "D2LineageMappingSidecar":
        _reject_unknown_keys(
            payload,
            {
                "schema_version",
                "record_schema_version",
                "producer_role",
                "usage",
                "identity_join",
                "provenance",
                "online_evidence_digest",
                "truth_sidecar_digest",
                "mapping_count",
                "mappings",
                "content_digest",
            },
            "D2 lineage mapping sidecar",
        )
        if (
            payload.get("record_schema_version")
            != D2_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION
        ):
            raise ValueError("unsupported D2 evaluator mapping record schema")
        if payload.get("usage") != "offline_evaluation_only":
            raise ValueError("D2 canonical mapping must be evaluator-only")
        if payload.get("identity_join") != "source_observation_lineage":
            raise ValueError("D2 mapping must use source observation lineage")
        mappings_payload = payload.get("mappings")
        if not isinstance(mappings_payload, list):
            raise ValueError("D2 canonical mappings must be a list")
        mappings = tuple(
            D2LineageTruthMapping.from_mapping(_as_mapping(item))
            for item in mappings_payload
        )
        if int(payload.get("mapping_count", -1)) != len(mappings):
            raise ValueError("D2 canonical mapping_count mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            producer_role=str(payload["producer_role"]),
            provenance=ConsistencySourceProvenance.from_mapping(
                _mapping(payload, "provenance")
            ),
            mappings=mappings,
            online_evidence_digest=str(payload["online_evidence_digest"]),
            truth_sidecar_digest=str(payload["truth_sidecar_digest"]),
            content_digest=str(payload["content_digest"]),
        )


def build_d2_lineage_mapping_sidecar(
    provenance: ConsistencySourceProvenance,
    mappings: Iterable[D2LineageTruthMapping | Mapping[str, Any]],
    *,
    online_evidence_digest: str,
    truth_sidecar_digest: str,
) -> D2LineageMappingSidecar:
    return D2LineageMappingSidecar(
        provenance=provenance,
        mappings=tuple(_coerce_mapping_record(item) for item in mappings),
        online_evidence_digest=online_evidence_digest,
        truth_sidecar_digest=truth_sidecar_digest,
    )


@dataclass(frozen=True, slots=True)
class ConsistencyMetricSummary:
    available: bool
    value: float | None
    sample_count: int
    reason: str | None = None

    def __post_init__(self) -> None:
        available = bool(self.available)
        value = None if self.value is None else _finite_float(self.value, "metric value")
        sample_count = int(self.sample_count)
        if sample_count < 0:
            raise ValueError("metric sample_count must be non-negative")
        reason = None if self.reason is None else str(self.reason)
        if available and (value is None or reason is not None or sample_count <= 0):
            raise ValueError("available metric requires value, samples, and no reason")
        if not available and (value is not None or not reason):
            raise ValueError("unavailable metric requires no value and a reason")
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "sample_count", sample_count)
        object.__setattr__(self, "reason", reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "value": self.value,
            "sample_count": self.sample_count,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class OfflineConsistencyRecord:
    evidence_id: str
    observation_id: str
    sensor_id: str
    sensor_type: str
    source_sensor_type: str
    measurement_timestamp: float
    arrival_timestamp: float
    source_global_track_id: str | None
    global_track_id: str | None
    truth_id: str | None
    range_m: float | None
    range_bin: str
    accepted: bool | None
    gate_decision: str
    innovation_dimension: int | None
    nis: float | None
    normalized_nis: float | None
    nis_within_gate: bool | None
    position_error_m: float | None
    velocity_error_mps: float | None
    nees: float | None
    normalized_nees: float | None
    truth_alignment_availability: EvidenceAvailability
    nees_availability: EvidenceAvailability
    nis_coverage_availability: EvidenceAvailability
    schema_version: str = OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported offline consistency record schema")
        for name in ("evidence_id", "observation_id", "sensor_id", "sensor_type"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        for name in (
            "measurement_timestamp",
            "arrival_timestamp",
            "nis",
            "normalized_nis",
            "position_error_m",
            "velocity_error_mps",
            "nees",
            "normalized_nees",
            "range_m",
        ):
            value = getattr(self, name)
            if value is not None:
                _finite_float(value, name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "observation_id": self.observation_id,
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "source_sensor_type": self.source_sensor_type,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "source_global_track_id": self.source_global_track_id,
            "global_track_id": self.global_track_id,
            "truth_id": self.truth_id,
            "range_m": self.range_m,
            "range_bin": self.range_bin,
            "range_bin_schema_version": CONSISTENCY_RANGE_BIN_SCHEMA_VERSION,
            "accepted": self.accepted,
            "gate_decision": self.gate_decision,
            "innovation_dimension": self.innovation_dimension,
            "nis": self.nis,
            "normalized_nis": self.normalized_nis,
            "nis_within_gate": self.nis_within_gate,
            "position_error_m": self.position_error_m,
            "velocity_error_mps": self.velocity_error_mps,
            "nees": self.nees,
            "normalized_nees": self.normalized_nees,
            "availability": {
                "truth_alignment": self.truth_alignment_availability.to_dict(),
                "nees": self.nees_availability.to_dict(),
                "nis_coverage": self.nis_coverage_availability.to_dict(),
            },
        }


@dataclass(frozen=True, slots=True)
class OfflineConsistencyResult:
    scenario_id: str
    scenario_version: str
    run_id: str
    seed: int | None
    status: str
    online_evidence_digest: str | None
    truth_sidecar_digest: str | None
    d2_lineage_mapping_digest: str | None
    records: tuple[OfflineConsistencyRecord, ...]
    metrics: Mapping[str, ConsistencyMetricSummary]
    failure_reasons: tuple[str, ...]
    content_digest: str = ""
    schema_version: str = OFFLINE_CONSISTENCY_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OFFLINE_CONSISTENCY_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported offline consistency result schema")
        if self.status not in {"available", "partial", "unavailable"}:
            raise ValueError("unsupported offline consistency status")
        records = tuple(self.records)
        metrics = dict(sorted(self.metrics.items()))
        failures = tuple(dict.fromkeys(str(item) for item in self.failure_reasons))
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "failure_reasons", failures)
        digest = consistency_payload_sha256(self._unsigned_payload())
        if self.content_digest and self.content_digest != digest:
            raise ValueError("offline consistency result digest mismatch")
        object.__setattr__(self, "content_digest", digest)

    def _unsigned_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_schema_version": OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "run_id": self.run_id,
            "seed": self.seed,
            "status": self.status,
            "input_digests": {
                "online_evidence": self.online_evidence_digest,
                "truth_sidecar": self.truth_sidecar_digest,
                "d2_lineage_mapping": self.d2_lineage_mapping_digest,
            },
            "record_count": len(self.records),
            "records": [record.to_dict() for record in self.records],
            "metrics": {
                name: summary.to_dict() for name, summary in self.metrics.items()
            },
            "failure_reasons": list(self.failure_reasons),
            "truth_usage": "offline_evaluation_only",
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._unsigned_payload(), "content_digest": self.content_digest}

    def aggregation_records(self) -> tuple[dict[str, Any], ...]:
        """Return flat rows for D6 grouping by scenario, sensor, and range bin."""

        context = {
            "schema_version": OFFLINE_CONSISTENCY_AGGREGATION_RECORD_SCHEMA_VERSION,
            "result_record_schema_version": OFFLINE_CONSISTENCY_RECORD_SCHEMA_VERSION,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "run_id": self.run_id,
            "seed": self.seed,
            "offline_result_digest": self.content_digest,
            "online_evidence_digest": self.online_evidence_digest,
            "truth_sidecar_digest": self.truth_sidecar_digest,
            "d2_lineage_mapping_digest": self.d2_lineage_mapping_digest,
        }
        return tuple({**record.to_dict(), **context} for record in self.records)


def evaluate_offline_consistency(
    online_evidence: OnlineConsistencyEvidenceBundle | Mapping[str, Any],
    truth_sidecar: OfflineTruthStateSidecar | Mapping[str, Any] | None,
    d2_lineage_mapping: D2LineageMappingSidecar | Mapping[str, Any] | None,
    *,
    timestamp_tolerance_s: float = 1.0e-9,
) -> OfflineConsistencyResult:
    """Evaluate truth-dependent consistency without identity inference or proximity matching."""

    tolerance = _finite_float(timestamp_tolerance_s, "timestamp_tolerance_s")
    if tolerance < 0.0:
        raise ValueError("timestamp_tolerance_s must be non-negative")
    try:
        evidence = _coerce_online_evidence(online_evidence)
    except (KeyError, TypeError, ValueError) as exc:
        reason = f"online_evidence_invalid:{_reason(exc)}"
        return _empty_result(reason)

    nis_metrics = _nis_metric_summaries(evidence.records)
    truth: OfflineTruthStateSidecar | None = None
    mapping: D2LineageMappingSidecar | None = None
    truth_failure: str | None = None
    try:
        if truth_sidecar is None:
            raise ValueError("offline_truth_sidecar_missing")
        truth = _coerce_truth_sidecar(truth_sidecar)
        if d2_lineage_mapping is None:
            raise ValueError("d2_lineage_mapping_missing")
        mapping = _coerce_mapping_sidecar(d2_lineage_mapping)
        _validate_cross_artifact_contract(evidence, truth, mapping)
        aligned = _align_truth(evidence, truth, mapping, tolerance)
    except (KeyError, TypeError, ValueError) as exc:
        truth_failure = _reason(exc)
        aligned = None

    failures: list[str] = []
    if truth_failure is not None:
        failures.append(truth_failure)
        records = tuple(
            _offline_record_without_truth(record, truth_failure)
            for record in evidence.records
        )
        truth_metrics = _unavailable_truth_metrics(truth_failure)
    else:
        assert truth is not None and mapping is not None and aligned is not None
        records, truth_metrics, nees_failure = _evaluate_aligned_records(
            evidence.records,
            aligned,
        )
        if nees_failure is not None:
            failures.append(nees_failure)

    metrics = {**truth_metrics, **nis_metrics}
    available_count = sum(summary.available for summary in metrics.values())
    status = (
        "available"
        if available_count == len(metrics)
        else "partial"
        if available_count > 0
        else "unavailable"
    )
    return OfflineConsistencyResult(
        scenario_id=evidence.provenance.scenario_id,
        scenario_version=evidence.provenance.scenario_version,
        run_id=evidence.provenance.run_id,
        seed=evidence.provenance.seed,
        status=status,
        online_evidence_digest=evidence.content_digest,
        truth_sidecar_digest=None if truth is None else truth.content_digest,
        d2_lineage_mapping_digest=None if mapping is None else mapping.content_digest,
        records=records,
        metrics=metrics,
        failure_reasons=tuple(failures),
    )


def _evaluate_aligned_records(
    evidence_records: Sequence[OnlineConsistencyEvidenceRecord],
    aligned: Sequence[tuple[str, str, np.ndarray] | None],
) -> tuple[
    tuple[OfflineConsistencyRecord, ...],
    dict[str, ConsistencyMetricSummary],
    str | None,
]:
    squared_position_errors: list[float] = []
    squared_velocity_errors: list[float] = []
    nees_values: list[float] = []
    raw_rows: list[dict[str, Any]] = []
    nees_failure: str | None = None

    for record, alignment in zip(evidence_records, aligned):
        base = _offline_record_fields(record)
        if alignment is None:
            reason = record.availability.estimate.reason or "estimate_unavailable"
            raw_rows.append(
                {
                    **base,
                    "truth_id": None,
                    "position_error_m": None,
                    "velocity_error_mps": None,
                    "nees": None,
                    "normalized_nees": None,
                    "truth_alignment_availability": EvidenceAvailability(False, reason),
                    "nees_availability": EvidenceAvailability(False, reason),
                }
            )
            continue

        global_track_id, truth_id, truth_state = alignment
        assert record.state_ned is not None and record.covariance_ned is not None
        estimate = np.asarray(record.state_ned, dtype=float)
        error = estimate - truth_state
        position_squared = float(error[:3] @ error[:3])
        velocity_squared = float(error[3:] @ error[3:])
        squared_position_errors.append(position_squared)
        squared_velocity_errors.append(velocity_squared)
        covariance = np.asarray(record.covariance_ned, dtype=float)
        try:
            np.linalg.cholesky(covariance)
            nees = float(error @ np.linalg.solve(covariance, error))
            if not np.isfinite(nees) or nees < -1.0e-9:
                raise np.linalg.LinAlgError("non-finite NEES")
            nees = max(0.0, nees)
            nees_values.append(nees)
            nees_availability = EvidenceAvailability(True)
        except np.linalg.LinAlgError:
            nees = None
            nees_availability = EvidenceAvailability(
                False, "estimate_covariance_singular"
            )
            nees_failure = "nees_unavailable:estimate_covariance_singular"
        raw_rows.append(
            {
                **base,
                "global_track_id": global_track_id,
                "truth_id": truth_id,
                "position_error_m": math.sqrt(position_squared),
                "velocity_error_mps": math.sqrt(velocity_squared),
                "nees": nees,
                "normalized_nees": None if nees is None else nees / 6.0,
                "truth_alignment_availability": EvidenceAvailability(True),
                "nees_availability": nees_availability,
            }
        )

    if nees_failure is not None:
        for row in raw_rows:
            if row["truth_alignment_availability"].available:
                row["nees"] = None
                row["normalized_nees"] = None
                row["nees_availability"] = EvidenceAvailability(
                    False, "episode_contains_singular_estimate_covariance"
                )
        nees_metric = _metric_unavailable(
            "episode_contains_singular_estimate_covariance",
            len(nees_values),
        )
        normalized_nees_metric = nees_metric
    elif nees_values:
        nees_metric = _metric_available(float(np.mean(nees_values)), len(nees_values))
        normalized_nees_metric = _metric_available(
            float(np.mean(nees_values) / 6.0), len(nees_values)
        )
    else:
        nees_metric = _metric_unavailable("no_truth_aligned_estimates")
        normalized_nees_metric = nees_metric

    records = tuple(OfflineConsistencyRecord(**row) for row in raw_rows)
    if squared_position_errors:
        count = len(squared_position_errors)
        position_metric = _metric_available(
            math.sqrt(float(np.mean(squared_position_errors))), count
        )
        velocity_metric = _metric_available(
            math.sqrt(float(np.mean(squared_velocity_errors))), count
        )
    else:
        position_metric = _metric_unavailable("no_truth_aligned_estimates")
        velocity_metric = position_metric
    return (
        records,
        {
            "position_rmse_m": position_metric,
            "velocity_rmse_mps": velocity_metric,
            "mean_nees": nees_metric,
            "mean_normalized_nees": normalized_nees_metric,
        },
        nees_failure,
    )


def _offline_record_without_truth(
    record: OnlineConsistencyEvidenceRecord,
    reason: str,
) -> OfflineConsistencyRecord:
    return OfflineConsistencyRecord(
        **_offline_record_fields(record),
        truth_id=None,
        position_error_m=None,
        velocity_error_mps=None,
        nees=None,
        normalized_nees=None,
        truth_alignment_availability=EvidenceAvailability(False, reason),
        nees_availability=EvidenceAvailability(False, reason),
    )


def _offline_record_fields(record: OnlineConsistencyEvidenceRecord) -> dict[str, Any]:
    normalized_nis = (
        None
        if record.nis is None or record.innovation_dimension is None
        else record.nis / record.innovation_dimension
    )
    gate_available = record.availability.gate.available
    return {
        "evidence_id": record.evidence_id,
        "observation_id": record.observation_id,
        "sensor_id": record.sensor_id,
        "sensor_type": record.sensor_type,
        "source_sensor_type": record.source_sensor_type,
        "measurement_timestamp": record.measurement_timestamp,
        "arrival_timestamp": record.arrival_timestamp,
        "source_global_track_id": record.source_global_track_id,
        "global_track_id": None,
        "range_m": record.range_m,
        "range_bin": record.range_bin,
        "accepted": record.accepted,
        "gate_decision": record.gate_decision,
        "innovation_dimension": record.innovation_dimension,
        "nis": record.nis,
        "normalized_nis": normalized_nis,
        "nis_within_gate": (
            None
            if not gate_available or record.nis is None or record.gate_threshold is None
            else record.nis <= record.gate_threshold
        ),
        "nis_coverage_availability": (
            EvidenceAvailability(True)
            if gate_available
            else EvidenceAvailability(
                False,
                record.availability.gate.reason or "filter_gate_not_configured",
            )
        ),
    }


def _nis_metric_summaries(
    records: Sequence[OnlineConsistencyEvidenceRecord],
) -> dict[str, ConsistencyMetricSummary]:
    nis_records = [record for record in records if record.availability.innovation.available]
    gated_records = [record for record in records if record.availability.gate.available]
    if nis_records:
        mean_nis = _metric_available(
            float(np.mean([record.nis for record in nis_records])), len(nis_records)
        )
        mean_normalized = _metric_available(
            float(
                np.mean(
                    [
                        record.nis / record.innovation_dimension
                        for record in nis_records
                        if record.nis is not None and record.innovation_dimension is not None
                    ]
                )
            ),
            len(nis_records),
        )
    else:
        mean_nis = _metric_unavailable("no_innovation_samples")
        mean_normalized = mean_nis
    if gated_records:
        within = [
            record.nis <= record.gate_threshold
            for record in gated_records
            if record.nis is not None and record.gate_threshold is not None
        ]
        coverage = _metric_available(float(np.mean(within)), len(within))
    else:
        coverage = _metric_unavailable("no_gate_configured_innovation_samples")
    return {
        "mean_nis": mean_nis,
        "mean_normalized_nis": mean_normalized,
        "nis_gate_coverage": coverage,
    }


def _unavailable_truth_metrics(reason: str) -> dict[str, ConsistencyMetricSummary]:
    unavailable = _metric_unavailable(reason)
    return {
        "position_rmse_m": unavailable,
        "velocity_rmse_mps": unavailable,
        "mean_nees": unavailable,
        "mean_normalized_nees": unavailable,
    }


def _align_truth(
    evidence: OnlineConsistencyEvidenceBundle,
    truth: OfflineTruthStateSidecar,
    mapping: D2LineageMappingSidecar,
    tolerance_s: float,
) -> tuple[tuple[str, str, np.ndarray] | None, ...]:
    estimate_records = [
        record for record in evidence.records if record.availability.estimate.available
    ]
    evidence_observation_ids = {record.observation_id for record in estimate_records}
    mappings = {item.observation_id: item for item in mapping.mappings}
    if not evidence_observation_ids.issubset(mappings):
        raise ValueError("d2_lineage_mapping_observation_coverage_mismatch")
    truth_ids = {sample.truth_id for sample in truth.samples}
    unknown_truth = {item.truth_id for item in mapping.mappings} - truth_ids
    if unknown_truth:
        raise ValueError("d2_lineage_mapping_references_unknown_truth_id")

    samples: dict[str, list[OfflineTruthStateSample]] = {}
    for sample in truth.samples:
        samples.setdefault(sample.truth_id, []).append(sample)
    aligned: list[tuple[str, str, np.ndarray] | None] = []
    for record in evidence.records:
        if not record.availability.estimate.available:
            aligned.append(None)
            continue
        if record.source_global_track_id is None or record.estimate_timestamp is None:
            raise ValueError("online_estimate_lacks_source_track_or_timestamp")
        if abs(record.estimate_timestamp - record.measurement_timestamp) > tolerance_s:
            raise ValueError("online_estimate_measurement_timestamp_mismatch")
        lineage_mapping = mappings[record.observation_id]
        if (
            abs(lineage_mapping.measurement_timestamp - record.measurement_timestamp)
            > tolerance_s
        ):
            raise ValueError("d2_lineage_mapping_timestamp_mismatch")
        truth_id = lineage_mapping.truth_id
        truth_candidates = [
            sample
            for sample in samples.get(truth_id, ())
            if abs(sample.timestamp - record.estimate_timestamp) <= tolerance_s
        ]
        if len(truth_candidates) != 1:
            raise ValueError("offline_truth_timestamp_missing_or_ambiguous")
        aligned.append(
            (
                lineage_mapping.global_track_id,
                truth_id,
                np.asarray(truth_candidates[0].state_ned, dtype=float),
            )
        )
    return tuple(aligned)


def _validate_cross_artifact_contract(
    evidence: OnlineConsistencyEvidenceBundle,
    truth: OfflineTruthStateSidecar,
    mapping: D2LineageMappingSidecar,
) -> None:
    expected = (
        evidence.provenance.scenario_id,
        evidence.provenance.scenario_version,
        evidence.provenance.run_id,
        evidence.provenance.seed,
        evidence.provenance.config_digest,
    )
    for label, provenance in (
        ("truth", truth.provenance),
        ("mapping", mapping.provenance),
    ):
        actual = (
            provenance.scenario_id,
            provenance.scenario_version,
            provenance.run_id,
            provenance.seed,
            provenance.config_digest,
        )
        if actual != expected:
            raise ValueError(f"{label}_provenance_mismatch")
    if mapping.online_evidence_digest != evidence.content_digest:
        raise ValueError("d2_lineage_mapping_online_evidence_digest_mismatch")
    if mapping.truth_sidecar_digest != truth.content_digest:
        raise ValueError("d2_lineage_mapping_truth_sidecar_digest_mismatch")


def _empty_result(reason: str) -> OfflineConsistencyResult:
    metrics = {
        name: _metric_unavailable(reason)
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
    return OfflineConsistencyResult(
        scenario_id="unavailable",
        scenario_version="unavailable",
        run_id="unavailable",
        seed=None,
        status="unavailable",
        online_evidence_digest=None,
        truth_sidecar_digest=None,
        d2_lineage_mapping_digest=None,
        records=(),
        metrics=metrics,
        failure_reasons=(reason,),
    )


def _metric_available(value: float, sample_count: int) -> ConsistencyMetricSummary:
    return ConsistencyMetricSummary(True, float(value), int(sample_count))


def _metric_unavailable(
    reason: str,
    sample_count: int = 0,
) -> ConsistencyMetricSummary:
    return ConsistencyMetricSummary(False, None, int(sample_count), str(reason))


def _coerce_online_evidence(
    value: OnlineConsistencyEvidenceBundle | Mapping[str, Any],
) -> OnlineConsistencyEvidenceBundle:
    if isinstance(value, OnlineConsistencyEvidenceBundle):
        return value
    return OnlineConsistencyEvidenceBundle.from_mapping(_as_mapping(value))


def _coerce_truth_sidecar(
    value: OfflineTruthStateSidecar | Mapping[str, Any],
) -> OfflineTruthStateSidecar:
    if isinstance(value, OfflineTruthStateSidecar):
        return value
    return OfflineTruthStateSidecar.from_mapping(_as_mapping(value))


def _coerce_mapping_sidecar(
    value: D2LineageMappingSidecar | Mapping[str, Any],
) -> D2LineageMappingSidecar:
    if isinstance(value, D2LineageMappingSidecar):
        return value
    return D2LineageMappingSidecar.from_mapping(_as_mapping(value))


def _coerce_truth_sample(
    value: OfflineTruthStateSample | Mapping[str, Any],
) -> OfflineTruthStateSample:
    if isinstance(value, OfflineTruthStateSample):
        return value
    payload = _as_mapping(value)
    return OfflineTruthStateSample(
        schema_version=str(
            payload.get("schema_version", OFFLINE_TRUTH_STATE_SAMPLE_SCHEMA_VERSION)
        ),
        truth_id=str(payload["truth_id"]),
        timestamp=float(payload["timestamp"]),
        state_ned=tuple(payload["state_ned"]),
    )


def _coerce_mapping_record(
    value: D2LineageTruthMapping | Mapping[str, Any],
) -> D2LineageTruthMapping:
    if isinstance(value, D2LineageTruthMapping):
        return value
    payload = _as_mapping(value)
    return D2LineageTruthMapping(
        schema_version=str(
            payload.get(
                "schema_version",
                D2_LINEAGE_MAPPING_RECORD_SCHEMA_VERSION,
            )
        ),
        observation_id=str(payload["observation_id"]),
        measurement_timestamp=float(payload["measurement_timestamp"]),
        global_track_id=str(payload["global_track_id"]),
        truth_id=str(payload["truth_id"]),
    )


def _reason(exc: BaseException) -> str:
    text = str(exc).strip().lower().replace(" ", "_")
    return text or type(exc).__name__.lower()


def _require_digest(value: str, name: str) -> None:
    text = str(value)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise ValueError(f"{name} must be a sha256 digest")
    try:
        int(text[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a sha256 digest") from exc


def _finite_float(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _as_mapping(payload[key])


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("consistency artifact member must be an object")
    return value


def _reject_unknown_keys(
    payload: Mapping[str, Any],
    allowed: set[str],
    context: str,
) -> None:
    unknown = {str(key) for key in payload} - allowed
    if unknown:
        raise ValueError(
            f"{context} contains unsupported field(s): {', '.join(sorted(unknown))}"
        )
