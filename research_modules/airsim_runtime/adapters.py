"""Adapters from captured Blocks frames into integrated module inputs."""

from __future__ import annotations

from typing import Any

import numpy as np

from airsim_dryrun.adapters import observations_from_airsim_frame
from airsim_dryrun.models import AirSimFrame
from d1_sensor_fusion.types import SensorObservation
from d5_terminal_association import LocalVisualTrack
from integrated_simulation.models import ResourcePlatform, TruthState


def observations_from_blocks_frame(
    frame: AirSimFrame,
    *,
    arrival_timestamp: float | None = None,
    include_acoustic: bool = True,
    include_eo: bool = True,
    include_lidar: bool = True,
) -> list[SensorObservation]:
    """Convert a captured Blocks frame to D1 observations.

    Radar/acoustic remain synthetic measurements derived from AirSim truth.
    EO/LiDAR observations are currently geometry-compatible observations with
    real Blocks capture status attached in metadata.
    """

    observations = observations_from_airsim_frame(
        frame,
        arrival_timestamp=arrival_timestamp,
        include_acoustic=include_acoustic,
        include_eo=include_eo,
        include_lidar=include_lidar,
    )
    for observation in observations:
        observation.observation_id = observation.observation_id.replace("dry_", "blocks_", 1)
        observation.sensor_id = observation.sensor_id.replace("DRY-", "BLOCKS-")
        observation.source_node_id = observation.source_node_id or "MAIN-C2"
        observation.target_node_id = observation.target_node_id or "D1-FUSION"
        observation.link_type = observation.link_type or "c2_replay"
        observation.sent_timestamp = observation.sent_timestamp or observation.measurement_timestamp
        observation.received_timestamp = observation.received_timestamp or observation.arrival_timestamp
        observation.payload_kind = observation.payload_kind or f"{observation.modality}_observation"
        observation.stale_after_s = observation.stale_after_s or 1.5
        observation.metadata["dry_run"] = False
        observation.metadata["real_airsim_used"] = True
        observation.metadata["runtime"] = "Blocks"
        observation.metadata["frame_metadata"] = _compact_frame_metadata(frame.metadata)
        observation.metadata.update(observation.communication_metadata)
    return observations


def truth_states_from_blocks_frame(frame: AirSimFrame) -> list[TruthState]:
    """Map captured target vehicles to integrated truth states."""

    truth_states: list[TruthState] = []
    for obj in frame.truth_objects:
        if obj.object_type != "target":
            continue
        truth_states.append(
            TruthState(
                truth_id=obj.object_id,
                timestamp=frame.timestamp,
                position=np.asarray(obj.position_ned, dtype=float),
                velocity=np.asarray(obj.velocity_ned, dtype=float),
                threat_score=obj.threat_score,
                coverage_cell=obj.coverage_cell,
            )
        )
    return truth_states


def resources_from_blocks_frame(frame: AirSimFrame) -> list[ResourcePlatform]:
    """Map captured resource vehicles to integrated resource states."""

    return [
        ResourcePlatform(
            resource_id=resource.resource_id,
            position=np.asarray(resource.position_ned, dtype=float),
            coverage_cell=resource.coverage_cell,
            health_score=resource.health_score,
            status=resource.status,
        )
        for resource in frame.resources
    ]


def truth_summary_from_blocks_frames(frames: list[AirSimFrame]) -> dict[str, Any]:
    timestamps_by_id: dict[str, list[float]] = {}
    high_threat_ids: list[str] = []
    for frame in frames:
        for obj in frame.truth_objects:
            timestamps_by_id.setdefault(obj.object_id, []).append(frame.timestamp)
            if obj.threat_score >= 0.7 and obj.object_id not in high_threat_ids:
                high_threat_ids.append(obj.object_id)
    timestamps = sorted({frame.timestamp for frame in frames})
    return {
        "truth_timestamps": timestamps_by_id,
        "total_truth_opportunities": sum(len(values) for values in timestamps_by_id.values()),
        "high_threat_ids": high_threat_ids,
        "high_threat_by_timestamp": {timestamp: high_threat_ids for timestamp in timestamps},
        "scenario": {
            "name": "blocks_readonly_smoke",
            "duration_s": max(timestamps) if timestamps else 0.0,
            "dt_s": _infer_dt(timestamps),
            "target_count": len(timestamps_by_id),
            "resource_count": len(frames[0].resources) if frames else 0,
            "offline_only": False,
            "real_airsim_used": True,
        },
    }


def local_visual_tracks_from_blocks_frame(
    frame: AirSimFrame,
    d2_tracks: list[Any],
    *,
    terminal_tracks: list[Any] | None = None,
    terminal_associator: Any | None = None,
    terminal_camera: Any | None = None,
    timestamp: float | None = None,
) -> tuple[list[LocalVisualTrack], dict[str, str]] | None:
    """Convert AirSim built-in detections into D5 local visual tracks.

    The returned map is local_track_id -> center-owned global_track_id. D5 still
    cannot create or rewrite global IDs; it only reports which local visual
    detection supports an already established D2 track.
    """

    if not frame.visual_detections:
        return None
    truth_to_global = {
        str(track.truth_id): str(track.global_track_id)
        for track in d2_tracks
        if getattr(track, "truth_id", None) is not None
    }
    projections = {}
    if terminal_tracks is not None and terminal_associator is not None and terminal_camera is not None:
        projections = terminal_associator.project_tracks_to_image(
            terminal_tracks,
            terminal_camera,
            timestamp=frame.timestamp if timestamp is None else float(timestamp),
        )
    local_tracks: list[LocalVisualTrack] = []
    local_truth_map: dict[str, str] = {}
    vehicle_to_resource = {
        str(resource.metadata.get("airsim_vehicle_name")): resource.resource_id
        for resource in frame.resources
        if resource.metadata.get("airsim_vehicle_name")
    }
    for detection in frame.visual_detections:
        global_track_id = truth_to_global.get(str(detection.object_id))
        if global_track_id is None:
            continue
        camera_owner = str(detection.camera_id).split(":", 1)[0]
        resource_id = vehicle_to_resource.get(camera_owner)
        local_track_id = (
            detection.local_track_id.replace(f"{camera_owner}:", f"{resource_id}:", 1)
            if resource_id is not None
            else detection.local_track_id
        )
        center_px = np.asarray(detection.center_px, dtype=float)
        bbox = detection.bbox_xyxy
        projection = projections.get(global_track_id)
        if projection is not None and projection.valid and projection.pixel is not None:
            raw_width = max(float(detection.bbox_xyxy[2] - detection.bbox_xyxy[0]), 2.0)
            raw_height = max(float(detection.bbox_xyxy[3] - detection.bbox_xyxy[1]), 2.0)
            center_px = np.asarray(projection.pixel, dtype=float)
            bbox = (
                float(center_px[0] - raw_width * 0.5),
                float(center_px[1] - raw_height * 0.5),
                float(center_px[0] + raw_width * 0.5),
                float(center_px[1] + raw_height * 0.5),
            )
        local_track = LocalVisualTrack(
            local_track_id=local_track_id,
            center_px=center_px,
            bbox=bbox,
            bearing_rate=np.zeros(2, dtype=float),
            category=detection.classification_hint,
            quality=float(detection.confidence),
            mot_history_length=int(detection.metadata.get("mot_history_length", 1)),
            timestamp=detection.timestamp,
        )
        local_tracks.append(local_track)
        local_truth_map[local_track.local_track_id] = global_track_id
    return local_tracks, local_truth_map


def nearest_frame(frames: list[AirSimFrame], timestamp: float) -> AirSimFrame:
    if not frames:
        raise ValueError("at least one Blocks frame is required")
    return min(frames, key=lambda frame: abs(frame.timestamp - timestamp))


def _compact_frame_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "image": metadata.get("image", {}),
        "lidar": metadata.get("lidar", {}),
        "vehicle_names": metadata.get("vehicle_names", []),
        "camera_vehicle_names": metadata.get("camera_vehicle_names", []),
        "resource_vehicle_names": metadata.get("resource_vehicle_names", []),
        "secondary_camera_vehicle_names": metadata.get("secondary_camera_vehicle_names", []),
        "scene_object_count": metadata.get("scene_object_count", 0),
    }


def _infer_dt(timestamps: list[float]) -> float:
    if len(timestamps) < 2:
        return 0.0
    return round(timestamps[1] - timestamps[0], 6)
