from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .fusion import FusionAdapter
from .types import COMMUNICATION_METADATA_KEYS, GlobalTrack, SensorObservation


def sensor_observation_from_jsonl_record(record: dict[str, Any]) -> SensorObservation:
    """Parse one D1 JSONL observation record into a SensorObservation."""

    metadata = dict(record.get("metadata") or {})
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
        covariance=_optional_array(record.get("covariance")),
        classification_hint=_optional_str(record.get("classification_hint")),
        confidence=float(record.get("confidence", 1.0)),
        quality_flags=tuple(str(item) for item in record.get("quality_flags", ())),
        metadata=metadata,
        **kwargs,
    )


def read_blocks_sensor_observations_jsonl(path: str | Path) -> list[SensorObservation]:
    """Read main/AirSim Blocks D1 observation JSONL into canonical observations."""

    return list(iter_blocks_sensor_observations_jsonl(path))


def iter_blocks_sensor_observations_jsonl(path: str | Path) -> Iterable[SensorObservation]:
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


def replay_blocks_sensor_observations_jsonl(
    path: str | Path,
    adapter: FusionAdapter | None = None,
) -> list[GlobalTrack]:
    """Replay a Blocks observation JSONL file through a FusionAdapter."""

    fusion = adapter or FusionAdapter()
    return fusion.ingest_many(read_blocks_sensor_observations_jsonl(path))


def _optional_array(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=float)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
