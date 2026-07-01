"""Camera projection and image-plane gating utilities."""

from __future__ import annotations

import numpy as np

from .models import CameraModel, GlobalTrack, ProjectionResult

try:  # pragma: no cover - fallback is tested by direct formula use.
    import cv2

    _HAS_CV2 = True
except Exception:  # pragma: no cover
    cv2 = None
    _HAS_CV2 = False


def _project_pixel(track: GlobalTrack, camera: CameraModel) -> tuple[np.ndarray, np.ndarray]:
    """Return `(pixel, camera_point)` for a world point."""

    camera_point = camera.R @ track.position + camera.t
    depth = camera_point[2]
    if depth <= 0:
        return np.array([np.nan, np.nan], dtype=float), camera_point

    # OpenCV is used when available so the implementation aligns with the
    # normal calibration toolchain. The manual formula remains the fallback.
    if _HAS_CV2:
        rvec, _ = cv2.Rodrigues(camera.R)
        dist = camera.dist_coeffs if camera.dist_coeffs is not None else np.zeros(5)
        point = track.position.reshape(1, 1, 3).astype(float)
        projected, _ = cv2.projectPoints(point, rvec, camera.t, camera.K, dist)
        return projected.reshape(2).astype(float), camera_point

    fx = camera.K[0, 0]
    fy = camera.K[1, 1]
    cx = camera.K[0, 2]
    cy = camera.K[1, 2]
    pixel = np.array(
        [
            fx * camera_point[0] / depth + cx,
            fy * camera_point[1] / depth + cy,
        ],
        dtype=float,
    )
    return pixel, camera_point


def projection_jacobian(camera_point: np.ndarray, camera: CameraModel) -> np.ndarray:
    """Compute `d(pixel) / d(world_position)` for the pinhole model."""

    x_c, y_c, z_c = camera_point
    fx = camera.K[0, 0]
    fy = camera.K[1, 1]
    if z_c <= 0:
        raise ValueError("projection Jacobian is undefined for non-positive depth")

    j_proj_cam = np.array(
        [
            [fx / z_c, 0.0, -fx * x_c / (z_c * z_c)],
            [0.0, fy / z_c, -fy * y_c / (z_c * z_c)],
        ],
        dtype=float,
    )
    return j_proj_cam @ camera.R


def project_track(
    track: GlobalTrack,
    camera: CameraModel,
    regularization: float = 1e-6,
    image_margin_px: float = 0.0,
) -> ProjectionResult:
    """Project a global track into the camera image with covariance propagation."""

    pixel, camera_point = _project_pixel(track, camera)
    depth = float(camera_point[2])

    if not np.isfinite(depth) or depth <= 0:
        return ProjectionResult(
            global_track_id=track.global_track_id,
            category=track.category,
            pixel=None,
            covariance_px=None,
            depth=depth,
            valid=False,
            reason="behind_camera",
        )
    if not np.all(np.isfinite(pixel)):
        return ProjectionResult(
            global_track_id=track.global_track_id,
            category=track.category,
            pixel=None,
            covariance_px=None,
            depth=depth,
            valid=False,
            reason="non_finite_projection",
        )

    width, height = camera.image_size
    if (
        pixel[0] < -image_margin_px
        or pixel[0] > width + image_margin_px
        or pixel[1] < -image_margin_px
        or pixel[1] > height + image_margin_px
    ):
        return ProjectionResult(
            global_track_id=track.global_track_id,
            category=track.category,
            pixel=pixel,
            covariance_px=None,
            depth=depth,
            valid=False,
            reason="outside_image",
        )

    jacobian = projection_jacobian(camera_point, camera)
    covariance_px = jacobian @ track.covariance @ jacobian.T + camera.measurement_cov
    covariance_px = covariance_px + np.eye(2) * regularization

    predicted_px_velocity = jacobian @ track.velocity
    if not np.all(np.isfinite(covariance_px)) or not np.all(np.isfinite(predicted_px_velocity)):
        return ProjectionResult(
            global_track_id=track.global_track_id,
            category=track.category,
            pixel=pixel,
            covariance_px=None,
            depth=depth,
            valid=False,
            reason="non_finite_covariance",
        )

    return ProjectionResult(
        global_track_id=track.global_track_id,
        category=track.category,
        pixel=pixel,
        covariance_px=covariance_px,
        depth=depth,
        valid=True,
        reason="ok",
        predicted_px_velocity=predicted_px_velocity,
    )


def mahalanobis_d2(pixel: np.ndarray, projection: ProjectionResult) -> float:
    """Squared Mahalanobis distance from a local pixel to a projection result."""

    if not projection.valid or projection.pixel is None or projection.covariance_px is None:
        return float("inf")
    residual = np.asarray(pixel, dtype=float).reshape(2) - projection.pixel
    inv_cov = np.linalg.pinv(projection.covariance_px)
    value = float(residual.T @ inv_cov @ residual)
    if not np.isfinite(value):
        return float("inf")
    return value
