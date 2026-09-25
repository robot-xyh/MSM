"""Search-terminal fixture with navigation, attitude, gimbal and detection errors."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal, Mapping, Sequence

import numpy as np

from ..common import LocalVisualTrackRecord
from ..common.scenario import (
    CampaignScenario,
    TargetTruth,
    build_source_fixture,
    generate_targets,
)
from .fixture import HandoverFixture, LocalTrackTruthLabel
from .geometry import (
    CameraIntrinsics,
    CameraModel,
    yaw_pitch_roll_from_matrix,
)


NavigationMode = Literal["satellite", "visual_navigation"]
AttitudeMode = Literal["normal", "degraded"]
DetectionMode = Literal["ideal", "light"]
HandoverMode = Literal["anonymous", "coarse_hint"]

NORMAL_ABSOLUTE_P95_Z = 1.959963984540054
RADIAL_3D_P95_Z = 2.7954834829151074


@dataclass(frozen=True)
class SearchTerminalErrorConfig:
    target_count: int
    seed: int
    navigation_mode: NavigationMode
    attitude_mode: AttitudeMode
    detection_mode: DetectionMode
    handover_mode: HandoverMode
    frame_timestamps_s: tuple[float, ...] = (0.2, 0.3, 0.4, 0.5, 0.6)
    observation_standoff_m: float = 700.0
    flight_elapsed_s: float = 200.0
    source_position_sigma_m: float = 1.0
    source_velocity_sigma_mps: float = 0.2
    image_width_px: int = 1920
    image_height_px: int = 1080
    horizontal_fov_deg: float = 19.0
    target_longest_dimension_m: float = 3.0
    target_speed_mps: float = 50.0
    light_miss_probability: float = 0.03
    light_false_alarms_per_camera_s: float = 2.0
    light_center_sigma_px: float = 0.25

    def __post_init__(self) -> None:
        if self.target_count not in {20, 40, 60}:
            raise ValueError("error campaign target_count must be 20, 40 or 60")
        if len(self.frame_timestamps_s) < 3:
            raise ValueError("at least three frames are required")
        if tuple(sorted(self.frame_timestamps_s)) != self.frame_timestamps_s:
            raise ValueError("frame timestamps must be ordered")
        if self.observation_standoff_m <= 0.0 or self.flight_elapsed_s < 0.0:
            raise ValueError("standoff must be positive and flight time cannot be negative")
        if not 0.0 <= self.light_miss_probability < 1.0:
            raise ValueError("light miss probability must be within [0, 1)")
        if self.light_false_alarms_per_camera_s < 0.0:
            raise ValueError("false-alarm rate cannot be negative")

    @property
    def navigation_radial_p95_m(self) -> float:
        return 5.0 if self.navigation_mode == "satellite" else 50.0

    @property
    def body_roll_pitch_p95_deg(self) -> float:
        return 1.0 if self.attitude_mode == "normal" else 5.0

    @property
    def body_yaw_p95_deg(self) -> float:
        return 3.0 if self.attitude_mode == "normal" else 10.0

    @property
    def gimbal_angle_p95_deg(self) -> float:
        return 0.1 if self.attitude_mode == "normal" else 0.5

    @property
    def accumulated_yaw_drift_p95_deg(self) -> float:
        return self.flight_elapsed_s / 200.0

    def to_public_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.update(
            {
                "navigation_radial_p95_m": self.navigation_radial_p95_m,
                "body_roll_pitch_p95_deg": self.body_roll_pitch_p95_deg,
                "body_yaw_p95_deg": self.body_yaw_p95_deg,
                "gimbal_angle_p95_deg": self.gimbal_angle_p95_deg,
                "accumulated_yaw_drift_p95_deg": self.accumulated_yaw_drift_p95_deg,
                "metric_condition": "P(association succeeds | search already found target)",
            }
        )
        return value


@dataclass(frozen=True)
class CameraErrorTruth:
    camera_id: str
    navigation_error_ned_m: tuple[float, float, float]
    body_yaw_pitch_roll_error_deg: tuple[float, float, float]
    gimbal_yaw_pitch_roll_error_deg: tuple[float, float, float]
    accumulated_yaw_drift_deg: float


@dataclass(frozen=True)
class SearchTerminalFixture:
    config: SearchTerminalErrorConfig
    handover_fixture: HandoverFixture
    true_camera_models: Mapping[str, CameraModel]
    camera_error_truth: tuple[CameraErrorTruth, ...]


def build_search_terminal_fixture(config: SearchTerminalErrorConfig) -> SearchTerminalFixture:
    scenario = CampaignScenario(
        target_count=config.target_count,
        seed=config.seed,
        target_speed_mps=config.target_speed_mps,
        target_longest_dimension_m=config.target_longest_dimension_m,
        source_precision=1.0,
        source_recall=1.0,
        source_position_sigma_m=config.source_position_sigma_m,
        source_velocity_sigma_mps=config.source_velocity_sigma_mps,
    )
    targets = generate_targets(scenario)
    source_cues, source_truth = build_source_fixture(scenario, targets)
    source_by_truth = {
        label.truth_target_id: label.source_track_id
        for label in source_truth
        if label.is_correct_source and label.truth_target_id is not None
    }
    true_cameras, reported_cameras, target_camera_ids, error_truth = _build_camera_models(
        targets,
        config,
    )
    frames, local_truth = _build_local_tracks(
        targets,
        source_by_truth,
        true_cameras,
        reported_cameras,
        target_camera_ids,
        config,
    )
    fixture = HandoverFixture(
        scenario=scenario,
        source_cues=source_cues,
        camera_models=reported_cameras,
        frames=frames,
        source_truth=source_truth,
        local_truth=local_truth,
        target_truth=targets,
    )
    return SearchTerminalFixture(
        config=config,
        handover_fixture=fixture,
        true_camera_models=true_cameras,
        camera_error_truth=error_truth,
    )


def _build_camera_models(
    targets: Sequence[TargetTruth],
    config: SearchTerminalErrorConfig,
) -> tuple[
    dict[str, CameraModel],
    dict[str, CameraModel],
    dict[str, str],
    tuple[CameraErrorTruth, ...],
]:
    rng = np.random.default_rng(config.seed + 440_087)
    intrinsics = CameraIntrinsics(
        width_px=config.image_width_px,
        height_px=config.image_height_px,
        horizontal_fov_deg=config.horizontal_fov_deg,
    )
    navigation_sigma = config.navigation_radial_p95_m / RADIAL_3D_P95_Z
    roll_pitch_sigma = config.body_roll_pitch_p95_deg / NORMAL_ABSOLUTE_P95_Z
    body_yaw_sigma = config.body_yaw_p95_deg / NORMAL_ABSOLUTE_P95_Z
    drift_sigma = config.accumulated_yaw_drift_p95_deg / NORMAL_ABSOLUTE_P95_Z
    gimbal_sigma = config.gimbal_angle_p95_deg / NORMAL_ABSOLUTE_P95_Z

    true_models: dict[str, CameraModel] = {}
    reported_models: dict[str, CameraModel] = {}
    target_camera_ids: dict[str, str] = {}
    error_rows: list[CameraErrorTruth] = []
    aim_timestamp = float(config.frame_timestamps_s[len(config.frame_timestamps_s) // 2])
    for index, target in enumerate(targets, start=1):
        camera_id = f"Terminal_CV_{index:02d}"
        aim_point = np.asarray(target.position_at(aim_timestamp), dtype=float)
        velocity = np.asarray(target.velocity_ned_mps, dtype=float)
        direction = velocity / max(float(np.linalg.norm(velocity)), 1.0e-9)
        lateral_jitter = np.asarray((0.0, rng.uniform(-18.0, 18.0), rng.uniform(-8.0, 8.0)))
        body_position = aim_point + direction * config.observation_standoff_m + lateral_jitter
        yaw, pitch = _look_at_yaw_pitch(body_position, aim_point)
        true_model = CameraModel(
            camera_id=camera_id,
            intrinsics=intrinsics,
            body_position_ned_m=tuple(float(value) for value in body_position),
            body_yaw_pitch_roll_deg=(yaw, pitch, 0.0),
            camera_offset_body_m=(0.5, 0.0, 0.0),
        )

        navigation_error = rng.normal(0.0, navigation_sigma, size=3)
        body_error = np.asarray(
            (
                rng.normal(0.0, body_yaw_sigma),
                rng.normal(0.0, roll_pitch_sigma),
                rng.normal(0.0, roll_pitch_sigma),
            ),
            dtype=float,
        )
        drift_error = float(rng.normal(0.0, drift_sigma))
        body_error[0] += drift_error
        gimbal_error = rng.normal(0.0, gimbal_sigma, size=3)
        reported_model = CameraModel(
            camera_id=camera_id,
            intrinsics=intrinsics,
            body_position_ned_m=tuple(float(value) for value in body_position + navigation_error),
            body_yaw_pitch_roll_deg=tuple(
                float(value) for value in np.asarray((yaw, pitch, 0.0)) + body_error
            ),
            gimbal_yaw_pitch_roll_deg=tuple(float(value) for value in gimbal_error),
            camera_offset_body_m=true_model.camera_offset_body_m,
        )
        true_models[camera_id] = true_model
        reported_models[camera_id] = reported_model
        target_camera_ids[target.truth_target_id] = camera_id
        error_rows.append(
            CameraErrorTruth(
                camera_id=camera_id,
                navigation_error_ned_m=tuple(float(value) for value in navigation_error),
                body_yaw_pitch_roll_error_deg=tuple(float(value) for value in body_error),
                gimbal_yaw_pitch_roll_error_deg=tuple(float(value) for value in gimbal_error),
                accumulated_yaw_drift_deg=drift_error,
            )
        )
    return true_models, reported_models, target_camera_ids, tuple(error_rows)


def _build_local_tracks(
    targets: Sequence[TargetTruth],
    source_by_truth: Mapping[str, str],
    true_cameras: Mapping[str, CameraModel],
    reported_cameras: Mapping[str, CameraModel],
    target_camera_ids: Mapping[str, str],
    config: SearchTerminalErrorConfig,
) -> tuple[tuple[tuple[LocalVisualTrackRecord, ...], ...], tuple[LocalTrackTruthLabel, ...]]:
    rng = np.random.default_rng(config.seed + 880_301)
    shuffled_tokens = rng.permutation(np.arange(100_000, 100_000 + len(targets)))
    local_ids = {
        target.truth_target_id: f"LCL-{int(shuffled_tokens[index]):06d}"
        for index, target in enumerate(targets)
    }
    labels = tuple(
        LocalTrackTruthLabel(
            camera_id=target_camera_ids[target.truth_target_id],
            local_track_id=local_ids[target.truth_target_id],
            truth_target_id=target.truth_target_id,
        )
        for target in targets
    )
    uncertainty = _projection_uncertainty_dict(config)
    frames: list[tuple[LocalVisualTrackRecord, ...]] = []
    interval_s = _frame_interval(config.frame_timestamps_s)
    for frame_index, timestamp in enumerate(config.frame_timestamps_s):
        frame: list[LocalVisualTrackRecord] = []
        for target in targets:
            camera_id = target_camera_ids[target.truth_target_id]
            if config.detection_mode == "light" and rng.random() < config.light_miss_probability:
                continue
            true_camera = true_cameras[camera_id]
            reported_camera = reported_cameras[camera_id]
            position = np.asarray(target.position_at(float(timestamp)), dtype=float)
            center = true_camera.project(position)
            if config.detection_mode == "light":
                center = center + rng.normal(0.0, config.light_center_sigma_px, size=2)
            depth = float(true_camera.world_to_camera(position)[0])
            extent = true_camera.intrinsics.focal_x_px * target.longest_dimension_m / depth
            if extent < 10.0:
                raise RuntimeError("search-terminal fixture violates the ten-pixel premise")
            metadata: dict[str, object] = {
                "frame_index": frame_index,
                "center_covariance_px2": (
                    (config.light_center_sigma_px**2, 0.0),
                    (0.0, config.light_center_sigma_px**2),
                )
                if config.detection_mode == "light"
                else ((1.0e-6, 0.0), (0.0, 1.0e-6)),
                "detection_source": "search_terminal_fixture",
                "reported_camera_pose": _reported_pose_dict(reported_camera),
                "projection_uncertainty": uncertainty,
                "search_status": "target_already_found",
            }
            if config.handover_mode == "coarse_hint":
                metadata["coarse_source_track_id"] = source_by_truth[target.truth_target_id]
            frame.append(
                _local_record(
                    camera_id=camera_id,
                    local_track_id=local_ids[target.truth_target_id],
                    timestamp=float(timestamp),
                    center=center,
                    extent=float(extent),
                    reported_camera=reported_camera,
                    metadata=metadata,
                    track_quality=0.98 if config.detection_mode == "ideal" else 0.92,
                )
            )

        if config.detection_mode == "light":
            for camera_id, reported_camera in reported_cameras.items():
                false_count = int(
                    rng.poisson(config.light_false_alarms_per_camera_s * interval_s)
                )
                for false_index in range(false_count):
                    center = np.asarray(
                        (
                            rng.uniform(8.0, config.image_width_px - 8.0),
                            rng.uniform(8.0, config.image_height_px - 8.0),
                        ),
                        dtype=float,
                    )
                    extent = float(rng.uniform(10.0, 18.0))
                    frame.append(
                        _local_record(
                            camera_id=camera_id,
                            local_track_id=(
                                f"FA-{camera_id.split('_')[-1]}-F{frame_index:02d}-{false_index:02d}"
                            ),
                            timestamp=float(timestamp),
                            center=center,
                            extent=extent,
                            reported_camera=reported_camera,
                            metadata={
                                "frame_index": frame_index,
                                "center_covariance_px2": (
                                    (config.light_center_sigma_px**2, 0.0),
                                    (0.0, config.light_center_sigma_px**2),
                                ),
                                "detection_source": "injected_false_alarm",
                                "reported_camera_pose": _reported_pose_dict(reported_camera),
                                "projection_uncertainty": uncertainty,
                                "search_status": "unassigned_detection",
                            },
                            track_quality=0.55,
                        )
                    )
        frames.append(tuple(sorted(frame, key=lambda item: (item.camera_id, item.local_track_id))))
    return tuple(frames), labels


def _local_record(
    *,
    camera_id: str,
    local_track_id: str,
    timestamp: float,
    center: np.ndarray,
    extent: float,
    reported_camera: CameraModel,
    metadata: Mapping[str, object],
    track_quality: float,
) -> LocalVisualTrackRecord:
    width = float(extent)
    height = width * 0.62
    bbox = (
        max(0.0, float(center[0] - width / 2.0)),
        max(0.0, float(center[1] - height / 2.0)),
        min(float(reported_camera.intrinsics.width_px), float(center[0] + width / 2.0)),
        min(float(reported_camera.intrinsics.height_px), float(center[1] + height / 2.0)),
    )
    pixel = (float(center[0]), float(center[1]))
    return LocalVisualTrackRecord(
        camera_id=camera_id,
        local_track_id=local_track_id,
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.02,
        bbox_xyxy=bbox,
        center_px=pixel,
        ray_origin_ned_m=tuple(float(value) for value in reported_camera.camera_position_ned_m),
        ray_direction_ned=tuple(
            float(value) for value in reported_camera.pixel_to_world_ray(pixel)
        ),
        camera_yaw_pitch_roll_deg=yaw_pitch_roll_from_matrix(
            reported_camera.rotation_ned_from_camera
        ),
        recognized=True,
        recognition_extent_px=width,
        track_quality=track_quality,
        metadata=dict(metadata),
    )


def _projection_uncertainty_dict(
    config: SearchTerminalErrorConfig,
) -> dict[str, tuple[tuple[float, ...], ...]]:
    navigation_sigma = config.navigation_radial_p95_m / RADIAL_3D_P95_Z
    roll_pitch_sigma = math.radians(
        config.body_roll_pitch_p95_deg / NORMAL_ABSOLUTE_P95_Z
    )
    yaw_sigma = math.radians(config.body_yaw_p95_deg / NORMAL_ABSOLUTE_P95_Z)
    drift_sigma = math.radians(
        config.accumulated_yaw_drift_p95_deg / NORMAL_ABSOLUTE_P95_Z
    )
    gimbal_sigma = math.radians(
        config.gimbal_angle_p95_deg / NORMAL_ABSOLUTE_P95_Z
    )
    return {
        "navigation_position_covariance_m2": _diagonal_tuple((navigation_sigma,) * 3),
        "body_attitude_covariance_rad2": _diagonal_tuple(
            (
                yaw_sigma**2 + drift_sigma**2,
                roll_pitch_sigma**2,
                roll_pitch_sigma**2,
            ),
            values_are_variances=True,
        ),
        "gimbal_angle_covariance_rad2": _diagonal_tuple((gimbal_sigma,) * 3),
        "pixel_center_covariance_px2": ((0.0, 0.0), (0.0, 0.0)),
    }


def _diagonal_tuple(
    values: Sequence[float],
    *,
    values_are_variances: bool = False,
) -> tuple[tuple[float, ...], ...]:
    diagonal = tuple(float(value if values_are_variances else value**2) for value in values)
    return tuple(
        tuple(diagonal[row] if row == column else 0.0 for column in range(len(diagonal)))
        for row in range(len(diagonal))
    )


def _reported_pose_dict(camera: CameraModel) -> dict[str, tuple[float, float, float]]:
    return {
        "body_position_ned_m": camera.body_position_ned_m,
        "body_yaw_pitch_roll_deg": camera.body_yaw_pitch_roll_deg,
        "gimbal_yaw_pitch_roll_deg": camera.gimbal_yaw_pitch_roll_deg,
    }


def _look_at_yaw_pitch(origin: np.ndarray, target: np.ndarray) -> tuple[float, float]:
    delta = np.asarray(target, dtype=float) - np.asarray(origin, dtype=float)
    horizontal = math.hypot(float(delta[0]), float(delta[1]))
    yaw = math.degrees(math.atan2(float(delta[1]), float(delta[0])))
    pitch = -math.degrees(math.atan2(float(delta[2]), horizontal))
    return yaw, pitch


def _frame_interval(timestamps: Sequence[float]) -> float:
    differences = np.diff(np.asarray(timestamps, dtype=float))
    return float(np.median(differences)) if differences.size else 0.1
