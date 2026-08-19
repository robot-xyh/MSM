"""Injectable AirSim detect adapter. This module never launches Blocks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..common.contracts import LocalVisualTrackRecord
from ..common.recognition import bbox_longest_side_px, is_recognizable_bbox
from .config import CameraCalibration
from .geometry import pixel_to_world_ray


@dataclass(frozen=True)
class CameraPoseNED:
    position_ned_m: tuple[float, float, float]
    yaw_pitch_roll_deg: tuple[float, float, float]


@dataclass(frozen=True)
class AnonymousDetection:
    bbox_xyxy: tuple[float, float, float, float]

    @property
    def center_px(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox_xyxy
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


@dataclass(frozen=True)
class AirSimOfflineDetectionLabel:
    """Offline-only name retained after the anonymous online record is built."""

    camera_id: str
    local_track_id: str
    measurement_timestamp: float
    raw_object_name: str
    resolved_truth_target_id: str | None
    resolution_method: str
    offline_truth_only: bool = True


@dataclass(frozen=True)
class AirSimDetectionBatch:
    local_tracks: tuple[LocalVisualTrackRecord, ...]
    offline_labels: tuple[AirSimOfflineDetectionLabel, ...]


class DetectionNameResolver:
    """Resolve exact, aliased, or AirSim-suffixed Actor names offline."""

    def __init__(
        self,
        actor_name_to_truth_target: Mapping[str, str] | None = None,
        actor_name_aliases: Mapping[str, str] | None = None,
    ) -> None:
        self.actor_name_to_truth_target = {
            str(key): str(value)
            for key, value in (actor_name_to_truth_target or {}).items()
            if str(key) and str(value)
        }
        self.actor_name_aliases = {
            str(key): str(value)
            for key, value in (actor_name_aliases or {}).items()
            if str(key) and str(value)
        }

    @staticmethod
    def _longest_match(value: str, candidates: Sequence[str]) -> str | None:
        matches = [candidate for candidate in candidates if value.startswith(candidate)]
        return max(matches, key=len) if matches else None

    def resolve(self, raw_object_name: str) -> tuple[str | None, str]:
        raw_name = str(raw_object_name)
        if raw_name in self.actor_name_aliases:
            canonical = self.actor_name_aliases[raw_name]
            return self.actor_name_to_truth_target.get(canonical), "explicit_alias"
        alias_prefix = self._longest_match(raw_name, tuple(self.actor_name_aliases))
        if alias_prefix is not None:
            canonical = self.actor_name_aliases[alias_prefix]
            return self.actor_name_to_truth_target.get(canonical), "alias_prefix"
        if raw_name in self.actor_name_to_truth_target:
            return self.actor_name_to_truth_target[raw_name], "exact_actor_name"
        actor_prefix = self._longest_match(
            raw_name, tuple(self.actor_name_to_truth_target)
        )
        if actor_prefix is not None:
            return self.actor_name_to_truth_target[actor_prefix], "actor_name_prefix"
        return None, "unresolved"


@dataclass
class _TrackState:
    local_track_id: str
    center_px: tuple[float, float]
    bbox_xyxy: tuple[float, float, float, float]
    last_timestamp: float
    hits: int = 1
    misses: int = 0


def _coordinate(value: Any, name: str) -> float:
    if hasattr(value, f"{name}_val"):
        return float(getattr(value, f"{name}_val"))
    return float(getattr(value, name))


def anonymous_detections_from_airsim(raw_detections: Sequence[Any]) -> tuple[AnonymousDetection, ...]:
    """Strip AirSim object names before local tracking or online publication."""

    values: list[AnonymousDetection] = []
    for detection in raw_detections:
        box = detection.box2D
        bbox = (
            _coordinate(box.min, "x"),
            _coordinate(box.min, "y"),
            _coordinate(box.max, "x"),
            _coordinate(box.max, "y"),
        )
        if bbox[2] < bbox[0] or bbox[3] < bbox[1]:
            continue
        values.append(AnonymousDetection(bbox))
    return tuple(values)


class LocalCentroidTracker:
    """Small camera-local tracker used only to create anonymous tracklets."""

    def __init__(self, *, maximum_distance_px: float = 90.0, maximum_misses: int = 3) -> None:
        if maximum_distance_px <= 0.0 or maximum_misses < 0:
            raise ValueError("tracker thresholds are invalid")
        self.maximum_distance_px = float(maximum_distance_px)
        self.maximum_misses = int(maximum_misses)
        self._states: dict[str, dict[str, _TrackState]] = {}
        self._next_sequence: dict[str, int] = {}

    def update(
        self,
        camera_id: str,
        detections: Sequence[AnonymousDetection],
        timestamp: float,
    ) -> tuple[_TrackState, ...]:
        return tuple(
            state
            for state, _ in self.update_with_assignments(
                camera_id, detections, timestamp
            )
        )

    def update_with_assignments(
        self,
        camera_id: str,
        detections: Sequence[AnonymousDetection],
        timestamp: float,
    ) -> tuple[tuple[_TrackState, int], ...]:
        states = self._states.setdefault(camera_id, {})
        self._next_sequence.setdefault(camera_id, 1)
        track_ids = sorted(states)
        centers = np.asarray([item.center_px for item in detections], dtype=float).reshape((-1, 2))
        matched_tracks: set[str] = set()
        matched_detections: set[int] = set()
        assignments: dict[int, _TrackState] = {}
        if track_ids and len(detections):
            previous = np.asarray([states[value].center_px for value in track_ids], dtype=float)
            distances = np.linalg.norm(previous[:, None, :] - centers[None, :, :], axis=2)
            rows, columns = linear_sum_assignment(distances)
            for row, column in zip(rows, columns):
                if distances[row, column] > self.maximum_distance_px:
                    continue
                track_id = track_ids[int(row)]
                detection = detections[int(column)]
                state = states[track_id]
                state.center_px = detection.center_px
                state.bbox_xyxy = detection.bbox_xyxy
                state.last_timestamp = float(timestamp)
                state.hits += 1
                state.misses = 0
                matched_tracks.add(track_id)
                matched_detections.add(int(column))
                assignments[int(column)] = state
        for track_id in track_ids:
            if track_id not in matched_tracks:
                states[track_id].misses += 1
        for track_id in [
            value for value, state in states.items() if state.misses > self.maximum_misses
        ]:
            states.pop(track_id)
        for index, detection in enumerate(detections):
            if index in matched_detections:
                continue
            sequence = self._next_sequence[camera_id]
            self._next_sequence[camera_id] += 1
            local_id = f"L{sequence:05d}"
            states[local_id] = _TrackState(
                local_track_id=local_id,
                center_px=detection.center_px,
                bbox_xyxy=detection.bbox_xyxy,
                last_timestamp=float(timestamp),
            )
            assignments[index] = states[local_id]
        return tuple(
            sorted(
                ((state, detection_index) for detection_index, state in assignments.items()),
                key=lambda item: item[0].local_track_id,
            )
        )


class AirSimDetectCollector:
    """Collect ``simGetDetections`` metadata from a main-owned AirSim client."""

    def __init__(
        self,
        client: Any,
        calibrations: Mapping[str, CameraCalibration],
        *,
        image_type: Any,
        camera_name: str = "0",
        tracker: LocalCentroidTracker | None = None,
        name_resolver: DetectionNameResolver | None = None,
    ) -> None:
        self.client = client
        self.calibrations = dict(calibrations)
        self.image_type = image_type
        self.camera_name = camera_name
        self.tracker = tracker or LocalCentroidTracker()
        self.name_resolver = name_resolver or DetectionNameResolver()

    def configure_detection_filter(
        self,
        camera_id: str,
        *,
        radius_cm: float,
        mesh_names: Sequence[str],
    ) -> None:
        self.client.simSetDetectionFilterRadius(
            self.camera_name,
            self.image_type,
            float(radius_cm),
            vehicle_name=camera_id,
        )
        self.client.simClearDetectionMeshNames(
            self.camera_name,
            self.image_type,
            vehicle_name=camera_id,
        )
        for mesh_name in mesh_names:
            self.client.simAddDetectionFilterMeshName(
                self.camera_name,
                self.image_type,
                str(mesh_name),
                vehicle_name=camera_id,
            )

    def collect(
        self,
        camera_id: str,
        *,
        measurement_timestamp: float,
        pose: CameraPoseNED,
        arrival_timestamp: float | None = None,
    ) -> tuple[LocalVisualTrackRecord, ...]:
        return self.collect_with_offline_labels(
            camera_id,
            measurement_timestamp=measurement_timestamp,
            pose=pose,
            arrival_timestamp=arrival_timestamp,
        ).local_tracks

    def collect_with_offline_labels(
        self,
        camera_id: str,
        *,
        measurement_timestamp: float,
        pose: CameraPoseNED,
        arrival_timestamp: float | None = None,
    ) -> AirSimDetectionBatch:
        if camera_id not in self.calibrations:
            raise ValueError(f"missing calibration for {camera_id}")
        raw = self.client.simGetDetections(
            self.camera_name,
            self.image_type,
            vehicle_name=camera_id,
        )
        raw_rows = tuple(raw or ())
        valid_rows: list[tuple[AnonymousDetection, str]] = []
        for raw_detection in raw_rows:
            anonymous = anonymous_detections_from_airsim((raw_detection,))
            if anonymous:
                valid_rows.append(
                    (anonymous[0], str(getattr(raw_detection, "name", "")))
                )
        detections = tuple(item[0] for item in valid_rows)
        assignments = self.tracker.update_with_assignments(
            camera_id, detections, measurement_timestamp
        )
        calibration = self.calibrations[camera_id]
        arrival = float(
            arrival_timestamp
            if arrival_timestamp is not None
            else measurement_timestamp
        )
        if arrival < measurement_timestamp:
            arrival = float(measurement_timestamp)
        records: list[LocalVisualTrackRecord] = []
        labels: list[AirSimOfflineDetectionLabel] = []
        for state, detection_index in assignments:
            ray = pixel_to_world_ray(
                state.center_px, calibration, pose.yaw_pitch_roll_deg
            )
            extent = bbox_longest_side_px(state.bbox_xyxy)
            records.append(
                LocalVisualTrackRecord(
                    camera_id=camera_id,
                    local_track_id=state.local_track_id,
                    measurement_timestamp=float(measurement_timestamp),
                    arrival_timestamp=arrival,
                    bbox_xyxy=state.bbox_xyxy,
                    center_px=state.center_px,
                    ray_origin_ned_m=pose.position_ned_m,
                    ray_direction_ned=tuple(float(value) for value in ray),
                    camera_yaw_pitch_roll_deg=pose.yaw_pitch_roll_deg,
                    recognized=is_recognizable_bbox(state.bbox_xyxy),
                    recognition_extent_px=extent,
                    track_quality=min(1.0, state.hits / 3.0),
                    metadata={"source_kind": "airsim_detect_anonymous"},
                )
            )
            raw_name = valid_rows[detection_index][1]
            truth_target_id, resolution_method = self.name_resolver.resolve(raw_name)
            labels.append(
                AirSimOfflineDetectionLabel(
                    camera_id=camera_id,
                    local_track_id=state.local_track_id,
                    measurement_timestamp=float(measurement_timestamp),
                    raw_object_name=raw_name,
                    resolved_truth_target_id=truth_target_id,
                    resolution_method=resolution_method,
                )
            )
        return AirSimDetectionBatch(tuple(records), tuple(labels))


__all__ = [
    "AirSimDetectCollector",
    "AirSimDetectionBatch",
    "AirSimOfflineDetectionLabel",
    "AnonymousDetection",
    "CameraPoseNED",
    "DetectionNameResolver",
    "LocalCentroidTracker",
    "anonymous_detections_from_airsim",
]
