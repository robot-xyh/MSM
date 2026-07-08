from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .ekf import numerical_jacobian
from .motion import wrap_angle
from .types import SensorObservation


VIDEO_DERIVED_PAYLOAD_KINDS = ("bbox", "video_metadata", "camera_metadata")


@dataclass
class CameraModel:
    """Pinhole camera model for offline EO projection constraints."""

    position_ned: np.ndarray = field(
        default_factory=lambda: np.array([0.0, 0.0, -10.0], dtype=float)
    )
    rotation_world_to_camera: np.ndarray = field(
        default_factory=lambda: np.array(
            [
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0],
            ],
            dtype=float,
        )
    )
    fx: float = 900.0
    fy: float = 900.0
    cx: float = 640.0
    cy: float = 360.0
    width: int = 1280
    height: int = 720

    @classmethod
    def from_metadata(cls, metadata: dict) -> "CameraModel":
        if "camera_model" in metadata and isinstance(metadata["camera_model"], CameraModel):
            return metadata["camera_model"]
        camera_model = metadata.get("camera_model")
        if isinstance(camera_model, dict):
            return cls(
                position_ned=np.asarray(
                    camera_model.get(
                        "position_ned",
                        camera_model.get(
                            "camera_position_ned",
                            metadata.get("camera_position_ned", [0.0, 0.0, -10.0]),
                        ),
                    ),
                    dtype=float,
                ),
                rotation_world_to_camera=np.asarray(
                    camera_model.get(
                        "rotation_world_to_camera",
                        metadata.get(
                            "rotation_world_to_camera",
                            [
                                [0.0, 1.0, 0.0],
                                [0.0, 0.0, 1.0],
                                [1.0, 0.0, 0.0],
                            ],
                        ),
                    ),
                    dtype=float,
                ),
                fx=float(camera_model.get("fx", metadata.get("fx", 900.0))),
                fy=float(camera_model.get("fy", metadata.get("fy", 900.0))),
                cx=float(camera_model.get("cx", metadata.get("cx", 640.0))),
                cy=float(camera_model.get("cy", metadata.get("cy", 360.0))),
                width=int(camera_model.get("width", metadata.get("width", 1280))),
                height=int(camera_model.get("height", metadata.get("height", 720))),
            )
        return cls(
            position_ned=np.asarray(
                metadata.get("camera_position_ned", [0.0, 0.0, -10.0]), dtype=float
            ),
            rotation_world_to_camera=np.asarray(
                metadata.get(
                    "rotation_world_to_camera",
                    [
                        [0.0, 1.0, 0.0],
                        [0.0, 0.0, 1.0],
                        [1.0, 0.0, 0.0],
                    ],
                ),
                dtype=float,
            ),
            fx=float(metadata.get("fx", 900.0)),
            fy=float(metadata.get("fy", 900.0)),
            cx=float(metadata.get("cx", 640.0)),
            cy=float(metadata.get("cy", 360.0)),
            width=int(metadata.get("width", 1280)),
            height=int(metadata.get("height", 720)),
        )


@dataclass
class MeasurementModel:
    z: np.ndarray
    r: np.ndarray
    h_fn: Callable[[np.ndarray], np.ndarray]
    h_jacobian_fn: Callable[[np.ndarray], np.ndarray]
    angle_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class RadarCovarianceConfig:
    """Distance-dependent radar measurement covariance parameters."""

    min_distance_m: float = 1.0
    range_sigma_base_m: float = 2.0
    range_sigma_per_m: float = 0.012
    azimuth_sigma_base_deg: float = 0.25
    azimuth_sigma_per_m_deg: float = 0.0008
    elevation_sigma_base_deg: float = 0.35
    elevation_sigma_per_m_deg: float = 0.0010
    radial_velocity_sigma_base_mps: float = 0.35
    radial_velocity_sigma_per_m_mps: float = 0.0015


def sensor_position_from_metadata(observation: SensorObservation) -> np.ndarray:
    return np.asarray(observation.metadata.get("sensor_position_ned", [0.0, 0.0, 0.0]), dtype=float)


def radar_h(state: np.ndarray, sensor_position: np.ndarray) -> np.ndarray:
    rel = np.asarray(state[:3], dtype=float) - sensor_position
    vel = np.asarray(state[3:], dtype=float)
    rho = max(float(np.linalg.norm(rel)), 1e-6)
    horizontal = max(float(np.linalg.norm(rel[:2])), 1e-6)
    unit = rel / rho
    return np.array(
        [
            rho,
            np.arctan2(rel[1], rel[0]),
            np.arctan2(-rel[2], horizontal),
            float(np.dot(vel, unit)),
        ],
        dtype=float,
    )


def radar_covariance_from_range(
    distance: float,
    config: RadarCovarianceConfig | dict | None = None,
) -> np.ndarray:
    cfg = _radar_covariance_config(config)
    distance = max(float(distance), cfg.min_distance_m)
    sigma_range = cfg.range_sigma_base_m + cfg.range_sigma_per_m * distance
    sigma_angle = np.deg2rad(cfg.azimuth_sigma_base_deg + cfg.azimuth_sigma_per_m_deg * distance)
    sigma_elevation = np.deg2rad(
        cfg.elevation_sigma_base_deg + cfg.elevation_sigma_per_m_deg * distance
    )
    sigma_rv = cfg.radial_velocity_sigma_base_mps + cfg.radial_velocity_sigma_per_m_mps * distance
    return np.diag([sigma_range**2, sigma_angle**2, sigma_elevation**2, sigma_rv**2])


def radar_state_from_observation(
    observation: SensorObservation,
    covariance_config: RadarCovarianceConfig | dict | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    sensor_position = sensor_position_from_metadata(observation)
    z = observation.measurement.reshape(-1)
    rho, azimuth, elevation = z[:3]
    radial_velocity = float(z[3]) if z.size >= 4 else 0.0
    horizontal = rho * np.cos(elevation)
    rel = np.array(
        [
            horizontal * np.cos(azimuth),
            horizontal * np.sin(azimuth),
            -rho * np.sin(elevation),
        ],
        dtype=float,
    )
    unit = rel / max(float(np.linalg.norm(rel)), 1e-6)
    state = np.zeros(6, dtype=float)
    state[:3] = sensor_position + rel
    state[3:] = radial_velocity * unit

    r = observation.covariance
    if r is None:
        r = radar_covariance_from_range(float(rho), covariance_config)
    sigma_rho, sigma_az, sigma_el, sigma_rv = np.sqrt(np.diag(r))
    tangential = max(float(rho), 1.0) * max(float(sigma_az), float(sigma_el))
    covariance = np.diag(
        [
            max(sigma_rho**2, tangential**2),
            max(sigma_rho**2, tangential**2),
            max(sigma_rho**2, (rho * sigma_el) ** 2),
            max(25.0, sigma_rv**2),
            max(25.0, (2.0 * sigma_rv) ** 2),
            max(25.0, (2.0 * sigma_rv) ** 2),
        ]
    )
    return state, covariance


def acoustic_h(state: np.ndarray, sensor_position: np.ndarray) -> np.ndarray:
    rel = np.asarray(state[:3], dtype=float) - sensor_position
    return np.array([np.arctan2(rel[1], rel[0])], dtype=float)


def acoustic_covariance(confidence: float) -> np.ndarray:
    sigma_deg = 2.5 + 8.0 * (1.0 - float(np.clip(confidence, 0.0, 1.0)))
    return np.diag([np.deg2rad(sigma_deg) ** 2])


def eo_project(state: np.ndarray, camera: CameraModel) -> np.ndarray:
    rel_world = np.asarray(state[:3], dtype=float) - camera.position_ned
    point_camera = camera.rotation_world_to_camera @ rel_world
    z_forward = point_camera[2]
    if z_forward <= 1e-3:
        z_forward = 1e-3
    u = camera.fx * point_camera[0] / z_forward + camera.cx
    v = camera.fy * point_camera[1] / z_forward + camera.cy
    return np.array([u, v], dtype=float)


def eo_covariance_from_bbox(
    bbox: np.ndarray | None,
    confidence: float,
    quality_flags: tuple[str, ...],
) -> np.ndarray:
    conf = float(np.clip(confidence, 0.05, 1.0))
    if bbox is None:
        base_sigma = 12.0 / conf
    else:
        bbox = np.asarray(bbox, dtype=float)
        width = max(float(bbox[2] - bbox[0]), 1.0)
        height = max(float(bbox[3] - bbox[1]), 1.0)
        base_sigma = max(2.0, 0.08 * max(width, height)) / conf
    if "occluded" in quality_flags:
        base_sigma *= 2.0
    if "small_bbox" in quality_flags:
        base_sigma *= 1.5
    return np.diag([base_sigma**2, base_sigma**2])


def lidar_covariance(distance: float, confidence: float = 0.9) -> np.ndarray:
    """Offline dry-run covariance for a synthetic lidar position sample."""

    distance = max(float(distance), 1.0)
    confidence = float(np.clip(confidence, 0.05, 1.0))
    sigma_xy = (0.35 + 0.0025 * distance) / confidence
    sigma_z = (0.50 + 0.0035 * distance) / confidence
    return np.diag([sigma_xy**2, sigma_xy**2, sigma_z**2])


def measurement_model_for(
    observation: SensorObservation,
    radar_covariance_config: RadarCovarianceConfig | dict | None = None,
) -> MeasurementModel:
    modality = observation.modality.lower()
    if modality == "radar":
        sensor_position = sensor_position_from_metadata(observation)
        r = (
            observation.covariance
            if observation.covariance is not None
            else radar_covariance_from_range(float(observation.measurement[0]), radar_covariance_config)
        )

        def h_fn(x: np.ndarray) -> np.ndarray:
            return radar_h(x, sensor_position)

        return MeasurementModel(
            z=observation.measurement.reshape(-1),
            r=r,
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(1, 2),
        )

    if modality == "acoustic":
        sensor_position = sensor_position_from_metadata(observation)
        r = (
            observation.covariance
            if observation.covariance is not None
            else acoustic_covariance(observation.confidence)
        )

        def h_fn(x: np.ndarray) -> np.ndarray:
            return acoustic_h(x, sensor_position)

        z = np.array([wrap_angle(float(observation.measurement[0]))], dtype=float)
        return MeasurementModel(
            z=z,
            r=r,
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(0,),
        )

    if modality == "eo":
        camera = CameraModel.from_metadata(observation.metadata)
        bbox = observation.metadata.get("bbox")
        r = (
            observation.covariance
            if observation.covariance is not None
            else eo_covariance_from_bbox(bbox, observation.confidence, observation.quality_flags)
        )

        def h_fn(x: np.ndarray) -> np.ndarray:
            return eo_project(x, camera)

        return MeasurementModel(
            z=observation.measurement.reshape(-1)[:2],
            r=r,
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(),
        )

    if modality == "lidar":
        sensor_position = sensor_position_from_metadata(observation)
        z = observation.measurement.reshape(-1)[:3]
        distance = float(np.linalg.norm(z - sensor_position))
        r = (
            observation.covariance
            if observation.covariance is not None
            else lidar_covariance(distance, observation.confidence)
        )

        def h_fn(x: np.ndarray) -> np.ndarray:
            return np.asarray(x[:3], dtype=float)

        return MeasurementModel(
            z=z,
            r=r,
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(),
        )

    raise ValueError(f"Unsupported modality: {observation.modality}")


def _radar_covariance_config(config: RadarCovarianceConfig | dict | None) -> RadarCovarianceConfig:
    if config is None:
        return RadarCovarianceConfig()
    if isinstance(config, RadarCovarianceConfig):
        return config
    return RadarCovarianceConfig(**dict(config))
