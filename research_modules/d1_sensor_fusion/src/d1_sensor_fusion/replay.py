from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .fusion import FusionAdapter
from .types import COMMUNICATION_METADATA_KEYS, GlobalTrack, SensorObservation

REPLAY_SCHEMA_VERSION = "d1.sensor_observation.v1"
LEGACY_BLOCKS_REPLAY_SCHEMA_VERSION = "legacy.blocks_sensor_observations"
_COMPATIBLE_SCHEMA_ALIASES = {
    REPLAY_SCHEMA_VERSION: REPLAY_SCHEMA_VERSION,
    "sensor_observations.v1": REPLAY_SCHEMA_VERSION,
    "blocks_sensor_observations.v1": REPLAY_SCHEMA_VERSION,
    "1": REPLAY_SCHEMA_VERSION,
    "1.0": REPLAY_SCHEMA_VERSION,
}
_REQUIRED_REPLAY_FIELDS = (
    "observation_id",
    "sensor_id",
    "modality",
    "measurement_timestamp",
    "arrival_timestamp",
    "frame_id",
    "measurement",
)


def sensor_observation_from_jsonl_record(record: dict[str, Any]) -> SensorObservation:
    """Parse one D1 JSONL observation record into a SensorObservation.

    Versioned v1 records should set ``schema_version`` to
    ``d1.sensor_observation.v1``. Existing Blocks logs without a schema version
    are accepted as legacy records when the required observation fields exist.
    """

    schema_version = _validate_replay_schema_version(record)
    _validate_replay_required_fields(record, schema_version)

    metadata = dict(record.get("metadata") or {})
    metadata.setdefault("d1_replay_schema_version", schema_version)
    if schema_version == LEGACY_BLOCKS_REPLAY_SCHEMA_VERSION:
        metadata.setdefault("d1_replay_schema_compatibility", "legacy_without_explicit_version")

    communication = dict(record.get("communication") or {})
    for key in COMMUNICATION_METADATA_KEYS:
        if key in communication and key not in metadata:
            metadata[key] = communication[key]

    kwargs = {
        key: record.get(key, communication.get(key, metadata.get(key)))
        for key in COMMUNICATION_METADATA_KEYS
    }
    return SensorObservation(
        observation_id=str(record["observation_id"]),
        sensor_id=str(record["sensor_id"]),
        modality=str(record["modality"]),
        measurement_timestamp=float(record["measurement_timestamp"]),
        arrival_timestamp=float(record["arrival_timestamp"]),
        frame_id=str(record["frame_id"]),
        measurement=np.asarray(record["measurement"], dtype=float),
        covariance=_covariance_array(record.get("covariance")),
        classification_hint=_optional_str(record.get("classification_hint")),
        confidence=float(record.get("confidence", 1.0)),
        quality_flags=_quality_flags_from_value(record.get("quality_flags", ())),
        metadata=metadata,
        **kwargs,
    )


def sensor_observation_from_csv_row(row: dict[str, Any]) -> SensorObservation:
    """Parse one minimal D1 CSV replay row into a SensorObservation.

    Minimal CSV support is intentionally conservative: ``measurement`` and
    ``covariance`` cells should contain JSON arrays. ``metadata``,
    ``communication``, and ``source_support`` cells may contain JSON objects.
    """

    clean = {str(key): value for key, value in row.items() if key is not None}
    metadata = _json_object_cell(clean.get("metadata"), "metadata")
    communication = _json_object_cell(clean.get("communication"), "communication")

    source_support = _json_object_cell(clean.get("source_support"), "source_support")
    if source_support:
        communication["source_support"] = source_support

    for key in COMMUNICATION_METADATA_KEYS:
        value = _non_empty(clean.get(key))
        if value is not None and key not in communication:
            communication[key] = value

    record = {
        "schema_version": clean.get("schema_version") or clean.get("d1_schema_version"),
        "observation_id": clean.get("observation_id"),
        "sensor_id": clean.get("sensor_id"),
        "modality": clean.get("modality"),
        "measurement_timestamp": clean.get("measurement_timestamp"),
        "arrival_timestamp": clean.get("arrival_timestamp"),
        "frame_id": clean.get("frame_id"),
        "measurement": _array_cell(clean.get("measurement"), "measurement"),
        "covariance": _optional_array_cell(clean.get("covariance"), "covariance"),
        "classification_hint": clean.get("classification_hint"),
        "confidence": clean.get("confidence") or 1.0,
        "quality_flags": _quality_flags_from_value(clean.get("quality_flags")),
        "metadata": metadata,
        "communication": communication,
    }
    return sensor_observation_from_jsonl_record(record)


def read_sensor_observations_jsonl(path: str | Path) -> list[SensorObservation]:
    """Read versioned D1 sensor_observations JSONL records."""

    return list(iter_sensor_observations_jsonl(path))


def iter_sensor_observations_jsonl(path: str | Path) -> Iterable[SensorObservation]:
    jsonl_path = Path(path)
    with jsonl_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
                yield sensor_observation_from_jsonl_record(payload)
            except Exception as exc:  # pragma: no cover - exercised through ValueError wrapping.
                raise ValueError(
                    f"failed to parse {jsonl_path} line {line_number} as D1 observation"
                ) from exc


def replay_sensor_observations_jsonl(
    path: str | Path,
    adapter: FusionAdapter | None = None,
) -> list[GlobalTrack]:
    """Replay a versioned D1 sensor_observations JSONL file."""

    fusion = adapter or FusionAdapter()
    return fusion.ingest_many(read_sensor_observations_jsonl(path))


def read_blocks_sensor_observations_jsonl(path: str | Path) -> list[SensorObservation]:
    """Read main/AirSim Blocks D1 observation JSONL into canonical observations."""

    return read_sensor_observations_jsonl(path)


def iter_blocks_sensor_observations_jsonl(path: str | Path) -> Iterable[SensorObservation]:
    return iter_sensor_observations_jsonl(path)


def replay_blocks_sensor_observations_jsonl(
    path: str | Path,
    adapter: FusionAdapter | None = None,
) -> list[GlobalTrack]:
    """Replay a Blocks observation JSONL file through a FusionAdapter."""

    return replay_sensor_observations_jsonl(path, adapter)


def read_sensor_observations_csv(path: str | Path) -> list[SensorObservation]:
    """Read minimal D1 CSV replay rows into canonical observations."""

    return list(iter_sensor_observations_csv(path))


def iter_sensor_observations_csv(path: str | Path) -> Iterable[SensorObservation]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for line_number, row in enumerate(reader, start=2):
            try:
                yield sensor_observation_from_csv_row(row)
            except Exception as exc:  # pragma: no cover - exercised through ValueError wrapping.
                raise ValueError(
                    f"failed to parse {csv_path} line {line_number} as D1 CSV observation"
                ) from exc


def replay_sensor_observations_csv(
    path: str | Path,
    adapter: FusionAdapter | None = None,
) -> list[GlobalTrack]:
    """Replay a minimal D1 sensor_observations CSV file."""

    fusion = adapter or FusionAdapter()
    return fusion.ingest_many(read_sensor_observations_csv(path))


def _validate_replay_schema_version(record: dict[str, Any]) -> str:
    raw_version = _schema_version_from_record(record)
    if raw_version is None:
        return LEGACY_BLOCKS_REPLAY_SCHEMA_VERSION
    normalized = _COMPATIBLE_SCHEMA_ALIASES.get(str(raw_version).strip())
    if normalized is None:
        supported = ", ".join(sorted(_COMPATIBLE_SCHEMA_ALIASES))
        raise ValueError(f"unsupported D1 replay schema_version {raw_version!r}; supported: {supported}")
    return normalized


def _schema_version_from_record(record: dict[str, Any]) -> Any:
    for key in ("schema_version", "d1_schema_version", "replay_schema_version"):
        value = record.get(key)
        if _non_empty(value) is not None:
            return value
    schema = record.get("schema")
    if isinstance(schema, dict):
        for key in ("version", "schema_version"):
            value = schema.get(key)
            if _non_empty(value) is not None:
                return value
    return None


def _validate_replay_required_fields(record: dict[str, Any], schema_version: str) -> None:
    required = list(_REQUIRED_REPLAY_FIELDS)
    if schema_version != LEGACY_BLOCKS_REPLAY_SCHEMA_VERSION:
        required.append("covariance")
    missing = [field for field in required if _non_empty(record.get(field)) is None]
    if missing:
        raise ValueError(f"D1 replay record missing required field(s): {', '.join(missing)}")


def _optional_array(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=float)


def _covariance_array(value: Any) -> np.ndarray | None:
    covariance = _optional_array(value)
    if covariance is None:
        return None
    if covariance.ndim == 0:
        return covariance.reshape(1, 1)
    if covariance.ndim == 1:
        size = int(np.sqrt(covariance.size))
        if size * size == covariance.size:
            return covariance.reshape(size, size)
    return covariance


def _array_cell(value: Any, field_name: str) -> Any:
    value = _non_empty(value)
    if value is None:
        raise ValueError(f"CSV field {field_name!r} is required")
    if isinstance(value, (list, tuple, np.ndarray)):
        return value
    text = str(value).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        normalized = text.replace("|", " ").replace(";", " ")
        parts = [part for part in normalized.split() if part]
        if not parts:
            raise ValueError(f"CSV field {field_name!r} is empty")
        return [float(part) for part in parts]


def _optional_array_cell(value: Any, field_name: str) -> Any:
    if _non_empty(value) is None:
        return None
    return _array_cell(value, field_name)


def _json_object_cell(value: Any, field_name: str) -> dict[str, Any]:
    value = _non_empty(value)
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(f"CSV field {field_name!r} must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"CSV field {field_name!r} must be a JSON object")
    return dict(parsed)


def _quality_flags_from_value(value: Any) -> tuple[str, ...]:
    value = _non_empty(value)
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            parsed = json.loads(text)
            return tuple(str(item) for item in parsed)
        return tuple(part for part in (item.strip() for item in text.replace("|", ";").split(";")) if part)
    return tuple(str(item) for item in value)


def _optional_str(value: Any) -> str | None:
    value = _non_empty(value)
    if value is None:
        return None
    return str(value)


def _non_empty(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value
