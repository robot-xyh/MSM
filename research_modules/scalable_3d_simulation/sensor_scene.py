"""Identity-free synthetic radar and camera observations for the 3D world."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

import numpy as np

from .camera_projection import (
    CameraIntrinsics,
    CameraPose,
    look_at_rotation_ned_to_camera,
    project_points,
)
from .models import (
    ObservationBatch,
    OfflineTruthLabel,
    ScenarioConfig,
    SensorMeasurement,
    WorldSnapshot,
)


@dataclass(frozen=True)
class CameraView:
    sensor_id: str
    platform_kind: str
    platform_index: int
    pose: CameraPose
    intrinsics: CameraIntrinsics


class SensorScene:
    """Generate online observations and a physically separate evaluator label stream."""

    def __init__(self, config: ScenarioConfig) -> None:
        self.config = config
        seeds = np.random.SeedSequence(config.seed + 10_000).spawn(3)
        self.radar_rng = np.random.default_rng(seeds[0])
        self.acoustic_rng = np.random.default_rng(seeds[1])
        self.visual_rng = np.random.default_rng(seeds[2])
        self._radar_scan_index = 0
        self._acoustic_scan_index = 0
        self._visual_scan_index = 0

    def reset(self) -> None:
        seeds = np.random.SeedSequence(self.config.seed + 10_000).spawn(3)
        self.radar_rng = np.random.default_rng(seeds[0])
        self.acoustic_rng = np.random.default_rng(seeds[1])
        self.visual_rng = np.random.default_rng(seeds[2])
        self._radar_scan_index = 0
        self._acoustic_scan_index = 0
        self._visual_scan_index = 0

    def radar_scan(self, snapshot: WorldSnapshot) -> ObservationBatch:
        """Generate one range/azimuth/elevation scan from the protected-site radar."""

        self._radar_scan_index += 1
        timestamp = float(snapshot.timestamp)
        positions = snapshot.intruders.position_ned
        active = snapshot.intruders.active
        ranges = np.linalg.norm(positions, axis=1)
        candidate = active & (ranges <= self.config.radar_range_limit_m)
        detected = candidate & (
            self.radar_rng.random(positions.shape[0]) < self.config.radar_detection_probability
        )
        measurements: list[SensorMeasurement] = []
        labels: list[OfflineTruthLabel] = []
        detection_index = 0
        for target_index in np.flatnonzero(detected):
            position = positions[target_index]
            range_m = float(ranges[target_index])
            horizontal = float(np.linalg.norm(position[:2]))
            azimuth = math.atan2(float(position[1]), float(position[0]))
            elevation = math.atan2(float(-position[2]), max(horizontal, 1.0e-9))
            range_std = self.config.radar_range_std_base_m + (
                range_m / 1_000.0
            ) * self.config.radar_range_std_per_km_m
            angle_std = math.radians(self.config.radar_angle_std_deg)
            covariance = np.diag([range_std**2, angle_std**2, angle_std**2])
            noise = self.radar_rng.multivariate_normal(np.zeros(3, dtype=float), covariance)
            value = np.array([range_m, azimuth, elevation], dtype=float) + noise
            value[1] = _wrap_angle(value[1])
            value[2] = float(np.clip(value[2], -0.5 * np.pi, 0.5 * np.pi))
            observation_id = (
                f"radar-s{self._radar_scan_index:06d}-d{detection_index:04d}"
            )
            detection_index += 1
            confidence = float(
                np.clip(
                    self.config.radar_detection_probability
                    * (1.0 - 0.25 * range_m / self.config.radar_range_limit_m),
                    0.05,
                    1.0,
                )
            )
            measurements.append(
                SensorMeasurement(
                    observation_id=observation_id,
                    sensor_id="RADAR-CENTER-001",
                    modality="radar_spherical",
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp + self.config.radar_latency_s,
                    frame_id="radar_center_frame",
                    measurement=value,
                    covariance=covariance,
                    confidence=confidence,
                    classification_hint="unmanned_aircraft",
                    metadata={
                        "measurement_order": ["range_m", "azimuth_rad", "elevation_rad"],
                        "sensor_position_ned": [0.0, 0.0, 0.0],
                        "range_dependent_covariance": True,
                        "scan_index": self._radar_scan_index,
                    },
                )
            )
            labels.append(
                OfflineTruthLabel(
                    observation_id=observation_id,
                    truth_entity_id=snapshot.intruders.entity_ids[target_index],
                    measurement_timestamp=timestamp,
                )
            )
        return ObservationBatch(tuple(measurements), tuple(labels))

    def acoustic_scan(self, snapshot: WorldSnapshot) -> ObservationBatch:
        """Generate coarse azimuth/elevation and class-level soundprint hints."""

        self._acoustic_scan_index += 1
        timestamp = float(snapshot.timestamp)
        measurements: list[SensorMeasurement] = []
        labels: list[OfflineTruthLabel] = []
        positions = snapshot.intruders.position_ned
        active = snapshot.intruders.active
        sensor_angles = np.arange(self.config.acoustic_sensor_count, dtype=float) * (
            2.0 * np.pi / self.config.acoustic_sensor_count
        )
        sensor_radius = self.config.protected_radius_m * 0.8
        sensor_positions = np.column_stack(
            (
                sensor_radius * np.cos(sensor_angles),
                sensor_radius * np.sin(sensor_angles),
                np.zeros(self.config.acoustic_sensor_count, dtype=float),
            )
        )
        angle_std = math.radians(self.config.acoustic_angle_std_deg)
        covariance = np.diag([angle_std**2, angle_std**2])
        for sensor_index, sensor_position in enumerate(sensor_positions):
            relative = positions - sensor_position[None, :]
            ranges = np.linalg.norm(relative, axis=1)
            candidate = active & (ranges <= self.config.acoustic_range_limit_m)
            detected = candidate & (
                self.acoustic_rng.random(positions.shape[0])
                < self.config.acoustic_detection_probability
            )
            for local_index, target_index in enumerate(np.flatnonzero(detected)):
                vector = relative[target_index]
                horizontal = float(np.linalg.norm(vector[:2]))
                noiseless = np.array(
                    [
                        math.atan2(float(vector[1]), float(vector[0])),
                        math.atan2(float(-vector[2]), max(horizontal, 1.0e-9)),
                    ],
                    dtype=float,
                )
                value = noiseless + self.acoustic_rng.multivariate_normal(
                    np.zeros(2, dtype=float), covariance
                )
                value[0] = _wrap_angle(value[0])
                value[1] = float(np.clip(value[1], -0.5 * np.pi, 0.5 * np.pi))
                soundprint = np.clip(
                    np.array([0.72, 0.19, 0.09], dtype=float)
                    + self.acoustic_rng.normal(0.0, 0.025, 3),
                    0.0,
                    1.0,
                )
                soundprint /= max(float(np.sum(soundprint)), 1.0e-9)
                observation_id = (
                    f"acoustic-s{self._acoustic_scan_index:06d}-"
                    f"a{sensor_index + 1:02d}-d{local_index:04d}"
                )
                sensor_id = f"ACOUSTIC-{sensor_index + 1:02d}"
                measurements.append(
                    SensorMeasurement(
                        observation_id=observation_id,
                        sensor_id=sensor_id,
                        modality="acoustic_bearing",
                        measurement_timestamp=timestamp,
                        arrival_timestamp=timestamp + self.config.acoustic_latency_s,
                        frame_id=f"acoustic_{sensor_index + 1:02d}_frame",
                        measurement=value,
                        covariance=covariance,
                        confidence=float(self.config.acoustic_detection_probability),
                        classification_hint="unmanned_aircraft",
                        metadata={
                            "measurement_order": ["azimuth_rad", "elevation_rad"],
                            "sensor_position_ned": sensor_position.tolist(),
                            "soundprint_class_probabilities": soundprint.tolist(),
                            "soundprint_is_identity": False,
                            "scan_index": self._acoustic_scan_index,
                        },
                    )
                )
                labels.append(
                    OfflineTruthLabel(
                        observation_id=observation_id,
                        truth_entity_id=snapshot.intruders.entity_ids[target_index],
                        measurement_timestamp=timestamp,
                    )
                )
        return ObservationBatch(tuple(measurements), tuple(labels))

    def visual_scan(
        self,
        snapshot: WorldSnapshot,
        *,
        camera_aim_points: Mapping[str, np.ndarray] | None = None,
    ) -> ObservationBatch:
        """Project active intruders into all interceptor and recon cameras."""

        self._visual_scan_index += 1
        timestamp = float(snapshot.timestamp)
        views = self.camera_views(snapshot, camera_aim_points=camera_aim_points)
        active_indices = np.flatnonzero(snapshot.intruders.active)
        active_positions = snapshot.intruders.position_ned[active_indices]
        point_covariance = np.broadcast_to(
            np.diag([4.0, 4.0, 4.0]),
            (active_indices.size, 3, 3),
        ).copy()
        measurements: list[SensorMeasurement] = []
        labels: list[OfflineTruthLabel] = []
        for view in views:
            if active_indices.size == 0:
                self._append_false_alarms(view, timestamp, measurements)
                continue
            projection = project_points(
                active_positions,
                camera_pose=view.pose,
                intrinsics=view.intrinsics,
                point_covariance_ned=point_covariance,
                object_size_m=(
                    self.config.target_proxy_width_m,
                    self.config.target_proxy_height_m,
                ),
                pixel_noise_std=0.8 if view.platform_kind == "recon" else 1.5,
            )
            projected_bbox = projection.bbox_xyxy
            projected_area = np.maximum(
                0.0,
                (projected_bbox[:, 2] - projected_bbox[:, 0])
                * (projected_bbox[:, 3] - projected_bbox[:, 1]),
            )
            minimum_area = (
                self.config.recon_visual_min_bbox_area_px2
                if view.platform_kind == "recon"
                else self.config.visual_min_bbox_area_px2
            )
            visible_local = np.flatnonzero(
                projection.visible & (projected_area >= minimum_area)
            )
            retained = visible_local[
                self.visual_rng.random(visible_local.size)
                < self.config.visual_detection_probability
            ]
            retained_covariance = projection.covariance_pixels[retained]
            if retained.size:
                cholesky = np.linalg.cholesky(
                    retained_covariance
                    + np.eye(2, dtype=float)[None, :, :] * 1.0e-12
                )
                standard_noise = self.visual_rng.normal(size=(retained.size, 2))
                center_noise = np.einsum("nij,nj->ni", cholesky, standard_noise)
                noisy_centers = projection.pixel_centers[retained] + center_noise
                retained_bbox = projection.bbox_xyxy[retained]
                widths = np.maximum(retained_bbox[:, 2] - retained_bbox[:, 0], 1.0)
                heights = np.maximum(retained_bbox[:, 3] - retained_bbox[:, 1], 1.0)
                scale_noise = np.maximum(
                    0.5,
                    1.0 + self.visual_rng.normal(0.0, 0.025, retained.size),
                )
                widths *= scale_noise
                heights *= scale_noise
            for local_detection_index, projection_index in enumerate(retained):
                target_index = int(active_indices[projection_index])
                center_covariance = retained_covariance[local_detection_index]
                center = noisy_centers[local_detection_index]
                width = float(widths[local_detection_index])
                height = float(heights[local_detection_index])
                bbox = np.array(
                    [
                        center[0] - 0.5 * width,
                        center[1] - 0.5 * height,
                        center[0] + 0.5 * width,
                        center[1] + 0.5 * height,
                    ],
                    dtype=float,
                )
                bbox[[0, 2]] = np.clip(bbox[[0, 2]], 0.0, view.intrinsics.width_px - 1.0)
                bbox[[1, 3]] = np.clip(bbox[[1, 3]], 0.0, view.intrinsics.height_px - 1.0)
                measurement = np.concatenate((center, bbox))
                bbox_variance = max(1.0, 0.0025 * width * height)
                covariance = np.zeros((6, 6), dtype=float)
                covariance[:2, :2] = center_covariance
                covariance[2:, 2:] = np.eye(4, dtype=float) * bbox_variance
                observation_id = (
                    f"vision-s{self._visual_scan_index:06d}-"
                    f"{view.sensor_id.lower()}-d{local_detection_index:04d}"
                )
                confidence = float(
                    np.clip(
                        self.config.visual_detection_probability
                        * min(1.0, math.sqrt(max(width * height, 1.0)) / 16.0),
                        0.05,
                        1.0,
                    )
                )
                measurements.append(
                    SensorMeasurement(
                        observation_id=observation_id,
                        sensor_id=view.sensor_id,
                        modality="vision_bbox",
                        measurement_timestamp=timestamp,
                        arrival_timestamp=timestamp + self.config.visual_latency_s,
                        frame_id=f"{view.sensor_id.lower()}_optical_frame",
                        measurement=measurement,
                        covariance=covariance,
                        confidence=confidence,
                        classification_hint="unmanned_aircraft",
                        metadata=_camera_metadata(view, width * height, self._visual_scan_index),
                    )
                )
                labels.append(
                    OfflineTruthLabel(
                        observation_id=observation_id,
                        truth_entity_id=snapshot.intruders.entity_ids[target_index],
                        measurement_timestamp=timestamp,
                    )
                )
            self._append_false_alarms(view, timestamp, measurements)
        return ObservationBatch(tuple(measurements), tuple(labels))

    def camera_views(
        self,
        snapshot: WorldSnapshot,
        *,
        camera_aim_points: Mapping[str, np.ndarray] | None = None,
    ) -> tuple[CameraView, ...]:
        """Build current camera extrinsics without exposing target identity."""

        aim_points = camera_aim_points or {}
        views: list[CameraView] = []
        interceptor_intrinsics = CameraIntrinsics.from_horizontal_fov(
            width_px=self.config.camera_width_px,
            height_px=self.config.camera_height_px,
            horizontal_fov_deg=self.config.camera_horizontal_fov_deg,
        )
        recon_intrinsics = CameraIntrinsics.from_horizontal_fov(
            width_px=self.config.recon_camera_width_px,
            height_px=self.config.recon_camera_height_px,
            horizontal_fov_deg=self.config.recon_camera_horizontal_fov_deg,
        )
        for index, (position, velocity, active) in enumerate(
            zip(
                snapshot.interceptors.position_ned,
                snapshot.interceptors.velocity_ned,
                snapshot.interceptors.active,
            )
        ):
            if not active:
                continue
            sensor_id = f"CAM-INT-{index + 1:04d}"
            direction = velocity.copy()
            if np.linalg.norm(direction) < 1.0e-6:
                direction = position.copy()
                direction[2] = 0.0
            direction /= max(float(np.linalg.norm(direction)), 1.0e-9)
            camera_position = position + 0.5 * direction
            target = np.asarray(
                aim_points.get(sensor_id, camera_position + direction * 1_000.0),
                dtype=float,
            )
            views.append(
                CameraView(
                    sensor_id=sensor_id,
                    platform_kind="interceptor",
                    platform_index=index,
                    pose=CameraPose(
                        camera_position,
                        look_at_rotation_ned_to_camera(camera_position, target),
                        position_covariance_ned=np.eye(3, dtype=float) * 0.04,
                        attitude_covariance_rad2=np.eye(3, dtype=float)
                        * math.radians(0.08) ** 2,
                    ),
                    intrinsics=interceptor_intrinsics,
                )
            )
        for index, (position, active) in enumerate(
            zip(snapshot.recon.position_ned, snapshot.recon.active)
        ):
            if not active:
                continue
            sensor_id = f"CAM-RECON-{index + 1:03d}"
            target = np.asarray(
                aim_points.get(sensor_id, np.array([0.0, 0.0, -150.0], dtype=float)),
                dtype=float,
            )
            views.append(
                CameraView(
                    sensor_id=sensor_id,
                    platform_kind="recon",
                    platform_index=index,
                    pose=CameraPose(
                        position,
                        look_at_rotation_ned_to_camera(position, target),
                        position_covariance_ned=np.eye(3, dtype=float) * 0.25,
                        attitude_covariance_rad2=np.eye(3, dtype=float)
                        * math.radians(0.04) ** 2,
                    ),
                    intrinsics=recon_intrinsics,
                )
            )
        return tuple(views)

    def _append_false_alarms(
        self,
        view: CameraView,
        timestamp: float,
        measurements: list[SensorMeasurement],
    ) -> None:
        count = int(self.visual_rng.poisson(self.config.visual_false_alarm_rate))
        for false_index in range(count):
            center = np.array(
                [
                    self.visual_rng.uniform(0.0, view.intrinsics.width_px - 1.0),
                    self.visual_rng.uniform(0.0, view.intrinsics.height_px - 1.0),
                ],
                dtype=float,
            )
            width = float(self.visual_rng.uniform(4.0, 24.0))
            height = float(self.visual_rng.uniform(3.0, 18.0))
            bbox = np.array(
                [
                    max(0.0, center[0] - 0.5 * width),
                    max(0.0, center[1] - 0.5 * height),
                    min(view.intrinsics.width_px - 1.0, center[0] + 0.5 * width),
                    min(view.intrinsics.height_px - 1.0, center[1] + 0.5 * height),
                ],
                dtype=float,
            )
            observation_id = (
                f"vision-s{self._visual_scan_index:06d}-{view.sensor_id.lower()}-"
                f"fa{false_index:03d}"
            )
            measurements.append(
                SensorMeasurement(
                    observation_id=observation_id,
                    sensor_id=view.sensor_id,
                    modality="vision_bbox",
                    measurement_timestamp=timestamp,
                    arrival_timestamp=timestamp + self.config.visual_latency_s,
                    frame_id=f"{view.sensor_id.lower()}_optical_frame",
                    measurement=np.concatenate((center, bbox)),
                    covariance=np.eye(6, dtype=float) * 16.0,
                    confidence=0.15,
                    classification_hint=None,
                    metadata=_camera_metadata(view, width * height, self._visual_scan_index),
                )
            )


def _camera_metadata(view: CameraView, bbox_area: float, scan_index: int) -> dict[str, object]:
    return {
        "measurement_order": ["u", "v", "xmin", "ymin", "xmax", "ymax"],
        "camera_position_ned": view.pose.position_ned.tolist(),
        "rotation_camera_from_ned": view.pose.rotation_camera_from_ned.tolist(),
        "camera_intrinsics": {
            "width_px": view.intrinsics.width_px,
            "height_px": view.intrinsics.height_px,
            "fx": view.intrinsics.fx,
            "fy": view.intrinsics.fy,
            "cx": view.intrinsics.cx,
            "cy": view.intrinsics.cy,
        },
        "camera_kind": view.platform_kind,
        "bbox_area_px2": float(bbox_area),
        "scan_index": int(scan_index),
    }


def _wrap_angle(value: float) -> float:
    return float((value + np.pi) % (2.0 * np.pi) - np.pi)
