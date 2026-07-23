from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .types import SensorObservation


CONSISTENCY_SOURCE_PROVENANCE_SCHEMA_VERSION = "d1.consistency.source_provenance.v1"
ONLINE_CONSISTENCY_EVIDENCE_RECORD_SCHEMA_VERSION = (
    "d1.consistency.online_evidence_record.v1"
)
ONLINE_CONSISTENCY_EVIDENCE_BUNDLE_SCHEMA_VERSION = (
    "d1.consistency.online_evidence_bundle.v1"
)
ONLINE_CONSISTENCY_AGGREGATION_RECORD_SCHEMA_VERSION = (
    "d1.consistency.online_aggregation_record.v1"
)
CONSISTENCY_RANGE_BIN_SCHEMA_VERSION = "d1.consistency.range_bins.v1"
CONSISTENCY_RANGE_BIN_EDGES_M = (1_000.0, 3_000.0, 5_000.0)

_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_GATE_DECISIONS = {
    "accepted",
    "rejected",
    "not_configured",
    "not_applicable",
    "unavailable",
}


def consistency_payload_sha256(payload: Any) -> str:
    """Return a deterministic SHA-256 digest for a finite JSON payload."""

    encoded = json.dumps(
        _json_value(payload),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class EvidenceAvailability:
    available: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        available = bool(self.available)
        reason = None if self.reason is None else str(self.reason).strip()
        if available and reason:
            raise ValueError("available evidence must not carry an unavailable reason")
        if not available and not reason:
            raise ValueError("unavailable evidence requires a reason")
        object.__setattr__(self, "available", available)
        object.__setattr__(self, "reason", reason)

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "reason": self.reason}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "EvidenceAvailability":
        _reject_unknown_keys(payload, {"available", "reason"}, "evidence availability")
        return cls(
            available=_strict_bool(payload["available"], "evidence availability.available"),
            reason=payload.get("reason"),
        )


@dataclass(frozen=True, slots=True)
class OnlineEvidenceAvailability:
    innovation: EvidenceAvailability
    gate: EvidenceAvailability
    estimate: EvidenceAvailability
    range: EvidenceAvailability
    source_global_track_id: EvidenceAvailability

    def to_dict(self) -> dict[str, Any]:
        return {
            "innovation": self.innovation.to_dict(),
            "gate": self.gate.to_dict(),
            "estimate": self.estimate.to_dict(),
            "range": self.range.to_dict(),
            "source_global_track_id": self.source_global_track_id.to_dict(),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OnlineEvidenceAvailability":
        _reject_unknown_keys(
            payload,
            {"innovation", "gate", "estimate", "range", "source_global_track_id"},
            "online evidence availability",
        )
        return cls(
            innovation=EvidenceAvailability.from_mapping(_mapping(payload, "innovation")),
            gate=EvidenceAvailability.from_mapping(_mapping(payload, "gate")),
            estimate=EvidenceAvailability.from_mapping(_mapping(payload, "estimate")),
            range=EvidenceAvailability.from_mapping(_mapping(payload, "range")),
            source_global_track_id=EvidenceAvailability.from_mapping(
                _mapping(payload, "source_global_track_id")
            ),
        )


@dataclass(frozen=True, slots=True)
class ConsistencySourceProvenance:
    """Episode/source identity shared by online and evaluator-only artifacts."""

    scenario_id: str
    scenario_version: str
    run_id: str
    seed: int
    producer_id: str
    producer_version: str
    source_schema_version: str
    source_digest: str
    config_digest: str
    schema_version: str = CONSISTENCY_SOURCE_PROVENANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CONSISTENCY_SOURCE_PROVENANCE_SCHEMA_VERSION:
            raise ValueError("unsupported consistency source provenance schema")
        for name in (
            "scenario_id",
            "scenario_version",
            "run_id",
            "producer_id",
            "producer_version",
            "source_schema_version",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "seed", int(self.seed))
        _validate_digest(self.source_digest, "source_digest")
        _validate_digest(self.config_digest, "config_digest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "run_id": self.run_id,
            "seed": self.seed,
            "producer_id": self.producer_id,
            "producer_version": self.producer_version,
            "source_schema_version": self.source_schema_version,
            "source_digest": self.source_digest,
            "config_digest": self.config_digest,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ConsistencySourceProvenance":
        _reject_unknown_keys(
            payload,
            {
                "schema_version",
                "scenario_id",
                "scenario_version",
                "run_id",
                "seed",
                "producer_id",
                "producer_version",
                "source_schema_version",
                "source_digest",
                "config_digest",
            },
            "consistency source provenance",
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            scenario_id=str(payload["scenario_id"]),
            scenario_version=str(payload["scenario_version"]),
            run_id=str(payload["run_id"]),
            seed=int(payload["seed"]),
            producer_id=str(payload["producer_id"]),
            producer_version=str(payload["producer_version"]),
            source_schema_version=str(payload["source_schema_version"]),
            source_digest=str(payload["source_digest"]),
            config_digest=str(payload["config_digest"]),
        )


@dataclass(frozen=True, slots=True)
class OnlineConsistencyEvidenceRecord:
    observation_id: str
    source_lineage: tuple[str, ...]
    sensor_id: str
    sensor_type: str
    source_sensor_type: str
    measurement_timestamp: float
    arrival_timestamp: float
    innovation_dimension: int | None
    nis: float | None
    gate_threshold: float | None
    gate_decision: str
    accepted: bool | None
    range_m: float | None
    range_bin: str
    confidence: float
    quality_flags: tuple[str, ...]
    covariance_scale_reasons: tuple[str, ...]
    source_global_track_id: str | None
    estimate_timestamp: float | None
    state_ned: tuple[float, ...] | None
    covariance_ned: tuple[tuple[float, ...], ...] | None
    oosm_replayed: bool
    replay_revision: int
    replay_count: int
    duplicate_count: int
    disposition: str
    availability: OnlineEvidenceAvailability
    evidence_id: str = ""
    schema_version: str = ONLINE_CONSISTENCY_EVIDENCE_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ONLINE_CONSISTENCY_EVIDENCE_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported online consistency evidence record schema")
        for name in (
            "observation_id",
            "sensor_id",
            "sensor_type",
            "source_sensor_type",
            "range_bin",
            "disposition",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        lineage = tuple(str(item) for item in self.source_lineage)
        if not lineage:
            raise ValueError("source_lineage must not be empty")
        object.__setattr__(self, "source_lineage", lineage)

        measurement_timestamp = _finite_float(
            self.measurement_timestamp, "measurement_timestamp"
        )
        arrival_timestamp = _finite_float(self.arrival_timestamp, "arrival_timestamp")
        if arrival_timestamp + 1.0e-12 < measurement_timestamp:
            raise ValueError("arrival_timestamp must not precede measurement_timestamp")
        object.__setattr__(self, "measurement_timestamp", measurement_timestamp)
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)

        innovation_dimension = self.innovation_dimension
        if innovation_dimension is not None:
            innovation_dimension = int(innovation_dimension)
            if innovation_dimension <= 0:
                raise ValueError("innovation_dimension must be positive")
            object.__setattr__(self, "innovation_dimension", innovation_dimension)
        nis = _optional_non_negative_float(self.nis, "nis")
        gate_threshold = _optional_positive_float(self.gate_threshold, "gate_threshold")
        object.__setattr__(self, "nis", nis)
        object.__setattr__(self, "gate_threshold", gate_threshold)
        if self.gate_decision not in _GATE_DECISIONS:
            raise ValueError(f"unsupported gate_decision: {self.gate_decision!r}")
        if self.accepted is not None and type(self.accepted) is not bool:
            raise ValueError("accepted must be a boolean or null")
        if self.gate_decision == "rejected" and self.accepted is not False:
            raise ValueError("a rejected gate decision requires accepted=False")
        if self.gate_decision == "accepted" and self.accepted is not True:
            raise ValueError("an accepted gate decision requires accepted=True")
        if gate_threshold is not None and nis is not None and self.accepted is not None:
            expected = nis <= gate_threshold
            if bool(self.accepted) != expected:
                raise ValueError("accepted does not match NIS gate decision")
        if self.availability.gate.available and self.gate_decision not in {
            "accepted",
            "rejected",
        }:
            raise ValueError("available gate evidence requires an accepted/rejected decision")
        if not self.availability.gate.available and self.gate_decision in {
            "accepted",
            "rejected",
        }:
            raise ValueError("accepted/rejected gate decisions require available gate evidence")

        range_m = _optional_positive_float(self.range_m, "range_m")
        object.__setattr__(self, "range_m", range_m)
        if self.range_bin != consistency_range_bin(range_m):
            raise ValueError("range_bin does not match range_m")
        confidence = _finite_float(self.confidence, "confidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "quality_flags", _unique_strings(self.quality_flags))
        object.__setattr__(
            self,
            "covariance_scale_reasons",
            _unique_strings(self.covariance_scale_reasons),
        )

        track_id = (
            None
            if self.source_global_track_id is None
            else str(self.source_global_track_id).strip()
        )
        if track_id == "":
            track_id = None
        object.__setattr__(self, "source_global_track_id", track_id)
        estimate_timestamp = (
            None
            if self.estimate_timestamp is None
            else _finite_float(self.estimate_timestamp, "estimate_timestamp")
        )
        object.__setattr__(self, "estimate_timestamp", estimate_timestamp)
        state = _state_tuple(self.state_ned)
        covariance = _covariance_tuple(self.covariance_ned)
        object.__setattr__(self, "state_ned", state)
        object.__setattr__(self, "covariance_ned", covariance)

        if type(self.oosm_replayed) is not bool:
            raise ValueError("oosm_replayed must be a boolean")
        replay_revision = int(self.replay_revision)
        replay_count = int(self.replay_count)
        duplicate_count = int(self.duplicate_count)
        if replay_revision < 0 or replay_count < 0 or duplicate_count < 0:
            raise ValueError(
                "replay_revision, replay_count, and duplicate_count must be non-negative"
            )
        object.__setattr__(self, "replay_revision", replay_revision)
        object.__setattr__(self, "replay_count", replay_count)
        object.__setattr__(self, "duplicate_count", duplicate_count)

        _validate_availability_consistency(
            self.availability,
            innovation_dimension=innovation_dimension,
            nis=nis,
            gate_threshold=gate_threshold,
            state=state,
            covariance=covariance,
            estimate_timestamp=estimate_timestamp,
            range_m=range_m,
            source_global_track_id=track_id,
        )
        expected_evidence_id = _evidence_id(
            observation_id=self.observation_id,
            source_lineage=lineage,
            sensor_id=self.sensor_id,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
        )
        if self.evidence_id and self.evidence_id != expected_evidence_id:
            raise ValueError("online consistency evidence_id does not match record lineage")
        object.__setattr__(self, "evidence_id", expected_evidence_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "observation_id": self.observation_id,
            "source_lineage": list(self.source_lineage),
            "sensor_id": self.sensor_id,
            "sensor_type": self.sensor_type,
            "source_sensor_type": self.source_sensor_type,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "innovation_dimension": self.innovation_dimension,
            "nis": self.nis,
            "gate_threshold": self.gate_threshold,
            "gate_decision": self.gate_decision,
            "accepted": self.accepted,
            "range_m": self.range_m,
            "range_bin": self.range_bin,
            "range_bin_schema_version": CONSISTENCY_RANGE_BIN_SCHEMA_VERSION,
            "confidence": self.confidence,
            "quality_flags": list(self.quality_flags),
            "covariance_scale_reasons": list(self.covariance_scale_reasons),
            "source_global_track_id": self.source_global_track_id,
            "estimate_timestamp": self.estimate_timestamp,
            "state_ned": None if self.state_ned is None else list(self.state_ned),
            "covariance_ned": (
                None
                if self.covariance_ned is None
                else [list(row) for row in self.covariance_ned]
            ),
            "oosm_replayed": self.oosm_replayed,
            "replay_revision": self.replay_revision,
            "replay_count": self.replay_count,
            "duplicate_count": self.duplicate_count,
            "disposition": self.disposition,
            "availability": self.availability.to_dict(),
        }

    def with_replay_counters(
        self,
        *,
        replay_revision: int,
        replay_count: int,
    ) -> "OnlineConsistencyEvidenceRecord":
        """Copy a validated record while changing only replay counters.

        Cached fixed-lag replay leaves every measurement, estimate, covariance,
        availability, timestamp, and lineage field unchanged. Re-running the
        complete constructor validation for that case is redundant and costly.
        The source instance has already passed ``__post_init__``; this method
        therefore validates the only two changed fields and copies the frozen
        slots verbatim. ``evidence_id`` remains valid because replay counters do
        not participate in its lineage-derived identity.
        """

        revision = int(replay_revision)
        count = int(replay_count)
        if revision < 0 or count < 0:
            raise ValueError("replay_revision and replay_count must be non-negative")

        refreshed = object.__new__(type(self))
        for name in self.__slots__:
            object.__setattr__(refreshed, name, getattr(self, name))
        object.__setattr__(refreshed, "replay_revision", revision)
        object.__setattr__(refreshed, "replay_count", count)
        return refreshed

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OnlineConsistencyEvidenceRecord":
        _reject_unknown_keys(
            payload,
            {
                "schema_version",
                "evidence_id",
                "observation_id",
                "source_lineage",
                "sensor_id",
                "sensor_type",
                "source_sensor_type",
                "measurement_timestamp",
                "arrival_timestamp",
                "innovation_dimension",
                "nis",
                "gate_threshold",
                "gate_decision",
                "accepted",
                "range_m",
                "range_bin",
                "range_bin_schema_version",
                "confidence",
                "quality_flags",
                "covariance_scale_reasons",
                "source_global_track_id",
                "estimate_timestamp",
                "state_ned",
                "covariance_ned",
                "oosm_replayed",
                "replay_revision",
                "replay_count",
                "duplicate_count",
                "disposition",
                "availability",
            },
            "online consistency evidence record",
        )
        if payload.get("range_bin_schema_version") != CONSISTENCY_RANGE_BIN_SCHEMA_VERSION:
            raise ValueError("unsupported consistency range-bin schema")
        covariance = payload.get("covariance_ned")
        return cls(
            schema_version=str(payload["schema_version"]),
            evidence_id=str(payload["evidence_id"]),
            observation_id=str(payload["observation_id"]),
            source_lineage=tuple(payload["source_lineage"]),
            sensor_id=str(payload["sensor_id"]),
            sensor_type=str(payload["sensor_type"]),
            source_sensor_type=str(payload["source_sensor_type"]),
            measurement_timestamp=float(payload["measurement_timestamp"]),
            arrival_timestamp=float(payload["arrival_timestamp"]),
            innovation_dimension=payload.get("innovation_dimension"),
            nis=payload.get("nis"),
            gate_threshold=payload.get("gate_threshold"),
            gate_decision=str(payload["gate_decision"]),
            accepted=(
                None
                if payload.get("accepted") is None
                else _strict_bool(payload["accepted"], "online evidence accepted")
            ),
            range_m=payload.get("range_m"),
            range_bin=str(payload["range_bin"]),
            confidence=float(payload["confidence"]),
            quality_flags=tuple(payload.get("quality_flags", ())),
            covariance_scale_reasons=tuple(
                payload.get("covariance_scale_reasons", ())
            ),
            source_global_track_id=payload.get("source_global_track_id"),
            estimate_timestamp=payload.get("estimate_timestamp"),
            state_ned=(
                None if payload.get("state_ned") is None else tuple(payload["state_ned"])
            ),
            covariance_ned=(
                None
                if covariance is None
                else tuple(tuple(row) for row in covariance)
            ),
            oosm_replayed=_strict_bool(
                payload["oosm_replayed"], "online evidence oosm_replayed"
            ),
            replay_revision=int(payload["replay_revision"]),
            replay_count=int(payload["replay_count"]),
            duplicate_count=int(payload["duplicate_count"]),
            disposition=str(payload["disposition"]),
            availability=OnlineEvidenceAvailability.from_mapping(
                _mapping(payload, "availability")
            ),
        )


@dataclass(frozen=True, slots=True)
class OnlineConsistencyEvidenceBundle:
    provenance: ConsistencySourceProvenance
    records: tuple[OnlineConsistencyEvidenceRecord, ...]
    records_digest: str = ""
    content_digest: str = ""
    schema_version: str = ONLINE_CONSISTENCY_EVIDENCE_BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ONLINE_CONSISTENCY_EVIDENCE_BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported online consistency evidence bundle schema")
        records = tuple(
            sorted(
                self.records,
                key=lambda item: (
                    item.arrival_timestamp,
                    item.measurement_timestamp,
                    item.observation_id,
                ),
            )
        )
        if len({record.observation_id for record in records}) != len(records):
            raise ValueError("online consistency observation_id values must be unique")
        if len({record.evidence_id for record in records}) != len(records):
            raise ValueError("online consistency evidence_id values must be unique")
        object.__setattr__(self, "records", records)

        records_digest = consistency_payload_sha256(
            [record.to_dict() for record in records]
        )
        if self.records_digest and self.records_digest != records_digest:
            raise ValueError("online consistency records digest mismatch")
        object.__setattr__(self, "records_digest", records_digest)
        content_digest = consistency_payload_sha256(
            self._unsigned_manifest(records_digest)
        )
        if self.content_digest and self.content_digest != content_digest:
            raise ValueError("online consistency bundle digest mismatch")
        object.__setattr__(self, "content_digest", content_digest)

    def _unsigned_manifest(self, records_digest: str) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_schema_version": ONLINE_CONSISTENCY_EVIDENCE_RECORD_SCHEMA_VERSION,
            "range_bin_schema_version": CONSISTENCY_RANGE_BIN_SCHEMA_VERSION,
            "range_bin_edges_m": list(CONSISTENCY_RANGE_BIN_EDGES_M),
            "provenance": self.provenance.to_dict(),
            "record_count": len(self.records),
            "records_digest": records_digest,
            "truth_policy": "online_truth_forbidden",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._unsigned_manifest(self.records_digest),
            "content_digest": self.content_digest,
            "records": [record.to_dict() for record in self.records],
        }

    def aggregation_records(self) -> tuple[dict[str, Any], ...]:
        """Return flat truth-free rows keyed for scenario/sensor/range grouping."""

        context = {
            "schema_version": ONLINE_CONSISTENCY_AGGREGATION_RECORD_SCHEMA_VERSION,
            "evidence_record_schema_version": (
                ONLINE_CONSISTENCY_EVIDENCE_RECORD_SCHEMA_VERSION
            ),
            "scenario_id": self.provenance.scenario_id,
            "scenario_version": self.provenance.scenario_version,
            "run_id": self.provenance.run_id,
            "seed": self.provenance.seed,
            "online_evidence_digest": self.content_digest,
            "source_schema_version": self.provenance.source_schema_version,
            "source_digest": self.provenance.source_digest,
            "config_digest": self.provenance.config_digest,
        }
        rows: list[dict[str, Any]] = []
        for record in self.records:
            rows.append(
                {
                    **context,
                    "evidence_id": record.evidence_id,
                    "observation_id": record.observation_id,
                    "source_lineage": list(record.source_lineage),
                    "sensor_id": record.sensor_id,
                    "sensor_type": record.sensor_type,
                    "source_sensor_type": record.source_sensor_type,
                    "measurement_timestamp": record.measurement_timestamp,
                    "arrival_timestamp": record.arrival_timestamp,
                    "innovation_dimension": record.innovation_dimension,
                    "nis": record.nis,
                    "normalized_nis": (
                        None
                        if record.nis is None or record.innovation_dimension is None
                        else record.nis / record.innovation_dimension
                    ),
                    "gate_threshold": record.gate_threshold,
                    "gate_decision": record.gate_decision,
                    "accepted": record.accepted,
                    "range_m": record.range_m,
                    "range_bin": record.range_bin,
                    "confidence": record.confidence,
                    "quality_flags": list(record.quality_flags),
                    "covariance_scale_reasons": list(
                        record.covariance_scale_reasons
                    ),
                    "source_global_track_id": record.source_global_track_id,
                    "oosm_replayed": record.oosm_replayed,
                    "replay_revision": record.replay_revision,
                    "disposition": record.disposition,
                    "availability": record.availability.to_dict(),
                }
            )
        return tuple(rows)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OnlineConsistencyEvidenceBundle":
        _reject_unknown_keys(
            payload,
            {
                "schema_version",
                "record_schema_version",
                "range_bin_schema_version",
                "range_bin_edges_m",
                "provenance",
                "record_count",
                "records_digest",
                "truth_policy",
                "content_digest",
                "records",
            },
            "online consistency evidence bundle",
        )
        if (
            payload.get("record_schema_version")
            != ONLINE_CONSISTENCY_EVIDENCE_RECORD_SCHEMA_VERSION
        ):
            raise ValueError("unsupported online consistency record schema")
        if payload.get("range_bin_schema_version") != CONSISTENCY_RANGE_BIN_SCHEMA_VERSION:
            raise ValueError("unsupported consistency range-bin schema")
        if tuple(float(item) for item in payload.get("range_bin_edges_m", ())) != (
            CONSISTENCY_RANGE_BIN_EDGES_M
        ):
            raise ValueError("online consistency range-bin edges mismatch")
        records_payload = payload.get("records")
        if not isinstance(records_payload, list):
            raise ValueError("online consistency bundle records must be a list")
        records = tuple(
            OnlineConsistencyEvidenceRecord.from_mapping(_as_mapping(item))
            for item in records_payload
        )
        if int(payload.get("record_count", -1)) != len(records):
            raise ValueError("online consistency record_count mismatch")
        if payload.get("truth_policy") != "online_truth_forbidden":
            raise ValueError("online consistency bundle truth policy mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            provenance=ConsistencySourceProvenance.from_mapping(
                _mapping(payload, "provenance")
            ),
            records=records,
            records_digest=str(payload["records_digest"]),
            content_digest=str(payload["content_digest"]),
        )


def export_online_consistency_evidence(
    records: Iterable[OnlineConsistencyEvidenceRecord],
    provenance: ConsistencySourceProvenance,
) -> OnlineConsistencyEvidenceBundle:
    return OnlineConsistencyEvidenceBundle(
        provenance=provenance,
        records=tuple(records),
    )


def consistency_range_bin(range_m: float | None) -> str:
    if range_m is None:
        return "unavailable"
    distance = _optional_positive_float(range_m, "range_m")
    assert distance is not None
    first, second, third = CONSISTENCY_RANGE_BIN_EDGES_M
    if distance < first:
        return "[0,1000)m"
    if distance < second:
        return "[1000,3000)m"
    if distance < third:
        return "[3000,5000)m"
    return "[5000,+inf)m"


def unavailable_consistency_evidence(
    observation: SensorObservation,
    reason: str,
    *,
    oosm_replayed: bool = False,
    previous: OnlineConsistencyEvidenceRecord | None = None,
) -> OnlineConsistencyEvidenceRecord:
    base = previous or _base_record(observation)
    return replace(
        base,
        innovation_dimension=None,
        nis=None,
        gate_threshold=None,
        gate_decision="unavailable",
        accepted=None,
        source_global_track_id=None,
        estimate_timestamp=None,
        state_ned=None,
        covariance_ned=None,
        oosm_replayed=bool(oosm_replayed or base.oosm_replayed),
        disposition=str(reason),
        availability=OnlineEvidenceAvailability(
            innovation=EvidenceAvailability(False, str(reason)),
            gate=EvidenceAvailability(False, str(reason)),
            estimate=EvidenceAvailability(False, str(reason)),
            range=base.availability.range,
            source_global_track_id=EvidenceAvailability(False, str(reason)),
        ),
    )


def mark_consistency_evidence_oosm(
    record: OnlineConsistencyEvidenceRecord,
) -> OnlineConsistencyEvidenceRecord:
    return replace(record, oosm_replayed=True)


def mark_consistency_evidence_duplicate(
    record: OnlineConsistencyEvidenceRecord,
) -> OnlineConsistencyEvidenceRecord:
    """Count an exact repeated arrival without erasing its accepted evidence."""

    return replace(record, duplicate_count=record.duplicate_count + 1)


def initialization_consistency_evidence(
    observation: SensorObservation,
    *,
    source_global_track_id: str,
    state: Sequence[float] | np.ndarray,
    covariance: Sequence[Sequence[float]] | np.ndarray,
    replay_revision: int,
    previous: OnlineConsistencyEvidenceRecord | None = None,
) -> OnlineConsistencyEvidenceRecord:
    base = previous or _base_record(observation)
    state_tuple, covariance_tuple, estimate_availability = _safe_estimate(
        state,
        covariance,
    )
    track_id = str(source_global_track_id).strip()
    if not track_id:
        raise ValueError("source_global_track_id must be non-empty")
    return replace(
        base,
        innovation_dimension=None,
        nis=None,
        gate_threshold=None,
        gate_decision="not_applicable",
        accepted=True,
        source_global_track_id=track_id,
        estimate_timestamp=observation.measurement_timestamp,
        state_ned=state_tuple,
        covariance_ned=covariance_tuple,
        replay_revision=int(replay_revision),
        replay_count=base.replay_count + 1,
        disposition="track_initialization",
        availability=OnlineEvidenceAvailability(
            innovation=EvidenceAvailability(False, "track_initialization_has_no_innovation"),
            gate=EvidenceAvailability(False, "track_initialization_has_no_gate"),
            estimate=estimate_availability,
            range=base.availability.range,
            source_global_track_id=EvidenceAvailability(True),
        ),
    )


def update_consistency_evidence(
    observation: SensorObservation,
    *,
    source_global_track_id: str,
    state: Sequence[float] | np.ndarray,
    covariance: Sequence[Sequence[float]] | np.ndarray,
    innovation_dimension: int,
    nis: float,
    gated: bool,
    replay_revision: int,
    previous: OnlineConsistencyEvidenceRecord | None = None,
) -> OnlineConsistencyEvidenceRecord:
    base = previous or _base_record(observation)
    state_tuple, covariance_tuple, estimate_availability = _safe_estimate(
        state,
        covariance,
    )
    track_id = str(source_global_track_id).strip()
    if not track_id:
        raise ValueError("source_global_track_id must be non-empty")
    finite_nis = float(nis) if np.isfinite(nis) and float(nis) >= -1.0e-9 else None
    if finite_nis is not None:
        finite_nis = max(0.0, finite_nis)
        innovation_availability = EvidenceAvailability(True)
    else:
        innovation_availability = EvidenceAvailability(False, "non_finite_innovation")
    raw_gate = observation.metadata.get("filter_innovation_gate_chi2")
    gate_threshold = None if raw_gate is None else float(raw_gate)
    if gate_threshold is None:
        gate_availability = EvidenceAvailability(False, "filter_gate_not_configured")
        gate_decision = "not_configured"
        accepted = True
    elif finite_nis is None:
        gate_availability = EvidenceAvailability(False, "non_finite_innovation")
        gate_decision = "unavailable"
        accepted = not bool(gated)
    else:
        gate_availability = EvidenceAvailability(True)
        gate_decision = "rejected" if gated else "accepted"
        accepted = not bool(gated)
    return replace(
        base,
        innovation_dimension=int(innovation_dimension),
        nis=finite_nis,
        gate_threshold=gate_threshold,
        gate_decision=gate_decision,
        accepted=accepted,
        source_global_track_id=track_id,
        estimate_timestamp=observation.measurement_timestamp,
        state_ned=state_tuple,
        covariance_ned=covariance_tuple,
        replay_revision=int(replay_revision),
        replay_count=base.replay_count + 1,
        disposition=(
            "innovation_gate_rejected" if gated else "filter_update_accepted"
        ),
        availability=OnlineEvidenceAvailability(
            innovation=innovation_availability,
            gate=gate_availability,
            estimate=estimate_availability,
            range=base.availability.range,
            source_global_track_id=EvidenceAvailability(True),
        ),
    )


def _base_record(observation: SensorObservation) -> OnlineConsistencyEvidenceRecord:
    range_m = _observation_range(observation)
    range_availability = (
        EvidenceAvailability(True)
        if range_m is not None
        else EvidenceAvailability(False, "sensor_observation_has_no_direct_range")
    )
    pending = EvidenceAvailability(False, "observation_not_yet_processed")
    return OnlineConsistencyEvidenceRecord(
        observation_id=str(observation.observation_id),
        source_lineage=_truth_free_lineage(observation),
        sensor_id=str(observation.sensor_id),
        sensor_type=str(observation.modality),
        source_sensor_type=str(
            observation.metadata.get("source_modality", observation.modality)
        ),
        measurement_timestamp=float(observation.measurement_timestamp),
        arrival_timestamp=float(observation.arrival_timestamp),
        innovation_dimension=None,
        nis=None,
        gate_threshold=None,
        gate_decision="unavailable",
        accepted=None,
        range_m=range_m,
        range_bin=consistency_range_bin(range_m),
        confidence=float(observation.confidence),
        quality_flags=tuple(observation.quality_flags),
        covariance_scale_reasons=_covariance_reasons(observation),
        source_global_track_id=None,
        estimate_timestamp=None,
        state_ned=None,
        covariance_ned=None,
        oosm_replayed=False,
        replay_revision=0,
        replay_count=0,
        duplicate_count=0,
        disposition="observation_not_yet_processed",
        availability=OnlineEvidenceAvailability(
            innovation=pending,
            gate=pending,
            estimate=pending,
            range=range_availability,
            source_global_track_id=pending,
        ),
    )


def _safe_estimate(
    state: Sequence[float] | np.ndarray,
    covariance: Sequence[Sequence[float]] | np.ndarray,
) -> tuple[
    tuple[float, ...] | None,
    tuple[tuple[float, ...], ...] | None,
    EvidenceAvailability,
]:
    try:
        state_tuple = _state_tuple(state)
        covariance_tuple = _covariance_tuple(covariance)
    except ValueError as exc:
        return None, None, EvidenceAvailability(False, f"invalid_estimate:{exc}")
    return state_tuple, covariance_tuple, EvidenceAvailability(True)


def _truth_free_lineage(observation: SensorObservation) -> tuple[str, ...]:
    explicit = observation.metadata.get("source_lineage_key")
    if explicit is None:
        explicit = observation.metadata.get("lineage_id")
    sequence = None
    for key in (
        "sequence_id",
        "sequence",
        "source_sequence",
        "payload_sequence",
        "airsim_frame_index",
    ):
        if observation.metadata.get(key) is not None:
            sequence = observation.metadata[key]
            break
    opaque = {
        "explicit": explicit,
        "source": observation.source_node_id or observation.sensor_id,
        "sensor_id": observation.sensor_id,
        "sensor_type": observation.modality,
        "payload_kind": observation.payload_kind,
        "sequence": sequence,
        "observation_id": None if explicit is not None else observation.observation_id,
    }
    return (
        "opaque_online_lineage",
        f"sensor:{observation.sensor_id}",
        consistency_payload_sha256(opaque),
    )


def _observation_range(observation: SensorObservation) -> float | None:
    if observation.modality != "radar":
        return None
    values = np.asarray(observation.measurement, dtype=float).reshape(-1)
    if values.size == 0 or not np.isfinite(values[0]) or values[0] <= 0.0:
        return None
    return float(values[0])


def _covariance_reasons(observation: SensorObservation) -> tuple[str, ...]:
    values: list[str] = []
    for key in (
        "covariance_scale_reason",
        "observation_covariance_limit_reasons",
        "covariance_limit_reasons",
    ):
        raw = observation.metadata.get(key)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple, set, frozenset)):
            values.extend(str(item) for item in raw)
        else:
            values.append(str(raw))
    return _unique_strings(values)


def _validate_availability_consistency(
    availability: OnlineEvidenceAvailability,
    *,
    innovation_dimension: int | None,
    nis: float | None,
    gate_threshold: float | None,
    state: tuple[float, ...] | None,
    covariance: tuple[tuple[float, ...], ...] | None,
    estimate_timestamp: float | None,
    range_m: float | None,
    source_global_track_id: str | None,
) -> None:
    if availability.innovation.available != (
        innovation_dimension is not None and nis is not None
    ):
        raise ValueError("innovation availability does not match innovation fields")
    if availability.gate.available != (gate_threshold is not None and nis is not None):
        raise ValueError("gate availability does not match gate fields")
    if availability.estimate.available != (
        state is not None and covariance is not None and estimate_timestamp is not None
    ):
        raise ValueError("estimate availability does not match estimate fields")
    if availability.range.available != (range_m is not None):
        raise ValueError("range availability does not match range_m")
    if availability.source_global_track_id.available != (
        source_global_track_id is not None
    ):
        raise ValueError(
            "source_global_track_id availability does not match source_global_track_id"
        )


def _state_tuple(value: Sequence[float] | np.ndarray | None) -> tuple[float, ...] | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=float)
    if array.shape != (6,) or not np.isfinite(array).all():
        raise ValueError("state_ned must be a finite six-state vector")
    return tuple(float(item) for item in array)


def _covariance_tuple(
    value: Sequence[Sequence[float]] | np.ndarray | None,
) -> tuple[tuple[float, ...], ...] | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=float)
    if array.shape != (6, 6) or not np.isfinite(array).all():
        raise ValueError("covariance_ned must be a finite 6x6 matrix")
    if not np.allclose(array, array.T, rtol=1.0e-9, atol=1.0e-9):
        raise ValueError("covariance_ned must be symmetric")
    eigenvalues = np.linalg.eigvalsh(0.5 * (array + array.T))
    tolerance = 1.0e-9 * max(1.0, float(np.max(np.abs(eigenvalues))))
    if float(eigenvalues[0]) < -tolerance:
        raise ValueError("covariance_ned must be positive semidefinite")
    return tuple(tuple(float(item) for item in row) for row in array)


def _evidence_id(
    *,
    observation_id: str,
    source_lineage: tuple[str, ...],
    sensor_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> str:
    digest = consistency_payload_sha256(
        {
            "observation_id": observation_id,
            "source_lineage": source_lineage,
            "sensor_id": sensor_id,
            "measurement_timestamp": measurement_timestamp,
            "arrival_timestamp": arrival_timestamp,
        }
    )
    return f"d1-evidence-{digest.split(':', 1)[1]}"


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("consistency payload contains a non-finite float")
        return value
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    raise TypeError(f"unsupported consistency payload type: {type(value).__name__}")


def _validate_digest(value: str, name: str) -> None:
    if not _DIGEST_PATTERN.fullmatch(str(value)):
        raise ValueError(f"{name} must be a lowercase sha256:<64 hex> digest")


def _finite_float(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _optional_non_negative_float(value: Any, name: str) -> float | None:
    if value is None:
        return None
    result = _finite_float(value, name)
    if result < -1.0e-9:
        raise ValueError(f"{name} must be non-negative")
    return max(0.0, result)


def _optional_positive_float(value: Any, name: str) -> float | None:
    if value is None:
        return None
    result = _finite_float(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _unique_strings(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in values if str(item)))


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _as_mapping(payload[key])


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("consistency payload member must be an object")
    return value


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
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
