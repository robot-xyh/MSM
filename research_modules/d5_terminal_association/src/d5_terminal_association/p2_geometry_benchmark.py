"""Isolated OpenCV calibration/solvePnP benchmark for D5 research.

This module is not imported by the online terminal association path. It uses
synthetic, reproducible geometry to quantify calibration drift and timestamp
alignment sensitivity. Offline truth labels are attached only after geometric
gating has completed and never participate in a cost or binding decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

import numpy as np

from .geometry import mahalanobis_d2, project_track
from .models import CameraModel, GlobalTrack

try:  # pragma: no cover - availability behavior is exercised with monkeypatching.
    import cv2

    _HAS_CV2 = True
except Exception:  # pragma: no cover
    cv2 = None
    _HAS_CV2 = False


@dataclass(frozen=True)
class OpenCvGeometryBenchmarkConfig:
    """Configuration for the isolated deterministic geometry benchmark."""

    seed: int = 7
    frame_count: int = 6
    track_count: int = 8
    calibration_view_count: int = 8
    calibration_pixel_noise_sigma: float = 0.15
    observation_pixel_noise_sigma: float = 0.35
    translation_drift_m: tuple[float, float, float] = (0.35, -0.20, 0.12)
    rotation_drift_deg: tuple[float, float, float] = (1.2, -0.9, 0.6)
    measurement_timestamp_bias_s: float = 0.08
    nominal_arrival_latency_s: float = 0.30
    arrival_timestamp_bias_s: float = 0.18
    gate_chi2: float = 9.21
    false_candidate_offset_px: tuple[float, float] = (-18.0, -12.0)
    offline_truth_label_prefix: str = "offline-truth"

    def __post_init__(self) -> None:
        if self.frame_count < 1 or self.track_count < 4:
            raise ValueError("frame_count must be positive and track_count must be at least 4")
        if self.calibration_view_count < 4:
            raise ValueError("calibration_view_count must be at least 4")
        if self.calibration_pixel_noise_sigma < 0 or self.observation_pixel_noise_sigma < 0:
            raise ValueError("pixel noise sigmas must be non-negative")
        if self.nominal_arrival_latency_s < 0:
            raise ValueError("nominal_arrival_latency_s must be non-negative")
        if self.gate_chi2 <= 0:
            raise ValueError("gate_chi2 must be positive")
        object.__setattr__(self, "translation_drift_m", _triple(self.translation_drift_m))
        object.__setattr__(self, "rotation_drift_deg", _triple(self.rotation_drift_deg))
        object.__setattr__(
            self,
            "false_candidate_offset_px",
            _pair(self.false_candidate_offset_px),
        )


@dataclass(frozen=True)
class GeometryBenchmarkRecord:
    """One offline-scored sample; truth fields are never gate inputs."""

    sample_index: int
    global_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    projection_error_pre_pnp_px: float
    projection_error_post_pnp_px: float
    projection_error_arrival_time_px: float
    true_gate_accepted_pre_pnp: bool
    true_gate_accepted_post_pnp: bool
    false_gate_accepted_pre_pnp: bool
    false_gate_accepted_post_pnp: bool
    mahalanobis_true_pre_pnp: float
    mahalanobis_true_post_pnp: float
    mahalanobis_false_pre_pnp: float
    mahalanobis_false_post_pnp: float
    offline_truth_label: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class OpenCvGeometryBenchmarkResult:
    """Serializable result of the optional P2 benchmark."""

    status: str
    reason: str
    config: OpenCvGeometryBenchmarkConfig
    metrics: Mapping[str, float | int | bool | None]
    records: tuple[GeometryBenchmarkRecord, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.status == "available"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "config": asdict(self.config),
            "metrics": dict(self.metrics),
            "records": [asdict(record) for record in self.records],
            "metadata": dict(self.metadata),
        }


def opencv_geometry_benchmark_available() -> bool:
    """Return whether the optional OpenCV calibration API is importable."""

    return bool(
        _HAS_CV2
        and cv2 is not None
        and all(
            hasattr(cv2, name)
            for name in ("calibrateCamera", "projectPoints", "Rodrigues", "solvePnP")
        )
    )


def run_opencv_geometry_perturbation_benchmark(
    config: OpenCvGeometryBenchmarkConfig | None = None,
) -> OpenCvGeometryBenchmarkResult:
    """Run the isolated calibration, solvePnP, and gate perturbation study."""

    config = config or OpenCvGeometryBenchmarkConfig()
    if not opencv_geometry_benchmark_available():
        return OpenCvGeometryBenchmarkResult(
            status="unavailable",
            reason="opencv_calib3d_unavailable",
            config=config,
            metrics={},
            metadata={
                "online_path_modified": False,
                "truth_policy": "offline_scoring_only",
            },
        )

    rng = np.random.default_rng(config.seed)
    true_camera = _make_reference_camera()
    calibrated_K, calibrated_dist, calibration_rms = _calibrate_intrinsics(
        true_camera,
        config,
        rng,
    )
    drifted_camera = _perturb_camera(true_camera, config)
    recovered_camera, pnp_reprojection_rmse = _recover_camera_with_solve_pnp(
        true_camera,
        drifted_camera,
        calibrated_K,
        calibrated_dist,
        config,
        rng,
    )
    tracks = _make_tracks(config.track_count)
    records = _evaluate_tracks(
        tracks,
        true_camera=true_camera,
        drifted_camera=drifted_camera,
        recovered_camera=recovered_camera,
        config=config,
        rng=rng,
    )
    metrics = _summarize_records(
        records,
        calibration_rms=calibration_rms,
        pnp_reprojection_rmse=pnp_reprojection_rmse,
        true_K=true_camera.K,
        calibrated_K=calibrated_K,
        true_camera=true_camera,
        recovered_camera=recovered_camera,
    )
    return OpenCvGeometryBenchmarkResult(
        status="available",
        reason="ok",
        config=config,
        metrics=metrics,
        records=records,
        metadata={
            "benchmark_mode": "offline_optional_p2",
            "online_path_modified": False,
            "geometry_contract": "CameraModel+GlobalTrack",
            "truth_policy": "offline_scoring_only",
            "gate_inputs": "pixel_residual+projected_covariance_only",
            "opencv_version": getattr(cv2, "__version__", "unknown"),
        },
    )


def _make_reference_camera() -> CameraModel:
    width, height = 1280, 720
    K = np.array(
        [[820.0, 0.0, width / 2.0], [0.0, 815.0, height / 2.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    return CameraModel(
        K=K,
        R=np.eye(3, dtype=float),
        t=np.zeros(3, dtype=float),
        image_size=(width, height),
        measurement_cov=np.diag([9.0, 9.0]),
        dist_coeffs=np.zeros(5, dtype=float),
    )


def _calibrate_intrinsics(
    camera: CameraModel,
    config: OpenCvGeometryBenchmarkConfig,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, float]:
    board = np.zeros((7 * 6, 3), dtype=np.float32)
    board[:, :2] = np.mgrid[0:7, 0:6].T.reshape(-1, 2).astype(np.float32) * 0.35
    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    for index in range(config.calibration_view_count):
        rvec = np.array(
            [
                0.18 * np.sin(0.7 * index),
                -0.16 * np.cos(0.5 * index),
                -0.08 + 0.018 * index,
            ],
            dtype=float,
        )
        tvec = np.array(
            [
                -1.0 + 0.18 * (index % 5),
                -0.8 + 0.2 * (index % 4),
                6.0 + 0.5 * (index % 4),
            ],
            dtype=float,
        )
        projected, _ = cv2.projectPoints(
            board.astype(float),
            rvec,
            tvec,
            camera.K,
            camera.dist_coeffs,
        )
        image = projected.reshape(-1, 2)
        if config.calibration_pixel_noise_sigma > 0:
            image += rng.normal(
                0.0,
                config.calibration_pixel_noise_sigma,
                size=image.shape,
            )
        object_points.append(board.copy())
        image_points.append(image.astype(np.float32).reshape(-1, 1, 2))

    initial_K = camera.K.copy()
    flags = (
        cv2.CALIB_USE_INTRINSIC_GUESS
        | cv2.CALIB_ZERO_TANGENT_DIST
        | cv2.CALIB_FIX_K1
        | cv2.CALIB_FIX_K2
        | cv2.CALIB_FIX_K3
    )
    rms, calibrated_K, calibrated_dist, _, _ = cv2.calibrateCamera(
        object_points,
        image_points,
        camera.image_size,
        initial_K,
        np.zeros(5, dtype=float),
        flags=flags,
    )
    return (
        np.asarray(calibrated_K, dtype=float),
        np.asarray(calibrated_dist, dtype=float).reshape(-1),
        float(rms),
    )


def _perturb_camera(
    camera: CameraModel,
    config: OpenCvGeometryBenchmarkConfig,
) -> CameraModel:
    drift_rvec = np.radians(np.asarray(config.rotation_drift_deg, dtype=float))
    drift_rotation, _ = cv2.Rodrigues(drift_rvec)
    drifted_R = drift_rotation @ camera.R
    true_center = -camera.R.T @ camera.t
    drifted_center = true_center + np.asarray(config.translation_drift_m, dtype=float)
    drifted_t = -drifted_R @ drifted_center
    return CameraModel(
        K=camera.K,
        R=drifted_R,
        t=drifted_t,
        image_size=camera.image_size,
        measurement_cov=camera.measurement_cov,
        dist_coeffs=camera.dist_coeffs,
    )


def _recover_camera_with_solve_pnp(
    true_camera: CameraModel,
    drifted_camera: CameraModel,
    calibrated_K: np.ndarray,
    calibrated_dist: np.ndarray,
    config: OpenCvGeometryBenchmarkConfig,
    rng: np.random.Generator,
) -> tuple[CameraModel, float]:
    reference_points = _reference_points()
    true_rvec, _ = cv2.Rodrigues(true_camera.R)
    image_points, _ = cv2.projectPoints(
        reference_points,
        true_rvec,
        true_camera.t,
        true_camera.K,
        true_camera.dist_coeffs,
    )
    image_points = image_points.reshape(-1, 2)
    if config.observation_pixel_noise_sigma > 0:
        image_points += rng.normal(
            0.0,
            config.observation_pixel_noise_sigma,
            size=image_points.shape,
        )
    initial_rvec, _ = cv2.Rodrigues(drifted_camera.R)
    success, recovered_rvec, recovered_t = cv2.solvePnP(
        reference_points,
        image_points.reshape(-1, 1, 2),
        calibrated_K,
        calibrated_dist,
        rvec=initial_rvec,
        tvec=drifted_camera.t.reshape(3, 1).copy(),
        useExtrinsicGuess=True,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        raise RuntimeError("opencv_solvepnp_failed")
    recovered_R, _ = cv2.Rodrigues(recovered_rvec)
    reprojected, _ = cv2.projectPoints(
        reference_points,
        recovered_rvec,
        recovered_t,
        calibrated_K,
        calibrated_dist,
    )
    residuals = reprojected.reshape(-1, 2) - image_points
    reprojection_rmse = float(np.sqrt(np.mean(np.sum(residuals * residuals, axis=1))))
    return (
        CameraModel(
            K=calibrated_K,
            R=recovered_R,
            t=recovered_t.reshape(3),
            image_size=true_camera.image_size,
            measurement_cov=true_camera.measurement_cov,
            dist_coeffs=calibrated_dist,
        ),
        reprojection_rmse,
    )


def _reference_points() -> np.ndarray:
    points: list[tuple[float, float, float]] = []
    for depth_index, depth in enumerate((24.0, 32.0, 41.0)):
        for lateral_index, lateral in enumerate((-5.0, -1.5, 2.0, 5.5)):
            vertical = -2.0 + 1.2 * ((depth_index + lateral_index) % 4)
            points.append((lateral, vertical, depth))
    return np.asarray(points, dtype=float)


def _make_tracks(count: int) -> tuple[GlobalTrack, ...]:
    tracks: list[GlobalTrack] = []
    for index in range(count):
        x = -5.0 + 10.0 * index / max(1, count - 1)
        y = -2.2 + 1.4 * (index % 4)
        z = 27.0 + 2.5 * (index % 5)
        velocity = np.array(
            [0.8 - 0.12 * (index % 3), 0.35 * (-1.0 if index % 2 else 1.0), 0.08],
            dtype=float,
        )
        tracks.append(
            GlobalTrack(
                global_track_id=f"GT-{index:03d}",
                position=np.array([x, y, z], dtype=float),
                velocity=velocity,
                covariance=np.diag([0.02, 0.02, 0.03]),
                category="uav",
                timestamp=0.0,
            )
        )
    return tuple(tracks)


def _evaluate_tracks(
    tracks: tuple[GlobalTrack, ...],
    *,
    true_camera: CameraModel,
    drifted_camera: CameraModel,
    recovered_camera: CameraModel,
    config: OpenCvGeometryBenchmarkConfig,
    rng: np.random.Generator,
) -> tuple[GeometryBenchmarkRecord, ...]:
    records: list[GeometryBenchmarkRecord] = []
    false_offset = np.asarray(config.false_candidate_offset_px, dtype=float)
    sample_index = 0
    for frame_index in range(config.frame_count):
        true_measurement_timestamp = 0.4 * frame_index
        reported_measurement_timestamp = (
            true_measurement_timestamp + config.measurement_timestamp_bias_s
        )
        reported_arrival_timestamp = (
            true_measurement_timestamp
            + config.nominal_arrival_latency_s
            + config.arrival_timestamp_bias_s
        )
        for track in tracks:
            truth_track = _track_at_time(track, true_measurement_timestamp)
            measurement_track = _track_at_time(track, reported_measurement_timestamp)
            arrival_track = _track_at_time(track, reported_arrival_timestamp)
            truth_projection = project_track(truth_track, true_camera)
            pre_projection = project_track(measurement_track, drifted_camera)
            post_projection = project_track(measurement_track, recovered_camera)
            arrival_projection = project_track(arrival_track, recovered_camera)
            if not all(
                projection.valid and projection.pixel is not None
                for projection in (
                    truth_projection,
                    pre_projection,
                    post_projection,
                    arrival_projection,
                )
            ):
                continue

            observed_pixel = truth_projection.pixel.copy()
            if config.observation_pixel_noise_sigma > 0:
                observed_pixel += rng.normal(
                    0.0,
                    config.observation_pixel_noise_sigma,
                    size=2,
                )
            false_pixel = observed_pixel + false_offset
            true_pre_d2 = mahalanobis_d2(observed_pixel, pre_projection)
            true_post_d2 = mahalanobis_d2(observed_pixel, post_projection)
            false_pre_d2 = mahalanobis_d2(false_pixel, pre_projection)
            false_post_d2 = mahalanobis_d2(false_pixel, post_projection)

            # Truth identity is attached only after all projections and gates.
            offline_truth_label = f"{config.offline_truth_label_prefix}-{sample_index:04d}"
            records.append(
                GeometryBenchmarkRecord(
                    sample_index=sample_index,
                    global_track_id=track.global_track_id,
                    measurement_timestamp=reported_measurement_timestamp,
                    arrival_timestamp=reported_arrival_timestamp,
                    projection_error_pre_pnp_px=_pixel_error(
                        pre_projection.pixel,
                        truth_projection.pixel,
                    ),
                    projection_error_post_pnp_px=_pixel_error(
                        post_projection.pixel,
                        truth_projection.pixel,
                    ),
                    projection_error_arrival_time_px=_pixel_error(
                        arrival_projection.pixel,
                        truth_projection.pixel,
                    ),
                    true_gate_accepted_pre_pnp=true_pre_d2 <= config.gate_chi2,
                    true_gate_accepted_post_pnp=true_post_d2 <= config.gate_chi2,
                    false_gate_accepted_pre_pnp=false_pre_d2 <= config.gate_chi2,
                    false_gate_accepted_post_pnp=false_post_d2 <= config.gate_chi2,
                    mahalanobis_true_pre_pnp=true_pre_d2,
                    mahalanobis_true_post_pnp=true_post_d2,
                    mahalanobis_false_pre_pnp=false_pre_d2,
                    mahalanobis_false_post_pnp=false_post_d2,
                    offline_truth_label=offline_truth_label,
                    metadata={
                        "offline_truth_only": True,
                        "truth_used_for_gate": False,
                        "measurement_timestamp_bias_s": config.measurement_timestamp_bias_s,
                        "arrival_timestamp_bias_s": config.arrival_timestamp_bias_s,
                    },
                )
            )
            sample_index += 1
    return tuple(records)


def _track_at_time(track: GlobalTrack, timestamp: float) -> GlobalTrack:
    delta_t = float(timestamp) - track.timestamp
    return GlobalTrack(
        global_track_id=track.global_track_id,
        position=track.position + track.velocity * delta_t,
        velocity=track.velocity,
        covariance=track.covariance,
        category=track.category,
        timestamp=float(timestamp),
        track_version=track.track_version,
    )


def _summarize_records(
    records: tuple[GeometryBenchmarkRecord, ...],
    *,
    calibration_rms: float,
    pnp_reprojection_rmse: float,
    true_K: np.ndarray,
    calibrated_K: np.ndarray,
    true_camera: CameraModel,
    recovered_camera: CameraModel,
) -> dict[str, float | int | bool | None]:
    if not records:
        return {
            "sample_count": 0,
            "calibration_rms_px": calibration_rms,
            "pnp_reprojection_rmse_px": pnp_reprojection_rmse,
        }
    pre_errors = np.asarray([record.projection_error_pre_pnp_px for record in records])
    post_errors = np.asarray([record.projection_error_post_pnp_px for record in records])
    arrival_errors = np.asarray(
        [record.projection_error_arrival_time_px for record in records]
    )
    true_center = -true_camera.R.T @ true_camera.t
    recovered_center = -recovered_camera.R.T @ recovered_camera.t
    rotation_delta = recovered_camera.R @ true_camera.R.T
    rotation_rvec, _ = cv2.Rodrigues(rotation_delta)
    return {
        "sample_count": len(records),
        "calibration_rms_px": calibration_rms,
        "intrinsics_relative_error": float(
            np.linalg.norm(calibrated_K - true_K) / np.linalg.norm(true_K)
        ),
        "pnp_reprojection_rmse_px": pnp_reprojection_rmse,
        "pnp_translation_error_m": float(np.linalg.norm(recovered_center - true_center)),
        "pnp_rotation_error_deg": float(np.linalg.norm(rotation_rvec) * 180.0 / np.pi),
        "projection_rmse_pre_pnp_px": _rmse(pre_errors),
        "projection_rmse_post_pnp_px": _rmse(post_errors),
        "projection_rmse_arrival_time_px": _rmse(arrival_errors),
        "gate_acceptance_rate_pre_pnp": _rate(
            record.true_gate_accepted_pre_pnp for record in records
        ),
        "gate_acceptance_rate_post_pnp": _rate(
            record.true_gate_accepted_post_pnp for record in records
        ),
        "false_acceptance_rate_pre_pnp": _rate(
            record.false_gate_accepted_pre_pnp for record in records
        ),
        "false_acceptance_rate_post_pnp": _rate(
            record.false_gate_accepted_post_pnp for record in records
        ),
        "truth_identity_used_online": False,
    }


def _pixel_error(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(left, dtype=float) - np.asarray(right, dtype=float)))


def _rmse(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(values, dtype=float) ** 2)))


def _rate(values: Any) -> float:
    array = np.asarray(tuple(values), dtype=float)
    return float(np.mean(array)) if array.size else 0.0


def _triple(value: Any) -> tuple[float, float, float]:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size != 3:
        raise ValueError("expected three values")
    return (float(array[0]), float(array[1]), float(array[2]))


def _pair(value: Any) -> tuple[float, float]:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size != 2:
        raise ValueError("expected two values")
    return (float(array[0]), float(array[1]))
