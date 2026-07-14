"""Adapters from captured Blocks frames into integrated module inputs."""

from __future__ import annotations

from typing import Any

import numpy as np

from airsim_dryrun.adapters import observations_from_airsim_frame
from airsim_dryrun.models import AirSimFrame
from d1_sensor_fusion.types import SensorObservation
from d3_assignment_planner import TargetTrack
from d5_terminal_association import GlobalTrack as TerminalGlobalTrack
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


def target_tracks_from_online_d2(
    tracks: list[Any],
    resources: list[ResourcePlatform],
    *,
    default_threat_score: float = 0.75,
) -> list[TargetTrack]:
    """Build D3 inputs without AirSim actor or truth identity.

    D2's center-owned ``global_track_id`` is the only identity carried into
    planning. Threat is a configurable runtime prior until a classified sensor
    product is available; coverage is inferred from online geometry.
    """

    output: list[TargetTrack] = []
    for track in tracks:
        position = np.asarray(track.state[:2], dtype=float)
        lifecycle = getattr(getattr(track, "lifecycle_state", None), "value", None)
        assignable = lifecycle not in {"lost", "dropped"}
        covariance_norm = min(float(np.trace(track.covariance[:2, :2])) / 120.0, 1.0)
        coverage_cell = _nearest_resource_coverage_cell(position, resources)
        fov_difficulty: dict[str, float] = {}
        conflict_risk: dict[str, float] = {}
        feasibility: dict[str, bool] = {}
        for resource in resources:
            distance = float(np.linalg.norm(resource.position[:2] - position))
            coverage_penalty = (
                0.25 if coverage_cell and resource.coverage_cell != coverage_cell else 0.0
            )
            fov_difficulty[resource.resource_id] = min(distance / 360.0 + coverage_penalty, 1.0)
            conflict_risk[resource.resource_id] = 0.10 if coverage_penalty else 0.02
            feasibility[resource.resource_id] = resource.status == "available"
        output.append(
            TargetTrack(
                track_id=str(track.global_track_id),
                threat_score=float(np.clip(default_threat_score, 0.0, 1.0)),
                covariance=covariance_norm,
                window_cost=min(float(np.linalg.norm(position)) / 1000.0, 1.0),
                assignable=assignable,
                fov_difficulty_by_resource=fov_difficulty,
                conflict_risk_by_resource=conflict_risk,
                feasibility_by_resource=feasibility,
                metadata={
                    "coverage_cell": coverage_cell,
                    "position": position.tolist(),
                    "identity_source": "d2_center_owned_global_track_id",
                    "threat_source": "runtime_default_prior",
                    "online_truth_id_used": False,
                },
            )
        )
    return output


def terminal_tracks_from_online_d2(
    tracks: list[Any],
    *,
    plan_version: int,
    timestamp: float,
    source_kinematics: dict[str, dict[str, Any]] | None = None,
    default_z_ned_m: float = -5.0,
    default_z_variance_m2: float = 25.0,
) -> list[TerminalGlobalTrack]:
    """Build D5 projection tracks from D2 and cached D1 kinematics only."""

    kinematics_by_track = source_kinematics or {}
    output: list[TerminalGlobalTrack] = []
    for track in tracks:
        source = kinematics_by_track.get(str(track.global_track_id), {})
        source_position = np.asarray(source.get("position_3d", (0.0, 0.0, default_z_ned_m)), dtype=float)
        source_velocity = np.asarray(source.get("velocity_3d", (0.0, 0.0, 0.0)), dtype=float)
        z = float(source_position[2]) if source_position.size >= 3 else float(default_z_ned_m)
        vz = float(source_velocity[2]) if source_velocity.size >= 3 else 0.0
        covariance_3d = np.diag(
            [
                max(float(track.covariance[0, 0]), 0.5),
                max(float(track.covariance[1, 1]), 0.5),
                max(float(source.get("z_variance_m2", default_z_variance_m2)), 0.5),
            ]
        )
        output.append(
            TerminalGlobalTrack(
                global_track_id=str(track.global_track_id),
                position=np.array([track.state[0], track.state[1], z], dtype=float),
                covariance=covariance_3d,
                velocity=np.array([track.state[2], track.state[3], vz], dtype=float),
                category="uav",
                timestamp=float(timestamp),
                track_version=int(plan_version),
            )
        )
    return output


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
    use_projected_detection_centers: bool = False,
) -> tuple[list[LocalVisualTrack], dict[str, str]] | None:
    """Convert AirSim built-in detections into D5 local visual tracks.

    The returned map is local_track_id -> center-owned global_track_id for
    offline evaluation only. D5 online association must use the returned bbox
    center, not AirSim object IDs. Projection-based center replacement is a
    legacy synthetic convenience and is disabled unless explicitly requested.
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
        if (
            use_projected_detection_centers
            and projection is not None
            and projection.valid
            and projection.pixel is not None
        ):
            raw_width = max(float(detection.bbox_xyxy[2] - detection.bbox_xyxy[0]), 2.0)
            raw_height = max(float(detection.bbox_xyxy[3] - detection.bbox_xyxy[1]), 2.0)
            center_px = np.asarray(projection.pixel, dtype=float)
            bbox = (
                float(center_px[0] - raw_width * 0.5),
                float(center_px[1] - raw_height * 0.5),
                float(center_px[0] + raw_width * 0.5),
                float(center_px[1] + raw_height * 0.5),
            )
        metadata = dict(detection.metadata)
        metadata["projection_center_override_enabled"] = bool(use_projected_detection_centers)
        if projection is not None and projection.valid and projection.pixel is not None:
            metadata["projected_px"] = [float(projection.pixel[0]), float(projection.pixel[1])]
        local_track = LocalVisualTrack(
            local_track_id=local_track_id,
            center_px=center_px,
            bbox=bbox,
            bearing_rate=np.zeros(2, dtype=float),
            category=detection.classification_hint,
            quality=float(detection.confidence),
            mot_history_length=int(metadata.get("mot_history_length", 1)),
            timestamp=detection.timestamp,
        )
        local_tracks.append(local_track)
        local_truth_map[local_track.local_track_id] = global_track_id
    return local_tracks, local_truth_map


def geometric_local_visual_tracks_from_blocks_frame(frame: AirSimFrame) -> list[LocalVisualTrack]:
    """Convert AirSim detections for real geometric D5 online association.

    This path intentionally does not read `object_id`, `actor_name`, truth
    labels, or D2 track truth mappings. It preserves detector-local identity and
    computes the measurement center from `bbox_xyxy`.
    """

    camera_sizes = {
        str(camera.camera_id): (int(camera.width), int(camera.height))
        for camera in frame.cameras
    }
    arrival_timestamp = float(
        frame.metadata.get("arrival_timestamp", frame.timestamp)
    )
    local_tracks: list[LocalVisualTrack] = []
    for index, detection in enumerate(frame.visual_detections):
        x1, y1, x2, y2 = (float(value) for value in detection.bbox_xyxy)
        local_track_id = str(detection.local_track_id or detection.detection_id or f"{detection.camera_id}:{index}")
        metadata = dict(detection.metadata)
        raw_image_size = metadata.get("image_size") or camera_sizes.get(
            str(detection.camera_id)
        )
        image_size = (
            None
            if raw_image_size is None
            else (int(raw_image_size[0]), int(raw_image_size[1]))
        )
        measurement_timestamp = float(
            metadata.get("measurement_timestamp", detection.timestamp)
        )
        local_tracks.append(
            LocalVisualTrack(
                local_track_id=local_track_id,
                center_px=np.array([(x1 + x2) * 0.5, (y1 + y2) * 0.5], dtype=float),
                bbox=(x1, y1, x2, y2),
                bearing_rate=np.zeros(2, dtype=float),
                category=detection.classification_hint,
                quality=float(detection.confidence),
                mot_history_length=int(metadata.get("mot_history_length", 1)),
                timestamp=measurement_timestamp,
                arrival_timestamp=float(
                    metadata.get("arrival_timestamp", arrival_timestamp)
                ),
                exposure_timestamp=float(
                    metadata.get("exposure_timestamp", measurement_timestamp)
                ),
                detection_source=str(
                    metadata.get("source", "airsim_runtime_detection")
                ),
                track_transition_state=str(
                    metadata.get("track_transition_state", "unknown")
                ),
                track_reset_reason=metadata.get("track_reset_reason"),
                image_size=image_size,
                metadata={
                    "camera_id": str(detection.camera_id),
                    "resource_id": _resource_id_for_detection(frame, detection.camera_id),
                    "raw_classification_hint": str(detection.classification_hint),
                    "image_size": image_size,
                },
            )
        )
    return local_tracks


def _resource_id_for_detection(frame: AirSimFrame, camera_id: str) -> str | None:
    camera = next(
        (item for item in frame.cameras if str(item.camera_id) == str(camera_id)),
        None,
    )
    if camera is None:
        return None
    resource = next(
        (
            item
            for item in frame.resources
            if str(item.metadata.get("airsim_vehicle_name", "")) == str(camera.owner_id)
        ),
        None,
    )
    return None if resource is None else str(resource.resource_id)


def offline_truth_map_from_blocks_frame(
    frame: AirSimFrame,
    d2_tracks: list[Any],
) -> dict[str, str]:
    """Build local_track_id -> global_track_id labels for offline evaluation.

    This function uses AirSim truth IDs and must not feed online association.
    """

    truth_to_global = offline_truth_to_global_track_map(frame, d2_tracks)
    truth_map: dict[str, str] = {}
    for detection in frame.visual_detections:
        global_track_id = truth_to_global.get(str(detection.object_id))
        if global_track_id is not None:
            truth_map[str(detection.local_track_id)] = global_track_id
    return truth_map


def offline_truth_to_global_track_map(
    frame: AirSimFrame,
    d2_tracks: list[Any],
) -> dict[str, str]:
    """Associate AirSim truth objects to D2 tracks for offline scoring only."""

    explicit = {
        str(track.truth_id): str(track.global_track_id)
        for track in d2_tracks
        if getattr(track, "truth_id", None) is not None
    }
    if explicit:
        return explicit
    targets = [obj for obj in frame.truth_objects if obj.object_type == "target"]
    if not targets or not d2_tracks:
        return {}
    candidates: list[tuple[float, int, int]] = []
    for track_index, track in enumerate(d2_tracks):
        track_position = np.asarray(track.state[:2], dtype=float)
        for target_index, target in enumerate(targets):
            truth_position = np.asarray(target.position_ned[:2], dtype=float)
            candidates.append(
                (float(np.linalg.norm(track_position - truth_position)), track_index, target_index)
            )
    mapping: dict[str, str] = {}
    used_tracks: set[int] = set()
    used_targets: set[int] = set()
    for _, track_index, target_index in sorted(candidates):
        if track_index in used_tracks or target_index in used_targets:
            continue
        used_tracks.add(track_index)
        used_targets.add(target_index)
        mapping[str(targets[target_index].object_id)] = str(
            d2_tracks[track_index].global_track_id
        )
    return mapping


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


def _nearest_resource_coverage_cell(
    position_xy: np.ndarray,
    resources: list[ResourcePlatform],
) -> str:
    if not resources:
        return "unassigned"
    nearest = min(
        resources,
        key=lambda resource: float(np.linalg.norm(resource.position[:2] - position_xy)),
    )
    return str(nearest.coverage_cell or "unassigned")
