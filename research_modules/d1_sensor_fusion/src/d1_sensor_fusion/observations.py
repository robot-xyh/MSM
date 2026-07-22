from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .covariance_contract import validate_sensor_observation_covariance
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
        camera_model = _camera_metadata_candidate(metadata)
        if isinstance(camera_model, CameraModel):
            return camera_model
        if isinstance(camera_model, dict):
            intrinsics = _mapping_or_empty(camera_model.get("intrinsics"))
            extrinsics = _mapping_or_empty(camera_model.get("extrinsics"))
            return cls(
                position_ned=np.asarray(
                    _first_present(
                        camera_model,
                        extrinsics,
                        metadata,
                        keys=("position_ned", "camera_position_ned", "translation_ned", "t"),
                        default=[0.0, 0.0, -10.0],
                    ),
                    dtype=float,
                ),
                rotation_world_to_camera=np.asarray(
                    _first_present(
                        camera_model,
                        extrinsics,
                        metadata,
                        keys=("rotation_world_to_camera", "R", "rotation_matrix"),
                        default=[
                            [0.0, 1.0, 0.0],
                            [0.0, 0.0, 1.0],
                            [1.0, 0.0, 0.0],
                        ],
                    ),
                    dtype=float,
                ),
                fx=float(_camera_intrinsic(camera_model, intrinsics, metadata, "fx", 900.0)),
                fy=float(_camera_intrinsic(camera_model, intrinsics, metadata, "fy", 900.0)),
                cx=float(_camera_intrinsic(camera_model, intrinsics, metadata, "cx", 640.0)),
                cy=float(_camera_intrinsic(camera_model, intrinsics, metadata, "cy", 360.0)),
                width=int(_camera_dimension(camera_model, intrinsics, metadata, "width", 1280)),
                height=int(_camera_dimension(camera_model, intrinsics, metadata, "height", 720)),
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
    geometry_key: tuple[Any, ...] = ()


def _geometry_array_key(value: np.ndarray) -> tuple[tuple[int, ...], bytes]:
    array = np.ascontiguousarray(np.asarray(value, dtype=float))
    return tuple(int(item) for item in array.shape), array.tobytes()


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
    radial_velocity_observed = bool(
        observation.metadata.get("radial_velocity_observed", z.size >= 4)
    )
    radial_velocity = (
        float(z[3]) if radial_velocity_observed and z.size >= 4 else 0.0
    )
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

    r = validate_sensor_observation_covariance(
        observation,
        context="D1 radar state initialization",
    )
    if observation.metadata.get("spherical_covariance_to_ned") == "analytic_jacobian":
        return state, _radar_state_covariance_from_spherical(
            rho=float(rho),
            azimuth=float(azimuth),
            elevation=float(elevation),
            radial_velocity=radial_velocity,
            radial_velocity_observed=radial_velocity_observed,
            measurement_covariance=r,
            metadata=observation.metadata,
        )

    sigma_rho, sigma_az, sigma_el, sigma_rv = np.sqrt(np.diag(r))
    tangential = max(float(rho), 1.0) * max(float(sigma_az), float(sigma_el))
    position_variances = [
        max(sigma_rho**2, tangential**2),
        max(sigma_rho**2, tangential**2),
        max(sigma_rho**2, (rho * sigma_el) ** 2),
    ]
    if radial_velocity_observed:
        velocity_variances = [
            max(25.0, sigma_rv**2),
            max(25.0, (2.0 * sigma_rv) ** 2),
            max(25.0, (2.0 * sigma_rv) ** 2),
        ]
    else:
        unobserved_variance = _unobserved_velocity_variance(observation.metadata)
        velocity_variances = [unobserved_variance] * 3
    covariance = np.diag([*position_variances, *velocity_variances])
    return state, covariance


def _radar_state_covariance_from_spherical(
    *,
    rho: float,
    azimuth: float,
    elevation: float,
    radial_velocity: float,
    radial_velocity_observed: bool,
    measurement_covariance: np.ndarray,
    metadata: dict[str, Any],
) -> np.ndarray:
    """Propagate spherical radar covariance into the six-state NED frame."""

    cos_azimuth = np.cos(azimuth)
    sin_azimuth = np.sin(azimuth)
    cos_elevation = np.cos(elevation)
    sin_elevation = np.sin(elevation)
    unit = np.array(
        [
            cos_elevation * cos_azimuth,
            cos_elevation * sin_azimuth,
            -sin_elevation,
        ],
        dtype=float,
    )
    jacobian = np.zeros((6, 4), dtype=float)
    jacobian[:3, 0] = unit
    jacobian[:3, 1] = np.array(
        [
            -rho * cos_elevation * sin_azimuth,
            rho * cos_elevation * cos_azimuth,
            0.0,
        ],
        dtype=float,
    )
    jacobian[:3, 2] = np.array(
        [
            -rho * sin_elevation * cos_azimuth,
            -rho * sin_elevation * sin_azimuth,
            -rho * cos_elevation,
        ],
        dtype=float,
    )
    if radial_velocity_observed:
        jacobian[3:, 1] = radial_velocity * np.array(
            [
                -cos_elevation * sin_azimuth,
                cos_elevation * cos_azimuth,
                0.0,
            ],
            dtype=float,
        )
        jacobian[3:, 2] = radial_velocity * np.array(
            [
                -sin_elevation * cos_azimuth,
                -sin_elevation * sin_azimuth,
                -cos_elevation,
            ],
            dtype=float,
        )
        jacobian[3:, 3] = unit
        covariance = jacobian @ measurement_covariance @ jacobian.T
    else:
        covariance = np.zeros((6, 6), dtype=float)
        position_jacobian = jacobian[:3, :3]
        covariance[:3, :3] = (
            position_jacobian
            @ measurement_covariance[:3, :3]
            @ position_jacobian.T
        )
        covariance[3:, 3:] = (
            np.eye(3, dtype=float) * _unobserved_velocity_variance(metadata)
        )

    sensor_covariance = metadata.get("sensor_position_covariance_ned")
    if sensor_covariance is not None:
        sensor_covariance = np.asarray(sensor_covariance, dtype=float)
        if sensor_covariance.shape != (3, 3) or not np.isfinite(sensor_covariance).all():
            raise ValueError("sensor_position_covariance_ned must be a finite 3x3 matrix")
        covariance[:3, :3] += sensor_covariance

    if radial_velocity_observed:
        tangential_variance = float(
            metadata.get("unobserved_tangential_velocity_variance_m2ps2", 100.0)
        )
        if not np.isfinite(tangential_variance) or tangential_variance <= 0.0:
            raise ValueError(
                "unobserved_tangential_velocity_variance_m2ps2 must be positive and finite"
            )
        covariance[3:, 3:] += tangential_variance * (
            np.eye(3, dtype=float) - np.outer(unit, unit)
        )
    covariance = 0.5 * (covariance + covariance.T)
    minimum_eigenvalue = float(np.linalg.eigvalsh(covariance).min())
    if minimum_eigenvalue < 0.0:
        covariance += np.eye(6, dtype=float) * (-minimum_eigenvalue + 1.0e-9)
    return covariance


def _unobserved_velocity_variance(metadata: dict[str, Any]) -> float:
    variance = float(
        metadata.get(
            "unobserved_velocity_variance_m2ps2",
            metadata.get("unobserved_tangential_velocity_variance_m2ps2", 100.0),
        )
    )
    if not np.isfinite(variance) or variance <= 0.0:
        raise ValueError(
            "unobserved_velocity_variance_m2ps2 must be positive and finite"
        )
    return variance


def acoustic_h(state: np.ndarray, sensor_position: np.ndarray) -> np.ndarray:
    rel = np.asarray(state[:3], dtype=float) - sensor_position
    return np.array([np.arctan2(rel[1], rel[0])], dtype=float)


def acoustic_3d_h(state: np.ndarray, sensor_position: np.ndarray) -> np.ndarray:
    rel = np.asarray(state[:3], dtype=float) - sensor_position
    horizontal = max(float(np.linalg.norm(rel[:2])), 1.0e-9)
    return np.array(
        [
            np.arctan2(rel[1], rel[0]),
            np.arctan2(-rel[2], horizontal),
        ],
        dtype=float,
    )


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
    covariance = validate_sensor_observation_covariance(
        observation,
        context="D1 measurement model",
    )
    if modality == "radar":
        sensor_position = sensor_position_from_metadata(observation)
        radial_velocity_observed = bool(
            observation.metadata.get(
                "radial_velocity_observed",
                observation.measurement.size >= 4,
            )
        )
        measurement_dimension = 4 if radial_velocity_observed else 3

        def h_fn(x: np.ndarray) -> np.ndarray:
            return radar_h(x, sensor_position)[:measurement_dimension]

        return MeasurementModel(
            z=observation.measurement.reshape(-1)[:measurement_dimension],
            r=covariance[:measurement_dimension, :measurement_dimension],
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(1, 2),
            geometry_key=(
                "radar",
                _geometry_array_key(sensor_position),
                measurement_dimension,
            ),
        )

    if modality == "acoustic":
        sensor_position = sensor_position_from_metadata(observation)

        def h_fn(x: np.ndarray) -> np.ndarray:
            return acoustic_h(x, sensor_position)

        z = np.array([wrap_angle(float(observation.measurement[0]))], dtype=float)
        return MeasurementModel(
            z=z,
            r=covariance,
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(0,),
            geometry_key=("acoustic", _geometry_array_key(sensor_position)),
        )

    if modality == "acoustic_3d":
        sensor_position = sensor_position_from_metadata(observation)

        def h_fn(x: np.ndarray) -> np.ndarray:
            return acoustic_3d_h(x, sensor_position)

        z = observation.measurement.reshape(-1).copy()
        z[0] = wrap_angle(float(z[0]))
        z[1] = wrap_angle(float(z[1]))
        return MeasurementModel(
            z=z,
            r=covariance,
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(0, 1),
            geometry_key=("acoustic_3d", _geometry_array_key(sensor_position)),
        )

    if modality == "eo":
        camera = CameraModel.from_metadata(observation.metadata)

        def h_fn(x: np.ndarray) -> np.ndarray:
            return eo_project(x, camera)

        return MeasurementModel(
            z=observation.measurement.reshape(-1)[:2],
            r=covariance,
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(),
            geometry_key=(
                "eo",
                _geometry_array_key(camera.position_ned),
                _geometry_array_key(camera.rotation_world_to_camera),
                float(camera.fx),
                float(camera.fy),
                float(camera.cx),
                float(camera.cy),
            ),
        )

    if modality == "lidar":
        z = observation.measurement.reshape(-1)[:3]

        def h_fn(x: np.ndarray) -> np.ndarray:
            return np.asarray(x[:3], dtype=float)

        return MeasurementModel(
            z=z,
            r=covariance,
            h_fn=h_fn,
            h_jacobian_fn=lambda x: numerical_jacobian(h_fn, x),
            angle_indices=(),
            geometry_key=("lidar",),
        )

    raise ValueError(f"Unsupported modality: {observation.modality}")


def _radar_covariance_config(config: RadarCovarianceConfig | dict | None) -> RadarCovarianceConfig:
    if config is None:
        return RadarCovarianceConfig()
    if isinstance(config, RadarCovarianceConfig):
        return config
    return RadarCovarianceConfig(**dict(config))


def _camera_metadata_candidate(metadata: dict[str, Any]) -> CameraModel | dict[str, Any] | None:
    for key in ("camera_model", "camera_metadata", "camera"):
        value = metadata.get(key)
        if isinstance(value, CameraModel):
            return value
        if isinstance(value, dict):
            return dict(value)
    return None


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _first_present(
    *mappings: dict[str, Any],
    keys: tuple[str, ...],
    default: Any,
) -> Any:
    for mapping in mappings:
        for key in keys:
            value = mapping.get(key)
            if value is not None:
                return value
    return default


def _camera_intrinsic(
    camera_model: dict[str, Any],
    intrinsics: dict[str, Any],
    metadata: dict[str, Any],
    key: str,
    default: float,
) -> float:
    for mapping in (camera_model, intrinsics, metadata):
        value = mapping.get(key)
        if value is not None:
            return float(value)
    matrix = _intrinsic_matrix(camera_model, intrinsics, metadata)
    if matrix is not None:
        indices = {"fx": (0, 0), "fy": (1, 1), "cx": (0, 2), "cy": (1, 2)}
        row, column = indices[key]
        return float(matrix[row, column])
    return float(default)


def _camera_dimension(
    camera_model: dict[str, Any],
    intrinsics: dict[str, Any],
    metadata: dict[str, Any],
    key: str,
    default: int,
) -> int:
    for mapping in (camera_model, intrinsics, metadata):
        value = mapping.get(key)
        if value is not None:
            return int(value)
        image_size = mapping.get("image_size")
        if image_size is not None:
            values = np.asarray(image_size, dtype=float).reshape(-1)
            if values.size >= 2:
                return int(values[0] if key == "width" else values[1])
    return int(default)


def _intrinsic_matrix(*mappings: dict[str, Any]) -> np.ndarray | None:
    for mapping in mappings:
        value = mapping.get("K")
        if value is None:
            value = mapping.get("intrinsic_matrix")
        if value is None:
            continue
        matrix = np.asarray(value, dtype=float)
        if matrix.shape == (3, 3):
            return matrix
    return None
