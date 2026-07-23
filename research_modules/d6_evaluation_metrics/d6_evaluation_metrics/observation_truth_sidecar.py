"""Versioned, evaluator-only observation truth sidecar validation.

D6 validates persisted sidecars without importing a producer or inferring
labels from observation names, geometry, actor metadata, or online state.
Version 1 is a target-only historical contract.  Version 2 carries an explicit
three-state disposition.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping


SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V1 = "scalable3d-offline-truth-v1"
SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V2 = "scalable3d-offline-truth-v2"
D2_OBSERVATION_TRUTH_SCHEMA_V1 = "d2.scalable3d_observation_truth.v1"
D2_OBSERVATION_TRUTH_SCHEMA_V2 = "d2.scalable3d_observation_truth.v2"

TRUTH_DISPOSITION_TARGET = "target"
TRUTH_DISPOSITION_KNOWN_FALSE_ALARM = "known_false_alarm"
TRUTH_DISPOSITION_UNKNOWN = "unknown"
TRUTH_DISPOSITIONS = frozenset(
    {
        TRUTH_DISPOSITION_TARGET,
        TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
        TRUTH_DISPOSITION_UNKNOWN,
    }
)

_EXTERNAL_SCHEMAS = frozenset(
    {
        SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V1,
        SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V2,
    }
)
_D2_SCHEMAS = frozenset(
    {
        D2_OBSERVATION_TRUTH_SCHEMA_V1,
        D2_OBSERVATION_TRUTH_SCHEMA_V2,
    }
)
_V1_SCHEMAS = frozenset(
    {
        SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V1,
        D2_OBSERVATION_TRUTH_SCHEMA_V1,
    }
)
_V2_SCHEMAS = frozenset(
    {
        SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V2,
        D2_OBSERVATION_TRUTH_SCHEMA_V2,
    }
)


class ObservationTruthSidecarError(ValueError):
    """Raised when evaluator-only observation truth fails closed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class ObservationTruthDispositionRecord:
    """One schema-validated evaluator-only observation disposition."""

    schema_version: str
    observation_id: str
    measurement_timestamp: float
    disposition: str
    truth_target_id: str | None


@dataclass(frozen=True, slots=True)
class ObservationTruthDispositionAudit:
    """Counts and availability for one homogeneous sidecar."""

    records: tuple[ObservationTruthDispositionRecord, ...]
    source_schema_version: str
    source_contract: str
    target_label_count: int
    known_false_alarm_count: int | None
    unknown_count: int | None
    missing_disposition_count: int
    complete_disposition_available: bool
    complete_disposition_reason: str | None
    strict_identity_eligible: bool
    strict_identity_blockers: tuple[str, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)

    def to_dict(self) -> dict[str, Any]:
        """Return a portable audit without exposing truth to online code."""

        complete_status = (
            "available" if self.complete_disposition_available else "unavailable"
        )
        return {
            "source_schema_version": self.source_schema_version,
            "source_contract": self.source_contract,
            "record_count": self.record_count,
            "target_label": {
                "availability": "available",
                "count": self.target_label_count,
                "reason": None,
            },
            "known_false_alarm": {
                "availability": complete_status,
                "count": self.known_false_alarm_count,
                "reason": self.complete_disposition_reason,
            },
            "unknown": {
                "availability": complete_status,
                "count": self.unknown_count,
                "reason": self.complete_disposition_reason,
            },
            "missing_disposition": {
                "availability": "available",
                "count": self.missing_disposition_count,
                "reason": None,
            },
            "complete_disposition_available": (
                self.complete_disposition_available
            ),
            "complete_disposition_reason": self.complete_disposition_reason,
            "strict_identity_eligible": self.strict_identity_eligible,
            "strict_identity_blockers": list(self.strict_identity_blockers),
            "known_false_alarm_treated_as_target": False,
            "strict_id_switch_backfilled": False,
            "inference_sources_used": [],
        }


def audit_observation_truth_sidecar(
    rows: Iterable[Mapping[str, Any]],
    *,
    accepted_contract: str,
    declared_schema_version: str | None = None,
) -> ObservationTruthDispositionAudit:
    """Validate and summarize an external or D2-normalized sidecar.

    ``accepted_contract`` is either ``external`` for main-produced
    ``scalable3d-offline-truth-*`` records or ``d2_normalized`` for D2's
    normalized evaluator artifact.
    """

    if accepted_contract == "external":
        accepted_schemas = _EXTERNAL_SCHEMAS
    elif accepted_contract == "d2_normalized":
        accepted_schemas = _D2_SCHEMAS
    else:
        raise ValueError(f"unsupported truth sidecar contract: {accepted_contract}")

    records: list[ObservationTruthDispositionRecord] = []
    source_schemas: set[str] = set()
    missing_disposition_count = 0
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, Mapping):
            _fail(
                "observation_truth_record_not_mapping",
                f"record {index} is not a mapping",
            )
        schema = _required_text(raw.get("schema_version"), "schema_version", index)
        source_schemas.add(schema)
        if schema not in accepted_schemas:
            _fail(
                "unsupported_observation_truth_schema",
                f"record {index} uses {schema!r}",
            )
        if declared_schema_version is not None and schema != declared_schema_version:
            _fail(
                "observation_truth_declared_schema_mismatch",
                f"record {index} uses {schema!r}, declared "
                f"{declared_schema_version!r}",
            )
        if schema in _V2_SCHEMAS and "disposition" not in raw:
            missing_disposition_count += 1
            _fail(
                "observation_truth_disposition_missing",
                f"record {index} omits disposition",
            )
        records.append(
            _parse_record(
                raw,
                schema=schema,
                record_index=index,
            )
        )

    if len(source_schemas) > 1:
        _fail(
            "observation_truth_mixed_schema_versions",
            f"sidecar mixes schemas {sorted(source_schemas)}",
        )
    if not records:
        if declared_schema_version is None:
            _fail(
                "observation_truth_schema_unavailable",
                "empty sidecar requires an externally declared schema",
            )
        if declared_schema_version not in accepted_schemas:
            _fail(
                "unsupported_observation_truth_schema",
                f"declared schema {declared_schema_version!r} is unsupported",
            )
        source_schema = declared_schema_version
    else:
        source_schema = records[0].schema_version

    _validate_unique_observation_semantics(records)
    counts = Counter(record.disposition for record in records)
    if source_schema in _V1_SCHEMAS:
        complete_available = False
        complete_reason = (
            "v1_target_only_schema_cannot_report_non_target_dispositions"
        )
        known_false_alarm_count: int | None = None
        unknown_count: int | None = None
    else:
        complete_available = True
        complete_reason = None
        known_false_alarm_count = counts[TRUTH_DISPOSITION_KNOWN_FALSE_ALARM]
        unknown_count = counts[TRUTH_DISPOSITION_UNKNOWN]

    blockers: list[str] = []
    if not complete_available:
        blockers.append("non_target_disposition_coverage_unavailable")
    if unknown_count:
        blockers.append("unknown_observation_truth_disposition_present")

    return ObservationTruthDispositionAudit(
        records=tuple(records),
        source_schema_version=source_schema,
        source_contract=accepted_contract,
        target_label_count=counts[TRUTH_DISPOSITION_TARGET],
        known_false_alarm_count=known_false_alarm_count,
        unknown_count=unknown_count,
        missing_disposition_count=missing_disposition_count,
        complete_disposition_available=complete_available,
        complete_disposition_reason=complete_reason,
        strict_identity_eligible=not blockers,
        strict_identity_blockers=tuple(blockers),
    )


def _parse_record(
    raw: Mapping[str, Any],
    *,
    schema: str,
    record_index: int,
) -> ObservationTruthDispositionRecord:
    if schema == SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V1:
        _require_exact_keys(
            raw,
            {
                "schema_version",
                "observation_id",
                "measurement_timestamp",
                "truth_entity_id",
            },
            record_index,
        )
        disposition = TRUTH_DISPOSITION_TARGET
        truth_target_id = _required_text(
            raw.get("truth_entity_id"),
            "truth_entity_id",
            record_index,
        )
    elif schema == SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V2:
        _require_exact_keys(
            raw,
            {
                "schema_version",
                "observation_id",
                "measurement_timestamp",
                "truth_entity_id",
                "disposition",
            },
            record_index,
        )
        disposition = _disposition(raw.get("disposition"), record_index)
        truth_target_id = _external_v2_truth_target(
            raw,
            disposition=disposition,
            record_index=record_index,
        )
    elif schema == D2_OBSERVATION_TRUTH_SCHEMA_V1:
        _require_exact_keys(
            raw,
            {
                "schema_version",
                "observation_id",
                "measurement_timestamp",
                "truth_target_id",
            },
            record_index,
        )
        disposition = TRUTH_DISPOSITION_TARGET
        truth_target_id = _required_text(
            raw.get("truth_target_id"),
            "truth_target_id",
            record_index,
        )
    else:
        disposition = _disposition(raw.get("disposition"), record_index)
        required = {
            "schema_version",
            "observation_id",
            "measurement_timestamp",
            "disposition",
        }
        allowed = required | {"truth_target_id"}
        _require_key_contract(raw, required, allowed, record_index)
        truth_target_id = _d2_v2_truth_target(
            raw,
            disposition=disposition,
            record_index=record_index,
        )

    return ObservationTruthDispositionRecord(
        schema_version=schema,
        observation_id=_required_text(
            raw.get("observation_id"),
            "observation_id",
            record_index,
        ),
        measurement_timestamp=_timestamp(
            raw.get("measurement_timestamp"),
            record_index,
        ),
        disposition=disposition,
        truth_target_id=truth_target_id,
    )


def _external_v2_truth_target(
    raw: Mapping[str, Any],
    *,
    disposition: str,
    record_index: int,
) -> str | None:
    value = raw.get("truth_entity_id")
    if disposition == TRUTH_DISPOSITION_TARGET:
        return _required_text(value, "truth_entity_id", record_index)
    if value is not None:
        _fail(
            "observation_truth_identity_disposition_conflict",
            f"record {record_index} carries truth_entity_id for {disposition}",
        )
    return None


def _d2_v2_truth_target(
    raw: Mapping[str, Any],
    *,
    disposition: str,
    record_index: int,
) -> str | None:
    has_truth = "truth_target_id" in raw
    if disposition == TRUTH_DISPOSITION_TARGET:
        if not has_truth:
            _fail(
                "observation_truth_target_identity_missing",
                f"record {record_index} target omits truth_target_id",
            )
        return _required_text(
            raw.get("truth_target_id"),
            "truth_target_id",
            record_index,
        )
    if has_truth:
        _fail(
            "observation_truth_identity_disposition_conflict",
            f"record {record_index} carries truth_target_id for {disposition}",
        )
    return None


def _validate_unique_observation_semantics(
    records: Iterable[ObservationTruthDispositionRecord],
) -> None:
    by_observation: dict[
        str,
        tuple[float, str, str | None],
    ] = {}
    for record in records:
        semantics = (
            record.measurement_timestamp,
            record.disposition,
            record.truth_target_id,
        )
        previous = by_observation.get(record.observation_id)
        if previous is None:
            by_observation[record.observation_id] = semantics
            continue
        if previous != semantics:
            _fail(
                "observation_truth_conflicting_duplicate",
                f"{record.observation_id!r} has conflicting dispositions or identity",
            )
        _fail(
            "observation_truth_duplicate",
            f"{record.observation_id!r} is repeated",
        )


def _disposition(value: Any, record_index: int) -> str:
    disposition = _required_text(value, "disposition", record_index).lower()
    if disposition not in TRUTH_DISPOSITIONS:
        _fail(
            "unsupported_observation_truth_disposition",
            f"record {record_index} uses {disposition!r}",
        )
    return disposition


def _timestamp(value: Any, record_index: int) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        _fail(
            "observation_truth_timestamp_invalid",
            f"record {record_index} measurement_timestamp is invalid",
        )
    return float(value)


def _required_text(value: Any, name: str, record_index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(
            "observation_truth_field_invalid",
            f"record {record_index} {name} must be non-empty text",
        )
    return value.strip()


def _require_exact_keys(
    raw: Mapping[str, Any],
    expected: set[str],
    record_index: int,
) -> None:
    _require_key_contract(raw, expected, expected, record_index)


def _require_key_contract(
    raw: Mapping[str, Any],
    required: set[str],
    allowed: set[str],
    record_index: int,
) -> None:
    missing = required - set(raw)
    unknown = set(raw) - allowed
    if missing:
        _fail(
            "observation_truth_fields_missing",
            f"record {record_index} omits {sorted(missing)}",
        )
    if unknown:
        _fail(
            "observation_truth_fields_unknown",
            f"record {record_index} adds {sorted(unknown)}",
        )


def _fail(code: str, message: str) -> None:
    raise ObservationTruthSidecarError(code, message)


__all__ = [
    "D2_OBSERVATION_TRUTH_SCHEMA_V1",
    "D2_OBSERVATION_TRUTH_SCHEMA_V2",
    "ObservationTruthDispositionAudit",
    "ObservationTruthDispositionRecord",
    "ObservationTruthSidecarError",
    "SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V1",
    "SCALABLE_3D_OFFLINE_TRUTH_SCHEMA_V2",
    "TRUTH_DISPOSITION_KNOWN_FALSE_ALARM",
    "TRUTH_DISPOSITION_TARGET",
    "TRUTH_DISPOSITION_UNKNOWN",
    "audit_observation_truth_sidecar",
]
