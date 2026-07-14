"""Convert D1 governed observation records into online-safe D2 replay frames."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
from math import isfinite
from typing import Any

import numpy as np


D1_GOVERNED_MANIFEST_SCHEMA = "d1.governed_replay_manifest.v1"
D1_OBSERVATION_SCHEMA = "d1.sensor_observation.v1"


def is_d1_governed_replay_payload(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    manifest = payload.get("manifest")
    records = payload.get("records")
    return (
        isinstance(manifest, Mapping)
        and manifest.get("schema_version") == D1_GOVERNED_MANIFEST_SCHEMA
        and isinstance(records, Sequence)
        and not isinstance(records, (str, bytes, bytearray))
    )


def d2_frames_from_d1_governed_replay(
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Project supported D1 radar records into timestamp-grouped D2 frames."""

    if not is_d1_governed_replay_payload(payload):
        raise ValueError("payload is not a supported D1 governed replay bundle")
    manifest = payload["manifest"]
    records = payload["records"]
    grouped: dict[tuple[float, int | None], list[dict[str, Any]]] = defaultdict(list)
    skipped_reasons: Counter[str] = Counter()
    accepted_count = 0

    for raw_record in records:
        if not isinstance(raw_record, Mapping):
            skipped_reasons["record_not_mapping"] += 1
            continue
        converted, reason = _convert_d1_radar_record(raw_record)
        if converted is None:
            skipped_reasons[reason] += 1
            continue
        frame_index = _record_frame_index(raw_record)
        timestamp = float(raw_record["measurement_timestamp"])
        grouped[(timestamp, frame_index)].append(converted)
        accepted_count += 1

    if not grouped:
        reasons = ", ".join(
            f"{reason}={count}" for reason, count in sorted(skipped_reasons.items())
        )
        raise ValueError(
            "D1 governed replay contains no supported radar/NED observations"
            + (f"; skipped: {reasons}" if reasons else "")
        )

    provenance = manifest.get("provenance", {})
    provenance_metadata = (
        provenance.get("metadata", {}) if isinstance(provenance, Mapping) else {}
    )
    episode_id = _first_string(
        provenance.get("run_id") if isinstance(provenance, Mapping) else None,
        _record_metadata_value(records, "airsim_episode_id"),
        "d1-governed-replay",
    )
    scenario_name = _first_string(
        provenance.get("scenario_id") if isinstance(provenance, Mapping) else None,
        _record_metadata_value(records, "airsim_scenario"),
        "d1_governed_replay",
    )
    seed = provenance.get("seed") if isinstance(provenance, Mapping) else None
    target_count = (
        provenance_metadata.get("target_count")
        if isinstance(provenance_metadata, Mapping)
        else None
    )
    target_spacing_m = _optional_positive_float(
        provenance_metadata.get("target_spacing_m")
        if isinstance(provenance_metadata, Mapping)
        else None,
        field="D1 provenance target_spacing_m",
    )
    stress_profile = manifest.get("d2_offline_stress_profile")
    if stress_profile is not None and not isinstance(stress_profile, Mapping):
        raise ValueError("D1 d2_offline_stress_profile must be a mapping")
    diagnostics = {
        "source_manifest_schema": D1_GOVERNED_MANIFEST_SCHEMA,
        "source_observation_schema": manifest.get("observation_schema_version"),
        "input_record_count": len(records),
        "accepted_radar_record_count": accepted_count,
        "skipped_record_count": len(records) - accepted_count,
        "skipped_reasons": dict(sorted(skipped_reasons.items())),
        "projection": "radar_spherical_ned_to_horizontal_ne",
        "truth_policy": "online_stripped_offline_labels_external",
    }
    frames: list[dict[str, Any]] = []
    for output_index, ((timestamp, explicit_frame_index), detections) in enumerate(
        sorted(
            grouped.items(),
            key=lambda item: (
                item[0][0],
                -1 if item[0][1] is None else item[0][1],
            ),
        )
    ):
        source_frame_index = (
            output_index if explicit_frame_index is None else explicit_frame_index
        )
        for detection_index, detection in enumerate(detections):
            detection["detection_id"] = (
                f"d1-online-{output_index:06d}-{detection_index:04d}"
            )
        arrival_timestamp = max(
            float(detection["metadata"]["arrival_timestamp"])
            for detection in detections
        )
        replay_metadata: dict[str, Any] = {
            "episode_id": episode_id,
            "scenario_name": scenario_name,
            "frame_index": source_frame_index,
            "source_format": "d1_serialize_governed_replay",
            "d1_governed_adapter": diagnostics,
        }
        if seed is not None:
            replay_metadata["seed"] = seed
        if target_count is not None:
            replay_metadata["target_count"] = int(target_count)
        if target_spacing_m is not None:
            replay_metadata["target_spacing_m"] = target_spacing_m
        if stress_profile is not None:
            replay_metadata["d2_offline_stress_profile"] = _json_ready(
                dict(stress_profile)
            )
        frames.append(
            {
                "frame_index": source_frame_index,
                "timestamp": timestamp,
                "measurement_timestamp": timestamp,
                "arrival_timestamp": arrival_timestamp,
                "detections": detections,
                "replay_metadata": replay_metadata,
            }
        )
    return frames


def _convert_d1_radar_record(
    record: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if record.get("schema_version") != D1_OBSERVATION_SCHEMA:
        return None, "unsupported_observation_schema"
    modality = str(record.get("modality", "")).lower()
    if modality != "radar":
        return None, f"unsupported_modality_{modality or 'unknown'}"
    if str(record.get("working_frame", "")).lower() != "ned":
        return None, "unsupported_working_frame"
    measurement = np.asarray(record.get("measurement"), dtype=float).reshape(-1)
    covariance = np.asarray(record.get("covariance"), dtype=float)
    if measurement.size < 3 or covariance.shape[0] < 3 or covariance.shape[1] < 3:
        return None, "invalid_radar_shape"
    if not np.all(np.isfinite(measurement[:3])) or not np.all(
        np.isfinite(covariance[:3, :3])
    ):
        return None, "non_finite_radar_measurement"
    metadata = record.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return None, "invalid_metadata"
    sensor_position = np.asarray(
        metadata.get("sensor_position_ned", [0.0, 0.0, 0.0]), dtype=float
    ).reshape(-1)
    if sensor_position.size < 3 or not np.all(np.isfinite(sensor_position[:3])):
        return None, "invalid_sensor_position"
    position, covariance_ne = _radar_to_horizontal_ne(
        measurement[:3], covariance[:3, :3], sensor_position[:3]
    )
    record_digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return (
        {
            "detection_id": "pending-online-id",
            "position": position.tolist(),
            "covariance": covariance_ne.tolist(),
            "confidence": float(record.get("confidence", 1.0)),
            "metadata": {
                "source_format": "d1_serialize_governed_replay",
                "source_schema_version": D1_OBSERVATION_SCHEMA,
                "sensor_id": str(record.get("sensor_id", "unknown")),
                "modality": "radar",
                "source_frame_id": str(record.get("frame_id", "ned")),
                "measurement_timestamp": float(record["measurement_timestamp"]),
                "arrival_timestamp": float(record["arrival_timestamp"]),
                "source_record_digest": f"sha256:{record_digest}",
                "projection": "radar_spherical_ned_to_horizontal_ne",
            },
        },
        "accepted",
    )


def _radar_to_horizontal_ne(
    measurement: np.ndarray,
    covariance: np.ndarray,
    sensor_position: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    rho, azimuth, elevation = (float(value) for value in measurement)
    cos_azimuth = np.cos(azimuth)
    sin_azimuth = np.sin(azimuth)
    cos_elevation = np.cos(elevation)
    sin_elevation = np.sin(elevation)
    horizontal = rho * cos_elevation
    relative_ne = np.array(
        [horizontal * cos_azimuth, horizontal * sin_azimuth], dtype=float
    )
    jacobian = np.array(
        [
            [
                cos_elevation * cos_azimuth,
                -rho * cos_elevation * sin_azimuth,
                -rho * sin_elevation * cos_azimuth,
            ],
            [
                cos_elevation * sin_azimuth,
                rho * cos_elevation * cos_azimuth,
                -rho * sin_elevation * sin_azimuth,
            ],
        ],
        dtype=float,
    )
    covariance_ne = jacobian @ covariance @ jacobian.T
    covariance_ne = 0.5 * (covariance_ne + covariance_ne.T)
    return sensor_position[:2] + relative_ne, covariance_ne


def _record_frame_index(record: Mapping[str, Any]) -> int | None:
    metadata = record.get("metadata", {})
    if isinstance(metadata, Mapping) and metadata.get("airsim_frame_index") is not None:
        return int(metadata["airsim_frame_index"])
    return None


def _record_metadata_value(records: Sequence[Any], key: str) -> Any:
    for record in records:
        if not isinstance(record, Mapping):
            continue
        metadata = record.get("metadata", {})
        if isinstance(metadata, Mapping) and metadata.get(key) is not None:
            return metadata[key]
    return None


def _first_string(*values: Any) -> str:
    for value in values:
        if value is not None and str(value):
            return str(value)
    raise ValueError("at least one non-empty value is required")


def _optional_positive_float(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be positive and finite") from exc
    if not isfinite(result) or result <= 0.0:
        raise ValueError(f"{field} must be positive and finite")
    return result


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value
