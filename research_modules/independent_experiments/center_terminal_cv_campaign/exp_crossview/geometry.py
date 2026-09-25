"""Pinhole projection, time alignment, ray intersection, and motion checks."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

from ..common.contracts import LocalVisualTrackRecord
from .config import CameraCalibration, CrossViewConfig


@dataclass(frozen=True)
class AlignedObservation:
    timestamp: float
    origin_a_ned_m: np.ndarray
    direction_a_ned: np.ndarray
    center_a_px: np.ndarray
    extent_a_px: float
    origin_b_ned_m: np.ndarray
    direction_b_ned: np.ndarray
    center_b_px: np.ndarray
    extent_b_px: float
    time_offset_s: float


@dataclass(frozen=True)
class RayIntersection:
    midpoint_ned_m: np.ndarray
    point_a_ned_m: np.ndarray
    point_b_ned_m: np.ndarray
    separation_m: float
    depth_a_m: float
    depth_b_m: float
    angle_deg: float


def normalize(values: Sequence[float]) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    magnitude = float(np.linalg.norm(vector))
    if not math.isfinite(magnitude) or magnitude <= 1.0e-12:
        raise ValueError("direction vector must be finite and non-zero")
    return vector / magnitude


def rotation_camera_to_ned(yaw_pitch_roll_deg: Sequence[float]) -> np.ndarray:
    """Return the AirSim camera/body rotation in NED.

    Camera x is forward, y is image-right, and z is image-down. The supplied
    tuple follows the common record order: yaw, pitch, roll.
    """

    yaw, pitch, roll = (math.radians(float(value)) for value in yaw_pitch_roll_deg)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    rz = np.asarray(((cy, -sy, 0.0), (sy, cy, 0.0), (0.0, 0.0, 1.0)))
    ry = np.asarray(((cp, 0.0, sp), (0.0, 1.0, 0.0), (-sp, 0.0, cp)))
    rx = np.asarray(((1.0, 0.0, 0.0), (0.0, cr, -sr), (0.0, sr, cr)))
    return rz @ ry @ rx


def pixel_to_world_ray(
    center_px: Sequence[float],
    calibration: CameraCalibration,
    yaw_pitch_roll_deg: Sequence[float],
) -> np.ndarray:
    u, v = (float(value) for value in center_px)
    direction_camera = normalize(
        (
            1.0,
            (u - calibration.cx_px) / calibration.fx_px,
            (v - calibration.cy_px) / calibration.fy_px,
        )
    )
    return normalize(rotation_camera_to_ned(yaw_pitch_roll_deg) @ direction_camera)


def project_world_point(
    point_ned_m: Sequence[float],
    origin_ned_m: Sequence[float],
    yaw_pitch_roll_deg: Sequence[float],
    calibration: CameraCalibration,
) -> tuple[float, float] | None:
    relative_ned = np.asarray(point_ned_m, dtype=float) - np.asarray(origin_ned_m, dtype=float)
    relative_camera = rotation_camera_to_ned(yaw_pitch_roll_deg).T @ relative_ned
    if relative_camera[0] <= 1.0e-6:
        return None
    return (
        float(calibration.cx_px + calibration.fx_px * relative_camera[1] / relative_camera[0]),
        float(calibration.cy_px + calibration.fy_px * relative_camera[2] / relative_camera[0]),
    )


def closest_ray_intersection(
    origin_a: Sequence[float],
    direction_a: Sequence[float],
    origin_b: Sequence[float],
    direction_b: Sequence[float],
) -> RayIntersection:
    oa = np.asarray(origin_a, dtype=float)
    ob = np.asarray(origin_b, dtype=float)
    da = normalize(direction_a)
    db = normalize(direction_b)
    cross_magnitude = float(np.linalg.norm(np.cross(da, db)))
    angle = math.degrees(math.asin(min(1.0, max(0.0, cross_magnitude))))
    dot = float(np.dot(da, db))
    denominator = 1.0 - dot * dot
    if denominator <= 1.0e-12:
        midpoint = (oa + ob) / 2.0
        return RayIntersection(midpoint, oa, ob, float(np.linalg.norm(oa - ob)), 0.0, 0.0, angle)
    delta = ob - oa
    depth_a = float((np.dot(delta, da) - dot * np.dot(delta, db)) / denominator)
    depth_b = float((dot * np.dot(delta, da) - np.dot(delta, db)) / denominator)
    point_a = oa + depth_a * da
    point_b = ob + depth_b * db
    return RayIntersection(
        midpoint_ned_m=(point_a + point_b) / 2.0,
        point_a_ned_m=point_a,
        point_b_ned_m=point_b,
        separation_m=float(np.linalg.norm(point_a - point_b)),
        depth_a_m=depth_a,
        depth_b_m=depth_b,
        angle_deg=angle,
    )


def propagate_ray_intersection_covariance(
    origin_a: Sequence[float],
    direction_a: Sequence[float],
    ray_a_covariance: np.ndarray,
    origin_b: Sequence[float],
    direction_b: Sequence[float],
    ray_b_covariance: np.ndarray,
    *,
    minimum_angle_deg: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Propagate two [origin, direction] covariances to the 3-D midpoint."""

    covariance_a = np.asarray(ray_a_covariance, dtype=float)
    covariance_b = np.asarray(ray_b_covariance, dtype=float)
    if covariance_a.shape != (6, 6) or covariance_b.shape != (6, 6):
        raise ValueError("ray covariance must be 6 by 6")
    state = np.concatenate(
        (
            np.asarray(origin_a, dtype=float),
            normalize(direction_a),
            np.asarray(origin_b, dtype=float),
            normalize(direction_b),
        )
    )
    nominal = closest_ray_intersection(state[:3], state[3:6], state[6:9], state[9:12])
    if nominal.angle_deg < minimum_angle_deg:
        raise ValueError("ray intersection angle is too small for covariance propagation")

    def midpoint(value: np.ndarray) -> np.ndarray:
        return closest_ray_intersection(
            value[:3], value[3:6], value[6:9], value[9:12]
        ).midpoint_ned_m

    steps = np.asarray((1.0e-3,) * 3 + (1.0e-6,) * 3 + (1.0e-3,) * 3 + (1.0e-6,) * 3)
    jacobian = np.zeros((3, 12), dtype=float)
    for index, step in enumerate(steps):
        plus = state.copy()
        minus = state.copy()
        plus[index] += step
        minus[index] -= step
        jacobian[:, index] = (midpoint(plus) - midpoint(minus)) / (2.0 * step)
    input_covariance = np.zeros((12, 12), dtype=float)
    input_covariance[:6, :6] = covariance_a
    input_covariance[6:, 6:] = covariance_b
    output_covariance = jacobian @ input_covariance @ jacobian.T
    output_covariance = (output_covariance + output_covariance.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(output_covariance)
    output_covariance = eigenvectors @ np.diag(np.maximum(eigenvalues, 0.0)) @ eigenvectors.T
    return nominal.midpoint_ned_m, output_covariance


def recognition_extent(record: LocalVisualTrackRecord) -> float:
    x1, y1, x2, y2 = (float(value) for value in record.bbox_xyxy)
    return max(x2 - x1, y2 - y1)


def validate_record_ray(
    record: LocalVisualTrackRecord,
    calibration: CameraCalibration,
    *,
    tolerance_deg: float = 0.25,
) -> np.ndarray:
    computed = pixel_to_world_ray(
        record.center_px,
        calibration,
        record.camera_yaw_pitch_roll_deg,
    )
    supplied = normalize(record.ray_direction_ned)
    angle = math.degrees(math.acos(float(np.clip(np.dot(computed, supplied), -1.0, 1.0))))
    if angle > tolerance_deg:
        raise ValueError(
            f"record ray disagrees with pinhole backprojection by {angle:.3f} deg"
        )
    return computed


def _interpolate_record(
    history: Sequence[LocalVisualTrackRecord],
    timestamp: float,
    calibration: CameraCalibration,
    maximum_offset_s: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float] | None:
    ordered = sorted(history, key=lambda item: item.measurement_timestamp)
    exact = min(ordered, key=lambda item: abs(item.measurement_timestamp - timestamp))
    nearest_offset = abs(exact.measurement_timestamp - timestamp)
    before = [item for item in ordered if item.measurement_timestamp <= timestamp]
    after = [item for item in ordered if item.measurement_timestamp >= timestamp]
    if before and after and before[-1] is not after[0]:
        left, right = before[-1], after[0]
        if max(timestamp - left.measurement_timestamp, right.measurement_timestamp - timestamp) <= maximum_offset_s:
            span = right.measurement_timestamp - left.measurement_timestamp
            fraction = 0.0 if span <= 1.0e-12 else (timestamp - left.measurement_timestamp) / span
            origin = (1.0 - fraction) * np.asarray(left.ray_origin_ned_m) + fraction * np.asarray(right.ray_origin_ned_m)
            center = (1.0 - fraction) * np.asarray(left.center_px) + fraction * np.asarray(right.center_px)
            extent = (1.0 - fraction) * recognition_extent(left) + fraction * recognition_extent(right)
            ray_left = validate_record_ray(left, calibration)
            ray_right = validate_record_ray(right, calibration)
            direction = normalize((1.0 - fraction) * ray_left + fraction * ray_right)
            return origin, direction, center, float(extent), 0.0
    if nearest_offset <= maximum_offset_s:
        return (
            np.asarray(exact.ray_origin_ned_m, dtype=float),
            validate_record_ray(exact, calibration),
            np.asarray(exact.center_px, dtype=float),
            recognition_extent(exact),
            float(nearest_offset),
        )
    return None


def align_track_histories(
    history_a: Sequence[LocalVisualTrackRecord],
    history_b: Sequence[LocalVisualTrackRecord],
    calibration_a: CameraCalibration,
    calibration_b: CameraCalibration,
    config: CrossViewConfig,
) -> tuple[AlignedObservation, ...]:
    if not history_a or not history_b:
        return ()
    timestamps = sorted(
        {
            float(item.measurement_timestamp)
            for item in (*history_a, *history_b)
        }
    )
    aligned: list[AlignedObservation] = []
    for timestamp in timestamps:
        sample_a = _interpolate_record(
            history_a, timestamp, calibration_a, config.maximum_alignment_offset_s
        )
        sample_b = _interpolate_record(
            history_b, timestamp, calibration_b, config.maximum_alignment_offset_s
        )
        if sample_a is None or sample_b is None:
            continue
        origin_a, direction_a, center_a, extent_a, offset_a = sample_a
        origin_b, direction_b, center_b, extent_b, offset_b = sample_b
        aligned.append(
            AlignedObservation(
                timestamp=timestamp,
                origin_a_ned_m=origin_a,
                direction_a_ned=direction_a,
                center_a_px=center_a,
                extent_a_px=extent_a,
                origin_b_ned_m=origin_b,
                direction_b_ned=direction_b,
                center_b_px=center_b,
                extent_b_px=extent_b,
                time_offset_s=max(offset_a, offset_b),
            )
        )
    unique: dict[float, AlignedObservation] = {item.timestamp: item for item in aligned}
    return tuple(unique[key] for key in sorted(unique))


def motion_fit_quality(
    timestamps: Sequence[float],
    points: Sequence[np.ndarray],
) -> tuple[float, float]:
    if len(points) < 2:
        return 0.0, 0.0
    times = np.asarray(timestamps, dtype=float)
    values = np.vstack(points).astype(float)
    reference = float(np.mean(times))
    design = np.column_stack((np.ones(len(times)), times - reference))
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    fitted = design @ coefficients
    residual = float(np.sqrt(np.mean(np.sum((values - fitted) ** 2, axis=1))))
    overall = values[-1] - values[0]
    overall_norm = float(np.linalg.norm(overall))
    maximum_turn = 0.0
    if overall_norm > 1.0e-6:
        for first, second in zip(values[:-1], values[1:]):
            segment = second - first
            segment_norm = float(np.linalg.norm(segment))
            if segment_norm <= 1.0e-6:
                continue
            angle = math.degrees(
                math.acos(float(np.clip(np.dot(segment, overall) / (segment_norm * overall_norm), -1.0, 1.0)))
            )
            maximum_turn = max(maximum_turn, angle)
    return residual, maximum_turn
