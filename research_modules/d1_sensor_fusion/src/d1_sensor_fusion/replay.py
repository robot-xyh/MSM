from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Iterable, Mapping

import numpy as np

from .fusion import FusionAdapter
from .types import COMMUNICATION_METADATA_KEYS, GlobalTrack, LatencyAuditSummary, SensorObservation

REPLAY_SCHEMA_VERSION = "d1.sensor_observation.v1"
REPLAY_PROVENANCE_SCHEMA_VERSION = "d1.replay_provenance.v1"
REPLAY_MANIFEST_SCHEMA_VERSION = "d1.governed_replay_manifest.v1"
REPLAY_WORKING_FRAME = "ned"
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
_REPLAY_METADATA_PASSTHROUGH_KEYS = (
    "coverage_cell",
    "working_frame",
    "source_lineage",
    "camera_id",
    "camera_name",
    "camera_model",
    "camera_metadata",
    "camera",
    "camera_position_ned",
    "rotation_world_to_camera",
    "intrinsics",
    "extrinsics",
    "K",
    "R",
    "fx",
    "fy",
    "cx",
    "cy",
    "width",
    "height",
    "image_size",
    "bbox",
    "bbox_xyxy",
    "bbox_center_px",
    "center_px",
    "eo_metadata",
    "detection_metadata",
    "detection_id",
    "local_track_id",
    "object_id",
    "object_id_offline_only",
    "truth_object_id_offline_only",
    "actor_name",
    "mesh_name",
    "airsim_frame_index",
    "frame_index",
    "sequence_id",
    "source_support",
    "recon_cue",
    "recon_cue_summary",
    "secondary_recon",
    "mobile_recon",
    "recon_node_id",
    "secondary_recon_node_id",
    "mobile_recon_node_id",
    "cue_source",
    "cue_position_ned",
    "cue_covariance",
    "coverage_cells",
    "timestamp_uncertainty_s",
    "timing_uncertainty_s",
    "timestamp_uncertainty_ms",
    "timing_uncertainty_ms",
    "clock_drift_s",
    "clock_offset_s",
    "timestamp_drift_s",
    "timestamp_jitter_s",
    "clock_drift_ms",
    "timestamp_jitter_ms",
    "covariance_limit_reasons",
    "observation_covariance_limit_reasons",
    "track_covariance_limit_reasons",
    "covariance_limited",
    "covariance_limit_applied",
    "covariance_scale_reason",
    "observation_covariance_anomaly",
    "expected_latency_s",
    "latency_tolerance_s",
    "oosm_expected",
    "provenance",
    "config_provenance",
    "scenario_provenance",
    "offline_truth",
)
_ARRAY_METADATA_KEYS = {
    "bbox",
    "bbox_xyxy",
    "bbox_center_px",
    "center_px",
    "camera_position_ned",
    "rotation_world_to_camera",
    "K",
    "R",
    "image_size",
    "cue_position_ned",
    "cue_covariance",
}
_OBJECT_METADATA_KEYS = {
    "camera_model",
    "camera_metadata",
    "camera",
    "intrinsics",
    "extrinsics",
    "eo_metadata",
    "detection_metadata",
    "source_support",
    "recon_cue",
    "recon_cue_summary",
    "secondary_recon",
    "mobile_recon",
    "provenance",
    "config_provenance",
    "scenario_provenance",
    "offline_truth",
}

_ONLINE_TRUTH_METADATA_KEYS = {
    "truth_id",
    "truth_object_id",
    "actor_id",
    "actor_name",
    "object_name",
    "object_id",
    "airsim_actor_name",
    "airsim_object_name",
}


@dataclass(frozen=True)
class ReplayProvenance:
    """Configuration and scenario identity written with each replay record."""

    scenario_id: str
    scenario_version: str
    config_id: str
    config_digest: str
    config_version: str | None = None
    scenario_digest: str | None = None
    run_id: str | None = None
    seed: int | None = None
    source_format: str = "blocks_cv"
    producer: str = "main"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        required = {
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "config_id": self.config_id,
            "config_digest": self.config_digest,
        }
        missing = [key for key, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"D1 replay provenance missing required field(s): {', '.join(missing)}")
        return {
            "schema_version": REPLAY_PROVENANCE_SCHEMA_VERSION,
            **required,
            "config_version": self.config_version,
            "scenario_digest": self.scenario_digest,
            "run_id": self.run_id,
            "seed": self.seed,
            "source_format": self.source_format,
            "producer": self.producer,
            "metadata": _json_safe(self.metadata),
        }


def sensor_observation_from_jsonl_record(record: dict[str, Any]) -> SensorObservation:
    """Parse one D1 JSONL observation record into a SensorObservation.

    Versioned v1 records should set ``schema_version`` to
    ``d1.sensor_observation.v1``. Existing Blocks logs without a schema version
    are accepted as legacy records when the required observation fields exist.
    """

    schema_version = _validate_replay_schema_version(record)
    _validate_replay_required_fields(record, schema_version)

    metadata = _metadata_from_replay_record(record, schema_version)

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
    Rows without an explicit schema version are treated as D1 replay schema v1
    so AirSim calibration CSVs cannot silently drop covariance.
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
        "schema_version": clean.get("schema_version")
        or clean.get("d1_schema_version")
        or REPLAY_SCHEMA_VERSION,
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
    provenance = _json_object_cell(clean.get("provenance"), "provenance")
    if provenance:
        record["provenance"] = provenance
    for key in _REPLAY_METADATA_PASSTHROUGH_KEYS:
        value = _non_empty(clean.get(key))
        if value is None:
            continue
        record[key] = _metadata_cell_value(value, key)
    return sensor_observation_from_jsonl_record(record)


def sensor_observation_to_replay_record(
    observation: SensorObservation,
    provenance: ReplayProvenance | Mapping[str, Any],
    *,
    include_offline_truth: bool = False,
) -> dict[str, Any]:
    """Serialize one canonical observation without exposing online truth hints."""

    if observation.covariance is None:
        raise ValueError("D1 replay writer requires covariance on every observation")
    provenance_payload = _provenance_payload(provenance)
    metadata = _sanitize_online_metadata(observation.metadata)
    coverage_cell = _optional_str(metadata.get("coverage_cell"))
    source_lineage = _governed_source_lineage(observation)
    record = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "observation_id": observation.observation_id,
        "sensor_id": observation.sensor_id,
        "modality": observation.modality,
        "measurement_timestamp": observation.measurement_timestamp,
        "arrival_timestamp": observation.arrival_timestamp,
        "frame_id": observation.frame_id,
        "working_frame": REPLAY_WORKING_FRAME,
        "coverage_cell": coverage_cell,
        "source_lineage": source_lineage,
        "measurement": observation.measurement.tolist(),
        "covariance": observation.covariance.tolist(),
        "classification_hint": _online_classification_hint(observation),
        "confidence": observation.confidence,
        "quality_flags": list(observation.quality_flags),
        "metadata": _json_safe(metadata),
        "communication": _json_safe(observation.communication_metadata),
        "provenance": provenance_payload,
    }
    if include_offline_truth:
        offline_truth = _extract_offline_truth(observation.metadata)
        if (
            observation.classification_hint is not None
            and _online_classification_hint(observation) is None
        ):
            offline_truth["classification_hint"] = observation.classification_hint
        if offline_truth:
            record["offline_truth"] = offline_truth
    return record


def serialize_governed_replay(
    observations: Iterable[SensorObservation],
    provenance: ReplayProvenance | Mapping[str, Any],
) -> dict[str, Any]:
    """Serialize a strict online replay bundle for main/runtime integration.

    Unlike the legacy-compatible readers and low-level record writer, this
    entry point requires the frozen governed contract on every observation.
    Truth, actor, and object identifiers are always removed.
    """

    return _serialize_governed_replay_bundle(
        observations,
        provenance,
        include_offline_truth=False,
    )


def serialize_offline_governed_replay(
    observations: Iterable[SensorObservation],
    provenance: ReplayProvenance | Mapping[str, Any],
) -> dict[str, Any]:
    """Serialize a governed bundle with labels in explicit offline-only fields."""

    return _serialize_governed_replay_bundle(
        observations,
        provenance,
        include_offline_truth=True,
    )


def build_governed_replay_manifest(
    observations: Iterable[SensorObservation],
    provenance: ReplayProvenance | Mapping[str, Any],
) -> dict[str, Any]:
    """Build and validate the frozen manifest consumed by main."""

    items = list(observations)
    provenance_payload = _governed_provenance_payload(provenance)
    observation_summaries = [
        _validate_governed_observation(observation) for observation in items
    ]
    measurement_timestamps = [
        float(observation.measurement_timestamp) for observation in items
    ]
    arrival_timestamps = [float(observation.arrival_timestamp) for observation in items]
    return {
        "schema_version": REPLAY_MANIFEST_SCHEMA_VERSION,
        "observation_schema_version": REPLAY_SCHEMA_VERSION,
        "provenance": provenance_payload,
        "working_frame": REPLAY_WORKING_FRAME,
        "observation_count": len(items),
        "measurement_timestamp_range": _timestamp_range(measurement_timestamps),
        "arrival_timestamp_range": _timestamp_range(arrival_timestamps),
        "observation_frames": sorted({observation.frame_id for observation in items}),
        "coverage_cells": sorted(
            {summary["coverage_cell"] for summary in observation_summaries}
        ),
        "source_lineage": [
            {
                "observation_id": observation.observation_id,
                "lineage": summary["source_lineage"],
            }
            for observation, summary in zip(items, observation_summaries)
        ],
        "required_record_fields": [
            *_REQUIRED_REPLAY_FIELDS,
            "covariance",
            "coverage_cell",
            "source_lineage",
        ],
        "truth_policy": {
            "online": "stripped",
            "offline": "explicit_offline_only_export",
        },
    }


def write_sensor_observations_jsonl(
    path: str | Path,
    observations: Iterable[SensorObservation],
    provenance: ReplayProvenance | Mapping[str, Any],
    *,
    include_offline_truth: bool = False,
) -> Path:
    """Write versioned JSONL records with required scenario/config provenance."""

    output_path = Path(path)
    with output_path.open("w", encoding="utf-8") as stream:
        for observation in observations:
            record = sensor_observation_to_replay_record(
                observation,
                provenance,
                include_offline_truth=include_offline_truth,
            )
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    return output_path


def write_sensor_observations_csv(
    path: str | Path,
    observations: Iterable[SensorObservation],
    provenance: ReplayProvenance | Mapping[str, Any],
    *,
    include_offline_truth: bool = False,
) -> Path:
    """Write the same governed replay contract in a stable CSV representation."""

    fieldnames = (
        "schema_version",
        "observation_id",
        "sensor_id",
        "modality",
        "measurement_timestamp",
        "arrival_timestamp",
        "frame_id",
        "measurement",
        "covariance",
        "classification_hint",
        "confidence",
        "quality_flags",
        "metadata",
        "communication",
        "provenance",
        "offline_truth",
    )
    output_path = Path(path)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for observation in observations:
            record = sensor_observation_to_replay_record(
                observation,
                provenance,
                include_offline_truth=include_offline_truth,
            )
            writer.writerow(
                {
                    key: (
                        json.dumps(record[key], sort_keys=True)
                        if key
                        in {
                            "measurement",
                            "covariance",
                            "quality_flags",
                            "metadata",
                            "communication",
                            "provenance",
                            "offline_truth",
                        }
                        and key in record
                        else record.get(key)
                    )
                    for key in fieldnames
                }
            )
    return output_path


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


def summarize_sensor_observation_latency_audit(
    observations: Iterable[SensorObservation],
) -> LatencyAuditSummary:
    """Summarize raw replay observation latency/OOSM evidence without running fusion."""

    ordered = sorted(
        list(observations),
        key=lambda obs: (obs.arrival_timestamp, obs.measurement_timestamp, obs.observation_id),
    )
    observation_count = len(ordered)
    if observation_count == 0:
        return LatencyAuditSummary(
            observation_count=0,
            replay_count=0,
            oosm_observation_count=0,
            stale_observation_count=0,
            stale_or_oosm_observation_count=0,
            max_delay_s=0.0,
            mean_delay_s=0.0,
            duplicate_observation_count=0,
            max_replay_observation_count=0,
            latency_compensation=False,
            published_at=None,
        )

    current_time = 0.0
    delay_sum_s = 0.0
    max_delay_s = 0.0
    oosm_count = 0
    stale_count = 0
    stale_or_oosm_count = 0
    duplicate_count = 0
    seen_lineage_keys: set[tuple[Any, ...]] = set()

    for observation in ordered:
        previous_time = current_time
        current_time = max(current_time, float(observation.arrival_timestamp))
        delay_s = max(0.0, float(observation.latency))
        delay_sum_s += delay_s
        max_delay_s = max(max_delay_s, delay_s)

        is_oosm = observation.measurement_timestamp < float(previous_time) - 1e-9
        is_stale = observation.is_stale_at(current_time)
        if observation.stale_after_s is not None and delay_s > observation.stale_after_s:
            is_stale = True
        if is_oosm:
            oosm_count += 1
        if is_stale:
            stale_count += 1
        if is_oosm or is_stale:
            stale_or_oosm_count += 1

        lineage_key = observation.source_lineage_key
        if lineage_key in seen_lineage_keys:
            duplicate_count += 1
        else:
            seen_lineage_keys.add(lineage_key)

    return LatencyAuditSummary(
        observation_count=observation_count,
        replay_count=0,
        oosm_observation_count=oosm_count,
        stale_observation_count=stale_count,
        stale_or_oosm_observation_count=stale_or_oosm_count,
        max_delay_s=max_delay_s,
        mean_delay_s=delay_sum_s / observation_count,
        duplicate_observation_count=duplicate_count,
        max_replay_observation_count=0,
        latency_compensation=False,
        published_at=max(float(obs.arrival_timestamp) for obs in ordered),
    )


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


def _metadata_from_replay_record(record: dict[str, Any], schema_version: str) -> dict[str, Any]:
    metadata = dict(record.get("metadata") or {})
    metadata.setdefault("d1_replay_schema_version", schema_version)
    if schema_version == LEGACY_BLOCKS_REPLAY_SCHEMA_VERSION:
        metadata.setdefault("d1_replay_schema_compatibility", "legacy_without_explicit_version")

    for key in _REPLAY_METADATA_PASSTHROUGH_KEYS:
        value = _non_empty(record.get(key))
        if value is not None and key not in metadata:
            metadata[key] = value
    if "source_lineage" in metadata and "source_lineage_key" not in metadata:
        metadata["source_lineage_key"] = metadata["source_lineage"]

    _normalize_replay_visual_metadata(metadata)
    provenance = record.get("provenance")
    if isinstance(provenance, dict):
        metadata["d1_replay_provenance"] = dict(provenance)
    return metadata


def _provenance_payload(
    provenance: ReplayProvenance | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(provenance, ReplayProvenance):
        return provenance.to_dict()
    payload = dict(provenance)
    schema_version = str(
        payload.get("schema_version", REPLAY_PROVENANCE_SCHEMA_VERSION)
    ).strip()
    if schema_version != REPLAY_PROVENANCE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported D1 replay provenance schema_version {schema_version!r}; "
            f"expected {REPLAY_PROVENANCE_SCHEMA_VERSION!r}"
        )
    return ReplayProvenance(
        scenario_id=str(payload.get("scenario_id", "")),
        scenario_version=str(payload.get("scenario_version", "")),
        config_id=str(payload.get("config_id", "")),
        config_digest=str(payload.get("config_digest", "")),
        config_version=_optional_str(payload.get("config_version")),
        scenario_digest=_optional_str(payload.get("scenario_digest")),
        run_id=_optional_str(payload.get("run_id")),
        seed=None if payload.get("seed") is None else int(payload["seed"]),
        source_format=str(payload.get("source_format", "blocks_cv")),
        producer=str(payload.get("producer", "main")),
        metadata=dict(payload.get("metadata") or {}),
    ).to_dict()


def _serialize_governed_replay_bundle(
    observations: Iterable[SensorObservation],
    provenance: ReplayProvenance | Mapping[str, Any],
    *,
    include_offline_truth: bool,
) -> dict[str, Any]:
    items = list(observations)
    manifest = build_governed_replay_manifest(items, provenance)
    records = [
        sensor_observation_to_replay_record(
            observation,
            manifest["provenance"],
            include_offline_truth=include_offline_truth,
        )
        for observation in items
    ]
    bundle = {"manifest": manifest, "records": records}
    # Fail before returning if a caller supplied a non-JSON-compatible value.
    json.dumps(bundle, sort_keys=True, allow_nan=False)
    return bundle


def _governed_provenance_payload(
    provenance: ReplayProvenance | Mapping[str, Any],
) -> dict[str, Any]:
    payload = _provenance_payload(provenance)
    missing = [
        key
        for key in ("scenario_digest", "config_version", "seed")
        if _non_empty(payload.get(key)) is None
    ]
    if missing:
        raise ValueError(
            "D1 governed replay provenance missing required field(s): "
            + ", ".join(missing)
        )
    payload["metadata"] = _sanitize_online_metadata(payload.get("metadata") or {})
    return payload


def _validate_governed_observation(observation: SensorObservation) -> dict[str, Any]:
    if not str(observation.observation_id).strip():
        raise ValueError("D1 governed replay observation_id must be non-empty")
    if not str(observation.sensor_id).strip():
        raise ValueError("D1 governed replay sensor_id must be non-empty")

    measurement_timestamp = float(observation.measurement_timestamp)
    arrival_timestamp = float(observation.arrival_timestamp)
    if not np.isfinite([measurement_timestamp, arrival_timestamp]).all():
        raise ValueError("D1 governed replay timestamps must be finite")
    if arrival_timestamp < measurement_timestamp:
        raise ValueError(
            "D1 governed replay arrival_timestamp must not precede measurement_timestamp"
        )

    covariance = observation.covariance
    if covariance is None:
        raise ValueError("D1 governed replay requires covariance on every observation")
    covariance_array = np.asarray(covariance, dtype=float)
    measurement_size = int(np.asarray(observation.measurement).size)
    if covariance_array.shape != (measurement_size, measurement_size):
        raise ValueError(
            "D1 governed replay covariance shape must match flattened measurement size"
        )
    if not np.isfinite(covariance_array).all():
        raise ValueError("D1 governed replay covariance must be finite")
    if not np.allclose(covariance_array, covariance_array.T, atol=1e-9):
        raise ValueError("D1 governed replay covariance must be symmetric")
    if float(np.linalg.eigvalsh(covariance_array).min()) < -1e-9:
        raise ValueError("D1 governed replay covariance must be positive semidefinite")

    coverage_cell = _optional_str(observation.metadata.get("coverage_cell"))
    if coverage_cell is None:
        raise ValueError("D1 governed replay observation missing coverage_cell")
    source_lineage = _governed_source_lineage(observation)
    if not source_lineage:
        raise ValueError("D1 governed replay observation missing source lineage")
    json.dumps(source_lineage, sort_keys=True, allow_nan=False)
    return {
        "coverage_cell": coverage_cell,
        "source_lineage": source_lineage,
    }


def _timestamp_range(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"minimum": None, "maximum": None}
    return {"minimum": min(values), "maximum": max(values)}


def _governed_source_lineage(observation: SensorObservation) -> list[Any]:
    metadata = observation.metadata
    sequence = (
        metadata.get("sequence_id")
        or metadata.get("sequence")
        or metadata.get("source_sequence")
        or metadata.get("payload_sequence")
        or metadata.get("airsim_frame_index")
        or observation.measurement_timestamp
    )
    fingerprint_input = {
        "measurement_timestamp": observation.measurement_timestamp,
        "measurement": observation.measurement,
        "covariance": observation.covariance,
        "sequence": sequence,
    }
    fingerprint_text = json.dumps(
        _json_safe(fingerprint_input),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    payload_digest = "sha256:" + hashlib.sha256(
        fingerprint_text.encode("utf-8")
    ).hexdigest()
    source = observation.source_node_id or metadata.get("source_node_id") or observation.sensor_id
    return [
        "source_payload",
        str(source),
        observation.sensor_id,
        observation.modality,
        observation.payload_kind or metadata.get("payload_kind") or "",
        _json_safe(sequence),
        payload_digest,
    ]


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _sanitize_online_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key)
        if (
            _is_online_truth_key(normalized_key)
            or normalized_key.startswith("d1_replay_")
            or normalized_key.endswith("_offline_only")
        ):
            continue
        sanitized[normalized_key] = _sanitize_online_value(item)
    return sanitized


def _extract_offline_truth(value: Mapping[str, Any]) -> dict[str, Any]:
    offline: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key)
        if _is_online_truth_key(normalized_key) or normalized_key.endswith("_offline_only"):
            offline[normalized_key] = _json_safe(item)
            continue
        if isinstance(item, Mapping):
            nested = _extract_offline_truth(item)
            if nested:
                offline[normalized_key] = nested
    return offline


def _online_classification_hint(observation: SensorObservation) -> str | None:
    hint = observation.classification_hint
    if hint is None:
        return None
    text = str(hint)
    offline_truth = _extract_offline_truth(observation.metadata)
    for value in _iter_scalar_values(offline_truth):
        candidate = str(value).strip()
        if candidate and candidate in text:
            return None
    return text


def _iter_scalar_values(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_scalar_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_scalar_values(item)
    elif value is not None:
        yield value


def _is_online_truth_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in _ONLINE_TRUTH_METADATA_KEYS or normalized.endswith(
        ("_truth_id", "_actor_id", "_actor_name", "_object_id", "_object_name")
    )


def _sanitize_online_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _sanitize_online_metadata(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_online_value(item) for item in value]
    return value


def _normalize_replay_visual_metadata(metadata: dict[str, Any]) -> None:
    bbox = _first_metadata_value(metadata, ("bbox_xyxy", "bbox"))
    bbox_values = _numeric_vector_or_none(bbox, 4)
    if bbox_values is not None:
        metadata.setdefault("bbox_xyxy", bbox_values)
        metadata.setdefault("bbox", bbox_values)

    center = _first_metadata_value(metadata, ("center_px", "bbox_center_px"))
    center_values = _numeric_vector_or_none(center, 2)
    if center_values is None and bbox_values is not None:
        center_values = [
            0.5 * (bbox_values[0] + bbox_values[2]),
            0.5 * (bbox_values[1] + bbox_values[3]),
        ]
    if center_values is not None:
        metadata.setdefault("center_px", center_values)
        metadata.setdefault("bbox_center_px", center_values)

    camera = _first_metadata_value(metadata, ("camera_model", "camera_metadata", "camera"))
    if isinstance(camera, dict):
        camera_metadata = dict(camera)
        for key in ("camera_id", "camera_name"):
            if key in metadata and key not in camera_metadata:
                camera_metadata[key] = metadata[key]
        metadata.setdefault("camera_metadata", camera_metadata)
        metadata["camera_model"] = camera_metadata


def _first_metadata_value(metadata: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = _non_empty(metadata.get(key))
        if value is not None:
            return value
    return None


def _numeric_vector_or_none(value: Any, expected_size: int) -> list[float] | None:
    if value is None:
        return None
    try:
        array = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if array.size != expected_size:
        return None
    if not np.isfinite(array).all():
        return None
    return [float(item) for item in array.tolist()]


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


def _metadata_cell_value(value: Any, field_name: str) -> Any:
    if field_name in _OBJECT_METADATA_KEYS:
        return _json_object_cell(value, field_name)
    if field_name in _ARRAY_METADATA_KEYS:
        return _array_cell(value, field_name)
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("[", "{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
    return value


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
