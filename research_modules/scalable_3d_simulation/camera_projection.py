"""Vectorized pinhole projection and covariance propagation for NED points."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


_EPS = 1.0e-12


@dataclass(frozen=True)
class CameraIntrinsics:
    """Pinhole intrinsics in pixels."""

    width_px: int
    height_px: int
    fx: float
    fy: float
    cx: float
    cy: float

    def __post_init__(self) -> None:
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("image dimensions must be positive")
        values = np.array([self.fx, self.fy, self.cx, self.cy], dtype=float)
        if not np.all(np.isfinite(values)) or self.fx <= 0.0 or self.fy <= 0.0:
            raise ValueError("camera intrinsics must be finite with positive focal lengths")

    @classmethod
    def from_horizontal_fov(
        cls,
        *,
        width_px: int,
        height_px: int,
        horizontal_fov_deg: float,
    ) -> "CameraIntrinsics":
        if not 1.0 < float(horizontal_fov_deg) < 179.0:
            raise ValueError("horizontal_fov_deg must be in (1, 179)")
        fx = 0.5 * float(width_px) / math.tan(math.radians(horizontal_fov_deg) * 0.5)
        return cls(
            width_px=int(width_px),
            height_px=int(height_px),
            fx=fx,
            fy=fx,
            cx=(float(width_px) - 1.0) * 0.5,
            cy=(float(height_px) - 1.0) * 0.5,
        )

    def matrix(self) -> np.ndarray:
        return np.array(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=float,
        )


@dataclass(frozen=True)
class CameraPose:
    """Camera center and rotation from NED into the optical frame.

    The optical frame uses x right, y down, and z forward.
    """

    position_ned: np.ndarray
    rotation_camera_from_ned: np.ndarray
    position_covariance_ned: np.ndarray | None = None
    attitude_covariance_rad2: np.ndarray | None = None

    def __post_init__(self) -> None:
        position = np.asarray(self.position_ned, dtype=float).reshape(3)
        rotation = np.asarray(self.rotation_camera_from_ned, dtype=float)
        if rotation.shape != (3, 3):
            raise ValueError("rotation_camera_from_ned must have shape (3, 3)")
        if not np.all(np.isfinite(position)) or not np.all(np.isfinite(rotation)):
            raise ValueError("camera pose must contain only finite values")
        if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1.0e-7):
            raise ValueError("rotation_camera_from_ned must be orthonormal")
        if np.linalg.det(rotation) < 0.999999:
            raise ValueError("rotation_camera_from_ned must be a proper rotation")
        position_covariance = _covariance_or_zero(self.position_covariance_ned, "position")
        attitude_covariance = _covariance_or_zero(self.attitude_covariance_rad2, "attitude")
        object.__setattr__(self, "position_ned", position.copy())
        object.__setattr__(self, "rotation_camera_from_ned", rotation.copy())
        object.__setattr__(self, "position_covariance_ned", position_covariance)
        object.__setattr__(self, "attitude_covariance_rad2", attitude_covariance)


@dataclass(frozen=True)
class ProjectionBatch:
    """Projection results for one camera and a batch of world points."""

    camera_points: np.ndarray
    pixel_centers: np.ndarray
    bbox_xyxy: np.ndarray
    covariance_pixels: np.ndarray
    visible: np.ndarray
    depth_m: np.ndarray

    def __post_init__(self) -> None:
        count = np.asarray(self.camera_points).shape[0]
        expected = {
            "camera_points": (count, 3),
            "pixel_centers": (count, 2),
            "bbox_xyxy": (count, 4),
            "covariance_pixels": (count, 2, 2),
            "visible": (count,),
            "depth_m": (count,),
        }
        for name, shape in expected.items():
            if np.asarray(getattr(self, name)).shape != shape:
                raise ValueError(f"{name} must have shape {shape}")


def look_at_rotation_ned_to_camera(
    camera_position_ned: np.ndarray,
    target_position_ned: np.ndarray,
) -> np.ndarray:
    """Build a proper NED-to-optical rotation aimed at a world point."""

    camera = np.asarray(camera_position_ned, dtype=float).reshape(3)
    target = np.asarray(target_position_ned, dtype=float).reshape(3)
    forward = target - camera
    norm = float(np.linalg.norm(forward))
    if norm <= _EPS:
        raise ValueError("camera and target positions must differ")
    forward /= norm

    ned_down = np.array([0.0, 0.0, 1.0], dtype=float)
    right = np.cross(ned_down, forward)
    if np.linalg.norm(right) <= 1.0e-8:
        # Straight-down/up views use east as image right and north/south as image down.
        fallback_down = np.array([-1.0, 0.0, 0.0], dtype=float)
        right = np.cross(fallback_down, forward)
    right /= max(float(np.linalg.norm(right)), _EPS)
    image_down = np.cross(forward, right)
    image_down /= max(float(np.linalg.norm(image_down)), _EPS)
    rotation = np.vstack((right, image_down, forward))
    if np.linalg.det(rotation) < 0.0:
        rotation[0] *= -1.0
        rotation[1] = np.cross(rotation[2], rotation[0])
    return rotation


def project_points(
    points_ned: np.ndarray,
    *,
    camera_pose: CameraPose,
    intrinsics: CameraIntrinsics,
    point_covariance_ned: np.ndarray | None = None,
    object_size_m: np.ndarray | tuple[float, float] = (1.0, 1.0),
    pixel_noise_std: float = 1.0,
    minimum_depth_m: float = 0.1,
) -> ProjectionBatch:
    """Project NED points and propagate position uncertainty into image pixels."""

    points = np.asarray(points_ned, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points_ned must have shape (point_count, 3)")
    if not np.all(np.isfinite(points)):
        raise ValueError("points_ned must contain only finite values")
    if pixel_noise_std < 0.0 or minimum_depth_m <= 0.0:
        raise ValueError("pixel noise must be non-negative and minimum depth positive")
    count = points.shape[0]
    point_covariance = _point_covariances(point_covariance_ned, count)
    object_sizes = _object_sizes(object_size_m, count)

    delta_ned = points - camera_pose.position_ned[None, :]
    camera_points = delta_ned @ camera_pose.rotation_camera_from_ned.T
    depth = camera_points[:, 2]
    in_front = depth > float(minimum_depth_m)
    safe_depth = np.where(in_front, depth, 1.0)
    pixel_centers = np.full((count, 2), np.nan, dtype=float)
    pixel_centers[:, 0] = intrinsics.fx * camera_points[:, 0] / safe_depth + intrinsics.cx
    pixel_centers[:, 1] = intrinsics.fy * camera_points[:, 1] / safe_depth + intrinsics.cy

    projected_width = intrinsics.fx * object_sizes[:, 0] / safe_depth
    projected_height = intrinsics.fy * object_sizes[:, 1] / safe_depth
    bbox = np.column_stack(
        (
            pixel_centers[:, 0] - 0.5 * projected_width,
            pixel_centers[:, 1] - 0.5 * projected_height,
            pixel_centers[:, 0] + 0.5 * projected_width,
            pixel_centers[:, 1] + 0.5 * projected_height,
        )
    )
    visible = (
        in_front
        & (bbox[:, 2] >= 0.0)
        & (bbox[:, 0] < float(intrinsics.width_px))
        & (bbox[:, 3] >= 0.0)
        & (bbox[:, 1] < float(intrinsics.height_px))
    )

    covariance_pixels = np.full((count, 2, 2), np.nan, dtype=float)
    rotation = camera_pose.rotation_camera_from_ned
    pose_covariance = np.asarray(camera_pose.position_covariance_ned, dtype=float)
    attitude_variance = float(np.trace(camera_pose.attitude_covariance_rad2) / 3.0)
    focal_mean = 0.5 * (intrinsics.fx + intrinsics.fy)
    image_noise_variance = float(pixel_noise_std) ** 2 + focal_mean**2 * attitude_variance
    for index in np.flatnonzero(in_front):
        x_camera, y_camera, z_camera = camera_points[index]
        jacobian_camera = np.array(
            [
                [intrinsics.fx / z_camera, 0.0, -intrinsics.fx * x_camera / z_camera**2],
                [0.0, intrinsics.fy / z_camera, -intrinsics.fy * y_camera / z_camera**2],
            ],
            dtype=float,
        )
        jacobian_ned = jacobian_camera @ rotation
        spatial_covariance = point_covariance[index] + pose_covariance
        covariance = jacobian_ned @ spatial_covariance @ jacobian_ned.T
        covariance += np.eye(2, dtype=float) * image_noise_variance
        covariance_pixels[index] = 0.5 * (covariance + covariance.T)

    pixel_centers[~in_front] = np.nan
    bbox[~in_front] = np.nan
    return ProjectionBatch(
        camera_points=camera_points,
        pixel_centers=pixel_centers,
        bbox_xyxy=bbox,
        covariance_pixels=covariance_pixels,
        visible=visible,
        depth_m=depth,
    )


def _covariance_or_zero(value: np.ndarray | None, label: str) -> np.ndarray:
    covariance = np.zeros((3, 3), dtype=float) if value is None else np.asarray(value, dtype=float)
    if covariance.shape != (3, 3):
        raise ValueError(f"{label} covariance must have shape (3, 3)")
    if not np.all(np.isfinite(covariance)):
        raise ValueError(f"{label} covariance must contain only finite values")
    if np.min(np.linalg.eigvalsh(0.5 * (covariance + covariance.T))) < -1.0e-9:
        raise ValueError(f"{label} covariance must be positive semidefinite")
    return 0.5 * (covariance + covariance.T)


def _point_covariances(value: np.ndarray | None, count: int) -> np.ndarray:
    if value is None:
        return np.zeros((count, 3, 3), dtype=float)
    covariance = np.asarray(value, dtype=float)
    if covariance.shape == (3, 3):
        covariance = np.broadcast_to(covariance, (count, 3, 3)).copy()
    if covariance.shape != (count, 3, 3):
        raise ValueError("point_covariance_ned must have shape (3, 3) or (point_count, 3, 3)")
    if not np.all(np.isfinite(covariance)):
        raise ValueError("point covariance must contain only finite values")
    return covariance


def _object_sizes(value: np.ndarray | tuple[float, float], count: int) -> np.ndarray:
    sizes = np.asarray(value, dtype=float)
    if sizes.shape == (2,):
        sizes = np.broadcast_to(sizes, (count, 2)).copy()
    if sizes.shape != (count, 2):
        raise ValueError("object_size_m must have shape (2,) or (point_count, 2)")
    if not np.all(np.isfinite(sizes)) or np.any(sizes <= 0.0):
        raise ValueError("object sizes must be positive and finite")
    return sizes
