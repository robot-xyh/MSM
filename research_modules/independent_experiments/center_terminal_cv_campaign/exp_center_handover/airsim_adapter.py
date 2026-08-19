"""Injectable AirSim detect/camera-info adapter; it never launches Blocks."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..common import LocalVisualTrackRecord
from ..common.recognition import bbox_longest_side_px, is_recognizable_bbox
from .geometry import CameraModel


@dataclass(frozen=True)
class AirSimOfflineDetectionLabel:
    camera_id: str
    local_track_id: str
    measurement_timestamp: float
    raw_detection_name: str


@dataclass(frozen=True)
class AirSimCollectedFrame:
    local_tracks: tuple[LocalVisualTrackRecord, ...]
    camera_models: Mapping[str, CameraModel]
    offline_labels: tuple[AirSimOfflineDetectionLabel, ...]


class AirSimDetectionAdapter:
    """Read only simGetCameraInfo and simGetDetections from an injected client."""

    def __init__(
        self,
        camera_models: Mapping[str, CameraModel],
        *,
        camera_name: str = "0",
        image_type: int = 0,
        recognition_extent_px: float = 10.0,
        maximum_track_step_px: float = 160.0,
    ) -> None:
        self.camera_models = dict(camera_models)
        self.camera_name = str(camera_name)
        self.image_type = int(image_type)
        self.recognition_extent_px = float(recognition_extent_px)
        self.maximum_track_step_px = float(maximum_track_step_px)
        self._previous_centers: dict[str, dict[str, np.ndarray]] = {}
        self._next_track_number: dict[str, int] = {}

    def collect_frame(
        self,
        client: Any,
        *,
        measurement_timestamp: float,
        arrival_timestamp: float,
        camera_ids: Sequence[str] | None = None,
    ) -> AirSimCollectedFrame:
        records: list[LocalVisualTrackRecord] = []
        offline_labels: list[AirSimOfflineDetectionLabel] = []
        observed_models: dict[str, CameraModel] = {}
        for camera_id in camera_ids or tuple(self.camera_models):
            base = self.camera_models[camera_id]
            info = client.simGetCameraInfo(self.camera_name, vehicle_name=camera_id)
            observed = _camera_model_from_info(base, info)
            observed_models[camera_id] = observed
            detections = tuple(
                client.simGetDetections(
                    self.camera_name,
                    self.image_type,
                    vehicle_name=camera_id,
                )
                or ()
            )
            bboxes = tuple(_bbox_from_detection(detection) for detection in detections)
            centers = tuple(
                np.asarray(((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0), dtype=float)
                for bbox in bboxes
            )
            track_ids = self._assign_anonymous_track_ids(camera_id, centers)
            for detection, bbox, center, local_track_id in zip(
                detections, bboxes, centers, track_ids, strict=True
            ):
                extent = bbox_longest_side_px(bbox)
                ray = observed.pixel_to_world_ray(tuple(float(value) for value in center))
                records.append(
                    LocalVisualTrackRecord(
                        camera_id=camera_id,
                        local_track_id=local_track_id,
                        measurement_timestamp=float(measurement_timestamp),
                        arrival_timestamp=float(arrival_timestamp),
                        bbox_xyxy=bbox,
                        center_px=tuple(float(value) for value in center),
                        ray_origin_ned_m=tuple(
                            float(value) for value in observed.camera_position_ned_m
                        ),
                        ray_direction_ned=tuple(float(value) for value in ray),
                        camera_yaw_pitch_roll_deg=observed.body_yaw_pitch_roll_deg,
                        recognized=is_recognizable_bbox(
                            bbox, minimum_extent_px=self.recognition_extent_px
                        ),
                        recognition_extent_px=extent,
                        track_quality=1.0,
                        metadata={
                            "detection_source": "simGetDetections",
                            "center_covariance_px2": ((2.25, 0.0), (0.0, 2.25)),
                        },
                    )
                )
                offline_labels.append(
                    AirSimOfflineDetectionLabel(
                        camera_id=camera_id,
                        local_track_id=local_track_id,
                        measurement_timestamp=float(measurement_timestamp),
                        raw_detection_name=str(getattr(detection, "name", "")),
                    )
                )
        return AirSimCollectedFrame(
            local_tracks=tuple(records),
            camera_models=observed_models,
            offline_labels=tuple(offline_labels),
        )

    def _assign_anonymous_track_ids(
        self, camera_id: str, centers: Sequence[np.ndarray]
    ) -> tuple[str, ...]:
        previous = self._previous_centers.get(camera_id, {})
        previous_ids = tuple(sorted(previous))
        assigned: list[str | None] = [None] * len(centers)
        if previous_ids and centers:
            costs = np.asarray(
                [
                    [float(np.linalg.norm(previous[track_id] - center)) for center in centers]
                    for track_id in previous_ids
                ],
                dtype=float,
            )
            rows, columns = linear_sum_assignment(costs)
            for row, column in zip(rows, columns, strict=True):
                if costs[row, column] <= self.maximum_track_step_px:
                    assigned[int(column)] = previous_ids[int(row)]
        next_number = self._next_track_number.get(camera_id, 1)
        for index, value in enumerate(assigned):
            if value is None:
                assigned[index] = f"LCL-{camera_id}-{next_number:04d}"
                next_number += 1
        self._next_track_number[camera_id] = next_number
        self._previous_centers[camera_id] = {
            str(track_id): np.asarray(center, dtype=float)
            for track_id, center in zip(assigned, centers, strict=True)
        }
        return tuple(str(value) for value in assigned)


def _bbox_from_detection(detection: Any) -> tuple[float, float, float, float]:
    box = detection.box2D
    return (
        float(box.min.x_val),
        float(box.min.y_val),
        float(box.max.x_val),
        float(box.max.y_val),
    )


def _camera_model_from_info(base: CameraModel, info: Any) -> CameraModel:
    pose = info.pose
    position = pose.position
    yaw_pitch_roll = _quaternion_to_yaw_pitch_roll(pose.orientation)
    fov = float(getattr(info, "fov", base.intrinsics.horizontal_fov_deg))
    intrinsics = type(base.intrinsics)(
        width_px=base.intrinsics.width_px,
        height_px=base.intrinsics.height_px,
        horizontal_fov_deg=fov,
    )
    return CameraModel(
        camera_id=base.camera_id,
        intrinsics=intrinsics,
        body_position_ned_m=(
            float(position.x_val),
            float(position.y_val),
            float(position.z_val),
        ),
        body_yaw_pitch_roll_deg=yaw_pitch_roll,
        gimbal_yaw_pitch_roll_deg=(0.0, 0.0, 0.0),
        camera_offset_body_m=(0.0, 0.0, 0.0),
    )


def _quaternion_to_yaw_pitch_roll(quaternion: Any) -> tuple[float, float, float]:
    x = float(quaternion.x_val)
    y = float(quaternion.y_val)
    z = float(quaternion.z_val)
    w = float(quaternion.w_val)
    sin_roll_cos_pitch = 2.0 * (w * x + y * z)
    cos_roll_cos_pitch = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sin_roll_cos_pitch, cos_roll_cos_pitch)
    sin_pitch = 2.0 * (w * y - z * x)
    pitch = math.copysign(math.pi / 2.0, sin_pitch) if abs(sin_pitch) >= 1.0 else math.asin(sin_pitch)
    sin_yaw_cos_pitch = 2.0 * (w * z + x * y)
    cos_yaw_cos_pitch = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(sin_yaw_cos_pitch, cos_yaw_cos_pitch)
    return tuple(math.degrees(value) for value in (yaw, pitch, roll))
