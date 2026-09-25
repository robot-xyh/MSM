"""NED-to-camera projection and covariance propagation for handover cues."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping, Sequence

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
    camera_yaw_pitch_roll_gimbal_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    gimbal_pivot_offset_body_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    camera_offset_gimbal_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    camera_offset_body_m: tuple[float, float, float] = (0.5, 0.0, 0.0)
    pose_representation: str = "decomposed_mount"

    def __post_init__(self) -> None:
        if not str(self.camera_id).strip():
            raise ValueError("camera_id must be non-empty")
        for value in (
            self.body_position_ned_m,
            self.body_yaw_pitch_roll_deg,
            self.gimbal_yaw_pitch_roll_deg,
            self.camera_yaw_pitch_roll_gimbal_deg,
            self.gimbal_pivot_offset_body_m,
            self.camera_offset_gimbal_m,
            self.camera_offset_body_m,
        ):
            if len(value) != 3 or not np.all(np.isfinite(value)):
                raise ValueError("camera pose components must contain three finite values")
        if self.pose_representation not in {
            "decomposed_mount",
            "composite_at_measurement_timestamp",
        }:
            raise ValueError("unsupported camera pose representation")

    @property
    def rotation_ned_from_body(self) -> np.ndarray:
        return yaw_pitch_roll_matrix(*self.body_yaw_pitch_roll_deg)

    @property
    def rotation_body_from_ned(self) -> np.ndarray:
        """R_B^N: NED coordinates to body coordinates."""

        return self.rotation_ned_from_body.T

    @property
    def rotation_body_from_gimbal(self) -> np.ndarray:
        return yaw_pitch_roll_matrix(*self.gimbal_yaw_pitch_roll_deg)

    @property
    def rotation_gimbal_from_body(self) -> np.ndarray:
        """R_G^B: body coordinates to gimbal coordinates."""

        return self.rotation_body_from_gimbal.T

    @property
    def rotation_gimbal_from_camera(self) -> np.ndarray:
        return yaw_pitch_roll_matrix(*self.camera_yaw_pitch_roll_gimbal_deg)

    @property
    def rotation_camera_from_gimbal(self) -> np.ndarray:
        """R_C^G: gimbal coordinates to camera coordinates."""

        return self.rotation_gimbal_from_camera.T

    @property
    def rotation_camera_from_ned(self) -> np.ndarray:
        """Complete R_C^G R_G^B R_B^N transform."""

        return (
            self.rotation_camera_from_gimbal
            @ self.rotation_gimbal_from_body
            @ self.rotation_body_from_ned
        )

    @property
    def rotation_ned_from_camera(self) -> np.ndarray:
        return self.rotation_camera_from_ned.T

    @property
    def camera_position_ned_m(self) -> np.ndarray:
        body_origin = np.asarray(self.body_position_ned_m, dtype=float)
        body_fixed_offset = np.asarray(self.camera_offset_body_m, dtype=float)
        gimbal_pivot_offset = np.asarray(self.gimbal_pivot_offset_body_m, dtype=float)
        optical_offset = np.asarray(self.camera_offset_gimbal_m, dtype=float)
        return body_origin + self.rotation_ned_from_body @ (
            body_fixed_offset
            + gimbal_pivot_offset
            + self.rotation_body_from_gimbal @ optical_offset
        )

    def world_to_camera(self, point_ned_m: np.ndarray) -> np.ndarray:
        delta_ned = np.asarray(point_ned_m, dtype=float) - self.camera_position_ned_m
        return self.rotation_camera_from_ned @ delta_ned

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
        return jacobian_camera @ self.rotation_camera_from_ned

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
            camera_yaw_pitch_roll_gimbal_deg=tuple(
                float(item)
                for item in value.get("camera_yaw_pitch_roll_gimbal_deg", (0.0, 0.0, 0.0))
            ),
            gimbal_pivot_offset_body_m=tuple(
                float(item)
                for item in value.get("gimbal_pivot_offset_body_m", (0.0, 0.0, 0.0))
            ),
            camera_offset_gimbal_m=tuple(
                float(item)
                for item in value.get("camera_offset_gimbal_m", (0.0, 0.0, 0.0))
            ),
            camera_offset_body_m=tuple(
                float(item) for item in value.get("camera_offset_body_m", (0.5, 0.0, 0.0))
            ),
            pose_representation=str(value.get("pose_representation", "decomposed_mount")),
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


class PoseInterpolationError(ValueError):
    """Raised when measurement-time platform/gimbal pose cannot be recovered."""


@dataclass(frozen=True)
class TimedCameraPose:
    measurement_timestamp: float
    arrival_timestamp: float
    body_position_ned_m: tuple[float, float, float]
    body_yaw_pitch_roll_deg: tuple[float, float, float]
    gimbal_yaw_pitch_roll_deg: tuple[float, float, float]

    def __post_init__(self) -> None:
        if self.arrival_timestamp < self.measurement_timestamp:
            raise ValueError("pose arrival_timestamp cannot precede measurement_timestamp")
        values = (
            self.body_position_ned_m,
            self.body_yaw_pitch_roll_deg,
            self.gimbal_yaw_pitch_roll_deg,
        )
        if any(len(value) != 3 or not np.all(np.isfinite(value)) for value in values):
            raise ValueError("timed pose components must contain three finite values")


@dataclass(frozen=True)
class ProjectionUncertainty:
    """Uncertainty blocks used by measurement-time projection and ray creation."""

    navigation_position_covariance_m2: tuple[tuple[float, ...], ...] = (
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    )
    body_attitude_covariance_rad2: tuple[tuple[float, ...], ...] = (
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    )
    gimbal_angle_covariance_rad2: tuple[tuple[float, ...], ...] = (
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    )
    pixel_center_covariance_px2: tuple[tuple[float, ...], ...] = (
        (0.0, 0.0),
        (0.0, 0.0),
    )

    def covariance_blocks(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        blocks = (
            np.asarray(self.navigation_position_covariance_m2, dtype=float),
            np.asarray(self.body_attitude_covariance_rad2, dtype=float),
            np.asarray(self.gimbal_angle_covariance_rad2, dtype=float),
            np.asarray(self.pixel_center_covariance_px2, dtype=float),
        )
        for block, shape in zip(blocks, ((3, 3), (3, 3), (3, 3), (2, 2)), strict=True):
            if block.shape != shape or not np.all(np.isfinite(block)):
                raise ValueError("projection uncertainty block has an invalid shape")
            if np.min(np.linalg.eigvalsh((block + block.T) / 2.0)) < -1.0e-10:
                raise ValueError("projection uncertainty must be positive semidefinite")
        return blocks


def yaw_pitch_roll_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    yaw, pitch, roll = (math.radians(float(value)) for value in (yaw_deg, pitch_deg, roll_deg))
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    rotation_z = np.asarray(((cy, -sy, 0.0), (sy, cy, 0.0), (0.0, 0.0, 1.0)))
    rotation_y = np.asarray(((cp, 0.0, sp), (0.0, 1.0, 0.0), (-sp, 0.0, cp)))
    rotation_x = np.asarray(((1.0, 0.0, 0.0), (0.0, cr, -sr), (0.0, sr, cr)))
    return rotation_z @ rotation_y @ rotation_x


def yaw_pitch_roll_from_matrix(rotation: np.ndarray) -> tuple[float, float, float]:
    """Recover yaw, pitch and roll from ``Rz(yaw) Ry(pitch) Rx(roll)``."""

    value = np.asarray(rotation, dtype=float)
    if value.shape != (3, 3) or not np.all(np.isfinite(value)):
        raise ValueError("rotation must be a finite 3 by 3 matrix")
    sin_pitch = min(max(-float(value[2, 0]), -1.0), 1.0)
    pitch = math.asin(sin_pitch)
    cos_pitch = math.cos(pitch)
    if abs(cos_pitch) > 1.0e-8:
        yaw = math.atan2(float(value[1, 0]), float(value[0, 0]))
        roll = math.atan2(float(value[2, 1]), float(value[2, 2]))
    else:
        yaw = math.atan2(-float(value[0, 1]), float(value[1, 1]))
        roll = 0.0
    return tuple(math.degrees(item) for item in (yaw, pitch, roll))


def _interpolate_angle_deg(start: float, end: float, fraction: float) -> float:
    delta = (float(end) - float(start) + 180.0) % 360.0 - 180.0
    return float(start) + fraction * delta


def interpolate_camera_pose_at_measurement(
    base: CameraModel,
    samples: Sequence[TimedCameraPose],
    measurement_timestamp: float,
    *,
    maximum_bracket_gap_s: float = 0.2,
) -> CameraModel:
    """Interpolate body and gimbal pose at image measurement time.

    Arrival timestamps are deliberately ignored here. They may be checked for
    freshness, but using them as the pose epoch would shift a moving camera.
    """

    if maximum_bracket_gap_s <= 0.0:
        raise ValueError("maximum_bracket_gap_s must be positive")
    ordered = sorted(samples, key=lambda item: item.measurement_timestamp)
    timestamp = float(measurement_timestamp)
    exact = [item for item in ordered if abs(item.measurement_timestamp - timestamp) <= 1.0e-9]
    if exact:
        before = after = exact[-1]
    else:
        before_values = [item for item in ordered if item.measurement_timestamp < timestamp]
        after_values = [item for item in ordered if item.measurement_timestamp > timestamp]
        if not before_values or not after_values:
            raise PoseInterpolationError("pose samples do not bracket measurement_timestamp")
        before, after = before_values[-1], after_values[0]
        if timestamp - before.measurement_timestamp > maximum_bracket_gap_s:
            raise PoseInterpolationError("pose sample before image exceeds interpolation limit")
        if after.measurement_timestamp - timestamp > maximum_bracket_gap_s:
            raise PoseInterpolationError("pose sample after image exceeds interpolation limit")
    span = after.measurement_timestamp - before.measurement_timestamp
    fraction = 0.0 if abs(span) <= 1.0e-12 else (timestamp - before.measurement_timestamp) / span
    position = tuple(
        float(left) + fraction * (float(right) - float(left))
        for left, right in zip(
            before.body_position_ned_m,
            after.body_position_ned_m,
            strict=True,
        )
    )
    body_angles = tuple(
        _interpolate_angle_deg(left, right, fraction)
        for left, right in zip(
            before.body_yaw_pitch_roll_deg,
            after.body_yaw_pitch_roll_deg,
            strict=True,
        )
    )
    gimbal_angles = tuple(
        _interpolate_angle_deg(left, right, fraction)
        for left, right in zip(
            before.gimbal_yaw_pitch_roll_deg,
            after.gimbal_yaw_pitch_roll_deg,
            strict=True,
        )
    )
    return CameraModel(
        camera_id=base.camera_id,
        intrinsics=base.intrinsics,
        body_position_ned_m=position,
        body_yaw_pitch_roll_deg=body_angles,
        gimbal_yaw_pitch_roll_deg=gimbal_angles,
        camera_yaw_pitch_roll_gimbal_deg=base.camera_yaw_pitch_roll_gimbal_deg,
        gimbal_pivot_offset_body_m=base.gimbal_pivot_offset_body_m,
        camera_offset_gimbal_m=base.camera_offset_gimbal_m,
        camera_offset_body_m=base.camera_offset_body_m,
        pose_representation="decomposed_mount",
    )


def validate_arrival_freshness(
    measurement_timestamp: float,
    arrival_timestamp: float,
    *,
    maximum_latency_s: float,
) -> None:
    if maximum_latency_s < 0.0:
        raise ValueError("maximum_latency_s cannot be negative")
    latency = float(arrival_timestamp) - float(measurement_timestamp)
    if latency < -1.0e-9:
        raise ValueError("arrival_timestamp cannot precede measurement_timestamp")
    if latency > maximum_latency_s:
        raise PoseInterpolationError("measurement arrived after the freshness limit")


def _block_diagonal(blocks: Sequence[np.ndarray]) -> np.ndarray:
    size = sum(block.shape[0] for block in blocks)
    result = np.zeros((size, size), dtype=float)
    cursor = 0
    for block in blocks:
        rows = block.shape[0]
        result[cursor : cursor + rows, cursor : cursor + rows] = block
        cursor += rows
    return result


def _central_difference_jacobian(
    function: Any,
    state: np.ndarray,
    steps: np.ndarray,
) -> np.ndarray:
    baseline = np.asarray(function(state), dtype=float)
    jacobian = np.zeros((baseline.size, state.size), dtype=float)
    for index, step in enumerate(steps):
        if step <= 0.0:
            raise ValueError("finite-difference steps must be positive")
        plus = state.copy()
        minus = state.copy()
        plus[index] += step
        minus[index] -= step
        jacobian[:, index] = (
            np.asarray(function(plus), dtype=float)
            - np.asarray(function(minus), dtype=float)
        ) / (2.0 * step)
    return jacobian


def _camera_from_joint_state(base: CameraModel, state: np.ndarray) -> CameraModel:
    return CameraModel(
        camera_id=base.camera_id,
        intrinsics=base.intrinsics,
        body_position_ned_m=tuple(float(value) for value in state[3:6]),
        body_yaw_pitch_roll_deg=tuple(math.degrees(float(value)) for value in state[6:9]),
        gimbal_yaw_pitch_roll_deg=tuple(math.degrees(float(value)) for value in state[9:12]),
        camera_yaw_pitch_roll_gimbal_deg=base.camera_yaw_pitch_roll_gimbal_deg,
        gimbal_pivot_offset_body_m=base.gimbal_pivot_offset_body_m,
        camera_offset_gimbal_m=base.camera_offset_gimbal_m,
        camera_offset_body_m=base.camera_offset_body_m,
        pose_representation="decomposed_mount",
    )


def joint_projection_covariance(
    camera: CameraModel,
    target_position_ned_m: Sequence[float],
    target_position_covariance_m2: np.ndarray,
    uncertainty: ProjectionUncertainty,
) -> np.ndarray:
    """Propagate target, navigation, attitude, gimbal, and pixel error to image."""

    target_covariance = np.asarray(target_position_covariance_m2, dtype=float)
    if target_covariance.shape != (3, 3):
        raise ValueError("target position covariance must be 3 by 3")
    navigation, body_attitude, gimbal_attitude, pixel = uncertainty.covariance_blocks()
    state = np.asarray(
        (
            *target_position_ned_m,
            *camera.body_position_ned_m,
            *(math.radians(value) for value in camera.body_yaw_pitch_roll_deg),
            *(math.radians(value) for value in camera.gimbal_yaw_pitch_roll_deg),
            0.0,
            0.0,
        ),
        dtype=float,
    )

    def project(value: np.ndarray) -> np.ndarray:
        model = _camera_from_joint_state(camera, value)
        return model.project(value[:3], require_in_frame=False) + value[12:14]

    steps = np.asarray((1.0e-3,) * 6 + (1.0e-6,) * 6 + (1.0e-3,) * 2)
    jacobian = _central_difference_jacobian(project, state, steps)
    covariance = _block_diagonal(
        (target_covariance, navigation, body_attitude, gimbal_attitude, pixel)
    )
    return _regularize_covariance(jacobian @ covariance @ jacobian.T)


def linearized_joint_projection_covariance(
    camera: CameraModel,
    target_position_ned_m: Sequence[float],
    target_position_covariance_m2: np.ndarray,
    uncertainty: ProjectionUncertainty,
) -> np.ndarray:
    """First-order covariance propagation for large association matrices.

    This path retains target, navigation, body-attitude, gimbal-angle and pixel
    terms while avoiding a numerical Jacobian for every source-local edge.
    Installation-offset rotation is neglected in the attitude term; at the
    documented sub-meter mount offset and roughly 700 m handover range that
    contribution is immaterial compared with navigation and boresight error.
    """

    target_covariance = np.asarray(target_position_covariance_m2, dtype=float)
    if target_covariance.shape != (3, 3):
        raise ValueError("target position covariance must be 3 by 3")
    navigation, body_attitude, gimbal_attitude, pixel = uncertainty.covariance_blocks()
    position = np.asarray(target_position_ned_m, dtype=float)
    point_camera = camera.world_to_camera(position)
    forward, right, down = (float(value) for value in point_camera)
    if forward <= 1.0e-6:
        raise ProjectionError("point is behind the camera")
    fx = camera.intrinsics.focal_x_px
    fy = camera.intrinsics.focal_y_px
    jacobian_camera = np.asarray(
        (
            (-fx * right / forward**2, fx / forward, 0.0),
            (-fy * down / forward**2, 0.0, fy / forward),
        ),
        dtype=float,
    )
    jacobian_ned = jacobian_camera @ camera.rotation_camera_from_ned
    position_covariance = jacobian_ned @ (
        target_covariance + navigation
    ) @ jacobian_ned.T

    skew_point = np.asarray(
        (
            (0.0, -down, right),
            (down, 0.0, -forward),
            (-right, forward, 0.0),
        ),
        dtype=float,
    )
    # Stored attitude blocks follow the public yaw, pitch, roll contract while
    # infinitesimal rotation vectors use x-roll, y-pitch, z-yaw order.
    axis_order = np.asarray((2, 1, 0), dtype=int)
    body_rotation_covariance = body_attitude[np.ix_(axis_order, axis_order)]
    gimbal_rotation_covariance = gimbal_attitude[np.ix_(axis_order, axis_order)]
    body_camera_covariance = (
        camera.rotation_camera_from_ned
        @ body_rotation_covariance
        @ camera.rotation_camera_from_ned.T
    )
    gimbal_camera_covariance = (
        camera.rotation_camera_from_gimbal
        @ gimbal_rotation_covariance
        @ camera.rotation_camera_from_gimbal.T
    )
    attitude_jacobian = jacobian_camera @ skew_point
    attitude_covariance = attitude_jacobian @ (
        body_camera_covariance + gimbal_camera_covariance
    ) @ attitude_jacobian.T
    return _regularize_covariance(position_covariance + attitude_covariance + pixel)


def world_ray_with_covariance(
    camera: CameraModel,
    center_px: tuple[float, float],
    uncertainty: ProjectionUncertainty,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return optical-center origin, NED ray, and their joint 6x6 covariance."""

    navigation, body_attitude, gimbal_attitude, pixel = uncertainty.covariance_blocks()
    state = np.asarray(
        (
            0.0,
            0.0,
            0.0,
            *camera.body_position_ned_m,
            *(math.radians(value) for value in camera.body_yaw_pitch_roll_deg),
            *(math.radians(value) for value in camera.gimbal_yaw_pitch_roll_deg),
            *center_px,
        ),
        dtype=float,
    )

    def ray(value: np.ndarray) -> np.ndarray:
        model = _camera_from_joint_state(camera, value)
        return np.concatenate(
            (model.camera_position_ned_m, model.pixel_to_world_ray(tuple(value[12:14])))
        )

    steps = np.asarray((1.0e-3,) * 6 + (1.0e-6,) * 6 + (1.0e-3,) * 2)
    jacobian = _central_difference_jacobian(ray, state, steps)
    zero_target = np.zeros((3, 3), dtype=float)
    covariance = _block_diagonal(
        (zero_target, navigation, body_attitude, gimbal_attitude, pixel)
    )
    output_covariance = (jacobian @ covariance @ jacobian.T)
    output_covariance = (output_covariance + output_covariance.T) / 2.0
    return ray(state)[:3], ray(state)[3:], output_covariance


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
    uncertainty: ProjectionUncertainty | None = None,
    require_in_frame: bool = True,
    uncertainty_method: str = "numerical",
) -> ProjectedSourceCue:
    state, covariance = propagate_source_state(
        cue,
        timestamp,
        acceleration_sigma_mps2=acceleration_sigma_mps2,
    )
    position = state[:3]
    center = camera.project(position, require_in_frame=require_in_frame)
    jacobian = camera.projection_jacobian_ned(position)
    if uncertainty is None:
        covariance_px = jacobian @ covariance[:3, :3] @ jacobian.T
    elif uncertainty_method == "numerical":
        covariance_px = joint_projection_covariance(
            camera,
            position,
            covariance[:3, :3],
            uncertainty,
        )
    elif uncertainty_method == "linearized":
        covariance_px = linearized_joint_projection_covariance(
            camera,
            position,
            covariance[:3, :3],
            uncertainty,
        )
    else:
        raise ValueError("uncertainty_method must be numerical or linearized")
    covariance_px += (
        np.eye(2, dtype=float)
        * max(float(projection_noise_px), 1.0e-6) ** 2
    )
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


def projection_support_intersects_image(
    center_px: Sequence[float],
    covariance_px2: np.ndarray,
    intrinsics: CameraIntrinsics,
    *,
    sigma_scale: float = 2.447746830680816,
) -> bool:
    """Return whether an axis-aligned bound of the error ellipse reaches the image.

    ``sigma_scale`` defaults to the square root of the 95% two-dimensional
    chi-square threshold. The bound is deliberately conservative: it keeps a
    candidate when its projected mean is just outside the frame but the stated
    pose uncertainty still covers observable pixels.
    """

    if sigma_scale <= 0.0:
        raise ValueError("sigma_scale must be positive")
    center = np.asarray(center_px, dtype=float)
    covariance = _regularize_covariance(np.asarray(covariance_px2, dtype=float))
    if center.shape != (2,) or covariance.shape != (2, 2):
        raise ValueError("projection support requires a 2D center and 2 by 2 covariance")
    half_extent = float(sigma_scale) * np.sqrt(np.maximum(np.diag(covariance), 0.0))
    lower = center - half_extent
    upper = center + half_extent
    return bool(
        upper[0] >= 0.0
        and lower[0] < intrinsics.width_px
        and upper[1] >= 0.0
        and lower[1] < intrinsics.height_px
    )


def camera_for_observation(base: CameraModel, origin_ned_m: tuple[float, float, float], yaw_pitch_roll_deg: tuple[float, float, float]) -> CameraModel:
    """Use the measured final camera pose as an equivalent zero-gimbal chain."""

    return CameraModel(
        camera_id=base.camera_id,
        intrinsics=base.intrinsics,
        body_position_ned_m=tuple(float(value) for value in origin_ned_m),
        body_yaw_pitch_roll_deg=tuple(float(value) for value in yaw_pitch_roll_deg),
        gimbal_yaw_pitch_roll_deg=(0.0, 0.0, 0.0),
        camera_yaw_pitch_roll_gimbal_deg=(0.0, 0.0, 0.0),
        gimbal_pivot_offset_body_m=(0.0, 0.0, 0.0),
        camera_offset_gimbal_m=(0.0, 0.0, 0.0),
        camera_offset_body_m=(0.0, 0.0, 0.0),
        pose_representation="composite_at_measurement_timestamp",
    )


def _regularize_covariance(value: np.ndarray, floor: float = 1.0e-6) -> np.ndarray:
    covariance = np.asarray(value, dtype=float)
    covariance = (covariance + covariance.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues, float(floor))
    return eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
