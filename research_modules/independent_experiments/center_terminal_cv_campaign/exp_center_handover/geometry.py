"""NED-to-camera projection and covariance propagation for handover cues."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping

import numpy as np

from ..common import SourceCueRecord


@dataclass(frozen=True)
class CameraIntrinsics:
    width_px: int = 1920
    height_px: int = 1080
    horizontal_fov_deg: float = 19.0

    def __post_init__(self) -> None:
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("camera resolution must be positive")
        if not 0.0 < self.horizontal_fov_deg < 180.0:
            raise ValueError("horizontal_fov_deg must be within (0, 180)")

    @property
    def focal_x_px(self) -> float:
        return self.width_px / (2.0 * math.tan(math.radians(self.horizontal_fov_deg) / 2.0))

    @property
    def focal_y_px(self) -> float:
        return self.focal_x_px

    @property
    def principal_x_px(self) -> float:
        return self.width_px / 2.0

    @property
    def principal_y_px(self) -> float:
        return self.height_px / 2.0


@dataclass(frozen=True)
class CameraModel:
    """Explicit NED -> body -> gimbal -> camera transform chain.

    AirSim cameras use x-forward, y-right and z-down axes, so an aligned camera
    shares the body-axis convention and needs no additional optical-axis swap.
    """

    camera_id: str
    intrinsics: CameraIntrinsics
    body_position_ned_m: tuple[float, float, float]
    body_yaw_pitch_roll_deg: tuple[float, float, float]
    gimbal_yaw_pitch_roll_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    camera_offset_body_m: tuple[float, float, float] = (0.5, 0.0, 0.0)

    def __post_init__(self) -> None:
        if not str(self.camera_id).strip():
            raise ValueError("camera_id must be non-empty")
        for value in (
            self.body_position_ned_m,
            self.body_yaw_pitch_roll_deg,
            self.gimbal_yaw_pitch_roll_deg,
            self.camera_offset_body_m,
        ):
            if len(value) != 3 or not np.all(np.isfinite(value)):
                raise ValueError("camera pose components must contain three finite values")

    @property
    def rotation_ned_from_body(self) -> np.ndarray:
        return yaw_pitch_roll_matrix(*self.body_yaw_pitch_roll_deg)

    @property
    def rotation_body_from_gimbal(self) -> np.ndarray:
        return yaw_pitch_roll_matrix(*self.gimbal_yaw_pitch_roll_deg)

    @property
    def rotation_ned_from_camera(self) -> np.ndarray:
        return self.rotation_ned_from_body @ self.rotation_body_from_gimbal

    @property
    def camera_position_ned_m(self) -> np.ndarray:
        return np.asarray(self.body_position_ned_m, dtype=float) + self.rotation_ned_from_body @ np.asarray(
            self.camera_offset_body_m, dtype=float
        )

    def world_to_camera(self, point_ned_m: np.ndarray) -> np.ndarray:
        delta_ned = np.asarray(point_ned_m, dtype=float) - self.camera_position_ned_m
        return self.rotation_ned_from_camera.T @ delta_ned

    def project(self, point_ned_m: np.ndarray, *, require_in_frame: bool = True) -> np.ndarray:
        point_camera = self.world_to_camera(point_ned_m)
        forward, right, down = (float(value) for value in point_camera)
        if forward <= 1.0e-6:
            raise ProjectionError("point is behind the camera")
        intrinsics = self.intrinsics
        pixel = np.asarray(
            (
                intrinsics.principal_x_px + intrinsics.focal_x_px * right / forward,
                intrinsics.principal_y_px + intrinsics.focal_y_px * down / forward,
            ),
            dtype=float,
        )
        if require_in_frame and not (
            0.0 <= pixel[0] < intrinsics.width_px and 0.0 <= pixel[1] < intrinsics.height_px
        ):
            raise ProjectionError("projected point is outside the image")
        return pixel

    def projection_jacobian_ned(self, point_ned_m: np.ndarray) -> np.ndarray:
        point_camera = self.world_to_camera(point_ned_m)
        forward, right, down = (float(value) for value in point_camera)
        if forward <= 1.0e-6:
            raise ProjectionError("point is behind the camera")
        fx = self.intrinsics.focal_x_px
        fy = self.intrinsics.focal_y_px
        jacobian_camera = np.asarray(
            (
                (-fx * right / forward**2, fx / forward, 0.0),
                (-fy * down / forward**2, 0.0, fy / forward),
            ),
            dtype=float,
        )
        return jacobian_camera @ self.rotation_ned_from_camera.T

    def pixel_to_world_ray(self, center_px: tuple[float, float]) -> np.ndarray:
        u, v = (float(value) for value in center_px)
        direction_camera = np.asarray(
            (
                1.0,
                (u - self.intrinsics.principal_x_px) / self.intrinsics.focal_x_px,
                (v - self.intrinsics.principal_y_px) / self.intrinsics.focal_y_px,
            ),
            dtype=float,
        )
        direction_ned = self.rotation_ned_from_camera @ direction_camera
        norm = float(np.linalg.norm(direction_ned))
        if norm <= 1.0e-12:
            raise ValueError("pixel ray is degenerate")
        return direction_ned / norm

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CameraModel":
        intrinsics_raw = value["intrinsics"]
        return cls(
            camera_id=str(value["camera_id"]),
            intrinsics=CameraIntrinsics(**dict(intrinsics_raw)),
            body_position_ned_m=tuple(float(item) for item in value["body_position_ned_m"]),
            body_yaw_pitch_roll_deg=tuple(
                float(item) for item in value["body_yaw_pitch_roll_deg"]
            ),
            gimbal_yaw_pitch_roll_deg=tuple(
                float(item) for item in value.get("gimbal_yaw_pitch_roll_deg", (0.0, 0.0, 0.0))
            ),
            camera_offset_body_m=tuple(
                float(item) for item in value.get("camera_offset_body_m", (0.5, 0.0, 0.0))
            ),
        )


@dataclass(frozen=True)
class ProjectedSourceCue:
    source_track_id: str
    timestamp: float
    position_ned_m: tuple[float, float, float]
    velocity_ned_mps: tuple[float, float, float]
    state_covariance_6x6: tuple[tuple[float, ...], ...]
    center_px: tuple[float, float]
    covariance_px2: tuple[tuple[float, float], tuple[float, float]]
    velocity_px_s: tuple[float, float]
    depth_m: float


class ProjectionError(ValueError):
    """Raised when a cue cannot be represented in a camera image."""


def yaw_pitch_roll_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    yaw, pitch, roll = (math.radians(float(value)) for value in (yaw_deg, pitch_deg, roll_deg))
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    rotation_z = np.asarray(((cy, -sy, 0.0), (sy, cy, 0.0), (0.0, 0.0, 1.0)))
    rotation_y = np.asarray(((cp, 0.0, sp), (0.0, 1.0, 0.0), (-sp, 0.0, cp)))
    rotation_x = np.asarray(((1.0, 0.0, 0.0), (0.0, cr, -sr), (0.0, sr, cr)))
    return rotation_z @ rotation_y @ rotation_x


def propagate_source_state(
    cue: SourceCueRecord,
    timestamp: float,
    *,
    acceleration_sigma_mps2: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Constant-velocity propagation from measurement time to image time."""

    dt = float(timestamp) - float(cue.measurement_timestamp)
    if dt < -1.0e-9:
        raise ValueError("cannot propagate a source cue backward before its measurement")
    transition = np.eye(6, dtype=float)
    transition[:3, 3:] = np.eye(3, dtype=float) * dt
    state = np.concatenate(
        (np.asarray(cue.position_ned_m, dtype=float), np.asarray(cue.velocity_ned_mps, dtype=float))
    )
    propagated_state = transition @ state
    covariance = np.asarray(cue.covariance_6x6, dtype=float)
    if covariance.shape != (6, 6) or not np.all(np.isfinite(covariance)):
        raise ValueError("source covariance must be a finite 6 by 6 matrix")
    q = max(float(acceleration_sigma_mps2), 0.0) ** 2
    process = np.zeros((6, 6), dtype=float)
    if dt > 0.0 and q > 0.0:
        process[:3, :3] = np.eye(3) * q * dt**4 / 4.0
        process[:3, 3:] = np.eye(3) * q * dt**3 / 2.0
        process[3:, :3] = np.eye(3) * q * dt**3 / 2.0
        process[3:, 3:] = np.eye(3) * q * dt**2
    propagated_covariance = transition @ covariance @ transition.T + process
    propagated_covariance = (propagated_covariance + propagated_covariance.T) / 2.0
    return propagated_state, propagated_covariance


def project_source_cue(
    cue: SourceCueRecord,
    camera: CameraModel,
    timestamp: float,
    *,
    acceleration_sigma_mps2: float = 0.5,
    projection_noise_px: float = 1.0,
) -> ProjectedSourceCue:
    state, covariance = propagate_source_state(
        cue,
        timestamp,
        acceleration_sigma_mps2=acceleration_sigma_mps2,
    )
    position = state[:3]
    center = camera.project(position)
    jacobian = camera.projection_jacobian_ned(position)
    covariance_px = jacobian @ covariance[:3, :3] @ jacobian.T
    covariance_px += np.eye(2, dtype=float) * max(float(projection_noise_px), 1.0e-6) ** 2
    covariance_px = _regularize_covariance(covariance_px)
    velocity = state[3:]
    velocity_px = jacobian @ velocity
    depth = float(camera.world_to_camera(position)[0])
    return ProjectedSourceCue(
        source_track_id=cue.source_track_id,
        timestamp=float(timestamp),
        position_ned_m=tuple(float(value) for value in position),
        velocity_ned_mps=tuple(float(value) for value in velocity),
        state_covariance_6x6=tuple(tuple(float(value) for value in row) for row in covariance),
        center_px=tuple(float(value) for value in center),
        covariance_px2=tuple(tuple(float(value) for value in row) for row in covariance_px),
        velocity_px_s=tuple(float(value) for value in velocity_px),
        depth_m=depth,
    )


def camera_for_observation(base: CameraModel, origin_ned_m: tuple[float, float, float], yaw_pitch_roll_deg: tuple[float, float, float]) -> CameraModel:
    """Use the measured final camera pose as an equivalent zero-gimbal chain."""

    return CameraModel(
        camera_id=base.camera_id,
        intrinsics=base.intrinsics,
        body_position_ned_m=tuple(float(value) for value in origin_ned_m),
        body_yaw_pitch_roll_deg=tuple(float(value) for value in yaw_pitch_roll_deg),
        gimbal_yaw_pitch_roll_deg=(0.0, 0.0, 0.0),
        camera_offset_body_m=(0.0, 0.0, 0.0),
    )


def _regularize_covariance(value: np.ndarray, floor: float = 1.0e-6) -> np.ndarray:
    covariance = np.asarray(value, dtype=float)
    covariance = (covariance + covariance.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues, float(floor))
    return eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
