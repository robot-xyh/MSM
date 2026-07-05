"""Adapters for evaluating persisted AirSim Blocks replay JSONL logs.

This module is intentionally file/offline only. It parses already-written
``blocks_frames.jsonl`` and optional ``blocks_sensor_observations.jsonl`` files
into D6 records without importing AirSim or the runtime package.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .metrics import (
    EventRecord,
    LinkRecord,
    MetricsCollector,
    TerminalRecord,
    TrackRecord,
)


def load_blocks_replay_jsonl(
    frames_path: str | Path,
    sensor_observations_path: str | Path | None = None,
) -> tuple[MetricsCollector, dict[str, Any]]:
    """Load raw Blocks replay logs into a D6 ``MetricsCollector``.

    ``blocks_frames.jsonl`` provides truth, camera metadata, detection boxes,
    local visual IDs, and object labels. ``blocks_sensor_observations.jsonl`` is
    optional and contributes communication-link metadata plus D1 replay coverage.
    """

    frames = _load_jsonl_objects(frames_path)
    collector = MetricsCollector()
    truth_summary = truth_summary_from_blocks_frames(frames)

    for frame in frames:
        _add_frame_records(collector, frame)

    if (
        sensor_observations_path is not None
        and Path(sensor_observations_path).exists()
    ):
        for observation in _load_jsonl_objects(sensor_observations_path):
            _add_sensor_observation_records(collector, observation)

    return collector, truth_summary


def truth_summary_from_blocks_frames(frames: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a D6 truth summary from raw Blocks frame dictionaries."""

    timestamps_by_id: dict[str, list[float]] = defaultdict(list)
    high_threat_ids: set[str] = set()
    high_threat_by_timestamp: dict[float, set[str]] = defaultdict(set)
    frame_timestamps: set[float] = set()
    scenario_name = "blocks_replay"
    resource_count = 0
    camera_count = 0

    for frame in frames:
        timestamp = float(frame.get("timestamp", 0.0))
        frame_timestamps.add(timestamp)
        scenario_name = str(frame.get("scenario_name", scenario_name))
        resource_count = max(resource_count, len(frame.get("resources", []) or []))
        camera_count = max(camera_count, len(frame.get("cameras", []) or []))
        for truth in frame.get("truth_objects", []) or []:
            if str(truth.get("object_type", "target")) != "target":
                continue
            object_id_raw = truth.get("object_id")
            if object_id_raw is None:
                continue
            object_id = str(object_id_raw)
            timestamps_by_id[object_id].append(timestamp)
            if float(truth.get("threat_score", 0.0) or 0.0) >= 0.7:
                high_threat_ids.add(object_id)
                high_threat_by_timestamp[timestamp].add(object_id)

    timestamps = sorted(frame_timestamps)
    high_threat_sorted = sorted(high_threat_ids)
    return {
        "truth_timestamps": {
            truth_id: sorted(values)
            for truth_id, values in timestamps_by_id.items()
        },
        "total_truth_opportunities": sum(len(values) for values in timestamps_by_id.values()),
        "high_threat_ids": high_threat_sorted,
        "high_threat_by_timestamp": {
            timestamp: sorted(high_threat_by_timestamp.get(timestamp, set()))
            for timestamp in timestamps
        },
        "scenario": {
            "name": scenario_name,
            "duration_s": (
                max(timestamps) - min(timestamps) if len(timestamps) > 1 else 0.0
            ),
            "frame_count": len(timestamps),
            "target_count": len(timestamps_by_id),
            "resource_count": resource_count,
            "drone_count": resource_count,
            "camera_count": camera_count,
            "source": "blocks_frames_jsonl",
            "offline_only": True,
            "real_airsim_used": True,
        },
    }


def _add_frame_records(collector: MetricsCollector, frame: Mapping[str, Any]) -> None:
    timestamp = float(frame.get("timestamp", 0.0))
    truth_by_id = {
        str(truth.get("object_id")): truth
        for truth in frame.get("truth_objects", []) or []
        if str(truth.get("object_type", "target")) == "target"
    }
    vehicle_to_resource = _vehicle_to_resource(frame)
    camera_by_id = {
        str(camera.get("camera_id")): camera
        for camera in frame.get("cameras", []) or []
    }

    for image in _frame_images(frame):
        owner = str(image.get("camera_vehicle_name") or image.get("owner_id") or "")
        delivered = bool(image.get("ok", False))
        collector.add_link(
            LinkRecord(
                timestamp=timestamp,
                source_node_id=owner or "unknown_camera",
                target_node_id="D6-EVALUATION",
                link_type="video_metadata",
                message_type="video_metadata",
                sent_timestamp=timestamp,
                received_timestamp=timestamp,
                payload_kind="video_metadata",
                delivered=delivered,
                metadata={
                    "camera_name": image.get("camera_name"),
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "png_saved": bool(image.get("path")),
                },
            )
        )

    detections_by_object: dict[str, set[str]] = defaultdict(set)
    local_history: dict[str, set[str]] = defaultdict(set)
    for detection in frame.get("visual_detections", []) or []:
        object_id = str(detection.get("object_id") or "")
        camera_id = str(detection.get("camera_id") or "")
        camera_owner = camera_id.split(":", 1)[0] if camera_id else ""
        resource_id = vehicle_to_resource.get(camera_owner, camera_owner or "unknown_resource")
        local_track_id = str(detection.get("local_track_id") or detection.get("detection_id") or "")
        truth = truth_by_id.get(object_id)
        truth_position = truth.get("position_ned") if truth is not None else None
        if truth is None:
            truth_id = None
            association_correct = False
        else:
            truth_id = object_id
            association_correct = True

        collector.add_track(
            TrackRecord(
                timestamp=timestamp,
                global_track_id=object_id or None,
                truth_id=truth_id,
                position=truth_position,
                truth_position=truth_position,
                track_state="detected",
                association_source="blocks_visual_detection",
            )
        )
        collector.add_terminal(
            TerminalRecord(
                timestamp=timestamp,
                resource_id=resource_id,
                assigned_global_track_id=object_id or None,
                local_track_id=local_track_id or None,
                decision_state="associated",
                expected_global_track_id=object_id or None,
                association_correct=association_correct,
            )
        )
        collector.add_link(
            LinkRecord(
                timestamp=timestamp,
                source_node_id=camera_owner or resource_id,
                target_node_id="D6-EVALUATION",
                link_type="video_cue",
                message_type="bbox",
                sent_timestamp=timestamp,
                received_timestamp=timestamp,
                payload_kind="bbox",
                delivered=True,
                metadata={
                    "camera_id": camera_id,
                    "resource_id": resource_id,
                    "bbox_xyxy": detection.get("bbox_xyxy"),
                    "object_name": _object_name(detection),
                    "object_id": object_id or None,
                    "camera_intrinsics": _camera_intrinsics(camera_by_id.get(camera_id)),
                    "camera_extrinsics": _camera_extrinsics(camera_by_id.get(camera_id)),
                    "confidence": detection.get("confidence"),
                },
            )
        )
        if object_id:
            detections_by_object[object_id].add(camera_id)
        if local_track_id and object_id:
            local_history[local_track_id].add(object_id)

    for object_id, camera_ids in detections_by_object.items():
        if len(camera_ids) > 1:
            collector.add_event(
                EventRecord(
                    timestamp=timestamp,
                    event_type="multi_view_consensus_result",
                    actor_id="blocks_replay",
                    metadata={
                        "assigned_global_track_id": object_id,
                        "camera_ids": sorted(camera_ids),
                        "consensus_reached": True,
                        "multi_view_consensus": True,
                    },
                )
            )

    for local_track_id, object_ids in local_history.items():
        if len(object_ids) > 1:
            collector.add_event(
                EventRecord(
                    timestamp=timestamp,
                    event_type="cross_view_conflict",
                    actor_id="blocks_replay",
                    metadata={
                        "local_track_id": local_track_id,
                        "candidate_object_ids": sorted(object_ids),
                    },
                )
            )


def _add_sensor_observation_records(
    collector: MetricsCollector,
    observation: Mapping[str, Any],
) -> None:
    timestamp = float(
        observation.get("measurement_timestamp", observation.get("timestamp", 0.0))
    )
    metadata = dict(observation.get("metadata", {}) or {})
    communication = dict(observation.get("communication", {}) or {})
    delivered = _optional_bool(
        communication.get("delivered", metadata.get("delivered")),
        default=True,
    )
    truth_id = metadata.get("truth_id")
    if truth_id is not None and delivered:
        collector.add_track(
            TrackRecord(
                timestamp=timestamp,
                global_track_id=str(truth_id),
                truth_id=str(truth_id),
                track_state="observed",
                association_source=f"blocks_{observation.get('modality', 'sensor')}",
            )
        )

    source_node_id = (
        communication.get("source_node_id")
        or metadata.get("source_node_id")
        or observation.get("sensor_id")
        or "blocks_sensor"
    )
    target_node_id = (
        communication.get("target_node_id")
        or metadata.get("target_node_id")
        or "D1-FUSION"
    )
    sent_timestamp = communication.get("sent_timestamp", timestamp)
    received_timestamp = communication.get(
        "received_timestamp",
        observation.get("arrival_timestamp", timestamp),
    )
    arrival_timestamp = observation.get("arrival_timestamp", received_timestamp)
    collector.add_link(
        LinkRecord(
            timestamp=timestamp,
            source_node_id=str(source_node_id),
            target_node_id=None if target_node_id is None else str(target_node_id),
            relay_node_id=communication.get("relay_node_id") or metadata.get("relay_node_id"),
            link_type=str(
                communication.get("link_type")
                or metadata.get("link_type")
                or "c2_replay"
            ),
            message_type=str(observation.get("modality") or "sensor_observation"),
            sequence_id=communication.get("sequence_id") or metadata.get("sequence_id"),
            sent_timestamp=float(sent_timestamp) if sent_timestamp is not None else None,
            received_timestamp=float(received_timestamp) if received_timestamp is not None else None,
            measurement_timestamp=timestamp,
            arrival_timestamp=float(arrival_timestamp) if arrival_timestamp is not None else None,
            payload_kind=str(
                communication.get("payload_kind")
                or metadata.get("payload_kind")
                or f"{observation.get('modality', 'sensor')}_observation"
            ),
            delivered=delivered,
            stale_after_s=_optional_float(
                communication.get("stale_after_s") or metadata.get("stale_after_s")
            ),
            metadata={
                "observation_id": observation.get("observation_id"),
                "sensor_id": observation.get("sensor_id"),
                "modality": observation.get("modality"),
                "quality_flags": observation.get("quality_flags", []),
            },
        )
    )


def _load_jsonl_objects(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            raw = json.loads(stripped)
            if not isinstance(raw, Mapping):
                raise ValueError(f"{path}:{line_number}: JSONL record must be an object")
            records.append(dict(raw))
    return records


def _vehicle_to_resource(frame: Mapping[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for resource in frame.get("resources", []) or []:
        metadata = resource.get("metadata", {}) or {}
        vehicle_name = metadata.get("airsim_vehicle_name")
        if vehicle_name:
            mapping[str(vehicle_name)] = str(resource.get("resource_id"))
    return mapping


def _frame_images(frame: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    metadata = frame.get("metadata", {}) or {}
    images = metadata.get("images")
    if isinstance(images, list):
        return [item for item in images if isinstance(item, Mapping)]
    image = metadata.get("image")
    if isinstance(image, Mapping):
        return [image]
    return [
        {
            "camera_vehicle_name": camera.get("owner_id"),
            "camera_name": str(camera.get("camera_id", "")).split(":", 1)[-1],
            "width": camera.get("width"),
            "height": camera.get("height"),
            "ok": True,
        }
        for camera in frame.get("cameras", []) or []
        if isinstance(camera, Mapping)
    ]


def _object_name(detection: Mapping[str, Any]) -> str | None:
    metadata = detection.get("metadata", {}) or {}
    value = metadata.get("airsim_detection_name") or detection.get("object_name")
    return None if value is None else str(value)


def _camera_intrinsics(camera: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if camera is None:
        return None
    return {
        "fx": camera.get("fx"),
        "fy": camera.get("fy"),
        "cx": camera.get("cx"),
        "cy": camera.get("cy"),
        "width": camera.get("width"),
        "height": camera.get("height"),
    }


def _camera_extrinsics(camera: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if camera is None:
        return None
    return {
        "position_ned": camera.get("position_ned"),
        "rotation_world_to_camera": camera.get("rotation_world_to_camera"),
    }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "pass", "passed", "ok"}:
        return True
    if text in {"false", "f", "no", "n", "0", "fail", "failed", "drop", "dropped"}:
        return False
    return default
