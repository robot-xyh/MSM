"""Offline bbox/LOS replay adapters for D7 visual PNG gates.

The replay path converts detector outputs such as YOLO/ByteTrack tracks or
AirSim detection metadata into D7 ``VisionGuidanceObservation`` samples.  It is
for offline gate analysis only and never sends SimpleFlight or AirSim commands.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .runtime_bus import (
    D7RuntimeBus,
    D7RuntimePairInput,
    D7RuntimePairOutput,
    coerce_vision_guidance_observation,
    summarize_runtime_bus_outputs,
)
from .terminal_gate import AssignmentGuidanceBinding, D4GuidancePermission
from .vision_png import PngGuidanceConfig, VisionGuidanceObservation


BBOX_LOS_REPLAY_BOUNDARY = "offline_bbox_los_replay_only_no_vehicle_control"


def vision_observations_from_bbox_replay(
    detections: Iterable[Mapping[str, Any] | Any],
    *,
    source: str = "yolo_replay",
    assigned_global_track_id: str | None = None,
    camera_id: str | None = None,
) -> list[VisionGuidanceObservation]:
    """Convert bbox replay rows into D7 visual guidance observations."""

    observations: list[VisionGuidanceObservation] = []
    for frame_index, detection in enumerate(detections):
        observations.append(
            bbox_replay_detection_to_observation(
                detection,
                source=source,
                assigned_global_track_id=assigned_global_track_id,
                camera_id=camera_id,
                frame_index=frame_index,
            )
        )
    return observations


def bbox_replay_detection_to_observation(
    detection: Mapping[str, Any] | Any,
    *,
    source: str = "yolo_replay",
    assigned_global_track_id: str | None = None,
    camera_id: str | None = None,
    frame_index: int | None = None,
) -> VisionGuidanceObservation:
    """Normalize one bbox replay detection into a D7 observation."""

    metadata = dict(_value(detection, ("metadata",), default={}) or {})
    metadata.update(
        {
            "replay": True,
            "source": source,
            "boundary": BBOX_LOS_REPLAY_BOUNDARY,
        }
    )
    if frame_index is not None:
        metadata["frame_index"] = frame_index
    for name in _REPLAY_METADATA_FIELD_NAMES:
        value = _value(detection, (name,), default=None)
        if value is not None:
            metadata.setdefault(name, value)

    record = {
        "timestamp_s": _required_float(detection, ("timestamp_s", "timestamp", "t")),
        "frame_timestamp_s": _optional_float_value(
            detection,
            ("frame_timestamp_s", "frame_time_s"),
        ),
        "bbox_xyxy": _bbox_xyxy(detection),
        "detection_confidence": _float_value(
            detection,
            ("detection_confidence", "confidence", "score"),
            default=1.0,
        ),
        "local_track_id": _optional_string_value(
            detection,
            ("local_track_id", "track_id", "bytetrack_id", "detection_track_id"),
        ),
        "assigned_global_track_id": _optional_string_value(
            detection,
            ("assigned_global_track_id", "global_track_id", "target_id"),
        )
        or assigned_global_track_id,
        "camera_id": _optional_string_value(detection, ("camera_id", "camera_name"))
        or camera_id,
        "metadata": metadata,
    }
    latency_s = _optional_float_value(detection, ("visual_latency_s", "measurement_age_s"))
    if latency_s is not None:
        record["metadata"]["visual_latency_s"] = latency_s
    return coerce_vision_guidance_observation(record)


_REPLAY_METADATA_FIELD_NAMES = (
    "detect_registration_outcome",
    "detect_registration_reject_reasons",
    "measurement_age_s",
    "projection_valid",
    "projection_reason",
    "projection_depth_m",
    "reprojection_error_px",
    "pixel_error_px",
    "reprojection_error",
    "mahalanobis_d2",
    "gate_pass",
    "covariance_px",
    "projection_covariance_px",
    "camera_pose_source",
    "calibration_health",
    "drift_warning",
    "tracker_backend",
    "requested_tracker_backend",
    "tracker_id_scope",
    "mot_history_length",
    "class_id",
    "class_name",
    "bbox_area_px",
    "association_probability",
)


def evaluate_bbox_los_replay(
    detections: Iterable[Mapping[str, Any] | Any],
    *,
    binding: AssignmentGuidanceBinding | Mapping[str, Any] | Any,
    d4_permission: D4GuidancePermission | Mapping[str, Any] | Any | None = None,
    terminal_association: Mapping[str, Any] | Any | None = None,
    config: PngGuidanceConfig | None = None,
    source: str = "yolo_replay",
    assigned_global_track_id: str | None = None,
    camera_id: str | None = None,
    current_heading_rad: float = 0.0,
    current_speed_mps: float = 0.0,
    intercept_speed_mps: float = 0.0,
    relative_position_ned: tuple[float, float, float] | None = None,
    relative_velocity_ned: tuple[float, float, float] | None = None,
    command_z_ned_m: float = 0.0,
) -> tuple[list[D7RuntimePairOutput], dict[str, Any]]:
    """Run an offline bbox replay through D7 contract and LOS/PNG gates."""

    observations = vision_observations_from_bbox_replay(
        detections,
        source=source,
        assigned_global_track_id=assigned_global_track_id,
        camera_id=camera_id,
    )
    bus = D7RuntimeBus(config)
    outputs = bus.inject_state(
        D7RuntimePairInput(
            binding=binding,
            d4_permission=d4_permission,
            terminal_association=terminal_association,
            observation=observation,
            timestamp_s=observation.timestamp_s,
            handover_pending=True,
            terminal_locked=True,
            current_heading_rad=current_heading_rad,
            current_speed_mps=current_speed_mps,
            intercept_speed_mps=intercept_speed_mps,
            relative_position_ned=relative_position_ned,
            relative_velocity_ned=relative_velocity_ned,
            command_z_ned_m=command_z_ned_m,
            metadata={"replay_source": source},
        )
        for observation in observations
    )
    summary = summarize_runtime_bus_outputs(outputs)
    summary.update(
        {
            "boundary": BBOX_LOS_REPLAY_BOUNDARY,
            "replay_source": source,
            "observation_count": len(observations),
            "vehicle_control": False,
            "simpleflight_control_called": False,
        }
    )
    return outputs, summary


def _bbox_xyxy(value: Any) -> tuple[float, float, float, float]:
    bbox = _value(value, ("bbox_xyxy", "xyxy", "bbox"), default=None)
    if bbox is not None:
        return _tuple4(bbox, "bbox_xyxy")
    xywh = _value(value, ("bbox_xywh", "xywh"), default=None)
    if xywh is None:
        raise ValueError("bbox replay detection requires bbox_xyxy/xyxy/bbox or bbox_xywh/xywh")
    x, y, width, height = _tuple4(xywh, "bbox_xywh")
    return (x, y, x + width, y + height)


def _tuple4(value: Any, name: str) -> tuple[float, float, float, float]:
    try:
        items = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a sequence") from exc
    if len(items) != 4:
        raise ValueError(f"{name} must contain exactly four values")
    return (float(items[0]), float(items[1]), float(items[2]), float(items[3]))


def _required_float(value: Any, names: tuple[str, ...]) -> float:
    raw = _value(value, names, default=None)
    if raw is None:
        raise ValueError(f"{names[0]} is required")
    return float(raw)


def _float_value(value: Any, names: tuple[str, ...], *, default: float) -> float:
    return float(_value(value, names, default=default))


def _optional_float_value(value: Any, names: tuple[str, ...]) -> float | None:
    raw = _value(value, names, default=None)
    if raw is None:
        return None
    return float(raw)


def _optional_string_value(value: Any, names: tuple[str, ...]) -> str | None:
    raw = _value(value, names, default=None)
    if raw is None:
        return None
    if hasattr(raw, "value"):
        raw = raw.value
    text = str(raw)
    return text if text else None


def _value(record: Any, names: tuple[str, ...], *, default: Any) -> Any:
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if not isinstance(record, Mapping) and hasattr(record, name):
            return getattr(record, name)
    return default
