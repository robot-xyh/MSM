from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .covariance_contract import validate_online_sensor_observation
from .replay import (
    REPLAY_SCHEMA_VERSION,
    ReplayProvenance,
    sensor_observation_from_jsonl_record,
    serialize_governed_replay,
)
from .types import SensorObservation


AIRSIM_FREEZE_SUMMARY_SCHEMA_VERSION = "d1.airsim_replay_freeze_summary.v1"
AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION = "d1.airsim_offline_truth.v1"
AIRSIM_FREEZE_OUTPUT_SCHEMA_VERSION = "d1.airsim_replay_freeze_output.v1"
AIRSIM_CAPTURE_PROVENANCE_SCHEMA_VERSION = "d1.airsim_capture_provenance.v1"

_OBSERVATION_CONTAINER_KEYS = ("sensor_observations", "observations", "records")
_IDENTITY_KEYS = {
    "truth_id",
    "truth_object_id",
    "actor_id",
    "actor_name",
    "object_id",
    "object_name",
    "airsim_actor_name",
    "airsim_object_name",
    "detection_id",
    "local_track_id",
}
_EVENT_ALIASES = {
    "crossing": "crossing",
    "target_crossing": "crossing",
    "occluded": "occlusion",
    "occlusion": "occlusion",
    "partial_occlusion": "occlusion",
    "miss": "missed_detection",
    "missed": "missed_detection",
    "missed_detection": "missed_detection",
    "false_alarm": "false_alarm",
    "clutter": "false_alarm",
    "oosm": "oosm",
    "out_of_sequence": "oosm",
    "out_of_sequence_measurement": "oosm",
    "node_exit": "node_exit",
    "node_departure": "node_exit",
    "node_lost": "node_exit",
}


@dataclass(frozen=True)
class AirSimReplayFreezeResult:
    """Frozen D1 replay products generated without importing the AirSim SDK."""

    manifest: dict[str, Any]
    records: list[dict[str, Any]]
    offline_truth: dict[str, Any]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AIRSIM_FREEZE_OUTPUT_SCHEMA_VERSION,
            "manifest": self.manifest,
            "records": self.records,
            "offline_truth": self.offline_truth,
            "summary": self.summary,
        }


def load_airsim_replay_payloads(path: str | Path) -> list[dict[str, Any]]:
    """Load main-persisted frame/observation JSON or JSONL payloads."""

    input_path = Path(path)
    if input_path.suffix.lower() == ".jsonl":
        payloads: list[dict[str, Any]] = []
        with input_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    value = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"failed to parse {input_path} line {line_number} as JSON"
                    ) from exc
                if not isinstance(value, Mapping):
                    raise ValueError(
                        f"{input_path} line {line_number} must contain a JSON object"
                    )
                payloads.append(dict(value))
        return payloads

    value = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        if not all(isinstance(item, Mapping) for item in value):
            raise ValueError("D1 AirSim replay JSON list must contain only objects")
        return [dict(item) for item in value]
    if not isinstance(value, Mapping):
        raise ValueError("D1 AirSim replay JSON must contain an object or object list")
    for key in ("frames", "payloads"):
        nested = value.get(key)
        if isinstance(nested, list):
            if not all(isinstance(item, Mapping) for item in nested):
                raise ValueError(f"D1 AirSim replay {key} must contain only objects")
            return [dict(item) for item in nested]
    return [dict(value)]


def freeze_airsim_replay_payloads(
    payloads: Iterable[Mapping[str, Any]],
    provenance: ReplayProvenance | Mapping[str, Any],
) -> AirSimReplayFreezeResult:
    """Freeze anonymous main payloads into the governed D1 replay contract.

    Truth objects are used only to build the evaluator sidecar. Frames without
    sensor observations, including missed detections and node exits, never
    create synthetic observations.
    """

    source_payloads = [dict(payload) for payload in payloads]
    capture_provenance = _resolve_capture_provenance(source_payloads)
    governed_provenance = _bind_capture_provenance(provenance, capture_provenance)
    identity_tokens = _collect_identity_tokens(source_payloads)
    truth_samples = _collect_truth_samples(source_payloads)
    event_counts: Counter[str] = Counter()
    sensor_health: dict[str, Any] = {}
    observations: list[SensorObservation] = []
    rejected: list[dict[str, Any]] = []
    timestamp_availability: Counter[str] = Counter()
    source_schema_versions: set[str] = set()
    scene_ids: set[str] = set()
    profile_ids: set[str] = set()
    candidate_count = 0

    for payload_index, payload in enumerate(source_payloads):
        context = _frame_context(payload, payload_index)
        event_counts.update(context["event_labels"])
        _collect_sensor_health(payload, sensor_health)
        _collect_source_identity(payload, source_schema_versions, scene_ids, profile_ids)

        candidates = _observation_candidates(payload)
        candidate_count += len(candidates)
        for candidate_index, candidate in enumerate(candidates):
            candidate_health = _sensor_health_for_candidate(candidate, context)
            if candidate_health is not None and candidate.get("sensor_id") is not None:
                sensor_health[str(candidate["sensor_id"])] = candidate_health
            try:
                observation = _canonical_observation(
                    candidate,
                    context=context,
                    opaque_index=len(observations),
                    identity_tokens=identity_tokens,
                )
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append(
                    {
                        "payload_index": payload_index,
                        "candidate_index": candidate_index,
                        "reason": str(exc),
                    }
                )
                continue
            observations.append(observation)
            event_counts.update(_event_labels(candidate))
            timestamp_availability.update(
                {
                    f"processing_timestamp_{observation.metadata['timestamp_availability']['processing']}": 1,
                    f"publish_timestamp_{observation.metadata['timestamp_availability']['publish']}": 1,
                }
            )

    governed = serialize_governed_replay(observations, governed_provenance)
    field_availability = _freeze_field_availability(
        observations,
        capture_provenance=capture_provenance,
        offline_truth_sample_count=len(truth_samples),
    )
    governed["manifest"].update(
        {
            "capture_provenance": capture_provenance,
            "field_availability": field_availability,
            "artifacts": {
                "online_records": "sensor_observations.jsonl",
                "offline_truth_sidecar": "offline_truth.json",
                "diagnostic_summary": "summary.json",
            },
        }
    )
    records = governed["records"]
    online_truth_leak_count = _online_truth_leak_count(records, identity_tokens)
    if online_truth_leak_count:
        raise ValueError("D1 frozen online replay still contains truth/actor/object identity")

    offline_truth = {
        "schema_version": AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION,
        "frame_id": "ned",
        "evaluator_only": True,
        "capture_provenance_digest": capture_provenance["capture_provenance_digest"],
        "source_evidence_path": capture_provenance["evidence_path"],
        "sample_count": len(truth_samples),
        "target_count": len(
            {sample["truth_id"] for sample in truth_samples if sample.get("truth_id")}
        ),
        "position_availability_counts": dict(
            sorted(Counter(sample["position_availability"] for sample in truth_samples).items())
        ),
        "samples": truth_samples,
    }
    summary = {
        "schema_version": AIRSIM_FREEZE_SUMMARY_SCHEMA_VERSION,
        "observation_schema_version": REPLAY_SCHEMA_VERSION,
        "capture_provenance": capture_provenance,
        "field_availability": field_availability,
        "target_spacing_m": capture_provenance["target_spacing_m"],
        "scenario_config_version": capture_provenance["scenario_config_version"],
        "seed": capture_provenance["seed"],
        "evidence_path": capture_provenance["evidence_path"],
        "input_payload_count": len(source_payloads),
        "observation_candidate_count": candidate_count,
        "accepted_observation_count": len(observations),
        "rejected_observation_count": len(rejected),
        "rejected_observations": rejected,
        "modality_counts": dict(sorted(Counter(obs.modality for obs in observations).items())),
        "event_counts": dict(sorted(event_counts.items())),
        "sensor_health": sensor_health,
        "sensor_health_availability": "available" if sensor_health else "unavailable",
        "timestamp_availability": dict(sorted(timestamp_availability.items())),
        "source_schema_versions": sorted(source_schema_versions) or ["unavailable"],
        "scene_ids": sorted(scene_ids) or ["unavailable"],
        "profile_ids": sorted(profile_ids) or ["unavailable"],
        "offline_truth_sample_count": len(truth_samples),
        "offline_truth_target_count": offline_truth["target_count"],
        "offline_truth_position_availability_counts": offline_truth[
            "position_availability_counts"
        ],
        "offline_truth_unavailable_position_sample_count": sum(
            sample["position_availability"] == "unavailable" for sample in truth_samples
        ),
        "online_truth_leak_count": online_truth_leak_count,
        "missing_measurements_fabricated": 0,
    }
    json.dumps(summary, allow_nan=False, sort_keys=True)
    return AirSimReplayFreezeResult(
        manifest=governed["manifest"],
        records=records,
        offline_truth=offline_truth,
        summary=summary,
    )


def _resolve_capture_provenance(
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return one authoritative capture declaration without using truth geometry."""

    declarations: list[tuple[int, dict[str, Any]]] = []
    payloads_with_declaration: set[int] = set()
    for payload_index, payload in enumerate(payloads):
        candidates: list[Any] = [payload.get("capture_provenance")]
        metadata = payload.get("metadata")
        if isinstance(metadata, Mapping):
            candidates.append(metadata.get("capture_provenance"))
        manifest = payload.get("manifest")
        if isinstance(manifest, Mapping):
            candidates.append(manifest.get("capture_provenance"))
        for observation in _observation_candidates(payload):
            candidates.append(observation.get("capture_provenance"))
            observation_metadata = observation.get("metadata")
            if isinstance(observation_metadata, Mapping):
                candidates.append(observation_metadata.get("capture_provenance"))
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            declarations.append((payload_index, _normalize_capture_declaration(candidate)))
            payloads_with_declaration.add(payload_index)

    if not declarations:
        raise ValueError(
            "D1 AirSim freeze requires explicit capture_provenance; "
            "target_spacing_m must not be inferred from truth geometry"
        )
    authoritative = declarations[0][1]
    for payload_index, candidate in declarations[1:]:
        for field in (
            "source_schema_version",
            "scenario_id",
            "scenario_version",
            "scenario_config_version",
            "seed",
            "target_spacing_m",
            "evidence_path",
        ):
            if not _capture_values_equal(field, authoritative[field], candidate[field]):
                raise ValueError(
                    "conflicting D1 AirSim capture provenance declaration for "
                    f"{field} at payload {payload_index}: "
                    f"{authoritative[field]!r} != {candidate[field]!r}"
                )

    capture_payload = {
        "schema_version": AIRSIM_CAPTURE_PROVENANCE_SCHEMA_VERSION,
        **authoritative,
        "source": "captured_payload_provenance",
        "declaration_count": len(declarations),
        "input_payload_count": len(payloads),
        "payloads_with_declaration_count": len(payloads_with_declaration),
    }
    capture_payload["capture_provenance_digest"] = _stable_digest(capture_payload)
    return capture_payload


def _normalize_capture_declaration(value: Mapping[str, Any]) -> dict[str, Any]:
    scenario_config = value.get("scenario_config")
    scenario_config = dict(scenario_config) if isinstance(scenario_config, Mapping) else {}
    source_schema_version = _required_text(value.get("schema_version"), "schema_version")
    scenario_id = _required_text(
        _first_value(
            value.get("scenario_id"),
            value.get("scenario_name"),
            scenario_config.get("scenario_id"),
            scenario_config.get("scenario_name"),
        ),
        "scenario_id",
    )
    scenario_version = _required_text(
        _first_value(value.get("scenario_version"), scenario_config.get("scenario_version")),
        "scenario_version",
    )
    scenario_config_version = _required_text(
        _first_value(
            value.get("scenario_config_version"),
            value.get("config_version"),
            scenario_config.get("config_version"),
        ),
        "scenario_config_version",
    )
    evidence_path = _required_text(
        _first_value(value.get("evidence_path"), value.get("capture_path")),
        "evidence_path",
    )
    try:
        seed = int(_first_value(value.get("seed"), scenario_config.get("seed")))
    except (TypeError, ValueError) as exc:
        raise ValueError("D1 AirSim capture provenance seed must be an integer") from exc
    try:
        target_spacing_m = float(
            _first_value(
                value.get("target_spacing_m"),
                value.get("actor_target_spacing_m"),
                scenario_config.get("target_spacing_m"),
                scenario_config.get("actor_target_spacing_m"),
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "D1 AirSim capture provenance target_spacing_m must be positive and finite"
        ) from exc
    if not math.isfinite(target_spacing_m) or target_spacing_m <= 0.0:
        raise ValueError(
            "D1 AirSim capture provenance target_spacing_m must be positive and finite"
        )
    return {
        "source_schema_version": source_schema_version,
        "scenario_id": scenario_id,
        "scenario_version": scenario_version,
        "scenario_config_version": scenario_config_version,
        "seed": seed,
        "target_spacing_m": target_spacing_m,
        "evidence_path": evidence_path,
    }


def _bind_capture_provenance(
    provenance: ReplayProvenance | Mapping[str, Any],
    capture: Mapping[str, Any],
) -> dict[str, Any]:
    payload = provenance.to_dict() if isinstance(provenance, ReplayProvenance) else dict(provenance)
    metadata = dict(payload.get("metadata") or {})
    comparisons = {
        "scenario_id": payload.get("scenario_id"),
        "scenario_version": payload.get("scenario_version"),
        "scenario_config_version": payload.get("config_version"),
        "seed": payload.get("seed"),
        "target_spacing_m": metadata.get("target_spacing_m"),
    }
    for field, declared in comparisons.items():
        if declared is None or declared == "":
            raise ValueError(
                f"D1 AirSim replay provenance must declare {field} for capture validation"
            )
        if not _capture_values_equal(field, declared, capture[field]):
            raise ValueError(
                f"D1 AirSim replay provenance {field} conflicts with capture provenance: "
                f"{declared!r} != {capture[field]!r}"
            )
    for optional_field in ("evidence_path", "scenario_config_version"):
        declared = metadata.get(optional_field)
        if declared is not None and not _capture_values_equal(
            optional_field, declared, capture[optional_field]
        ):
            raise ValueError(
                f"D1 AirSim replay provenance {optional_field} conflicts with capture provenance: "
                f"{declared!r} != {capture[optional_field]!r}"
            )
    metadata.update(
        {
            "target_spacing_m": capture["target_spacing_m"],
            "target_spacing_source": "capture_provenance",
            "scenario_config_version": capture["scenario_config_version"],
            "evidence_path": capture["evidence_path"],
            "capture_provenance_digest": capture["capture_provenance_digest"],
            "capture_provenance_schema_version": capture["schema_version"],
        }
    )
    payload["metadata"] = metadata
    return payload


def _freeze_field_availability(
    observations: Sequence[SensorObservation],
    *,
    capture_provenance: Mapping[str, Any],
    offline_truth_sample_count: int,
) -> dict[str, dict[str, Any]]:
    count = len(observations)
    return {
        "measurement_timestamp": {"status": "available", "count": count},
        "arrival_timestamp": {"status": "available", "count": count},
        "covariance": {"status": "available", "count": count},
        "source_lineage": {"status": "available", "count": count},
        "working_frame_ned": {"status": "available", "count": count},
        "scenario_config_version": {"status": "available", "count": 1},
        "seed": {"status": "available", "count": 1},
        "target_spacing_m": {
            "status": "available",
            "count": 1,
            "source": capture_provenance["source"],
        },
        "evidence_path": {"status": "available", "count": 1},
        "offline_truth_sidecar": {
            "status": "available",
            "count": int(offline_truth_sample_count),
            "online_access": False,
        },
    }


def _capture_values_equal(field: str, first: Any, second: Any) -> bool:
    if field == "target_spacing_m":
        try:
            return math.isclose(float(first), float(second), rel_tol=0.0, abs_tol=1e-6)
        except (TypeError, ValueError):
            return False
    if field == "seed":
        try:
            return int(first) == int(second)
        except (TypeError, ValueError):
            return False
    return str(first) == str(second)


def _required_text(value: Any, field: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"D1 AirSim capture provenance missing required field {field}")
    return str(value).strip()


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def freeze_airsim_replay_file(
    input_path: str | Path,
    provenance: ReplayProvenance | Mapping[str, Any],
) -> AirSimReplayFreezeResult:
    return freeze_airsim_replay_payloads(load_airsim_replay_payloads(input_path), provenance)


def write_frozen_airsim_replay(
    output_dir: str | Path,
    result: AirSimReplayFreezeResult,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "manifest": output / "manifest.json",
        "records": output / "sensor_observations.jsonl",
        "offline_truth": output / "offline_truth.json",
        "summary": output / "summary.json",
    }
    paths["manifest"].write_text(
        json.dumps(result.manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with paths["records"].open("w", encoding="utf-8") as stream:
        for record in result.records:
            stream.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    paths["offline_truth"].write_text(
        json.dumps(result.offline_truth, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["summary"].write_text(
        json.dumps(result.summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return paths


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _observation_candidates(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if _looks_like_observation(payload):
        return [dict(payload)]
    for key in _OBSERVATION_CONTAINER_KEYS:
        nested = payload.get(key)
        if isinstance(nested, list):
            return [dict(item) for item in nested if isinstance(item, Mapping)]
    return []


def _looks_like_observation(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in ("measurement", "modality", "sensor_id"))


def _frame_context(payload: Mapping[str, Any], payload_index: int) -> dict[str, Any]:
    metadata = payload.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    manifest = payload.get("manifest")
    manifest = dict(manifest) if isinstance(manifest, Mapping) else {}
    manifest_provenance = manifest.get("provenance")
    manifest_provenance = (
        dict(manifest_provenance) if isinstance(manifest_provenance, Mapping) else {}
    )
    provenance_metadata = manifest_provenance.get("metadata")
    provenance_metadata = (
        dict(provenance_metadata) if isinstance(provenance_metadata, Mapping) else {}
    )
    clock = payload.get("clock")
    clock = dict(clock) if isinstance(clock, Mapping) else {}
    processing_timestamp = _first_value(
        payload.get("processing_timestamp"),
        clock.get("processing_timestamp"),
        metadata.get("processing_timestamp"),
    )
    publish_timestamp = _first_value(
        payload.get("publish_timestamp"),
        clock.get("publish_timestamp"),
        metadata.get("publish_timestamp"),
    )
    return {
        "payload_index": payload_index,
        "frame_index": _first_value(payload.get("frame_index"), metadata.get("frame_index")),
        "processing_timestamp": processing_timestamp,
        "publish_timestamp": publish_timestamp,
        "sensor_health": payload.get("sensor_health"),
        "event_labels": _event_labels(payload),
        "scene_id": _first_value(
            payload.get("scene_id"),
            payload.get("scenario_name"),
            payload.get("episode_id"),
            metadata.get("scene_id"),
            metadata.get("scenario_name"),
            manifest_provenance.get("scenario_id"),
        ),
        "profile_id": _first_value(
            payload.get("profile_id"),
            payload.get("profile"),
            metadata.get("profile_id"),
            provenance_metadata.get("profile_id"),
        ),
        "source_schema_version": _first_value(
            payload.get("schema_version"),
            payload.get("source_schema_version"),
            metadata.get("schema_version"),
            manifest.get("observation_schema_version"),
        ),
    }


def _canonical_observation(
    candidate: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    opaque_index: int,
    identity_tokens: set[str],
) -> SensorObservation:
    record = dict(candidate)
    metadata = record.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    for key in (
        "coverage_cell",
        "source_lineage",
        "timestamp_uncertainty_s",
        "expected_latency_s",
        "latency_tolerance_s",
        "oosm_expected",
    ):
        if key in record and key not in metadata:
            metadata[key] = record[key]

    processing_timestamp = _first_value(
        record.get("processing_timestamp"),
        metadata.get("processing_timestamp"),
        context.get("processing_timestamp"),
    )
    publish_timestamp = _first_value(
        record.get("publish_timestamp"),
        metadata.get("publish_timestamp"),
        context.get("publish_timestamp"),
    )
    metadata.update(
        {
            "processing_timestamp": _float_or_none(processing_timestamp),
            "publish_timestamp": _float_or_none(publish_timestamp),
            "timestamp_availability": {
                "measurement": "available",
                "arrival": "available",
                "processing": "available" if processing_timestamp is not None else "unavailable",
                "publish": "available" if publish_timestamp is not None else "unavailable",
            },
            "sensor_health": _sensor_health_for_candidate(record, context),
            "sensor_health_availability": (
                "available" if _sensor_health_for_candidate(record, context) is not None else "unavailable"
            ),
            "scene_id": context.get("scene_id") or "unavailable",
            "profile_id": context.get("profile_id") or "unavailable",
            "source_schema_version": context.get("source_schema_version") or "unavailable",
            "airsim_payload_index": context["payload_index"],
            "event_labels": sorted(set(context["event_labels"]) | set(_event_labels(record))),
        }
    )
    if context.get("frame_index") is not None:
        metadata.setdefault("airsim_frame_index", context["frame_index"])
    metadata = _sanitize_value(metadata, identity_tokens)

    metadata.setdefault("source_observation_schema_version", record.get("schema_version") or "unavailable")
    record["schema_version"] = REPLAY_SCHEMA_VERSION
    record["observation_id"] = f"airsim-obs-{opaque_index + 1:08d}"
    record["metadata"] = metadata
    record["classification_hint"] = _sanitize_classification_hint(
        record.get("classification_hint"), identity_tokens
    )
    observation = sensor_observation_from_jsonl_record(record)
    validate_online_sensor_observation(
        observation,
        context="D1 AirSim freeze",
    )
    if not observation.metadata.get("coverage_cell"):
        raise ValueError("D1 AirSim freeze requires coverage_cell")
    return observation


def _sensor_health_for_candidate(
    candidate: Mapping[str, Any], context: Mapping[str, Any]
) -> Any:
    if candidate.get("sensor_health") is not None:
        return candidate.get("sensor_health")
    metadata = candidate.get("metadata")
    if isinstance(metadata, Mapping) and metadata.get("sensor_health") is not None:
        return metadata.get("sensor_health")
    health = context.get("sensor_health")
    sensor_id = candidate.get("sensor_id")
    if isinstance(health, Mapping) and sensor_id in health:
        return health[sensor_id]
    return None


def _collect_sensor_health(payload: Mapping[str, Any], target: dict[str, Any]) -> None:
    health = payload.get("sensor_health")
    if isinstance(health, Mapping):
        for sensor_id, value in health.items():
            target[str(sensor_id)] = value
    elif isinstance(health, list):
        for item in health:
            if isinstance(item, Mapping) and item.get("sensor_id") is not None:
                target[str(item["sensor_id"])] = dict(item)


def _collect_source_identity(
    payload: Mapping[str, Any],
    schema_versions: set[str],
    scene_ids: set[str],
    profile_ids: set[str],
) -> None:
    context = _frame_context(payload, 0)
    for value, target in (
        (context["source_schema_version"], schema_versions),
        (context["scene_id"], scene_ids),
        (context["profile_id"], profile_ids),
    ):
        if value is not None:
            target.add(str(value))


def _event_labels(value: Mapping[str, Any]) -> list[str]:
    raw_values: list[Any] = []
    for key in ("event_labels", "labels", "events", "quality_flags"):
        raw = value.get(key)
        if isinstance(raw, (list, tuple)):
            raw_values.extend(raw)
        elif raw is not None:
            raw_values.append(raw)
    for key in _EVENT_ALIASES:
        if value.get(key) is True:
            raw_values.append(key)
    labels: list[str] = []
    for item in raw_values:
        if isinstance(item, Mapping):
            item = _first_value(item.get("event_type"), item.get("type"), item.get("label"))
        if item is None:
            continue
        normalized = str(item).strip().lower().replace("-", "_").replace(" ", "_")
        labels.append(_EVENT_ALIASES.get(normalized, normalized))
    return sorted(set(labels))


def _collect_truth_samples(payloads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    samples_by_key: dict[tuple[str, float | None], dict[str, Any]] = {}
    for payload_index, payload in enumerate(payloads):
        timestamp = _first_value(payload.get("timestamp"), payload.get("measurement_timestamp"))
        containers: list[Any] = []
        for key in ("offline_truth", "truth_objects", "truth_samples"):
            value = payload.get(key)
            if value is not None:
                containers.append(value)
        for candidate in _observation_candidates(payload):
            metadata = candidate.get("metadata")
            if isinstance(metadata, Mapping):
                containers.append(metadata)
        for container in containers:
            items = container if isinstance(container, list) else [container]
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                truth_id = _truth_id(item)
                if truth_id is None:
                    continue
                position = _truth_position(item)
                sample_timestamp = _first_value(
                    item.get("timestamp"), item.get("measurement_timestamp"), timestamp
                )
                normalized_timestamp = _float_or_none(sample_timestamp)
                key = (str(truth_id), normalized_timestamp)
                candidate = {
                    "truth_id": str(truth_id),
                    "timestamp": normalized_timestamp,
                    "position_ned": position,
                    "position_availability": "available" if position is not None else "unavailable",
                    "source_payload_index": payload_index,
                }
                existing = samples_by_key.get(key)
                if existing is None:
                    samples_by_key[key] = candidate
                    continue
                _merge_truth_sample(samples_by_key, key, existing, candidate)
    samples = list(samples_by_key.values())
    return sorted(samples, key=lambda row: (row["timestamp"] is None, row["timestamp"] or 0.0, row["truth_id"]))


def _merge_truth_sample(
    samples_by_key: dict[tuple[str, float | None], dict[str, Any]],
    key: tuple[str, float | None],
    existing: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    existing_position = existing.get("position_ned")
    candidate_position = candidate.get("position_ned")
    if existing_position is None and candidate_position is not None:
        samples_by_key[key] = candidate
        return
    if existing_position is not None and candidate_position is None:
        return
    if existing_position is None:
        return
    if not _positions_equal(existing_position, candidate_position):
        raise ValueError(
            "conflicting available D1 offline truth positions for "
            f"truth_id={key[0]!r}, timestamp={key[1]!r}: "
            f"{existing_position!r} != {candidate_position!r}"
        )


def _positions_equal(first: Any, second: Any, *, tolerance: float = 1e-6) -> bool:
    if not isinstance(first, (list, tuple)) or not isinstance(second, (list, tuple)):
        return False
    if len(first) != 3 or len(second) != 3:
        return False
    return all(abs(float(left) - float(right)) <= tolerance for left, right in zip(first, second))


def _truth_id(value: Mapping[str, Any]) -> str | None:
    for key in ("truth_id", "truth_object_id", "object_id", "actor_id"):
        candidate = value.get(key)
        if candidate is not None and str(candidate).strip():
            return str(candidate)
    offline = value.get("offline_truth")
    if isinstance(offline, Mapping):
        return _truth_id(offline)
    return None


def _truth_position(value: Mapping[str, Any]) -> list[float] | None:
    for key in ("truth_position_ned", "position_ned", "state_position_ned"):
        candidate = value.get(key)
        if isinstance(candidate, (list, tuple)) and len(candidate) == 3:
            try:
                return [float(component) for component in candidate]
            except (TypeError, ValueError):
                return None
    offline = value.get("offline_truth")
    if isinstance(offline, Mapping):
        return _truth_position(offline)
    return None


def _collect_identity_tokens(payloads: Sequence[Mapping[str, Any]]) -> set[str]:
    tokens: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).strip().lower()
                if _is_identity_key(normalized) and item is not None:
                    if isinstance(item, (str, int)) and str(item).strip():
                        tokens.add(str(item))
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(payloads)
    return tokens


def _sanitize_value(value: Any, identity_tokens: set[str]) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if _is_identity_key(normalized) or normalized.endswith("_offline_only"):
                continue
            sanitized_item = _sanitize_value(item, identity_tokens)
            if sanitized_item is not None:
                sanitized[str(key)] = sanitized_item
        return sanitized
    if isinstance(value, (list, tuple)):
        return [item for item in (_sanitize_value(item, identity_tokens) for item in value) if item is not None]
    if isinstance(value, str) and any(token and token in value for token in identity_tokens):
        return None
    return value


def _sanitize_classification_hint(value: Any, identity_tokens: set[str]) -> str | None:
    if value is None:
        return None
    text = str(value)
    if any(token and token in text for token in identity_tokens):
        return None
    return text


def _online_truth_leak_count(records: Sequence[Mapping[str, Any]], tokens: set[str]) -> int:
    count = 0

    def visit(value: Any) -> None:
        nonlocal count
        if isinstance(value, Mapping):
            for key, item in value.items():
                if _is_identity_key(str(key).strip().lower()):
                    count += 1
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
        elif isinstance(value, str) and any(token and token in value for token in tokens):
            count += 1

    visit(records)
    return count


def _is_identity_key(key: str) -> bool:
    return key in _IDENTITY_KEYS or key.endswith(
        ("_truth_id", "_actor_id", "_actor_name", "_object_id", "_object_name")
    )


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    return None if value is None else float(value)
