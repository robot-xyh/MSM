"""Optional delivery-style 6D LOS Kalman filter for offline replay only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .vision_png import PngGuidanceConfig, VisionGuidanceObservation


LOS_6D_REPLAY_BOUNDARY = "d7_optional_replay_only_no_online_guidance_authority"


@dataclass(frozen=True)
class Los6DReplayConfig:
    process_lambda: float = 1.0e-4
    process_lambda_dot: float = 5.0e-3
    measurement_noise: float = 5.0e-3
    innovation_reject: float = 0.25
    max_attitude_sync_error_s: float = 0.05


@dataclass(frozen=True)
class Los6DReplayEstimate:
    available: bool
    reason: str
    timestamp_s: float | None = None
    lambda_ned: tuple[float, float, float] | None = None
    lambda_dot_ned: tuple[float, float, float] | None = None
    omega_los_ned: tuple[float, float, float] | None = None
    innovation_norm: float | None = None
    quality: float = 0.0
    local_track_id: str | None = None
    reset: bool = False
    boundary: str = LOS_6D_REPLAY_BOUNDARY


class OptionalLos6DKalmanReplay:
    """Replay backend requiring exposure time, extrinsics and synchronized attitude."""

    def __init__(
        self,
        png_config: PngGuidanceConfig | None = None,
        config: Los6DReplayConfig | None = None,
    ) -> None:
        self.png_config = png_config or PngGuidanceConfig()
        self.config = config or Los6DReplayConfig()
        self.reset()

    def reset(self) -> None:
        self.x = np.zeros(6, dtype=float)
        self.x[2] = 1.0
        self.P = np.eye(6, dtype=float)
        self.initialized = False
        self.last_timestamp_s: float | None = None
        self.local_track_id: str | None = None

    def evaluate(self, observation: VisionGuidanceObservation) -> Los6DReplayEstimate:
        exposure_timestamp_s = observation.frame_timestamp_s
        if exposure_timestamp_s is None:
            return self._unavailable("exposure_timestamp_missing", observation)
        metadata = observation.metadata
        camera_to_ned = _rotation_from_metadata(metadata, "camera_to_ned_rotation")
        if camera_to_ned is None:
            camera_to_body = _rotation_from_metadata(metadata, "camera_to_body_rotation")
            body_to_ned = _rotation_from_metadata(metadata, "body_to_ned_rotation")
            if camera_to_body is None or body_to_ned is None:
                return self._unavailable("camera_to_ned_rotation_unavailable", observation)
            camera_to_ned = body_to_ned @ camera_to_body
        attitude_timestamp_s = _timestamp_from_metadata(metadata)
        if attitude_timestamp_s is None:
            return self._unavailable("attitude_timestamp_missing", observation)
        if abs(attitude_timestamp_s - float(exposure_timestamp_s)) > self.config.max_attitude_sync_error_s:
            return self._unavailable("attitude_timestamp_unsynchronized", observation)

        ray_camera = self._camera_ray(observation)
        lambda_ned = _normalize(camera_to_ned @ ray_camera)
        reset = False
        if self.local_track_id is not None and observation.local_track_id != self.local_track_id:
            self.reset()
            reset = True
        self.local_track_id = observation.local_track_id
        return self._update(
            float(exposure_timestamp_s),
            lambda_ned,
            observation,
            reset=reset,
        )

    def _camera_ray(self, observation: VisionGuidanceObservation) -> np.ndarray:
        center_x, center_y = observation.center_px
        cfg = self.png_config
        return _normalize(
            np.array(
                [
                    (center_x - 0.5 * cfg.image_width_px) / cfg.focal_length_px,
                    (center_y - 0.5 * cfg.image_height_px) / cfg.focal_length_px,
                    1.0,
                ],
                dtype=float,
            )
        )

    def _update(
        self,
        timestamp_s: float,
        lambda_measured: np.ndarray,
        observation: VisionGuidanceObservation,
        *,
        reset: bool,
    ) -> Los6DReplayEstimate:
        if not self.initialized:
            self.x[:3] = lambda_measured
            self.x[3:] = 0.0
            self.P = np.eye(6, dtype=float)
            self.initialized = True
            self.last_timestamp_s = timestamp_s
            return self._estimate(timestamp_s, 0.0, 1.0, observation, reset=reset)

        dt = max(1.0e-3, timestamp_s - float(self.last_timestamp_s or timestamp_s))
        self.last_timestamp_s = timestamp_s
        transition = np.eye(6, dtype=float)
        transition[:3, 3:] = dt * np.eye(3)
        process_noise = np.diag(
            [
                self.config.process_lambda,
                self.config.process_lambda,
                self.config.process_lambda,
                self.config.process_lambda_dot,
                self.config.process_lambda_dot,
                self.config.process_lambda_dot,
            ]
        )
        self.x = transition @ self.x
        self.P = transition @ self.P @ transition.T + process_noise
        self._apply_constraints()

        measurement = np.zeros((3, 6), dtype=float)
        measurement[:, :3] = np.eye(3)
        innovation = lambda_measured - measurement @ self.x
        innovation_norm = float(np.linalg.norm(innovation))
        if innovation_norm > self.config.innovation_reject:
            return self._unavailable(
                "los_innovation_reject",
                observation,
                timestamp_s=timestamp_s,
                innovation_norm=innovation_norm,
            )
        residual_covariance = (
            measurement @ self.P @ measurement.T
            + self.config.measurement_noise * np.eye(3)
        )
        gain = self.P @ measurement.T @ np.linalg.inv(residual_covariance)
        self.x = self.x + gain @ innovation
        self.P = (np.eye(6) - gain @ measurement) @ self.P
        self._apply_constraints()
        quality = max(
            0.0,
            1.0 - innovation_norm / max(1.0e-9, self.config.innovation_reject),
        )
        return self._estimate(
            timestamp_s,
            innovation_norm,
            quality,
            observation,
            reset=reset,
        )

    def _apply_constraints(self) -> None:
        line_of_sight = _normalize(self.x[:3])
        line_of_sight_rate = self.x[3:] - float(np.dot(self.x[3:], line_of_sight)) * line_of_sight
        self.x[:3] = line_of_sight
        self.x[3:] = line_of_sight_rate

    def _estimate(
        self,
        timestamp_s: float,
        innovation_norm: float,
        quality: float,
        observation: VisionGuidanceObservation,
        *,
        reset: bool,
    ) -> Los6DReplayEstimate:
        line_of_sight = _normalize(self.x[:3])
        line_of_sight_rate = self.x[3:] - float(np.dot(self.x[3:], line_of_sight)) * line_of_sight
        omega = np.cross(line_of_sight, line_of_sight_rate)
        return Los6DReplayEstimate(
            available=True,
            reason="los_6d_replay_available",
            timestamp_s=timestamp_s,
            lambda_ned=tuple(float(value) for value in line_of_sight),
            lambda_dot_ned=tuple(float(value) for value in line_of_sight_rate),
            omega_los_ned=tuple(float(value) for value in omega),
            innovation_norm=innovation_norm,
            quality=quality,
            local_track_id=observation.local_track_id,
            reset=reset,
        )

    @staticmethod
    def _unavailable(
        reason: str,
        observation: VisionGuidanceObservation,
        *,
        timestamp_s: float | None = None,
        innovation_norm: float | None = None,
    ) -> Los6DReplayEstimate:
        return Los6DReplayEstimate(
            available=False,
            reason=reason,
            timestamp_s=timestamp_s,
            innovation_norm=innovation_norm,
            local_track_id=observation.local_track_id,
        )


def _rotation_from_metadata(metadata: Mapping[str, Any], key: str) -> np.ndarray | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        rotation = np.asarray(value, dtype=float).reshape(3, 3)
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(rotation)):
        return None
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1.0e-3):
        return None
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=1.0e-3):
        return None
    return rotation


def _timestamp_from_metadata(metadata: Mapping[str, Any]) -> float | None:
    for key in (
        "attitude_timestamp_s",
        "attitude_timestamp",
        "camera_pose_timestamp_s",
        "camera_pose_timestamp",
    ):
        timestamp = _optional_float(metadata.get(key))
        if timestamp is not None:
            return timestamp
    return None


def _normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=float).reshape(3)
    norm = float(np.linalg.norm(vector))
    if norm <= 1.0e-12 or not np.isfinite(norm):
        raise ValueError("cannot normalize invalid LOS vector")
    return vector / norm


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None
