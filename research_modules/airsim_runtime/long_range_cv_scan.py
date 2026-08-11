"""Long-range ComputerVision scan and geometric-registration experiment.

The experiment keeps AirSim actor identity in an offline sidecar. Online D5
association consumes only center-owned tracks, camera calibration, anonymous
camera-local tracks, timestamps, and covariance.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field, replace
import csv
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from airsim_dryrun.models import AirSimFrame
from d5_terminal_association import (
    AssociationConfig,
    GlobalTrack,
    TemporalGeometricAssociationConfig,
    TemporalGeometricAssociationResult,
    TemporalGeometricAssociator,
    camera_model_from_airsim_camera_info,
)

from .adapters import geometric_local_visual_tracks_from_blocks_frame
from .blocks import BlocksProcessManager
from .long_range_visual_evidence import write_long_range_registration_visual_evidence
from .models import BlocksActorTargetSpec, BlocksSmokeConfig
from .real_runtime import RealAirSimRuntimeClient


CENTER_CAMERA_NAME = "Center_CV"
INTERCEPTOR_CAMERA_NAME = "Interceptor_CV"
CAMERA_NAME = "0"
SUPPORTED_SCAN_MODES = ("mechanical_2s", "coverage_safe")
SUPPORTED_GEOMETRY_PROFILES = ("baseline_v1", "crossing_calibration_v1")
ASSOCIATION_LOG_FIELDS = (
    "frame_index",
    "camera_id",
    "measurement_timestamp",
    "arrival_timestamp",
    "global_track_id",
    "local_track_id",
    "association_source",
    "measured_evidence",
    "terminal_authorization_allowed",
    "truth_identity_used",
)
TEMPORAL_BINDING_EVENT_FIELDS = (
    "frame_index",
    "mode",
    "camera_vehicle_name",
    "record_type",
    "resource_id",
    "camera_id",
    "stream_id",
    "local_track_id",
    "incumbent_global_track_id",
    "candidate_global_track_id",
    "binding_event",
    "binding_reason",
    "measurement_timestamp",
    "arrival_timestamp",
    "prediction_age_s",
    "measured_evidence",
    "association_confirmed",
    "terminal_authorization_allowed",
    "truth_identity_used",
)
DROPOUT_EVENT_FIELDS = (
    "frame_index",
    "mode",
    "camera_vehicle_name",
    "record_type",
    "resource_id",
    "camera_id",
    "stream_id",
    "global_track_id",
    "local_track_id",
    "local_track_state",
    "decision_state",
    "prediction_age_s",
    "last_measurement_timestamp",
    "measurement_timestamp",
    "arrival_timestamp",
    "terminal_authorization_allowed",
    "truth_identity_used",
)


@dataclass(frozen=True)
class OpticalCameraSpec:
    """Configured AirSim camera plus physical-equivalent reporting values."""

    width: int
    height: int
    horizontal_fov_deg: float
    equivalent_focal_length_mm: float
    ifov_urad: float

    @property
    def vertical_fov_deg(self) -> float:
        return vertical_fov_degrees(
            self.horizontal_fov_deg,
            width=self.width,
            height=self.height,
        )

    @property
    def focal_length_px(self) -> float:
        return self.width / (
            2.0 * math.tan(math.radians(self.horizontal_fov_deg) * 0.5)
        )


CENTER_CAMERA_SPEC = OpticalCameraSpec(
    width=2600,
    height=2160,
    horizontal_fov_deg=0.621,
    equivalent_focal_length_mm=600.0,
    ifov_urad=4.17,
)


def derive_interceptor_camera_spec(
    *,
    center: OpticalCameraSpec = CENTER_CAMERA_SPEC,
    center_range_m: float = 3000.0,
    interceptor_range_m: float = 500.0,
    width: int = 1920,
    height: int = 1080,
) -> OpticalCameraSpec:
    """Match target pixel size at two ranges under the same pixel-pitch assumption."""

    if center_range_m <= 0.0 or interceptor_range_m <= 0.0:
        raise ValueError("camera ranges must be positive")
    center_focal_px = center.focal_length_px
    interceptor_focal_px = center_focal_px * interceptor_range_m / center_range_m
    horizontal_fov = math.degrees(2.0 * math.atan(width / (2.0 * interceptor_focal_px)))
    focal_mm = center.equivalent_focal_length_mm * interceptor_range_m / center_range_m
    ifov_urad = 1_000_000.0 / interceptor_focal_px
    return OpticalCameraSpec(
        width=int(width),
        height=int(height),
        horizontal_fov_deg=float(horizontal_fov),
        equivalent_focal_length_mm=float(focal_mm),
        ifov_urad=float(ifov_urad),
    )


INTERCEPTOR_CAMERA_SPEC = OpticalCameraSpec(
    width=1920,
    height=1080,
    horizontal_fov_deg=2.750979,
    equivalent_focal_length_mm=100.0,
    ifov_urad=25.0,
)


@dataclass(frozen=True)
class LongRangeCVScenario:
    target_count: int = 20
    seed: int = 20260810
    duration_s: float = 12.0
    logic_rate_hz: float = 100.0
    center_position_ned: tuple[float, float, float] = (0.0, 0.0, -100.0)
    target_range_min_m: float = 2800.0
    target_range_max_m: float = 3200.0
    target_azimuth_span_deg: float = 12.0
    interceptor_standoff_m: float = 500.0
    target_speed_min_mps: float = 50.0
    target_speed_max_mps: float = 50.0
    target_asset_name: str = "Quadrotor1"
    target_scale: float = 1.0
    search_sector_min_deg: float = -22.5
    search_sector_max_deg: float = 22.5
    scan_overlap_ratio: float = 0.20
    dwell_frames: int = 5
    cue_timeout_s: float = 2.0
    snapshot_interval_s: float = 2.0
    capture_registration_events: bool = True
    max_multi_target_event_snapshots_per_camera: int = 4
    global_track_position_sigma_m: float = 15.0
    mot_max_coast_s: float = 0.50
    crossing_window_half_width_s: float = 0.25
    detection_radius_cm: int = 350_000
    camera_name: str = CAMERA_NAME
    center_vehicle_name: str = CENTER_CAMERA_NAME
    interceptor_vehicle_name: str = INTERCEPTOR_CAMERA_NAME
    api_port: int = 41451
    clock_speed: float = 1.0
    measurement_sigma_px: float = 20.0
    temporal_association_coast_s: float = 0.25
    temporal_challenger_required_frames: int = 2
    geometry_profile: str = "baseline_v1"

    def __post_init__(self) -> None:
        if int(self.target_count) <= 0:
            raise ValueError("target_count must be positive")
        if float(self.duration_s) <= 0.0 or float(self.logic_rate_hz) <= 0.0:
            raise ValueError("duration and logic rate must be positive")
        if self.target_range_min_m <= 0.0 or self.target_range_max_m < self.target_range_min_m:
            raise ValueError("invalid target range")
        if self.target_speed_min_mps <= 0.0 or self.target_speed_max_mps < self.target_speed_min_mps:
            raise ValueError("invalid target speed interval")
        if not 0.0 <= float(self.scan_overlap_ratio) < 1.0:
            raise ValueError("scan_overlap_ratio must be in [0, 1)")
        if self.dwell_frames <= 0:
            raise ValueError("dwell_frames must be positive")
        if self.cue_timeout_s <= 0.0:
            raise ValueError("cue_timeout_s must be positive")
        if self.snapshot_interval_s <= 0.0:
            raise ValueError("snapshot_interval_s must be positive")
        if self.max_multi_target_event_snapshots_per_camera < 0:
            raise ValueError("max_multi_target_event_snapshots_per_camera must be non-negative")
        if self.global_track_position_sigma_m <= 0.0:
            raise ValueError("global_track_position_sigma_m must be positive")
        if self.mot_max_coast_s <= 0.0:
            raise ValueError("mot_max_coast_s must be positive")
        if self.crossing_window_half_width_s <= 0.0:
            raise ValueError("crossing_window_half_width_s must be positive")
        if self.temporal_association_coast_s < 0.0:
            raise ValueError("temporal_association_coast_s must be non-negative")
        if self.temporal_challenger_required_frames < 2:
            raise ValueError("temporal_challenger_required_frames must be at least 2")
        if self.detection_radius_cm < 350_000:
            raise ValueError("detection_radius_cm must cover at least 3.5 km")
        if self.geometry_profile not in SUPPORTED_GEOMETRY_PROFILES:
            raise ValueError(
                f"geometry_profile must be one of {SUPPORTED_GEOMETRY_PROFILES}"
            )

    @property
    def dt_s(self) -> float:
        return 1.0 / float(self.logic_rate_hz)

    @property
    def frame_count(self) -> int:
        return int(round(self.duration_s * self.logic_rate_hz))

    @property
    def sample_count(self) -> int:
        """Include both logical endpoints while advancing exactly ``duration_s``."""

        return self.frame_count + 1


@dataclass(frozen=True)
class ScanModeDefinition:
    name: str
    speed_deg_s: float
    step_deg: float
    overlap_ratio: float | None
    mandatory_coverage_gate: bool


def scan_mode_definition(
    mode: str,
    *,
    camera_fov_deg: float = CENTER_CAMERA_SPEC.horizontal_fov_deg,
    logic_rate_hz: float = 100.0,
) -> ScanModeDefinition:
    mode = str(mode)
    if mode == "mechanical_2s":
        speed = 180.0
        return ScanModeDefinition(mode, speed, speed / logic_rate_hz, None, False)
    if mode == "coverage_safe":
        overlap = 0.20
        step = float(camera_fov_deg) * (1.0 - overlap)
        return ScanModeDefinition(mode, step * logic_rate_hz, step, overlap, True)
    raise ValueError(f"unsupported scan mode: {mode}")


@dataclass(frozen=True)
class PitchSearchPlan:
    """Pitch coverage derived only from center-owned GlobalTrack uncertainty."""

    min_pitch_deg: float
    max_pitch_deg: float
    row_step_deg: float
    pitch_rows_deg: tuple[float, ...]
    sigma_multiplier: float
    source_track_count: int
    source: str = "center_global_tracks_with_covariance"


def derive_pitch_search_plan(
    tracks: Sequence[GlobalTrack],
    *,
    camera_position_ned: tuple[float, float, float],
    camera_spec: OpticalCameraSpec = CENTER_CAMERA_SPEC,
    overlap_ratio: float = 0.20,
    sigma_multiplier: float = 3.0,
) -> PitchSearchPlan:
    """Bound the raster rows from track elevation and projected covariance."""

    if not tracks:
        return PitchSearchPlan(0.0, 0.0, camera_spec.vertical_fov_deg, (0.0,), sigma_multiplier, 0)
    if not 0.0 <= float(overlap_ratio) < 1.0:
        raise ValueError("overlap_ratio must be in [0, 1)")
    camera = np.asarray(camera_position_ned, dtype=float)
    lower: list[float] = []
    upper: list[float] = []
    for track in tracks:
        position = np.asarray(track.position, dtype=float)
        delta = position - camera
        slant_range = max(float(np.linalg.norm(delta)), 1e-6)
        pitch = _look_angles_deg(tuple(camera), tuple(position))[1]
        covariance = np.asarray(track.covariance, dtype=float)
        position_covariance = covariance[:3, :3]
        sigma_position = math.sqrt(max(float(np.linalg.eigvalsh(position_covariance).max()), 0.0))
        angular_margin = math.degrees(
            math.atan2(float(sigma_multiplier) * sigma_position, slant_range)
        )
        lower.append(pitch - angular_margin)
        upper.append(pitch + angular_margin)
    row_step = camera_spec.vertical_fov_deg * (1.0 - float(overlap_ratio))
    rows = _inclusive_axis_points(min(lower), max(upper), row_step)
    return PitchSearchPlan(
        min_pitch_deg=float(rows[0]),
        max_pitch_deg=float(rows[-1]),
        row_step_deg=float(row_step),
        pitch_rows_deg=rows,
        sigma_multiplier=float(sigma_multiplier),
        source_track_count=len(tracks),
    )


def build_serpentine_scan_grid(
    *,
    min_yaw_deg: float,
    max_yaw_deg: float,
    min_pitch_deg: float,
    max_pitch_deg: float,
    horizontal_fov_deg: float,
    vertical_fov_deg: float,
    overlap_ratio: float,
) -> tuple[tuple[float, float], ...]:
    """Generate an endpoint-complete FOV-overlap raster in yaw/pitch space."""

    if horizontal_fov_deg <= 0.0 or vertical_fov_deg <= 0.0:
        raise ValueError("camera FOV values must be positive")
    if not 0.0 <= float(overlap_ratio) < 1.0:
        raise ValueError("overlap_ratio must be in [0, 1)")
    yaw_step = float(horizontal_fov_deg) * (1.0 - float(overlap_ratio))
    pitch_step = float(vertical_fov_deg) * (1.0 - float(overlap_ratio))
    yaws = _inclusive_axis_points(min_yaw_deg, max_yaw_deg, yaw_step)
    pitches = _inclusive_axis_points(min_pitch_deg, max_pitch_deg, pitch_step)
    waypoints: list[tuple[float, float]] = []
    for row_index, pitch in enumerate(pitches):
        row = yaws if row_index % 2 == 0 else tuple(reversed(yaws))
        waypoints.extend((float(yaw), float(pitch)) for yaw in row)
    return tuple(waypoints)


@dataclass
class SectorScanScheduler:
    """Triangular sector scan with a fixed consecutive-frame confirmation dwell."""

    mode: ScanModeDefinition
    min_yaw_deg: float = -22.5
    max_yaw_deg: float = 22.5
    dwell_frames: int = 5
    current_yaw_deg: float = field(init=False)
    current_pitch_deg: float = 0.0
    direction: int = 1
    state: str = "scan"
    dwell_target_id: str | None = None
    dwell_elapsed_frames: int = 0
    dwell_hit_frames: int = 0
    total_dwell_frames: int = 0
    endpoint_reversal_count: int = 0
    completed_sweep_count: int = 0
    first_sweep_completed_frame: int | None = None
    _visited_max: bool = False
    raster_waypoints: tuple[tuple[float, float], ...] = ()
    raster_index: int = 0

    def __post_init__(self) -> None:
        if self.raster_waypoints:
            self.current_yaw_deg, self.current_pitch_deg = self.raster_waypoints[0]
        else:
            self.current_yaw_deg = float(self.min_yaw_deg)

    def command(self) -> tuple[float, float, str, str | None]:
        return self.current_yaw_deg, self.current_pitch_deg, self.state, self.dwell_target_id

    def observe(
        self,
        observed_global_ids: Sequence[str],
        *,
        frame_index: int,
        preferred_target_id: str | None = None,
        preferred_angles_deg: tuple[float, float] | None = None,
    ) -> tuple[str, ...]:
        observed = set(str(value) for value in observed_global_ids)
        confirmed: list[str] = []
        if self.state == "dwell" and self.dwell_target_id is not None:
            self.dwell_elapsed_frames += 1
            self.total_dwell_frames += 1
            if self.dwell_target_id in observed:
                self.dwell_hit_frames += 1
            if self.dwell_elapsed_frames >= self.dwell_frames:
                if self.dwell_hit_frames >= self.dwell_frames:
                    confirmed.append(self.dwell_target_id)
                self.state = "scan"
                self.dwell_target_id = None
                self.dwell_elapsed_frames = 0
                self.dwell_hit_frames = 0
                self._advance_scan(frame_index)
            return tuple(confirmed)

        if preferred_target_id is not None and preferred_target_id in observed:
            self.state = "dwell"
            self.dwell_target_id = str(preferred_target_id)
            self.dwell_elapsed_frames = 1
            self.dwell_hit_frames = 1
            self.total_dwell_frames += 1
            if preferred_angles_deg is not None:
                self.current_yaw_deg = float(preferred_angles_deg[0])
                self.current_pitch_deg = float(preferred_angles_deg[1])
            if self.dwell_frames == 1:
                confirmed.append(self.dwell_target_id)
                self.state = "scan"
                self.dwell_target_id = None
                self.dwell_elapsed_frames = 0
                self.dwell_hit_frames = 0
                self._advance_scan(frame_index)
            return tuple(confirmed)

        self._advance_scan(frame_index)
        return ()

    def _advance_scan(self, frame_index: int) -> None:
        if self.raster_waypoints:
            previous_pitch = self.current_pitch_deg
            self.raster_index += 1
            if self.raster_index >= len(self.raster_waypoints):
                self.raster_index = 0
                self.completed_sweep_count += 1
                if self.first_sweep_completed_frame is None:
                    self.first_sweep_completed_frame = int(frame_index)
            next_yaw, next_pitch = self.raster_waypoints[self.raster_index]
            if not math.isclose(previous_pitch, next_pitch, abs_tol=1e-9):
                self.endpoint_reversal_count += 1
            delta = _angle_delta_deg(self.current_yaw_deg, next_yaw)
            if not math.isclose(delta, 0.0, abs_tol=1e-9):
                self.direction = 1 if delta > 0.0 else -1
            self.current_yaw_deg = float(next_yaw)
            self.current_pitch_deg = float(next_pitch)
            return
        proposed = self.current_yaw_deg + self.direction * self.mode.step_deg
        if proposed >= self.max_yaw_deg:
            overshoot = proposed - self.max_yaw_deg
            self.current_yaw_deg = self.max_yaw_deg - overshoot
            self.direction = -1
            self.endpoint_reversal_count += 1
            self._visited_max = True
        elif proposed <= self.min_yaw_deg:
            overshoot = self.min_yaw_deg - proposed
            self.current_yaw_deg = self.min_yaw_deg + overshoot
            self.direction = 1
            self.endpoint_reversal_count += 1
            if self._visited_max:
                self.completed_sweep_count += 1
                if self.first_sweep_completed_frame is None:
                    self.first_sweep_completed_frame = int(frame_index)
        else:
            self.current_yaw_deg = proposed


@dataclass
class _AnonymousMotionTrack:
    track_id: str
    center_px: np.ndarray
    world_ray_ned: np.ndarray
    world_ray_velocity_s: np.ndarray
    bbox_xyxy: tuple[float, float, float, float]
    log_bbox_area: float
    log_bbox_area_rate_s: float
    timestamp: float
    frame_index: int
    history_length: int = 1


def pixel_to_world_unit_ray(
    pixel: Sequence[float],
    camera_info: Any,
) -> np.ndarray:
    """Back-project one anonymous pixel through synchronized camera extrinsics."""

    fx = float(camera_info.fx)
    fy = float(camera_info.fy)
    if fx <= 0.0 or fy <= 0.0:
        raise ValueError("camera focal lengths must be positive")
    camera_ray = np.array(
        [
            (float(pixel[0]) - float(camera_info.cx)) / fx,
            (float(pixel[1]) - float(camera_info.cy)) / fy,
            1.0,
        ],
        dtype=float,
    )
    rotation_world_to_camera = np.asarray(
        camera_info.rotation_world_to_camera,
        dtype=float,
    ).reshape(3, 3)
    return _unit_vector(rotation_world_to_camera.T @ camera_ray)


def world_ray_velocity_to_pixel_rate(
    camera_info: Any,
    world_ray_ned: Sequence[float],
    world_ray_velocity_s: Sequence[float],
) -> np.ndarray:
    """Project an instantaneous world-ray derivative into image pixels/second."""

    rotation = np.asarray(camera_info.rotation_world_to_camera, dtype=float).reshape(3, 3)
    ray = rotation @ _unit_vector(world_ray_ned)
    velocity = rotation @ np.asarray(world_ray_velocity_s, dtype=float).reshape(3)
    depth = float(ray[2])
    if not np.isfinite(depth) or depth <= 1e-9:
        return np.zeros(2, dtype=float)
    return np.asarray(
        [
            float(camera_info.fx)
            * (float(velocity[0]) * depth - float(ray[0]) * float(velocity[2]))
            / (depth * depth),
            float(camera_info.fy)
            * (float(velocity[1]) * depth - float(ray[1]) * float(velocity[2]))
            / (depth * depth),
        ],
        dtype=float,
    )


def _unit_vector(value: Sequence[float]) -> np.ndarray:
    vector = np.asarray(value, dtype=float).reshape(3)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 1e-12:
        raise ValueError("unit ray is undefined for a zero or non-finite vector")
    return vector / norm


def _unit_ray_angle_rad(first: Sequence[float], second: Sequence[float]) -> float:
    first_unit = _unit_vector(first)
    second_unit = _unit_vector(second)
    return math.acos(float(np.clip(np.dot(first_unit, second_unit), -1.0, 1.0)))


class VelocityAwareAnonymousTracker:
    """Long-range-only constant-velocity bbox tracker with no truth inputs."""

    def __init__(
        self,
        camera_id: str,
        *,
        max_coast_s: float = 0.50,
        minimum_gate_px: float = 60.0,
    ) -> None:
        if max_coast_s <= 0.0 or minimum_gate_px <= 0.0:
            raise ValueError("tracker coast time and gate must be positive")
        self.camera_id = str(camera_id)
        self.max_coast_s = float(max_coast_s)
        self.minimum_gate_px = float(minimum_gate_px)
        self._tracks: dict[str, _AnonymousMotionTrack] = {}
        self._sequence = 0

    def update(
        self,
        detections: Sequence[Any],
        *,
        timestamp: float,
        frame_index: int,
        camera_info: Any,
    ) -> tuple[Any, ...]:
        timestamp = float(timestamp)
        active = {
            track_id: state
            for track_id, state in self._tracks.items()
            if timestamp - state.timestamp <= self.max_coast_s + 1e-9
        }
        track_ids = sorted(active)
        centers = [np.asarray(detection.center_px, dtype=float) for detection in detections]
        world_rays = [
            pixel_to_world_unit_ray(detection.center_px, camera_info)
            for detection in detections
        ]
        focal_px = max(float(camera_info.fx), float(camera_info.fy), 1.0)
        assignments: dict[int, str] = {}
        if track_ids and centers:
            costs = np.full((len(track_ids), len(centers)), 1e9, dtype=float)
            for track_index, track_id in enumerate(track_ids):
                state = active[track_id]
                dt = max(0.0, timestamp - state.timestamp)
                predicted_ray = _unit_vector(
                    state.world_ray_ned + state.world_ray_velocity_s * dt
                )
                predicted_log_area = state.log_bbox_area + state.log_bbox_area_rate_s * dt
                previous_extent = _bbox_max_extent(state.bbox_xyxy)
                for detection_index, detection in enumerate(detections):
                    bbox = tuple(float(value) for value in detection.bbox_xyxy)
                    extent = _bbox_max_extent(bbox)
                    gate_px = max(self.minimum_gate_px, 3.5 * max(previous_extent, extent))
                    gate_angle_rad = math.atan2(gate_px, focal_px)
                    angular_distance = _unit_ray_angle_rad(
                        world_rays[detection_index], predicted_ray
                    )
                    if angular_distance > gate_angle_rad:
                        continue
                    area = max(_bbox_area(bbox), 1.0)
                    size_cost = abs(math.log(area) - predicted_log_area)
                    costs[track_index, detection_index] = (
                        angular_distance / max(gate_angle_rad, 1e-9) + 0.20 * size_cost
                    )
            rows, columns = linear_sum_assignment(costs)
            for row, column in zip(rows.tolist(), columns.tolist()):
                if costs[row, column] < 1e8:
                    assignments[int(column)] = track_ids[int(row)]

        updated: dict[str, _AnonymousMotionTrack] = dict(active)
        results: list[Any] = []
        for detection_index, detection in enumerate(detections):
            center = centers[detection_index]
            world_ray = world_rays[detection_index]
            bbox = tuple(float(value) for value in detection.bbox_xyxy)
            log_area = math.log(max(_bbox_area(bbox), 1.0))
            track_id = assignments.get(detection_index)
            transition = "continued"
            if track_id is None:
                self._sequence += 1
                track_id = f"{self.camera_id}:lr-mot:{self._sequence:04d}"
                ray_velocity = np.zeros(3, dtype=float)
                log_area_rate = 0.0
                history_length = 1
                transition = "initialized"
            else:
                previous = active[track_id]
                dt = max(timestamp - previous.timestamp, 1e-6)
                observed_ray_velocity = (world_ray - previous.world_ray_ned) / dt
                observed_ray_velocity -= (
                    float(np.dot(observed_ray_velocity, world_ray)) * world_ray
                )
                ray_velocity = (
                    0.65 * previous.world_ray_velocity_s + 0.35 * observed_ray_velocity
                )
                ray_velocity -= float(np.dot(ray_velocity, world_ray)) * world_ray
                observed_log_area_rate = (log_area - previous.log_bbox_area) / dt
                log_area_rate = (
                    0.65 * previous.log_bbox_area_rate_s
                    + 0.35 * observed_log_area_rate
                )
                history_length = previous.history_length + 1
            updated[track_id] = _AnonymousMotionTrack(
                track_id=track_id,
                center_px=center,
                world_ray_ned=world_ray,
                world_ray_velocity_s=np.asarray(ray_velocity, dtype=float),
                bbox_xyxy=bbox,
                log_bbox_area=log_area,
                log_bbox_area_rate_s=float(log_area_rate),
                timestamp=timestamp,
                frame_index=int(frame_index),
                history_length=int(history_length),
            )
            metadata = dict(detection.metadata)
            metadata.update(
                {
                    "mot_backend": "long_range_world_ray_velocity_anonymous",
                    "camera_motion_compensated": True,
                    "world_ray_ned": [float(value) for value in world_ray],
                    "bearing_rate_px_s": [
                        float(value)
                        for value in world_ray_velocity_to_pixel_rate(
                            camera_info,
                            world_ray,
                            ray_velocity,
                        )
                    ],
                    "mot_history_length": int(history_length),
                    "track_transition_state": transition,
                    "online_truth_identity_used": False,
                }
            )
            results.append(replace(detection, local_track_id=track_id, metadata=metadata))
        self._tracks = updated
        return tuple(results)


def build_temporal_geometric_associators(
    scenario: LongRangeCVScenario,
    camera_vehicle_names: Iterable[str],
) -> dict[str, TemporalGeometricAssociator]:
    """Create episode-scoped D5 temporal state, isolated for every camera."""

    association_config = AssociationConfig(
        gate_chi2=25.0,
        min_lock_margin=1.0,
        max_lock_cost=100.0,
        min_mot_history=1,
        projection_regularization=1e-6,
    )
    temporal_config = TemporalGeometricAssociationConfig(
        association_config=association_config,
        coast_time_s=scenario.temporal_association_coast_s,
        challenger_required_frames=scenario.temporal_challenger_required_frames,
    )
    return {
        str(vehicle_name): TemporalGeometricAssociator(temporal_config)
        for vehicle_name in camera_vehicle_names
    }


def accepted_measured_pairs(
    result: TemporalGeometricAssociationResult,
) -> list[Any]:
    """Return only instantaneous pairs accepted by measured temporal evidence."""

    accepted = set(result.measured_assignments.items())
    return [
        pair
        for pair in result.instantaneous_result.pairs
        if (pair.track_id, pair.local_track_id) in accepted
    ]


@dataclass
class CuedGimbalScheduler:
    """Rate-limited interceptor gimbal that dwells on confirmed center cues."""

    max_rate_deg_s: float
    logic_rate_hz: float
    dwell_frames: int
    current_yaw_deg: float = 0.0
    current_pitch_deg: float = 0.0
    active_target_id: str | None = None
    queue: deque[str] = field(default_factory=deque)
    queued_ids: set[str] = field(default_factory=set)
    observed_ids: set[str] = field(default_factory=set)
    confirmed_ids: set[str] = field(default_factory=set)
    consecutive_hits: int = 0
    active_frames: int = 0
    target_timeout_frames: int = 100
    last_started_target_id: str | None = None
    last_failed_target: tuple[str, str] | None = None

    @property
    def max_step_deg(self) -> float:
        return self.max_rate_deg_s / self.logic_rate_hz

    def add_cues(self, global_track_ids: Iterable[str]) -> None:
        for raw_id in global_track_ids:
            target_id = str(raw_id)
            if target_id in self.queued_ids or target_id in self.confirmed_ids:
                continue
            self.queue.append(target_id)
            self.queued_ids.add(target_id)

    def command(
        self,
        desired_angles_deg: Mapping[str, tuple[float, float]],
    ) -> tuple[float, float, str, str | None]:
        self.last_started_target_id = None
        if self.active_target_id is None and self.queue:
            self.active_target_id = self.queue.popleft()
            self.active_frames = 0
            self.consecutive_hits = 0
            self.last_started_target_id = self.active_target_id
        if self.active_target_id is None:
            return self.current_yaw_deg, self.current_pitch_deg, "standby", None
        desired = desired_angles_deg.get(self.active_target_id)
        if desired is not None:
            self.current_yaw_deg = _rate_limit_angle(
                self.current_yaw_deg,
                desired[0],
                self.max_step_deg,
            )
            self.current_pitch_deg = _rate_limit_linear(
                self.current_pitch_deg,
                desired[1],
                self.max_step_deg,
            )
        return self.current_yaw_deg, self.current_pitch_deg, "cue_track", self.active_target_id

    def observe(self, observed_global_ids: Sequence[str]) -> tuple[str, ...]:
        self.last_failed_target = None
        observed = set(str(value) for value in observed_global_ids)
        self.observed_ids.update(observed.intersection(self.queued_ids))
        if self.active_target_id is None:
            return ()
        self.active_frames += 1
        if self.active_target_id in observed:
            self.observed_ids.add(self.active_target_id)
            self.consecutive_hits += 1
        else:
            self.consecutive_hits = 0
        completed: list[str] = []
        if self.consecutive_hits >= self.dwell_frames:
            self.confirmed_ids.add(self.active_target_id)
            completed.append(self.active_target_id)
            self.active_target_id = None
            self.consecutive_hits = 0
            self.active_frames = 0
        elif self.active_frames >= self.target_timeout_frames:
            self.last_failed_target = (
                self.active_target_id,
                "timeout_without_consecutive_detection",
            )
            self.active_target_id = None
            self.consecutive_hits = 0
            self.active_frames = 0
        return tuple(completed)


@dataclass(frozen=True)
class LongRangeEpisodeResult:
    mode: str
    output_dir: Path
    metrics: dict[str, Any]
    output_paths: dict[str, Path]


@dataclass(frozen=True)
class LongRangeCampaignResult:
    output_dir: Path
    settings_path: Path
    episode_results: tuple[LongRangeEpisodeResult, ...]
    output_paths: dict[str, Path]


def vertical_fov_degrees(horizontal_fov_deg: float, *, width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    half_horizontal = math.tan(math.radians(float(horizontal_fov_deg)) * 0.5)
    return math.degrees(2.0 * math.atan(half_horizontal * float(height) / float(width)))


def write_long_range_cv_settings(
    path: Path,
    *,
    scenario: LongRangeCVScenario,
    interceptor_initial_position_ned: tuple[float, float, float],
) -> Path:
    """Write two independently configured ComputerVision camera vehicles."""

    center_capture = _capture_settings(CENTER_CAMERA_SPEC)
    interceptor_capture = _capture_settings(INTERCEPTOR_CAMERA_SPEC)
    payload = {
        "SeeDocsAt": "https://microsoft.github.io/AirSim/settings/",
        "SettingsVersion": 1.2,
        "SimMode": "ComputerVision",
        "EnableRpc": True,
        "RpcEnabled": True,
        "ApiServerPort": int(scenario.api_port),
        "LocalHostIp": "127.0.0.1",
        "ClockSpeed": float(scenario.clock_speed),
        "ViewMode": "NoDisplay",
        "CameraDefaults": {"CaptureSettings": [center_capture]},
        "SubWindows": [],
        "Vehicles": {
            scenario.center_vehicle_name: _cv_vehicle_settings(
                scenario.center_position_ned,
                center_capture,
            ),
            scenario.interceptor_vehicle_name: _cv_vehicle_settings(
                interceptor_initial_position_ned,
                interceptor_capture,
            ),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def generate_long_range_target_specs(
    scenario: LongRangeCVScenario,
) -> tuple[BlocksActorTargetSpec, ...]:
    """Generate the selected immutable baseline or crossing-calibration geometry."""

    if scenario.geometry_profile == "baseline_v1":
        return _generate_baseline_target_specs(scenario)
    return _generate_crossing_calibration_target_specs(scenario)


def _generate_baseline_target_specs(
    scenario: LongRangeCVScenario,
) -> tuple[BlocksActorTargetSpec, ...]:
    """Generate depth-staggered trajectories with mild image-plane crossings."""

    rng = np.random.default_rng(int(scenario.seed))
    count = int(scenario.target_count)
    pair_count = count // 2
    if pair_count:
        base_yaws = np.linspace(
            -0.46 * scenario.target_azimuth_span_deg,
            0.46 * scenario.target_azimuth_span_deg,
            pair_count,
        )
        base_yaws += rng.uniform(-0.12, 0.12, size=pair_count)
        base_ranges = np.linspace(
            scenario.target_range_min_m + 70.0,
            scenario.target_range_max_m - 70.0,
            pair_count,
        )
        if pair_count > 2:
            base_ranges[1:-1] += rng.uniform(-18.0, 18.0, size=pair_count - 2)
    else:
        base_yaws = np.empty(0, dtype=float)
        base_ranges = np.empty(0, dtype=float)
    specs: list[BlocksActorTargetSpec] = []
    center_z = float(scenario.center_position_ned[2])
    for pair_index in range(pair_count):
        base_yaw = math.radians(float(base_yaws[pair_index]))
        crossing_time = float(
            rng.uniform(1.0, max(1.01, min(9.0, scenario.duration_s * 0.75)))
        )
        base_range = float(base_ranges[pair_index])
        depth_gap = float(rng.uniform(65.0, 115.0))
        elevation = math.radians(float(rng.uniform(-0.8, 0.8)))
        for member_index, lateral_sign in enumerate((1.0, -1.0)):
            index = pair_index * 2 + member_index
            range_x = base_range + (member_index - 0.5) * depth_gap
            speed = float(rng.uniform(scenario.target_speed_min_mps, scenario.target_speed_max_mps))
            lateral_speed = lateral_sign * min(float(rng.uniform(1.8, 2.8)), speed * 0.72)
            approach_speed = math.sqrt(max(speed * speed - lateral_speed * lateral_speed, 0.01))
            crossing_x = range_x - approach_speed * crossing_time
            crossing_y = crossing_x * math.tan(base_yaw)
            start_y = crossing_y - lateral_speed * crossing_time
            crossing_z = center_z - crossing_x * math.tan(elevation)
            object_id = f"TGT-{index + 1:03d}"
            specs.append(
                BlocksActorTargetSpec(
                    object_id=object_id,
                    actor_name=f"MSM_TargetActor_{index + 1}",
                    start_ned=(float(range_x), float(start_y), float(crossing_z)),
                    velocity_ned=(-float(approach_speed), float(lateral_speed), 0.0),
                    asset_name=scenario.target_asset_name,
                    scale=(scenario.target_scale,) * 3,
                    threat_score=max(0.5, 0.95 - index * 0.01),
                    coverage_cell="long-range-sector",
                )
            )
    if count % 2:
        index = count - 1
        range_x = float(rng.uniform(scenario.target_range_min_m, scenario.target_range_max_m))
        yaw = math.radians(float(rng.uniform(-5.0, 5.0)))
        speed = float(rng.uniform(scenario.target_speed_min_mps, scenario.target_speed_max_mps))
        lateral_speed = float(rng.uniform(-1.4, 1.4))
        approach_speed = math.sqrt(max(speed * speed - lateral_speed * lateral_speed, 0.01))
        specs.append(
            BlocksActorTargetSpec(
                object_id=f"TGT-{index + 1:03d}",
                actor_name=f"MSM_TargetActor_{index + 1}",
                start_ned=(range_x, range_x * math.tan(yaw), center_z + float(rng.uniform(-45.0, 45.0))),
                velocity_ned=(-approach_speed, lateral_speed, 0.0),
                asset_name=scenario.target_asset_name,
                scale=(scenario.target_scale,) * 3,
                threat_score=0.7,
                coverage_cell="long-range-sector",
            )
        )
    minimum = minimum_target_separation(specs, duration_s=scenario.duration_s)
    if minimum < 25.0:
        raise RuntimeError(f"generated target geometry violates 25 m separation: {minimum:.3f} m")
    return tuple(specs)


def _generate_crossing_calibration_target_specs(
    scenario: LongRangeCVScenario,
) -> tuple[BlocksActorTargetSpec, ...]:
    """Generate depth-separated pairs that remain jointly observable near crossings."""

    rng = np.random.default_rng(int(scenario.seed))
    count = int(scenario.target_count)
    pair_count = count // 2
    center_z = float(scenario.center_position_ned[2])
    specs: list[BlocksActorTargetSpec] = []
    if pair_count:
        base_yaws = np.linspace(
            -0.42 * scenario.target_azimuth_span_deg,
            0.42 * scenario.target_azimuth_span_deg,
            pair_count,
        )
        base_ranges = np.linspace(
            scenario.target_range_min_m + 90.0,
            scenario.target_range_max_m - 90.0,
            pair_count,
        )
        start_time = min(2.0, scenario.duration_s * 0.20)
        end_time = max(start_time + 0.10, scenario.duration_s - 2.0)
        crossing_times = np.linspace(start_time, end_time, pair_count)
        base_yaws += rng.uniform(-0.05, 0.05, size=pair_count)
        base_ranges += rng.uniform(-4.0, 4.0, size=pair_count)
        crossing_times += rng.uniform(-0.08, 0.08, size=pair_count)
    else:
        base_yaws = np.empty(0, dtype=float)
        base_ranges = np.empty(0, dtype=float)
        crossing_times = np.empty(0, dtype=float)

    for pair_index in range(pair_count):
        base_yaw = math.radians(float(base_yaws[pair_index]))
        crossing_time = float(
            np.clip(crossing_times[pair_index], 0.25, scenario.duration_s - 0.25)
        )
        base_range = float(base_ranges[pair_index])
        depth_gap = float(76.0 + 4.0 * (pair_index % 3))
        elevation = math.radians(float((-0.35, 0.0, 0.35)[pair_index % 3]))
        for member_index, lateral_sign in enumerate((1.0, -1.0)):
            index = pair_index * 2 + member_index
            range_x = base_range + (member_index - 0.5) * depth_gap
            speed = float(
                rng.uniform(scenario.target_speed_min_mps, scenario.target_speed_max_mps)
            )
            lateral_speed = lateral_sign * float(0.65 + 0.08 * (pair_index % 4))
            approach_speed = math.sqrt(max(speed * speed - lateral_speed * lateral_speed, 0.01))
            crossing_x = range_x - approach_speed * crossing_time
            crossing_y = crossing_x * math.tan(base_yaw)
            start_y = crossing_y - lateral_speed * crossing_time
            crossing_z = center_z - crossing_x * math.tan(elevation)
            specs.append(
                BlocksActorTargetSpec(
                    object_id=f"TGT-{index + 1:03d}",
                    actor_name=f"MSM_TargetActor_{index + 1}",
                    start_ned=(float(range_x), float(start_y), float(crossing_z)),
                    velocity_ned=(-float(approach_speed), float(lateral_speed), 0.0),
                    asset_name=scenario.target_asset_name,
                    scale=(scenario.target_scale,) * 3,
                    threat_score=max(0.5, 0.95 - index * 0.01),
                    coverage_cell="long-range-crossing-calibration",
                )
            )

    if count % 2:
        index = count - 1
        range_x = float((scenario.target_range_min_m + scenario.target_range_max_m) * 0.5)
        speed = float((scenario.target_speed_min_mps + scenario.target_speed_max_mps) * 0.5)
        specs.append(
            BlocksActorTargetSpec(
                object_id=f"TGT-{index + 1:03d}",
                actor_name=f"MSM_TargetActor_{index + 1}",
                start_ned=(range_x, 0.0, center_z - 55.0),
                velocity_ned=(-speed, 0.0, 0.0),
                asset_name=scenario.target_asset_name,
                scale=(scenario.target_scale,) * 3,
                threat_score=0.7,
                coverage_cell="long-range-crossing-calibration",
            )
        )

    minimum = minimum_target_separation(specs, duration_s=scenario.duration_s)
    if minimum < 25.0:
        raise RuntimeError(
            f"crossing calibration geometry violates 25 m separation: {minimum:.3f} m"
        )
    preflight = crossing_geometry_preflight(tuple(specs), scenario)
    if not preflight["passed"]:
        raise RuntimeError(
            "crossing calibration geometry preflight failed: "
            f"{preflight['planned_evaluable_pair_count']}/"
            f"{preflight['required_pair_count']} pairs"
        )
    return tuple(specs)


def crossing_geometry_preflight(
    specs: Sequence[BlocksActorTargetSpec],
    scenario: LongRangeCVScenario,
) -> dict[str, Any]:
    """Check pair crossings and shared camera footprint before launching AirSim."""

    pair_count = len(specs) // 2
    sample_times = np.linspace(0.0, scenario.duration_s, max(1001, scenario.frame_count + 1))
    pair_rows: list[dict[str, Any]] = []
    for pair_index in range(pair_count):
        first = specs[pair_index * 2]
        second = specs[pair_index * 2 + 1]
        differences = []
        for timestamp in sample_times:
            camera = np.asarray(scenario.center_position_ned, dtype=float)
            first_delta = np.asarray(first.position_at(float(timestamp)), dtype=float) - camera
            second_delta = np.asarray(second.position_at(float(timestamp)), dtype=float) - camera
            differences.append(
                math.atan2(float(first_delta[1]), float(first_delta[0]))
                - math.atan2(float(second_delta[1]), float(second_delta[0]))
            )
        crossing_time = None
        for index in range(1, len(sample_times)):
            before = differences[index - 1]
            after = differences[index]
            if before * after <= 0.0:
                fraction = abs(before) / max(abs(before) + abs(after), 1e-12)
                crossing_time = float(
                    sample_times[index - 1]
                    + fraction * (sample_times[index] - sample_times[index - 1])
                )
                break
        jointly_visible_samples = 0
        if crossing_time is not None:
            for timestamp in (
                max(0.0, crossing_time - scenario.dt_s),
                crossing_time,
                min(scenario.duration_s, crossing_time + scenario.dt_s),
            ):
                camera = np.asarray(scenario.center_position_ned, dtype=float)
                first_delta = np.asarray(first.position_at(timestamp), dtype=float) - camera
                second_delta = np.asarray(second.position_at(timestamp), dtype=float) - camera
                yaw_delta = abs(
                    math.degrees(
                        math.atan2(float(first_delta[1]), float(first_delta[0]))
                        - math.atan2(float(second_delta[1]), float(second_delta[0]))
                    )
                )
                first_pitch = math.degrees(
                    math.atan2(-float(first_delta[2]), math.hypot(first_delta[0], first_delta[1]))
                )
                second_pitch = math.degrees(
                    math.atan2(-float(second_delta[2]), math.hypot(second_delta[0], second_delta[1]))
                )
                if (
                    yaw_delta <= CENTER_CAMERA_SPEC.horizontal_fov_deg * 0.90
                    and abs(first_pitch - second_pitch)
                    <= CENTER_CAMERA_SPEC.vertical_fov_deg * 0.90
                ):
                    jointly_visible_samples += 1
        pair_rows.append(
            {
                "pair_index": pair_index,
                "target_ids": [first.object_id, second.object_id],
                "crossing_timestamp": crossing_time,
                "jointly_visible_sample_count": jointly_visible_samples,
                "planned_evaluable": bool(
                    crossing_time is not None and jointly_visible_samples >= 2
                ),
            }
        )
    planned = sum(row["planned_evaluable"] for row in pair_rows)
    minimum = minimum_target_separation(specs, duration_s=scenario.duration_s)
    return {
        "schema_version": "d5-crossing-geometry-preflight-v1",
        "geometry_only": True,
        "does_not_use_detection_results": True,
        "required_pair_count": pair_count,
        "planned_evaluable_pair_count": planned,
        "minimum_3d_separation_m": minimum,
        "passed": bool(planned == pair_count and minimum >= 25.0),
        "pairs": pair_rows,
    }


def minimum_target_separation(
    specs: Sequence[BlocksActorTargetSpec],
    *,
    duration_s: float,
    samples: int = 121,
) -> float:
    if len(specs) < 2:
        return math.inf
    minimum = math.inf
    for timestamp in np.linspace(0.0, float(duration_s), max(2, int(samples))):
        positions = np.asarray([spec.position_at(float(timestamp)) for spec in specs], dtype=float)
        for row in range(len(specs)):
            delta = positions[row + 1 :] - positions[row]
            if delta.size:
                minimum = min(minimum, float(np.min(np.linalg.norm(delta, axis=1))))
    return minimum


def projected_trajectory_crossing_count(
    specs: Sequence[BlocksActorTargetSpec],
    *,
    camera_position_ned: tuple[float, float, float],
    duration_s: float,
) -> int:
    """Count horizontal line-of-sight ordering reversals over the episode."""

    camera = np.asarray(camera_position_ned, dtype=float)
    starts = np.asarray([spec.position_at(0.0) for spec in specs], dtype=float) - camera
    ends = np.asarray([spec.position_at(duration_s) for spec in specs], dtype=float) - camera
    start_angles = np.arctan2(starts[:, 1], starts[:, 0])
    end_angles = np.arctan2(ends[:, 1], ends[:, 0])
    count = 0
    for first in range(len(specs)):
        for second in range(first + 1, len(specs)):
            before = float(start_angles[first] - start_angles[second])
            after = float(end_angles[first] - end_angles[second])
            if before == 0.0 or after == 0.0 or before * after < 0.0:
                count += 1
    return count


def snapshot_frame_indices(
    *,
    duration_s: float,
    logic_rate_hz: float,
    interval_s: float,
) -> tuple[int, ...]:
    """Return endpoint-inclusive logical frames for periodic scene evidence."""

    if duration_s <= 0.0 or logic_rate_hz <= 0.0 or interval_s <= 0.0:
        raise ValueError("duration, logic rate, and snapshot interval must be positive")
    last_frame = int(round(float(duration_s) * float(logic_rate_hz)))
    timestamps = np.arange(0.0, float(duration_s) + 1e-9, float(interval_s))
    frames = {
        min(last_frame, max(0, int(round(float(timestamp) * float(logic_rate_hz)))))
        for timestamp in timestamps
    }
    return tuple(sorted(frames))


def _long_range_crossing_windows(
    specs: Sequence[BlocksActorTargetSpec],
    scenario: LongRangeCVScenario,
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    sample_count = max(401, scenario.frame_count + 1)
    timestamps = np.linspace(0.0, scenario.duration_s, sample_count)
    camera_positions = {
        scenario.center_vehicle_name: lambda timestamp: scenario.center_position_ned,
        scenario.interceptor_vehicle_name: lambda timestamp: _interceptor_position(
            specs, timestamp, scenario
        ),
    }
    for camera_name, camera_position_at in camera_positions.items():
        for first in range(len(specs)):
            for second in range(first + 1, len(specs)):
                differences: list[float] = []
                for timestamp in timestamps:
                    camera = np.asarray(camera_position_at(float(timestamp)), dtype=float)
                    first_delta = np.asarray(specs[first].position_at(float(timestamp))) - camera
                    second_delta = np.asarray(specs[second].position_at(float(timestamp))) - camera
                    differences.append(
                        math.atan2(float(first_delta[1]), float(first_delta[0]))
                        - math.atan2(float(second_delta[1]), float(second_delta[0]))
                    )
                crossing_time: float | None = None
                for index in range(1, len(timestamps)):
                    before = differences[index - 1]
                    after = differences[index]
                    if math.isclose(before, 0.0, abs_tol=1e-12):
                        crossing_time = float(timestamps[index - 1])
                        break
                    if before * after < 0.0 or math.isclose(after, 0.0, abs_tol=1e-12):
                        fraction = abs(before) / max(abs(before) + abs(after), 1e-12)
                        crossing_time = float(
                            timestamps[index - 1]
                            + fraction * (timestamps[index] - timestamps[index - 1])
                        )
                        break
                if crossing_time is None:
                    continue
                half_width = scenario.crossing_window_half_width_s
                windows.append(
                    {
                        "camera_vehicle_name": camera_name,
                        "target_a_global_track_id": _global_id_from_object_id(specs[first].object_id),
                        "target_b_global_track_id": _global_id_from_object_id(specs[second].object_id),
                        "crossing_timestamp": crossing_time,
                        "window_start_timestamp": max(0.0, crossing_time - half_width),
                        "window_end_timestamp": min(
                            scenario.duration_s, crossing_time + half_width
                        ),
                        "offline_truth_only": True,
                    }
                )
    return windows


def evaluate_mot_continuity(
    rows: Sequence[Mapping[str, Any]],
    *,
    crossing_windows: Sequence[Mapping[str, Any]] = (),
    continuous_visibility_gap_s: float = 0.05,
    reacquisition_gap_s: float = 0.50,
) -> dict[str, Any]:
    """Score visible tracking, short gaps, and long reacquisition separately."""

    if continuous_visibility_gap_s <= 0.0:
        raise ValueError("continuous_visibility_gap_s must be positive")
    if reacquisition_gap_s <= continuous_visibility_gap_s:
        raise ValueError("reacquisition_gap_s must exceed continuous_visibility_gap_s")

    camera_names = sorted(
        {str(row.get("camera_vehicle_name", "")) for row in rows if row.get("camera_vehicle_name")}
        | {
            str(window.get("camera_vehicle_name", ""))
            for window in crossing_windows
            if window.get("camera_vehicle_name")
        }
    )
    by_camera: dict[str, dict[str, Any]] = {}
    for camera_name in camera_names:
        camera_rows = [
            row
            for row in rows
            if str(row.get("camera_vehicle_name", "")) == camera_name
        ]
        windows = [
            window
            for window in crossing_windows
            if str(window.get("camera_vehicle_name", "")) == camera_name
        ]
        by_camera[camera_name] = _mot_continuity_summary(
            camera_rows,
            windows,
            continuous_visibility_gap_s=continuous_visibility_gap_s,
            reacquisition_gap_s=reacquisition_gap_s,
        )

    observation_count = sum(item["observation_count"] for item in by_camera.values())
    crossing_observation_count = sum(
        item["crossing_observation_count"] for item in by_camera.values()
    )

    def weighted(name: str, weight_name: str) -> float | None:
        weighted_values = [
            (float(item[name]), int(item[weight_name]))
            for item in by_camera.values()
            if item[name] is not None and int(item[weight_name]) > 0
        ]
        denominator = sum(weight for _value, weight in weighted_values)
        if denominator == 0:
            return None
        return sum(value * weight for value, weight in weighted_values) / denominator

    aggregate = {
        "camera_count": len(by_camera),
        "observation_count": observation_count,
        "truth_track_count": sum(item["truth_track_count"] for item in by_camera.values()),
        "anonymous_track_count": sum(item["anonymous_track_count"] for item in by_camera.values()),
        "raw_total_id_switch_count": sum(
            item["raw_total_id_switch_count"] for item in by_camera.values()
        ),
        "raw_total_fragmentation_count": sum(
            item["raw_total_fragmentation_count"] for item in by_camera.values()
        ),
        "id_switch_count": sum(item["id_switch_count"] for item in by_camera.values()),
        "fragmentation_count": sum(item["fragmentation_count"] for item in by_camera.values()),
        "short_gap_identity_change_count": sum(
            item["short_gap_identity_change_count"] for item in by_camera.values()
        ),
        "reacquisition_count": sum(
            item["reacquisition_count"] for item in by_camera.values()
        ),
        "reacquisition_identity_changed_count": sum(
            item["reacquisition_identity_changed_count"] for item in by_camera.values()
        ),
        "unmatched_count": sum(item["unmatched_count"] for item in by_camera.values()),
        "track_purity": weighted("track_purity", "observation_count"),
        "track_continuity": weighted("track_continuity", "observation_count"),
        "crossing_window_count": sum(item["crossing_window_count"] for item in by_camera.values()),
        "crossing_evaluable_window_count": sum(
            item["crossing_evaluable_window_count"] for item in by_camera.values()
        ),
        "crossing_not_evaluable_window_count": sum(
            item["crossing_not_evaluable_window_count"] for item in by_camera.values()
        ),
        "crossing_observation_count": crossing_observation_count,
        "crossing_id_switch_count": sum(
            item["crossing_id_switch_count"] for item in by_camera.values()
        ),
        "crossing_track_purity": weighted(
            "crossing_track_purity", "crossing_observation_count"
        ),
        "crossing_track_continuity": weighted(
            "crossing_track_continuity", "crossing_observation_count"
        ),
        "crossing_window_results": [
            window
            for item in by_camera.values()
            for window in item["crossing_window_results"]
        ],
    }
    aggregate["crossing_availability"] = bool(
        aggregate["crossing_evaluable_window_count"] > 0
    )
    aggregate["gate_passed"] = bool(
        observation_count > 0
        and aggregate["id_switch_count"] == 0
        and aggregate["fragmentation_count"] == 0
        and aggregate["track_purity"] is not None
        and aggregate["track_purity"] >= 0.95
        and aggregate["track_continuity"] is not None
        and aggregate["track_continuity"] >= 0.90
        and aggregate["crossing_availability"]
        and aggregate["crossing_id_switch_count"] == 0
        and aggregate["crossing_track_purity"] is not None
        and aggregate["crossing_track_purity"] >= 0.95
        and aggregate["crossing_track_continuity"] is not None
        and aggregate["crossing_track_continuity"] >= 0.90
    )
    return {
        "schema_version": "d5-long-range-mot-continuity-v2",
        "tracker_backend": "long_range_world_ray_velocity_anonymous",
        "truth_usage": "offline_scoring_only",
        "gap_policy": {
            "continuous_visibility_gap_s": float(continuous_visibility_gap_s),
            "reacquisition_gap_s": float(reacquisition_gap_s),
            "short_gap_definition": "continuous_visibility_gap_s < gap <= reacquisition_gap_s",
            "long_reacquisition_definition": "gap > reacquisition_gap_s",
        },
        "thresholds": {
            "id_switch_count": 0,
            "short_gap_fragmentation_count": 0,
            "minimum_track_purity": 0.95,
            "minimum_track_continuity": 0.90,
            "minimum_evaluable_crossing_window_count": 1,
            "crossing_id_switch_count": 0,
            "minimum_crossing_track_purity": 0.95,
            "minimum_crossing_track_continuity": 0.90,
        },
        "by_camera": by_camera,
        "aggregate": aggregate,
    }


def _mot_continuity_summary(
    rows: Sequence[Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]],
    *,
    continuous_visibility_gap_s: float,
    reacquisition_gap_s: float,
) -> dict[str, Any]:
    valid_rows = [row for row in rows if row.get("truth_global_track_id")]
    unmatched_count = sum(not row.get("local_track_id") for row in valid_rows)
    matched_rows = [row for row in valid_rows if row.get("local_track_id")]
    by_truth: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_local: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in matched_rows:
        by_truth[str(row["truth_global_track_id"])].append(row)
        by_local[str(row["local_track_id"])].append(row)

    raw_id_switch_count = 0
    raw_fragmentation_count = 0
    visible_id_switch_count = 0
    short_gap_fragmentation_count = 0
    short_gap_identity_change_count = 0
    reacquisition_count = 0
    reacquisition_identity_changed_count = 0
    continuity_numerator = 0.0
    continuity_denominator = 0
    for truth_rows in by_truth.values():
        ordered = sorted(
            truth_rows,
            key=lambda row: (int(row["frame_index"]), float(row["measurement_timestamp"])),
        )
        visible_segments: list[list[Mapping[str, Any]]] = [[ordered[0]]]
        raw_segment_count = 1
        for previous, current in zip(ordered, ordered[1:]):
            same_id = str(previous["local_track_id"]) == str(current["local_track_id"])
            frame_gap = int(current["frame_index"]) - int(previous["frame_index"])
            time_gap = float(current["measurement_timestamp"]) - float(
                previous["measurement_timestamp"]
            )
            if not same_id:
                raw_id_switch_count += 1
            if not same_id or frame_gap > 1:
                raw_segment_count += 1
            if time_gap > reacquisition_gap_s:
                reacquisition_count += 1
                reacquisition_identity_changed_count += int(not same_id)
                visible_segments.append([current])
            elif time_gap > continuous_visibility_gap_s:
                short_gap_fragmentation_count += 1
                short_gap_identity_change_count += int(not same_id)
                visible_segments.append([current])
            else:
                visible_id_switch_count += int(not same_id)
                visible_segments[-1].append(current)
        raw_fragmentation_count += max(0, raw_segment_count - 1)
        for segment in visible_segments:
            longest_run = 1
            current_run = 1
            for previous, current in zip(segment, segment[1:]):
                if str(previous["local_track_id"]) == str(current["local_track_id"]):
                    current_run += 1
                else:
                    current_run = 1
                longest_run = max(longest_run, current_run)
            continuity_numerator += longest_run
            continuity_denominator += len(segment)

    purity_numerator = 0
    for local_rows in by_local.values():
        counts = _count_values(str(row["truth_global_track_id"]) for row in local_rows)
        purity_numerator += max(counts.values(), default=0)
    track_purity = purity_numerator / len(matched_rows) if matched_rows else None
    crossing_results = [
        _evaluate_pair_crossing_window(
            matched_rows,
            window,
            continuous_visibility_gap_s=continuous_visibility_gap_s,
        )
        for window in windows
    ]
    evaluable_crossings = [row for row in crossing_results if row["availability"]]
    crossing_observation_count = sum(
        int(row["observation_count"]) for row in evaluable_crossings
    )

    def crossing_weighted(name: str) -> float | None:
        if crossing_observation_count <= 0:
            return None
        return sum(
            float(row[name]) * int(row["observation_count"])
            for row in evaluable_crossings
            if row[name] is not None
        ) / crossing_observation_count

    summary = {
        "observation_count": len(valid_rows),
        "truth_track_count": len(by_truth),
        "anonymous_track_count": len(by_local),
        "raw_total_id_switch_count": raw_id_switch_count,
        "raw_total_fragmentation_count": raw_fragmentation_count,
        "id_switch_count": visible_id_switch_count,
        "fragmentation_count": short_gap_fragmentation_count,
        "short_gap_identity_change_count": short_gap_identity_change_count,
        "reacquisition_count": reacquisition_count,
        "reacquisition_identity_changed_count": reacquisition_identity_changed_count,
        "unmatched_count": unmatched_count,
        "track_purity": track_purity,
        "track_continuity": (
            continuity_numerator / continuity_denominator
            if continuity_denominator > 0
            else None
        ),
        "crossing_window_count": len(windows),
        "crossing_evaluable_window_count": len(evaluable_crossings),
        "crossing_not_evaluable_window_count": len(windows) - len(evaluable_crossings),
        "crossing_availability": bool(evaluable_crossings),
        "crossing_observation_count": crossing_observation_count,
        "crossing_id_switch_count": sum(
            int(row["id_switch_count"]) for row in evaluable_crossings
        ),
        "crossing_track_purity": crossing_weighted("track_purity"),
        "crossing_track_continuity": crossing_weighted("track_continuity"),
        "crossing_window_results": crossing_results,
    }
    summary["gate_passed"] = bool(
        summary["observation_count"] > 0
        and summary["id_switch_count"] == 0
        and summary["fragmentation_count"] == 0
        and summary["track_purity"] is not None
        and summary["track_purity"] >= 0.95
        and summary["track_continuity"] is not None
        and summary["track_continuity"] >= 0.90
        and summary["crossing_availability"]
        and summary["crossing_id_switch_count"] == 0
        and summary["crossing_track_purity"] is not None
        and summary["crossing_track_purity"] >= 0.95
        and summary["crossing_track_continuity"] is not None
        and summary["crossing_track_continuity"] >= 0.90
    )
    return summary


def _evaluate_pair_crossing_window(
    rows: Sequence[Mapping[str, Any]],
    window: Mapping[str, Any],
    *,
    continuous_visibility_gap_s: float,
) -> dict[str, Any]:
    target_a = str(window.get("target_a_global_track_id", ""))
    target_b = str(window.get("target_b_global_track_id", ""))
    pair = {target_a, target_b} - {""}
    start = float(window["window_start_timestamp"])
    end = float(window["window_end_timestamp"])
    pair_rows = [
        row
        for row in rows
        if str(row.get("truth_global_track_id", "")) in pair
        and start - 1e-9 <= float(row["measurement_timestamp"]) <= end + 1e-9
    ]
    by_truth: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in pair_rows:
        by_truth[str(row["truth_global_track_id"])].append(row)
    missing = sorted(pair - set(by_truth))
    shared_frames = (
        {
            int(row["frame_index"])
            for row in by_truth.get(target_a, [])
        }
        & {
            int(row["frame_index"])
            for row in by_truth.get(target_b, [])
        }
    )
    unavailable_reason = ""
    if len(pair) != 2:
        unavailable_reason = "crossing_pair_ids_missing"
    elif missing:
        unavailable_reason = "missing_pair_observation:" + ",".join(missing)
    elif min(len(by_truth[target_a]), len(by_truth[target_b])) < 2:
        unavailable_reason = "insufficient_temporal_samples"
    elif not shared_frames:
        unavailable_reason = "pair_not_simultaneously_visible"
    availability = not unavailable_reason
    result = {
        "camera_vehicle_name": str(window.get("camera_vehicle_name", "")),
        "target_a_global_track_id": target_a,
        "target_b_global_track_id": target_b,
        "window_start_timestamp": start,
        "window_end_timestamp": end,
        "availability": availability,
        "status": "evaluable" if availability else "not_evaluable",
        "unavailable_reason": unavailable_reason,
        "raw_pair_observation_count": len(pair_rows),
        "observation_count": len(pair_rows) if availability else 0,
        "simultaneous_frame_count": len(shared_frames),
        "id_switch_count": None,
        "track_purity": None,
        "track_continuity": None,
        "gate_passed": False,
    }
    if not availability:
        return result
    id_switch_count = 0
    continuity_numerator = 0.0
    continuity_denominator = 0
    for truth_id in (target_a, target_b):
        ordered = sorted(
            by_truth[truth_id],
            key=lambda row: (int(row["frame_index"]), float(row["measurement_timestamp"])),
        )
        segments: list[list[Mapping[str, Any]]] = [[ordered[0]]]
        for previous, current in zip(ordered, ordered[1:]):
            gap = float(current["measurement_timestamp"]) - float(
                previous["measurement_timestamp"]
            )
            same_id = str(previous["local_track_id"]) == str(current["local_track_id"])
            if gap <= continuous_visibility_gap_s:
                id_switch_count += int(not same_id)
                segments[-1].append(current)
            else:
                segments.append([current])
        for segment in segments:
            longest = 1
            run = 1
            for previous, current in zip(segment, segment[1:]):
                if str(previous["local_track_id"]) == str(current["local_track_id"]):
                    run += 1
                else:
                    run = 1
                longest = max(longest, run)
            continuity_numerator += longest
            continuity_denominator += len(segment)
    by_local: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in pair_rows:
        by_local[str(row["local_track_id"])].append(row)
    purity_numerator = sum(
        max(
            _count_values(str(row["truth_global_track_id"]) for row in local_rows).values(),
            default=0,
        )
        for local_rows in by_local.values()
    )
    purity = purity_numerator / len(pair_rows)
    continuity = (
        continuity_numerator / continuity_denominator
        if continuity_denominator > 0
        else None
    )
    result.update(
        {
            "id_switch_count": id_switch_count,
            "track_purity": purity,
            "track_continuity": continuity,
            "gate_passed": bool(
                id_switch_count == 0
                and purity >= 0.95
                and continuity is not None
                and continuity >= 0.90
            ),
        }
    )
    return result


def run_long_range_cv_campaign(
    *,
    scenario: LongRangeCVScenario,
    output_dir: Path,
    modes: Sequence[str] = SUPPORTED_SCAN_MODES,
    blocks_script: Path = Path("Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh"),
    blocks_args: tuple[str, ...] = ("-windowed", "-ResX=640", "-ResY=480", "-NoVSync", "-NoHMD", "-NoSound"),
    launch_blocks: bool = True,
    connection_timeout_s: float = 90.0,
    client_timeout_s: float = 5.0,
    prefer_nvidia_offload: bool = True,
    runtime: RealAirSimRuntimeClient | None = None,
    process_manager: BlocksProcessManager | None = None,
) -> LongRangeCampaignResult:
    """Run scan modes under one Blocks process with a reset between episodes."""

    normalized_modes = tuple(str(mode) for mode in modes)
    if not normalized_modes or any(mode not in SUPPORTED_SCAN_MODES for mode in normalized_modes):
        raise ValueError(f"modes must be drawn from {SUPPORTED_SCAN_MODES}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target_specs = generate_long_range_target_specs(scenario)
    interceptor_initial = _interceptor_position(target_specs, 0.0, scenario)
    settings_path = write_long_range_cv_settings(
        output_dir / "settings.json",
        scenario=scenario,
        interceptor_initial_position_ned=interceptor_initial,
    )
    scenario_path = _write_json(
        output_dir / "scenario.json",
        _scenario_payload(scenario, target_specs, interceptor_initial),
    )
    process = process_manager or BlocksProcessManager(
        blocks_script=Path(blocks_script),
        settings_path=settings_path,
        output_dir=output_dir,
        extra_args=tuple(blocks_args),
        prefer_nvidia_offload=bool(prefer_nvidia_offload),
    )
    shared_runtime = runtime or RealAirSimRuntimeClient(
        ip="127.0.0.1",
        port=scenario.api_port,
        timeout_value=float(client_timeout_s),
        client_kind="vehicle",
    )
    if launch_blocks:
        process.start()
    try:
        shared_runtime.wait_for_connection(float(connection_timeout_s))
        results: list[LongRangeEpisodeResult] = []
        for index, mode in enumerate(normalized_modes):
            if index > 0:
                shared_runtime.reset()
                shared_runtime.wait_for_connection(float(connection_timeout_s))
            episode_dir = output_dir / mode
            result = _run_long_range_mode(
                shared_runtime,
                scenario=scenario,
                target_specs=target_specs,
                settings_path=settings_path,
                output_dir=episode_dir,
                mode=mode,
            )
            results.append(result)
    finally:
        if launch_blocks:
            process.stop()
    output_paths: dict[str, Path] = {
        "settings": settings_path,
        "scenario": scenario_path,
    }
    if launch_blocks:
        if process.log_path.exists():
            output_paths["blocks_log"] = process.log_path
        try:
            output_paths["blocks_diagnostics"] = process.write_diagnostics()
        except Exception:
            pass
    if len(results) > 1:
        output_paths.update(_write_campaign_comparison(output_dir, results, scenario))
    video_files = sorted(
        str(path.relative_to(output_dir))
        for suffix in ("*.mp4", "*.gif", "*.avi", "*.mov", "*.mkv")
        for path in output_dir.rglob(suffix)
    )
    campaign_manifest = {
        "schema_version": "d5-long-range-campaign-record-manifest-v1",
        "modes": list(normalized_modes),
        "reset_between_profiles": len(normalized_modes) > 1,
        "launch_blocks": bool(launch_blocks),
        "root_artifacts": {
            name: {"path": str(path), "exists": path.exists()}
            for name, path in sorted(output_paths.items())
        },
        "episode_manifests": {
            result.mode: str(result.output_paths.get("record_manifest", ""))
            for result in results
        },
        "blocks_log_missing_reason": (
            ""
            if "blocks_log" in output_paths
            else "external_or_mock_runtime" if not launch_blocks else "log_not_generated"
        ),
        "video_generated": bool(video_files),
        "video_files": video_files,
    }
    output_paths["record_manifest"] = _write_json(
        output_dir / "record_manifest.json", campaign_manifest
    )
    return LongRangeCampaignResult(
        output_dir=output_dir,
        settings_path=settings_path,
        episode_results=tuple(results),
        output_paths=output_paths,
    )


def _run_long_range_mode(
    runtime: RealAirSimRuntimeClient,
    *,
    scenario: LongRangeCVScenario,
    target_specs: tuple[BlocksActorTargetSpec, ...],
    settings_path: Path,
    output_dir: Path,
    mode: str,
) -> LongRangeEpisodeResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    definition = scan_mode_definition(
        mode,
        camera_fov_deg=CENTER_CAMERA_SPEC.horizontal_fov_deg,
        logic_rate_hz=scenario.logic_rate_hz,
    )
    initial_tracks, _initial_positions = _global_tracks(
        target_specs,
        0.0,
        position_sigma_m=scenario.global_track_position_sigma_m,
    )
    pitch_plan = derive_pitch_search_plan(
        initial_tracks,
        camera_position_ned=scenario.center_position_ned,
        overlap_ratio=scenario.scan_overlap_ratio,
    )
    raster_overlap = scenario.scan_overlap_ratio if mode == "coverage_safe" else 0.0
    raster_horizontal_fov = (
        CENTER_CAMERA_SPEC.horizontal_fov_deg
        if mode == "coverage_safe"
        else definition.step_deg
    )
    raster_waypoints = build_serpentine_scan_grid(
        min_yaw_deg=scenario.search_sector_min_deg,
        max_yaw_deg=scenario.search_sector_max_deg,
        min_pitch_deg=pitch_plan.min_pitch_deg,
        max_pitch_deg=pitch_plan.max_pitch_deg,
        horizontal_fov_deg=raster_horizontal_fov,
        vertical_fov_deg=CENTER_CAMERA_SPEC.vertical_fov_deg,
        overlap_ratio=raster_overlap,
    )
    raster_pitch_rows = tuple(dict.fromkeys(pitch for _yaw, pitch in raster_waypoints))
    smoke_config = BlocksSmokeConfig(
        episode_id=f"d5_long_range_{mode}",
        scenario_name="d5_long_range_cv_scan",
        duration_s=scenario.duration_s,
        dt_s=scenario.dt_s,
        clock_speed=scenario.clock_speed,
        seed=scenario.seed,
        settings_path=settings_path,
        output_root=output_dir.parent,
        camera_vehicle_name=scenario.center_vehicle_name,
        camera_vehicle_names=(scenario.center_vehicle_name, scenario.interceptor_vehicle_name),
        camera_name=scenario.camera_name,
        capture_lidar=False,
        target_vehicle_names=(),
        resource_vehicle_names=(scenario.interceptor_vehicle_name,),
        target_actor_specs=target_specs,
        detection_backend="airsim",
        detection_filter_names=("MSM_TargetActor_*",),
        detection_radius_cm=scenario.detection_radius_cm,
        include_integrated_pipeline=False,
        save_images=False,
        destroy_spawned_actor_targets=True,
        metadata={
            "runtime_mode": "long_range_cv_scan",
            "scan_mode": mode,
            "online_truth_identity_use_count": 0,
            "global_track_id_rewrite_count": 0,
            "global_track_source": "synthetic_d1_d2_fixture",
        },
    )
    center_scheduler = SectorScanScheduler(
        definition,
        min_yaw_deg=scenario.search_sector_min_deg,
        max_yaw_deg=scenario.search_sector_max_deg,
        dwell_frames=scenario.dwell_frames,
        raster_waypoints=raster_waypoints,
    )
    interceptor_scheduler = CuedGimbalScheduler(
        max_rate_deg_s=180.0,
        logic_rate_hz=scenario.logic_rate_hz,
        dwell_frames=scenario.dwell_frames,
        target_timeout_frames=max(1, int(round(scenario.cue_timeout_s * scenario.logic_rate_hz))),
    )
    anonymous_trackers = {
        vehicle_name: VelocityAwareAnonymousTracker(
            f"{vehicle_name}:{scenario.camera_name}",
            max_coast_s=scenario.mot_max_coast_s,
        )
        for vehicle_name in (
            scenario.center_vehicle_name,
            scenario.interceptor_vehicle_name,
        )
    }
    temporal_associators = build_temporal_geometric_associators(
        scenario,
        (
            scenario.center_vehicle_name,
            scenario.interceptor_vehicle_name,
        ),
    )
    scan_rows: list[dict[str, Any]] = []
    detection_rows: list[dict[str, Any]] = []
    offline_rows: list[dict[str, Any]] = []
    association_rows: list[dict[str, Any]] = []
    accuracy_rows: list[dict[str, Any]] = []
    actor_trajectory_rows: list[dict[str, Any]] = []
    global_track_rows: list[dict[str, Any]] = []
    cue_records: dict[str, dict[str, Any]] = {}
    latency_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    mot_score_rows: list[dict[str, Any]] = []
    temporal_binding_event_rows: list[dict[str, Any]] = []
    dropout_event_rows: list[dict[str, Any]] = []
    evidence_first_bindings: dict[str, set[str]] = defaultdict(set)
    evidence_multi_target_counts: dict[str, int] = defaultdict(int)
    discovery_times: dict[str, list[float]] = defaultdict(list)
    center_confirmed: set[str] = set()
    center_discovered: set[str] = set()
    gimbal_successes = 0
    gimbal_attempts = 0
    actor_motion_successes = 0
    actor_motion_attempts = 0
    rpc_latencies: list[float] = []
    previous_instantaneous_binding: dict[tuple[str, str], str] = {}
    instantaneous_geometric_binding_switch_count = 0
    geometric_binding_switch_count = 0
    duplicate_assignment_count = 0
    unmatched_detection_count = 0
    simulation_advance_attempts = 0
    simulation_advance_successes = 0
    snapshot_frames = set(
        snapshot_frame_indices(
            duration_s=scenario.duration_s,
            logic_rate_hz=scenario.logic_rate_hz,
            interval_s=scenario.snapshot_interval_s,
        )
    )
    crossing_windows = _long_range_crossing_windows(target_specs, scenario)
    runtime.setup_episode(smoke_config)
    setup_metadata = runtime.episode_setup_metadata()
    actor_name_by_object = {
        str(item.get("object_id")): str(item.get("actor_name"))
        for item in setup_metadata.get("actor_targets", [])
    }
    runtime.set_simulation_paused(True)
    wall_started = time.perf_counter()
    try:
        camera_fov_commands = {
            scenario.center_vehicle_name: runtime.set_cv_camera_fov(
                vehicle_name=scenario.center_vehicle_name,
                camera_name=scenario.camera_name,
                horizontal_fov_deg=CENTER_CAMERA_SPEC.horizontal_fov_deg,
            ),
            scenario.interceptor_vehicle_name: runtime.set_cv_camera_fov(
                vehicle_name=scenario.interceptor_vehicle_name,
                camera_name=scenario.camera_name,
                horizontal_fov_deg=INTERCEPTOR_CAMERA_SPEC.horizontal_fov_deg,
            ),
        }
        camera_validation = {
            scenario.center_vehicle_name: _validate_runtime_camera(
                runtime, smoke_config, scenario.center_vehicle_name, CENTER_CAMERA_SPEC
            ),
            scenario.interceptor_vehicle_name: _validate_runtime_camera(
                runtime, smoke_config, scenario.interceptor_vehicle_name, INTERCEPTOR_CAMERA_SPEC
            ),
        }
        for frame_index in range(scenario.sample_count):
            timestamp = frame_index * scenario.dt_s
            tracks, track_positions = _global_tracks(
                target_specs,
                timestamp,
                position_sigma_m=scenario.global_track_position_sigma_m,
            )
            for track in tracks:
                covariance = np.asarray(track.covariance, dtype=float)
                global_track_rows.append(
                    {
                        "frame_index": frame_index,
                        "measurement_timestamp": timestamp,
                        "arrival_timestamp": timestamp,
                        "global_track_id": track.global_track_id,
                        "px_ned_m": float(track.position[0]),
                        "py_ned_m": float(track.position[1]),
                        "pz_ned_m": float(track.position[2]),
                        "vx_ned_mps": float(track.velocity[0]),
                        "vy_ned_mps": float(track.velocity[1]),
                        "vz_ned_mps": float(track.velocity[2]),
                        "covariance_xx": float(covariance[0, 0]),
                        "covariance_yy": float(covariance[1, 1]),
                        "covariance_zz": float(covariance[2, 2]),
                        "source": "synthetic_d1_d2_global_track_fixture",
                    }
                )
            for spec in target_specs:
                actor_motion_attempts += 1
                position = spec.position_at(timestamp)
                yaw_deg = math.degrees(math.atan2(spec.velocity_ned[1], spec.velocity_ned[0]))
                actor_name = actor_name_by_object.get(spec.object_id, spec.actor_name)
                actor_trajectory_rows.append(
                    {
                        "frame_index": frame_index,
                        "simulation_timestamp": timestamp,
                        "object_id": spec.object_id,
                        "actor_name": actor_name,
                        "px_ned_m": position[0],
                        "py_ned_m": position[1],
                        "pz_ned_m": position[2],
                        "vx_ned_mps": spec.velocity_ned[0],
                        "vy_ned_mps": spec.velocity_ned[1],
                        "vz_ned_mps": spec.velocity_ned[2],
                        "offline_truth_only": True,
                    }
                )
                if runtime.set_actor_target_pose(
                    actor_name=actor_name,
                    position_ned=position,
                    yaw_deg=yaw_deg,
                ):
                    actor_motion_successes += 1
            interceptor_position = _interceptor_position(target_specs, timestamp, scenario)
            interceptor_move = runtime.set_cv_vehicle_position(
                smoke_config,
                vehicle_name=scenario.interceptor_vehicle_name,
                position_ned=interceptor_position,
            )
            desired_center_angles = {
                track_id: _look_angles_deg(scenario.center_position_ned, position)
                for track_id, position in track_positions.items()
            }
            desired_interceptor_angles = {
                track_id: _look_angles_deg(interceptor_position, position)
                for track_id, position in track_positions.items()
            }
            center_waypoint_index = center_scheduler.raster_index
            center_yaw, center_pitch, center_state, center_target = center_scheduler.command()
            center_command = runtime.set_cv_camera_gimbal_pose(
                vehicle_name=scenario.center_vehicle_name,
                camera_name=scenario.camera_name,
                yaw_deg=center_yaw,
                pitch_deg=center_pitch,
            )
            interceptor_yaw, interceptor_pitch, interceptor_state, interceptor_target = (
                interceptor_scheduler.command(desired_interceptor_angles)
            )
            if interceptor_scheduler.last_started_target_id is not None:
                started_id = interceptor_scheduler.last_started_target_id
                cue_records.setdefault(started_id, {"global_track_id": started_id})[
                    "execution_started_timestamp"
                ] = timestamp
                cue_records[started_id]["status"] = "executing"
            interceptor_command = runtime.set_cv_camera_gimbal_pose(
                vehicle_name=scenario.interceptor_vehicle_name,
                camera_name=scenario.camera_name,
                yaw_deg=interceptor_yaw,
                pitch_deg=interceptor_pitch,
            )
            gimbal_attempts += 2
            gimbal_successes += int(center_command["ok"]) + int(interceptor_command["ok"])
            simulation_advanced = False
            if frame_index < scenario.frame_count:
                simulation_advance_attempts += 1
                simulation_advanced = runtime.continue_simulation_for_time(scenario.dt_s)
                simulation_advance_successes += int(simulation_advanced)

            frame_associations: dict[str, list[str]] = {}
            frame_selected_pairs: dict[str, list[Any]] = {}
            frame_detection_counts: dict[str, int] = {}
            frame_detection_count = 0
            for vehicle_name in (
                scenario.center_vehicle_name,
                scenario.interceptor_vehicle_name,
            ):
                detections, offline, detection_meta = runtime.capture_anonymous_cv_detections(
                    smoke_config,
                    frame_index=frame_index,
                    measurement_timestamp=timestamp,
                    vehicle_name=vehicle_name,
                )
                camera_info = runtime.cv_camera_info(
                    smoke_config,
                    timestamp=timestamp,
                    vehicle_name=vehicle_name,
                )
                detections = anonymous_trackers[vehicle_name].update(
                    detections,
                    timestamp=timestamp,
                    frame_index=frame_index,
                    camera_info=camera_info,
                )
                rpc_latencies.append(float(detection_meta["rpc_latency_s"]))
                latency_rows.append(
                    {
                        "frame_index": frame_index,
                        "measurement_timestamp": timestamp,
                        "arrival_timestamp": detection_meta["arrival_timestamp"],
                        "camera_vehicle_name": vehicle_name,
                        "rpc_latency_s": detection_meta["rpc_latency_s"],
                        "detection_count": len(detections),
                        "ok": detection_meta["ok"],
                    }
                )
                frame_detection_count += len(detections)
                frame = AirSimFrame(
                    episode_id=smoke_config.episode_id,
                    scenario_name=smoke_config.scenario_name,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    truth_objects=(),
                    resources=(),
                    cameras=(camera_info,),
                    visual_detections=detections,
                    metadata={"arrival_timestamp": detection_meta["arrival_timestamp"]},
                )
                local_tracks = geometric_local_visual_tracks_from_blocks_frame(frame)
                association_tracks = tracks
                if vehicle_name == scenario.interceptor_vehicle_name:
                    cued_ids = interceptor_scheduler.queued_ids
                    association_tracks = [
                        track for track in tracks if track.global_track_id in cued_ids
                    ]
                camera = camera_model_from_airsim_camera_info(
                    camera_info,
                    measurement_sigma_px=scenario.measurement_sigma_px,
                )
                temporal_result = temporal_associators[vehicle_name].associate(
                    association_tracks,
                    local_tracks,
                    camera,
                    resource_id=vehicle_name,
                    camera_id=str(camera_info.camera_id),
                    stream_id=f"{smoke_config.episode_id}:{vehicle_name}:{scenario.camera_name}",
                    measurement_timestamp=timestamp,
                    arrival_timestamp=float(detection_meta["arrival_timestamp"]),
                    frame_id=f"{mode}:{frame_index:04d}:{vehicle_name}",
                )
                association = temporal_result.instantaneous_result
                selected_ids = list(temporal_result.measured_assignments)
                frame_associations[vehicle_name] = selected_ids
                selected_local_ids = set(temporal_result.measured_assignments.values())
                unmatched_detection_count += max(0, len(local_tracks) - len(selected_local_ids))
                if len(selected_local_ids) != len(temporal_result.measured_assignments):
                    duplicate_assignment_count += (
                        len(temporal_result.measured_assignments) - len(selected_local_ids)
                    )
                for event in temporal_result.binding_events:
                    event_row = event.to_log_record()
                    event_row.update(
                        {
                            "frame_index": frame_index,
                            "mode": mode,
                            "camera_vehicle_name": vehicle_name,
                        }
                    )
                    temporal_binding_event_rows.append(event_row)
                    if (
                        event.event == "confirmed"
                        and event.incumbent_global_track_id is not None
                        and event.candidate_global_track_id is not None
                        and event.incumbent_global_track_id
                        != event.candidate_global_track_id
                    ):
                        geometric_binding_switch_count += 1
                for record in temporal_result.coasted_records:
                    dropout_row = record.to_log_record()
                    dropout_row.update(
                        {
                            "frame_index": frame_index,
                            "mode": mode,
                            "camera_vehicle_name": vehicle_name,
                        }
                    )
                    dropout_event_rows.append(dropout_row)
                offline_by_detection = {str(item["detection_id"]): item for item in offline}
                offline_by_local = {
                    str(detection.local_track_id): _global_id_from_object_id(
                        str(offline_by_detection[str(detection.detection_id)]["object_id"])
                    )
                    for detection in detections
                    if str(detection.detection_id) in offline_by_detection
                    and offline_by_detection[str(detection.detection_id)].get("object_id")
                }
                for detection in detections:
                    covariance = np.eye(2, dtype=float) * scenario.measurement_sigma_px**2
                    detection_rows.append(
                        {
                            "frame_index": frame_index,
                            "camera_id": detection.camera_id,
                            "detection_id": detection.detection_id,
                            "local_track_id": detection.local_track_id,
                            "measurement_timestamp": detection.metadata["measurement_timestamp"],
                            "arrival_timestamp": detection.metadata["arrival_timestamp"],
                            "bbox_x1": detection.bbox_xyxy[0],
                            "bbox_y1": detection.bbox_xyxy[1],
                            "bbox_x2": detection.bbox_xyxy[2],
                            "bbox_y2": detection.bbox_xyxy[3],
                            "center_u": detection.center_px[0],
                            "center_v": detection.center_px[1],
                            "covariance_uu": covariance[0, 0],
                            "covariance_uv": covariance[0, 1],
                            "covariance_vv": covariance[1, 1],
                            "rpc_latency_s": detection.metadata["rpc_latency_s"],
                            "mot_backend": detection.metadata.get("mot_backend", ""),
                            "camera_motion_compensated": detection.metadata.get(
                                "camera_motion_compensated", False
                            ),
                            "world_ray_ned": detection.metadata.get("world_ray_ned", ()),
                            "bearing_rate_px_s": detection.metadata.get(
                                "bearing_rate_px_s", (0.0, 0.0)
                            ),
                            "mot_history_length": detection.metadata.get("mot_history_length", 0),
                            "online_truth_identity_used": False,
                        }
                    )
                    truth = offline_by_detection.get(str(detection.detection_id), {})
                    truth_global_id = (
                        _global_id_from_object_id(str(truth.get("object_id", "")))
                        if truth.get("object_id")
                        else ""
                    )
                    offline_rows.append(
                        {
                            **truth,
                            "frame_index": frame_index,
                            "camera_vehicle_name": vehicle_name,
                            "anonymous_local_track_id": detection.local_track_id,
                            "global_track_id": truth_global_id,
                        }
                    )
                    mot_score_rows.append(
                        {
                            "frame_index": frame_index,
                            "measurement_timestamp": timestamp,
                            "camera_vehicle_name": vehicle_name,
                            "local_track_id": detection.local_track_id,
                            "truth_global_track_id": truth_global_id,
                            "offline_truth_only": True,
                        }
                    )
                instantaneous_selected_pairs = [
                    pair for pair in association.pairs if pair.assignment_selected
                ]
                for pair in instantaneous_selected_pairs:
                    binding_key = (vehicle_name, pair.local_track_id)
                    previous = previous_instantaneous_binding.get(binding_key)
                    if previous is not None and previous != pair.track_id:
                        instantaneous_geometric_binding_switch_count += 1
                    previous_instantaneous_binding[binding_key] = pair.track_id
                selected_pairs = accepted_measured_pairs(temporal_result)
                frame_selected_pairs[vehicle_name] = selected_pairs
                frame_detection_counts[vehicle_name] = len(detections)
                for pair in selected_pairs:
                    truth_global_id = offline_by_local.get(pair.local_track_id)
                    is_correct = None if truth_global_id is None else truth_global_id == pair.track_id
                    accuracy_rows.append(
                        {
                            "camera_vehicle_name": vehicle_name,
                            "frame_index": frame_index,
                            "global_track_id": pair.track_id,
                            "local_track_id": pair.local_track_id,
                            "truth_global_track_id": truth_global_id,
                            "correct": is_correct,
                        }
                    )
                    association_rows.append(
                        {
                            "frame_index": frame_index,
                            "camera_id": f"{vehicle_name}:{scenario.camera_name}",
                            "measurement_timestamp": timestamp,
                            "arrival_timestamp": detection_meta["arrival_timestamp"],
                            "global_track_id": pair.track_id,
                            "local_track_id": pair.local_track_id,
                            "projected_u": None if pair.projected_px is None else pair.projected_px[0],
                            "projected_v": None if pair.projected_px is None else pair.projected_px[1],
                            "bbox_center_u": pair.bbox_center_px[0],
                            "bbox_center_v": pair.bbox_center_px[1],
                            "pixel_error": pair.pixel_error,
                            "mahalanobis_d2": pair.mahalanobis_d2,
                            "gate_pass": pair.gate_pass,
                            "assignment_selected": pair.assignment_selected,
                            "association_source": "temporal_geometric_detect",
                            "measured_evidence": True,
                            "terminal_authorization_allowed": False,
                            "truth_identity_used": False,
                            "track_covariance_xx": scenario.global_track_position_sigma_m**2,
                            "track_covariance_yy": scenario.global_track_position_sigma_m**2,
                            "track_covariance_zz": scenario.global_track_position_sigma_m**2,
                        }
                    )
                if vehicle_name == scenario.center_vehicle_name:
                    for target_id in selected_ids:
                        center_discovered.add(target_id)
                        discovery_times[target_id].append(timestamp)

            center_selected = frame_associations.get(scenario.center_vehicle_name, [])
            center_confirmation_candidates = [
                target_id for target_id in center_selected if target_id not in center_confirmed
            ]
            preferred_center = _preferred_center_target(
                center_confirmation_candidates,
                desired_center_angles,
                current_yaw_deg=center_yaw,
            )
            center_confirmations = center_scheduler.observe(
                center_confirmation_candidates,
                frame_index=frame_index,
                preferred_target_id=preferred_center,
                preferred_angles_deg=None,
            )
            center_confirmed.update(center_confirmations)
            interceptor_scheduler.add_cues(center_confirmations)
            for target_id in center_confirmations:
                desired = desired_interceptor_angles.get(target_id)
                cue_records[target_id] = {
                    "global_track_id": target_id,
                    "issued_frame_index": frame_index,
                    "issued_timestamp": timestamp,
                    "planned_yaw_deg": None if desired is None else desired[0],
                    "planned_pitch_deg": None if desired is None else desired[1],
                    "execution_started_timestamp": None,
                    "completed_timestamp": None,
                    "status": "queued",
                    "failure_reason": "",
                }
            interceptor_selected = frame_associations.get(scenario.interceptor_vehicle_name, [])
            interceptor_completions = interceptor_scheduler.observe(interceptor_selected)
            for target_id in interceptor_completions:
                record = cue_records.setdefault(target_id, {"global_track_id": target_id})
                record["completed_timestamp"] = timestamp
                record["status"] = "completed"
                record["failure_reason"] = ""
            if interceptor_scheduler.last_failed_target is not None:
                target_id, failure_reason = interceptor_scheduler.last_failed_target
                record = cue_records.setdefault(target_id, {"global_track_id": target_id})
                record["status"] = "failed"
                record["failure_reason"] = failure_reason
                record["failed_timestamp"] = timestamp

            for vehicle_name in (
                scenario.center_vehicle_name,
                scenario.interceptor_vehicle_name,
            ):
                pairs = frame_selected_pairs.get(vehicle_name, [])
                selected_track_ids = [str(pair.track_id) for pair in pairs]
                new_binding_ids = sorted(
                    set(selected_track_ids) - evidence_first_bindings[vehicle_name]
                )
                reasons: list[str] = []
                if frame_index in snapshot_frames:
                    reasons.append("periodic")
                if scenario.capture_registration_events and new_binding_ids:
                    reasons.append("first_binding:" + ",".join(new_binding_ids))
                if (
                    scenario.capture_registration_events
                    and vehicle_name == scenario.center_vehicle_name
                    and center_confirmations
                ):
                    reasons.append("center_confirmed:" + ",".join(sorted(center_confirmations)))
                if (
                    scenario.capture_registration_events
                    and vehicle_name == scenario.interceptor_vehicle_name
                    and interceptor_completions
                ):
                    reasons.append(
                        "interceptor_completed:" + ",".join(sorted(interceptor_completions))
                    )
                if (
                    scenario.capture_registration_events
                    and len(pairs) >= 2
                    and evidence_multi_target_counts[vehicle_name]
                    < scenario.max_multi_target_event_snapshots_per_camera
                ):
                    reasons.append("multi_target")
                if reasons:
                    snapshot = runtime.capture_cv_scene_snapshot(
                        smoke_config,
                        frame_index=frame_index,
                        output_dir=output_dir / "snapshots",
                        vehicle_name=vehicle_name,
                    )
                    snapshot_rows.append(
                        {
                            "frame_index": frame_index,
                            "logical_timestamp": timestamp,
                            "camera_vehicle_name": vehicle_name,
                            "requested_interval_s": scenario.snapshot_interval_s,
                            "capture_reasons": "|".join(reasons),
                            "detection_count": frame_detection_counts.get(vehicle_name, 0),
                            "association_count": len(pairs),
                            "associated_global_track_ids": selected_track_ids,
                            **snapshot,
                        }
                    )
                    if snapshot.get("saved"):
                        evidence_first_bindings[vehicle_name].update(new_binding_ids)
                        if "multi_target" in reasons:
                            evidence_multi_target_counts[vehicle_name] += 1
            scan_rows.append(
                {
                    "frame_index": frame_index,
                    "measurement_timestamp": timestamp,
                    "center_state": center_state,
                    "center_target_id": center_target or "",
                    "center_yaw_deg": center_yaw,
                    "center_pitch_deg": center_pitch,
                    "center_raster_waypoint_index": center_waypoint_index,
                    "center_raster_waypoint_count": len(center_scheduler.raster_waypoints),
                    "center_gimbal_ok": center_command["ok"],
                    "center_unique_discovery_count": len(center_discovered),
                    "center_confirmed_count": len(center_confirmed),
                    "interceptor_state": interceptor_state,
                    "interceptor_target_id": interceptor_target or "",
                    "interceptor_yaw_deg": interceptor_yaw,
                    "interceptor_pitch_deg": interceptor_pitch,
                    "interceptor_gimbal_ok": interceptor_command["ok"],
                    "interceptor_position_x": interceptor_position[0],
                    "interceptor_position_y": interceptor_position[1],
                    "interceptor_position_z": interceptor_position[2],
                    "interceptor_cued_count": len(interceptor_scheduler.queued_ids),
                    "interceptor_observed_count": len(interceptor_scheduler.observed_ids),
                    "interceptor_confirmed_count": len(interceptor_scheduler.confirmed_ids),
                    "new_center_confirmation_count": len(center_confirmations),
                    "new_interceptor_completion_count": len(interceptor_completions),
                    "detection_count": frame_detection_count,
                    "vehicle_pose_update_ok": interceptor_move["ok"],
                    "simulation_advanced": simulation_advanced,
                }
            )
    finally:
        wall_elapsed_s = max(0.0, time.perf_counter() - wall_started)
        runtime.set_simulation_paused(False)
        runtime.teardown_episode(smoke_config)

    for record in cue_records.values():
        if record.get("status") in {"completed", "failed"}:
            continue
        if record.get("execution_started_timestamp") is None:
            record["status"] = "not_started"
            record["failure_reason"] = "observation_window_ended_before_execution"
        else:
            record["status"] = "incomplete"
            record["failure_reason"] = "observation_window_ended_before_confirmation"
    cue_plan_rows = sorted(
        cue_records.values(),
        key=lambda row: (float(row.get("issued_timestamp", math.inf)), str(row["global_track_id"])),
    )
    mot_continuity = evaluate_mot_continuity(
        mot_score_rows,
        crossing_windows=crossing_windows,
    )
    aggregate_mot = mot_continuity["aggregate"]
    temporal_expiry_by_camera = _count_values(
        str(row.get("camera_vehicle_name", ""))
        for row in temporal_binding_event_rows
        if row.get("binding_event") == "expired"
        and row.get("binding_reason")
        in {"coast_window_expired", "prediction_age_exceeded_coast_window"}
    )
    aggregate_mot["effective_short_gap_fragmentation_count"] = sum(
        temporal_expiry_by_camera.values()
    )
    for camera_name, camera_metrics in mot_continuity.get("by_camera", {}).items():
        camera_metrics["effective_short_gap_fragmentation_count"] = int(
            temporal_expiry_by_camera.get(str(camera_name), 0)
        )
    id_switch_count = int(aggregate_mot["id_switch_count"])
    evaluable = [row for row in accuracy_rows if row["correct"] is not None]
    correct = sum(bool(row["correct"]) for row in evaluable)
    target_count = len(target_specs)
    center_ratio = len(center_discovered) / target_count
    center_confirm_ratio = len(center_confirmed) / target_count
    cued_count = len(interceptor_scheduler.queued_ids)
    interceptor_observed_ratio = (
        len(interceptor_scheduler.observed_ids) / cued_count if cued_count else 0.0
    )
    cue_completed_count = sum(row.get("status") == "completed" for row in cue_plan_rows)
    cue_completion_ratio = cue_completed_count / cued_count if cued_count else 0.0
    association_accuracy = correct / len(evaluable) if evaluable else None
    camera_configuration_passed = bool(
        all(command["ok"] for command in camera_fov_commands.values())
        and all(validation["ok"] for validation in camera_validation.values())
    )
    setup_actors = setup_metadata.get("actor_targets", [])
    snapshot_saved_count = sum(bool(row.get("saved")) for row in snapshot_rows)
    snapshot_expected_count = len(snapshot_rows)
    periodic_snapshot_expected_count = len(snapshot_frames) * 2
    periodic_snapshot_saved_count = sum(
        bool(row.get("saved")) and "periodic" in str(row.get("capture_reasons", ""))
        for row in snapshot_rows
    )
    event_snapshot_count = sum(
        str(row.get("capture_reasons", "")) != "periodic" for row in snapshot_rows
    )
    event_snapshot_saved_count = sum(
        bool(row.get("saved")) and str(row.get("capture_reasons", "")) != "periodic"
        for row in snapshot_rows
    )
    actual_simulated_duration_s = simulation_advance_successes * scenario.dt_s
    execution_record_gate_passed = bool(
        camera_configuration_passed
        and len(setup_actors) == target_count
        and all(bool(item.get("spawned")) for item in setup_actors)
        and actor_motion_attempts > 0
        and actor_motion_successes == actor_motion_attempts
        and gimbal_attempts > 0
        and gimbal_successes == gimbal_attempts
        and simulation_advance_attempts == scenario.frame_count
        and simulation_advance_successes == simulation_advance_attempts
        and math.isclose(
            actual_simulated_duration_s,
            scenario.duration_s,
            rel_tol=0.0,
            abs_tol=scenario.dt_s * 0.5,
        )
        and snapshot_saved_count == snapshot_expected_count
        and periodic_snapshot_saved_count == periodic_snapshot_expected_count
        and all(bool(row.get("ok")) for row in latency_rows)
    )
    coverage_gate_passed = bool(
        mode != "coverage_safe"
        or (
            execution_record_gate_passed
            and len(center_discovered) >= math.ceil(0.9 * target_count)
            and interceptor_observed_ratio >= 0.90
            and cue_completion_ratio >= 0.90
            and association_accuracy is not None
            and association_accuracy >= 0.95
            and bool(aggregate_mot["gate_passed"])
        )
    )
    revisit_intervals = [
        later - earlier
        for values in discovery_times.values()
        for earlier, later in zip(values, values[1:])
    ]
    scan_plan_payload = {
        "schema_version": "d5-long-range-2d-scan-plan-v1",
        "mode": mode,
        "geometry_profile": scenario.geometry_profile,
        "crossing_geometry_preflight": crossing_geometry_preflight(
            target_specs, scenario
        ),
        "source": pitch_plan.source,
        "online_truth_identity_used": False,
        "pitch_search": asdict(pitch_plan),
        "search_sector_yaw_deg": [
            scenario.search_sector_min_deg,
            scenario.search_sector_max_deg,
        ],
        "horizontal_fov_deg": CENTER_CAMERA_SPEC.horizontal_fov_deg,
        "vertical_fov_deg": CENTER_CAMERA_SPEC.vertical_fov_deg,
        "overlap_ratio": raster_overlap,
        "waypoint_count": len(raster_waypoints),
        "waypoints": [
            {"index": index, "yaw_deg": yaw, "pitch_deg": pitch}
            for index, (yaw, pitch) in enumerate(raster_waypoints)
        ],
    }
    metrics = {
        "schema_version": "d5-long-range-cv-scan-metrics-v3",
        "mode": mode,
        "seed": scenario.seed,
        "geometry_profile": scenario.geometry_profile,
        "crossing_geometry_preflight": crossing_geometry_preflight(
            target_specs, scenario
        ),
        "diagnostic_target_scale": scenario.target_scale,
        "diagnostic_result": not math.isclose(scenario.target_scale, 1.0),
        "target_count": target_count,
        "actor_spawn_count": sum(bool(item.get("spawned")) for item in setup_actors),
        "actor_setup_count": len(setup_actors),
        "actor_motion_attempt_count": actor_motion_attempts,
        "actor_motion_success_count": actor_motion_successes,
        "actor_motion_success_rate": actor_motion_successes / actor_motion_attempts if actor_motion_attempts else None,
        "camera_fov_commands": camera_fov_commands,
        "camera_validation": camera_validation,
        "camera_configuration_passed": camera_configuration_passed,
        "gimbal_update_attempt_count": gimbal_attempts,
        "gimbal_update_success_count": gimbal_successes,
        "gimbal_update_success_rate": gimbal_successes / gimbal_attempts if gimbal_attempts else None,
        "center_unique_discovery_count": len(center_discovered),
        "center_unique_discovery_ratio": center_ratio,
        "center_confirmed_count": len(center_confirmed),
        "center_confirmed_ratio": center_confirm_ratio,
        "center_first_full_sweep_duration_s": None
        if center_scheduler.first_sweep_completed_frame is None
        else center_scheduler.first_sweep_completed_frame * scenario.dt_s,
        "center_completed_sweep_count": center_scheduler.completed_sweep_count,
        "center_endpoint_reversal_count": center_scheduler.endpoint_reversal_count,
        "center_dwell_duration_s": center_scheduler.total_dwell_frames * scenario.dt_s,
        "center_pitch_search_min_deg": pitch_plan.min_pitch_deg,
        "center_pitch_search_max_deg": pitch_plan.max_pitch_deg,
        "center_pitch_row_count": len(raster_pitch_rows),
        "center_raster_waypoint_count": len(raster_waypoints),
        "center_scan_plan_source": pitch_plan.source,
        "mean_revisit_interval_s": _mean(revisit_intervals),
        "p95_revisit_interval_s": _percentile(revisit_intervals, 95.0),
        "interceptor_cued_count": cued_count,
        "interceptor_observed_count": len(interceptor_scheduler.observed_ids),
        "interceptor_observed_ratio": interceptor_observed_ratio,
        "interceptor_confirmed_count": len(interceptor_scheduler.confirmed_ids),
        "interceptor_cue_execution_started_count": sum(
            row.get("execution_started_timestamp") is not None for row in cue_plan_rows
        ),
        "interceptor_cue_completed_count": cue_completed_count,
        "interceptor_cue_completion_ratio": cue_completion_ratio,
        "interceptor_cue_failure_reasons": _count_values(
            str(row.get("failure_reason", ""))
            for row in cue_plan_rows
            if row.get("failure_reason")
        ),
        "association_evaluable_count": len(evaluable),
        "association_accuracy": association_accuracy,
        "id_switch_count": id_switch_count,
        "geometric_binding_switch_count": geometric_binding_switch_count,
        "instantaneous_geometric_binding_switch_count": (
            instantaneous_geometric_binding_switch_count
        ),
        "temporal_association": {
            "coast_time_s": scenario.temporal_association_coast_s,
            "challenger_required_frames": scenario.temporal_challenger_required_frames,
            "binding_event_count": len(temporal_binding_event_rows),
            "binding_event_counts": _count_values(
                str(row.get("binding_event", ""))
                for row in temporal_binding_event_rows
                if row.get("binding_event")
            ),
            "coasted_record_count": len(dropout_event_rows),
            "coasted_binding_count": len(
                {
                    (
                        str(row.get("camera_vehicle_name", "")),
                        str(row.get("local_track_id", "")),
                        str(row.get("global_track_id", "")),
                    )
                    for row in dropout_event_rows
                }
            ),
            "recovery_count": sum(
                row.get("binding_event") == "recovered"
                for row in temporal_binding_event_rows
            ),
            "expiry_count": sum(
                row.get("binding_event") == "expired"
                and row.get("binding_reason")
                in {"coast_window_expired", "prediction_age_exceeded_coast_window"}
                for row in temporal_binding_event_rows
            ),
            "confirmed_switch_count": geometric_binding_switch_count,
            "raw_short_gap_fragmentation_count": int(
                aggregate_mot.get("fragmentation_count", 0)
            ),
            "effective_fragmentation_count": sum(
                row.get("binding_event") == "expired"
                and row.get("binding_reason")
                in {"coast_window_expired", "prediction_age_exceeded_coast_window"}
                for row in temporal_binding_event_rows
            ),
            "predicted_record_authorization_count": sum(
                bool(row.get("terminal_authorization_allowed"))
                for row in dropout_event_rows
            ),
            "episode_scoped_state": True,
        },
        "mot_continuity": mot_continuity,
        "duplicate_assignment_count": duplicate_assignment_count,
        "unmatched_detection_count": unmatched_detection_count,
        "detection_rpc_latency_mean_ms": None if not rpc_latencies else statistics.fmean(rpc_latencies) * 1000.0,
        "detection_rpc_latency_p95_ms": None if not rpc_latencies else _percentile(rpc_latencies, 95.0) * 1000.0,
        "wall_elapsed_s": wall_elapsed_s,
        "requested_duration_s": scenario.duration_s,
        "actual_simulated_duration_s": actual_simulated_duration_s,
        "logical_duration_s": actual_simulated_duration_s,
        "sample_count": scenario.sample_count,
        "simulation_advance_attempt_count": simulation_advance_attempts,
        "simulation_advance_success_count": simulation_advance_successes,
        "wall_time_realtime_factor": actual_simulated_duration_s / wall_elapsed_s if wall_elapsed_s > 0.0 else None,
        "snapshot_interval_s": scenario.snapshot_interval_s,
        "snapshot_expected_count": snapshot_expected_count,
        "snapshot_saved_count": snapshot_saved_count,
        "periodic_snapshot_expected_count": periodic_snapshot_expected_count,
        "periodic_snapshot_saved_count": periodic_snapshot_saved_count,
        "event_snapshot_count": event_snapshot_count,
        "event_snapshot_saved_count": event_snapshot_saved_count,
        "snapshot_capture_passed": (
            snapshot_saved_count == snapshot_expected_count
            and periodic_snapshot_saved_count == periodic_snapshot_expected_count
        ),
        "execution_record_gate_required": True,
        "execution_record_gate_passed": execution_record_gate_passed,
        "video_generated": False,
        "online_truth_identity_use_count": 0,
        "global_track_id_rewrite_count": 0,
        "global_track_source": "synthetic_d1_d2_fixture",
        "coverage_gate_required": mode == "coverage_safe",
        "coverage_gate_passed": coverage_gate_passed,
        "coverage_gate_thresholds": {
            "center_min_count": math.ceil(0.9 * target_count),
            "interceptor_min_observed_ratio": 0.90,
            "interceptor_min_cue_completion_ratio": 0.90,
            "association_min_accuracy": 0.95,
            "mot_continuity_gate_passed": True,
            "camera_configuration_passed": True,
        },
    }
    visual_evidence_paths, visual_evidence_metrics = (
        write_long_range_registration_visual_evidence(
            output_dir,
            snapshot_rows=snapshot_rows,
            detection_rows=detection_rows,
            association_rows=association_rows,
            accuracy_rows=accuracy_rows,
            metrics=metrics,
            center_vehicle_name=scenario.center_vehicle_name,
            interceptor_vehicle_name=scenario.interceptor_vehicle_name,
        )
    )
    metrics["visual_evidence"] = visual_evidence_metrics
    output_paths = _write_episode_outputs(
        output_dir,
        scenario=scenario,
        mode_definition=definition,
        metrics=metrics,
        scan_rows=scan_rows,
        detection_rows=detection_rows,
        association_rows=association_rows,
        temporal_binding_event_rows=temporal_binding_event_rows,
        dropout_event_rows=dropout_event_rows,
        offline_rows=offline_rows,
        actor_trajectory_rows=actor_trajectory_rows,
        global_track_rows=global_track_rows,
        cue_plan_rows=cue_plan_rows,
        latency_rows=latency_rows,
        snapshot_rows=snapshot_rows,
        mot_score_rows=mot_score_rows,
        crossing_windows=crossing_windows,
        scan_plan_payload=scan_plan_payload,
        visual_evidence_paths=visual_evidence_paths,
    )
    return LongRangeEpisodeResult(mode=mode, output_dir=output_dir, metrics=metrics, output_paths=output_paths)


def _validate_runtime_camera(
    runtime: RealAirSimRuntimeClient,
    config: BlocksSmokeConfig,
    vehicle_name: str,
    expected: OpticalCameraSpec,
) -> dict[str, Any]:
    try:
        raw_info = runtime.client.simGetCameraInfo(config.camera_name, vehicle_name=vehicle_name)
        actual_fov = float(getattr(raw_info, "fov", expected.horizontal_fov_deg))
        request = runtime.airsim.ImageRequest(
            config.camera_name,
            runtime.airsim.ImageType.Scene,
            False,
            True,
        )
        responses = runtime.client.simGetImages([request], vehicle_name=vehicle_name)
        width = int(responses[0].width) if responses else 0
        height = int(responses[0].height) if responses else 0
        camera_info = runtime.cv_camera_info(config, timestamp=0.0, vehicle_name=vehicle_name)
        ok = bool(
            width == expected.width
            and height == expected.height
            and math.isclose(actual_fov, expected.horizontal_fov_deg, rel_tol=0.0, abs_tol=1e-3)
        )
        return {
            "ok": ok,
            "vehicle_name": vehicle_name,
            "actual_width": width,
            "actual_height": height,
            "actual_horizontal_fov_deg": actual_fov,
            "expected_width": expected.width,
            "expected_height": expected.height,
            "expected_horizontal_fov_deg": expected.horizontal_fov_deg,
            "reported_position_ned": list(camera_info.position_ned),
            "sim_get_camera_info_read": True,
            "image_dimensions_read": bool(responses),
        }
    except Exception as exc:
        return {
            "ok": False,
            "vehicle_name": vehicle_name,
            "reason": f"{type(exc).__name__}: {exc}",
            "sim_get_camera_info_read": False,
            "image_dimensions_read": False,
        }


def _global_tracks(
    specs: Sequence[BlocksActorTargetSpec],
    timestamp: float,
    *,
    position_sigma_m: float = 15.0,
) -> tuple[list[GlobalTrack], dict[str, tuple[float, float, float]]]:
    tracks: list[GlobalTrack] = []
    positions: dict[str, tuple[float, float, float]] = {}
    for spec in specs:
        global_track_id = _global_id_from_object_id(spec.object_id)
        position = spec.position_at(timestamp)
        positions[global_track_id] = position
        tracks.append(
            GlobalTrack(
                global_track_id=global_track_id,
                position=np.asarray(position, dtype=float),
                velocity=np.asarray(spec.velocity_ned, dtype=float),
                covariance=np.eye(3, dtype=float) * float(position_sigma_m) ** 2,
                category="uav",
                timestamp=float(timestamp),
                track_version=1,
            )
        )
    return tracks, positions


def _interceptor_position(
    specs: Sequence[BlocksActorTargetSpec],
    timestamp: float,
    scenario: LongRangeCVScenario,
) -> tuple[float, float, float]:
    centroid = np.mean(np.asarray([spec.position_at(timestamp) for spec in specs], dtype=float), axis=0)
    return (
        float(centroid[0] - scenario.interceptor_standoff_m),
        float(centroid[1]),
        float(centroid[2]),
    )


def _look_angles_deg(
    camera_position_ned: tuple[float, float, float],
    target_position_ned: tuple[float, float, float],
) -> tuple[float, float]:
    delta = np.asarray(target_position_ned, dtype=float) - np.asarray(camera_position_ned, dtype=float)
    yaw = math.degrees(math.atan2(float(delta[1]), float(delta[0])))
    horizontal = math.hypot(float(delta[0]), float(delta[1]))
    pitch = math.degrees(-math.atan2(float(delta[2]), max(horizontal, 1e-9)))
    return yaw, pitch


def _group_pitch_deg(
    camera_position_ned: tuple[float, float, float],
    target_positions: Iterable[tuple[float, float, float]],
) -> float:
    positions = list(target_positions)
    if not positions:
        return 0.0
    centroid = tuple(float(value) for value in np.mean(np.asarray(positions), axis=0))
    return _look_angles_deg(camera_position_ned, centroid)[1]


def _preferred_center_target(
    selected_ids: Sequence[str],
    target_angles: Mapping[str, tuple[float, float]],
    *,
    current_yaw_deg: float,
) -> str | None:
    if not selected_ids:
        return None
    return min(
        (str(value) for value in selected_ids),
        key=lambda target_id: abs(_angle_delta_deg(current_yaw_deg, target_angles[target_id][0])),
    )


def _global_id_from_object_id(object_id: str) -> str:
    suffix = str(object_id).split("-")[-1]
    return f"GT-{int(suffix):04d}" if suffix.isdigit() else f"GT-{suffix}"


def _rate_limit_angle(current: float, desired: float, maximum_step: float) -> float:
    delta = _angle_delta_deg(current, desired)
    return _normalize_angle_deg(current + float(np.clip(delta, -maximum_step, maximum_step)))


def _rate_limit_linear(current: float, desired: float, maximum_step: float) -> float:
    return float(current + np.clip(desired - current, -maximum_step, maximum_step))


def _angle_delta_deg(current: float, desired: float) -> float:
    return (float(desired) - float(current) + 180.0) % 360.0 - 180.0


def _normalize_angle_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def _inclusive_axis_points(
    minimum: float,
    maximum: float,
    maximum_step: float,
) -> tuple[float, ...]:
    minimum = float(minimum)
    maximum = float(maximum)
    maximum_step = float(maximum_step)
    if maximum < minimum:
        raise ValueError("axis maximum must not be less than minimum")
    if maximum_step <= 0.0:
        raise ValueError("axis step must be positive")
    span = maximum - minimum
    if math.isclose(span, 0.0, abs_tol=1e-12):
        return (minimum,)
    interval_count = max(1, int(math.ceil(span / maximum_step)))
    return tuple(float(value) for value in np.linspace(minimum, maximum, interval_count + 1))


def _bbox_max_extent(bbox: Sequence[float]) -> float:
    return max(abs(float(bbox[2]) - float(bbox[0])), abs(float(bbox[3]) - float(bbox[1])))


def _bbox_area(bbox: Sequence[float]) -> float:
    return max(0.0, float(bbox[2]) - float(bbox[0])) * max(
        0.0, float(bbox[3]) - float(bbox[1])
    )


def _count_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[str(value)] += 1
    return dict(sorted(counts.items()))


def _capture_settings(spec: OpticalCameraSpec) -> dict[str, Any]:
    return {
        "ImageType": 0,
        "Width": int(spec.width),
        "Height": int(spec.height),
        "FOV_Degrees": float(spec.horizontal_fov_deg),
        "MotionBlurAmount": 0,
    }


def _cv_vehicle_settings(
    position_ned: tuple[float, float, float],
    capture_settings: dict[str, Any],
) -> dict[str, Any]:
    return {
        "VehicleType": "ComputerVision",
        "AutoCreate": True,
        "AllowAPIAlways": True,
        "X": float(position_ned[0]),
        "Y": float(position_ned[1]),
        "Z": float(position_ned[2]),
        "Pitch": 0,
        "Roll": 0,
        "Yaw": 0,
        "Cameras": {
            CAMERA_NAME: {
                "X": 0,
                "Y": 0,
                "Z": 0,
                "Pitch": 0,
                "Roll": 0,
                "Yaw": 0,
                "CaptureSettings": [dict(capture_settings)],
            }
        },
    }


def _scenario_payload(
    scenario: LongRangeCVScenario,
    target_specs: Sequence[BlocksActorTargetSpec],
    interceptor_initial: tuple[float, float, float],
) -> dict[str, Any]:
    return {
        "schema_version": "d5-long-range-cv-scenario-v1",
        "scenario": asdict(scenario),
        "center_camera": asdict(CENTER_CAMERA_SPEC) | {"vertical_fov_deg": CENTER_CAMERA_SPEC.vertical_fov_deg},
        "interceptor_camera": asdict(INTERCEPTOR_CAMERA_SPEC)
        | {"vertical_fov_deg": INTERCEPTOR_CAMERA_SPEC.vertical_fov_deg},
        "interceptor_initial_position_ned": list(interceptor_initial),
        "target_specs": [asdict(spec) for spec in target_specs],
        "minimum_3d_separation_m": minimum_target_separation(
            target_specs, duration_s=scenario.duration_s
        ),
        "projected_horizontal_crossing_count": projected_trajectory_crossing_count(
            target_specs,
            camera_position_ned=scenario.center_position_ned,
            duration_s=scenario.duration_s,
        ),
        "crossing_geometry_preflight": crossing_geometry_preflight(
            target_specs, scenario
        ),
        "online_truth_identity_use_count": 0,
        "global_track_id_rewrite_count": 0,
    }


def _write_episode_outputs(
    output_dir: Path,
    *,
    scenario: LongRangeCVScenario,
    mode_definition: ScanModeDefinition,
    metrics: dict[str, Any],
    scan_rows: list[dict[str, Any]],
    detection_rows: list[dict[str, Any]],
    association_rows: list[dict[str, Any]],
    temporal_binding_event_rows: list[dict[str, Any]],
    dropout_event_rows: list[dict[str, Any]],
    offline_rows: list[dict[str, Any]],
    actor_trajectory_rows: list[dict[str, Any]],
    global_track_rows: list[dict[str, Any]],
    cue_plan_rows: list[dict[str, Any]],
    latency_rows: list[dict[str, Any]],
    snapshot_rows: list[dict[str, Any]],
    mot_score_rows: list[dict[str, Any]],
    crossing_windows: list[dict[str, Any]],
    scan_plan_payload: dict[str, Any],
    visual_evidence_paths: Mapping[str, Path],
) -> dict[str, Path]:
    paths = {
        "scan_gimbal_csv": _write_csv(output_dir / "scan_gimbal.csv", scan_rows),
        "scan_plan_json": _write_json(output_dir / "scan_plan.json", scan_plan_payload),
        "cue_plan_csv": _write_csv(output_dir / "interceptor_cue_plan.csv", cue_plan_rows),
        "cue_plan_json": _write_json(output_dir / "interceptor_cue_plan.json", cue_plan_rows),
        "actor_trajectory_truth_csv": _write_csv(
            output_dir / "actor_trajectory_truth.csv", actor_trajectory_rows
        ),
        "global_tracks_csv": _write_csv(output_dir / "global_tracks.csv", global_track_rows),
        "detections_csv": _write_csv(output_dir / "detections.csv", detection_rows),
        "detections_jsonl": _write_jsonl(output_dir / "detections.jsonl", detection_rows),
        "associations_csv": _write_csv(
            output_dir / "associations.csv",
            association_rows,
            required_fields=ASSOCIATION_LOG_FIELDS,
        ),
        "temporal_binding_events_csv": _write_csv(
            output_dir / "temporal_binding_events.csv",
            temporal_binding_event_rows,
            required_fields=TEMPORAL_BINDING_EVENT_FIELDS,
        ),
        "dropout_events_csv": _write_csv(
            output_dir / "dropout_events.csv",
            dropout_event_rows,
            required_fields=DROPOUT_EVENT_FIELDS,
        ),
        "offline_truth_csv": _write_csv(output_dir / "offline_truth.csv", offline_rows),
        "mot_offline_score_csv": _write_csv(
            output_dir / "mot_offline_score.csv", mot_score_rows
        ),
        "crossing_windows_csv": _write_csv(
            output_dir / "crossing_windows.csv", crossing_windows
        ),
        "mot_continuity_json": _write_json(
            output_dir / "mot_continuity.json", metrics["mot_continuity"]
        ),
        "latency_rpc_csv": _write_csv(output_dir / "latency_rpc.csv", latency_rows),
        "snapshots_manifest_csv": _write_csv(
            output_dir / "snapshots_manifest.csv", snapshot_rows
        ),
        "snapshot_directory": output_dir / "snapshots",
        "metrics_json": _write_json(output_dir / "metrics.json", metrics),
    }
    paths.update(visual_evidence_paths)
    paths.update(_write_episode_plots(output_dir, scan_rows, metrics["mot_continuity"]))
    d6_result, d6_paths = _write_d6_long_range_evaluation(output_dir)
    paths.update({f"d6_{name}": path for name, path in d6_paths.items()})
    paths["d6_evaluation_index"] = _write_json(
        output_dir / "d6_evaluation_index.json",
        {
            "schema_version": "main-d5-long-range-d6-evaluation-index-v1",
            "status": d6_result["status"],
            "episode_count": d6_result["episode_count"],
            "multi_seed_evidence_available": d6_result[
                "multi_seed_evidence_available"
            ],
            "p1_closed": d6_result["p1_closed"],
            "report_paths": {
                name: str(path.relative_to(output_dir))
                for name, path in sorted(d6_paths.items())
            },
            "control_authority": False,
        },
    )
    paths["report"] = _write_episode_report(
        output_dir / "D5_LONG_RANGE_CV_SCAN_REPORT_CN.md",
        scenario=scenario,
        mode_definition=mode_definition,
        metrics=metrics,
        paths=paths,
    )
    video_files = sorted(
        str(path.relative_to(output_dir))
        for suffix in ("*.mp4", "*.gif", "*.avi", "*.mov", "*.mkv")
        for path in output_dir.rglob(suffix)
    )
    artifact_rows = [
        {
            "name": name,
            "path": str(path.relative_to(output_dir)) if path.is_relative_to(output_dir) else str(path),
            "exists": path.exists(),
            "kind": "directory" if path.is_dir() else "file",
            "required": name != "snapshot_directory" or metrics["snapshot_expected_count"] > 0,
            "missing_reason": "" if path.exists() else "not_generated",
        }
        for name, path in sorted(paths.items())
    ]
    manifest_payload = {
        "schema_version": "d5-long-range-record-manifest-v1",
        "mode": mode_definition.name,
        "requested_duration_s": metrics["requested_duration_s"],
        "actual_simulated_duration_s": metrics["actual_simulated_duration_s"],
        "wall_elapsed_s": metrics["wall_elapsed_s"],
        "artifacts": artifact_rows,
        "missing_required_records": [
            row["name"] for row in artifact_rows if row["required"] and not row["exists"]
        ],
        "video_generated": bool(video_files),
        "video_files": video_files,
        "root_level_records": {
            "settings": "../settings.json",
            "scenario": "../scenario.json",
            "blocks_log": "../blocks_stdout_stderr.log",
            "blocks_diagnostics": "../blocks_diagnostics.json",
        },
    }
    paths["record_manifest"] = _write_json(
        output_dir / "record_manifest.json", manifest_payload
    )
    return paths


def _write_d6_long_range_evaluation(
    episode_dir: Path,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Ask D6 to evaluate persisted episode artifacts without online authority."""

    from d6_evaluation_metrics.d5_long_range_registration import (
        evaluate_d5_long_range_registration,
        load_d5_long_range_registration_episode,
        write_d5_long_range_registration_report,
    )

    episode = load_d5_long_range_registration_episode(episode_dir)
    result = evaluate_d5_long_range_registration(episode)
    paths = write_d5_long_range_registration_report(
        episode_dir / "d6_evaluation",
        result,
        title="D5长距离视觉配准D6离线评估",
    )
    return result, paths


def _write_episode_plots(
    output_dir: Path,
    scan_rows: list[dict[str, Any]],
    mot_continuity: Mapping[str, Any],
) -> dict[str, Path]:
    if not scan_rows:
        return {}
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    times = [float(row["measurement_timestamp"]) for row in scan_rows]
    yaw_path = output_dir / "gimbal_yaw_curve.png"
    figure, axis = plt.subplots(figsize=(10, 4.5))
    axis.plot(times, [row["center_yaw_deg"] for row in scan_rows], label="Center gimbal")
    axis.plot(times, [row["interceptor_yaw_deg"] for row in scan_rows], label="Interceptor gimbal")
    axis.set_xlabel("Logical time (s)")
    axis.set_ylabel("Yaw (deg)")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(yaw_path, dpi=160)
    plt.close(figure)

    pitch_path = output_dir / "gimbal_pitch_curve.png"
    figure, axis = plt.subplots(figsize=(10, 4.5))
    axis.plot(times, [row["center_pitch_deg"] for row in scan_rows], label="Center gimbal")
    axis.plot(times, [row["interceptor_pitch_deg"] for row in scan_rows], label="Interceptor gimbal")
    axis.set_xlabel("Logical time (s)")
    axis.set_ylabel("Pitch (deg)")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(pitch_path, dpi=160)
    plt.close(figure)

    raster_path = output_dir / "center_scan_raster.png"
    figure, axis = plt.subplots(figsize=(8, 6))
    scatter = axis.scatter(
        [row["center_yaw_deg"] for row in scan_rows],
        [row["center_pitch_deg"] for row in scan_rows],
        c=times,
        s=8,
        cmap="viridis",
    )
    axis.set_xlabel("Yaw (deg)")
    axis.set_ylabel("Pitch (deg)")
    axis.grid(alpha=0.25)
    figure.colorbar(scatter, ax=axis, label="Logical time (s)")
    figure.tight_layout()
    figure.savefig(raster_path, dpi=160)
    plt.close(figure)

    discovery_path = output_dir / "cumulative_discovery_curve.png"
    figure, axis = plt.subplots(figsize=(10, 4.5))
    axis.step(times, [row["center_unique_discovery_count"] for row in scan_rows], where="post", label="Center discovered")
    axis.step(times, [row["center_confirmed_count"] for row in scan_rows], where="post", label="Center confirmed")
    axis.step(times, [row["interceptor_observed_count"] for row in scan_rows], where="post", label="Interceptor observed")
    axis.set_xlabel("Logical time (s)")
    axis.set_ylabel("Unique target count")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(discovery_path, dpi=160)
    plt.close(figure)

    continuity_path = output_dir / "mot_continuity_summary.png"
    camera_items = list(mot_continuity.get("by_camera", {}).items())
    figure, axis = plt.subplots(figsize=(8, 4.5))
    labels = [name for name, _item in camera_items]
    purity = [float(item.get("track_purity") or 0.0) for _name, item in camera_items]
    continuity = [float(item.get("track_continuity") or 0.0) for _name, item in camera_items]
    positions = np.arange(len(labels), dtype=float)
    axis.bar(positions - 0.18, purity, width=0.36, label="Track purity")
    axis.bar(positions + 0.18, continuity, width=0.36, label="Track continuity")
    axis.set_xticks(positions, labels, rotation=10)
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("Ratio")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(continuity_path, dpi=160)
    plt.close(figure)
    return {
        "gimbal_yaw_curve": yaw_path,
        "gimbal_pitch_curve": pitch_path,
        "center_scan_raster": raster_path,
        "cumulative_discovery_curve": discovery_path,
        "mot_continuity_summary": continuity_path,
    }


def _write_episode_report(
    path: Path,
    *,
    scenario: LongRangeCVScenario,
    mode_definition: ScanModeDefinition,
    metrics: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> Path:
    gate_text = (
        "通过"
        if metrics["coverage_gate_required"] and metrics["coverage_gate_passed"]
        else "未通过"
        if metrics["coverage_gate_required"]
        else "不适用（诊断模式）"
    )
    center_validation = metrics["camera_validation"][scenario.center_vehicle_name]
    interceptor_validation = metrics["camera_validation"][scenario.interceptor_vehicle_name]
    mot = metrics["mot_continuity"]["aggregate"]
    temporal = metrics["temporal_association"]
    missing_items = []
    if not metrics["snapshot_capture_passed"]:
        missing_items.append(
            "定时截图不完整：保存{}/{}".format(
                metrics["snapshot_saved_count"], metrics["snapshot_expected_count"]
            )
        )
    if metrics["actual_simulated_duration_s"] + 1e-9 < metrics["requested_duration_s"]:
        missing_items.append("AirSim逻辑推进未达到请求时长")
    if not missing_items:
        missing_items.append("episode级必需记录未发现缺失；Blocks日志和诊断位于试验根目录")
    record_names = "、".join(
        sorted(name for name in paths if name != "snapshot_directory")
    )
    lines = [
        "# D5 长距离 ComputerVision 扫描与配准试验",
        "",
        "## 结论",
        "",
        f"本轮采用 `{mode_definition.name}` 扫描模式，覆盖验收结果为**{gate_text}**。该结果属于 AirSim ComputerVision 接口试验，不代表真实光电设备性能。",
        "",
        "## 场景",
        "",
        f"- 目标数量：{scenario.target_count}",
        f"- 目标距离：{scenario.target_range_min_m:.0f}至{scenario.target_range_max_m:.0f}米",
        f"- 目标速度：{scenario.target_speed_min_mps:.1f}至{scenario.target_speed_max_mps:.1f}米/秒",
        f"- 请求观察时长：{metrics['requested_duration_s']:.2f}秒；实际逻辑推进：{metrics['actual_simulated_duration_s']:.2f}秒；墙钟耗时：{metrics['wall_elapsed_s']:.2f}秒",
        f"- 目标网格比例：{scenario.target_scale:.1f}；{'诊断场景，不能替代主场景' if not math.isclose(scenario.target_scale, 1.0) else '主场景'}",
        f"- 中心相机：{CENTER_CAMERA_SPEC.width}×{CENTER_CAMERA_SPEC.height}，水平视场{CENTER_CAMERA_SPEC.horizontal_fov_deg:.3f}度，等效焦距{CENTER_CAMERA_SPEC.equivalent_focal_length_mm:.0f}毫米",
        f"- 拦截相机：{INTERCEPTOR_CAMERA_SPEC.width}×{INTERCEPTOR_CAMERA_SPEC.height}，水平视场{INTERCEPTOR_CAMERA_SPEC.horizontal_fov_deg:.6f}度，等效焦距{INTERCEPTOR_CAMERA_SPEC.equivalent_focal_length_mm:.0f}毫米",
        f"- 二维扫描：偏航{scenario.search_sector_min_deg:.1f}至{scenario.search_sector_max_deg:.1f}度，俯仰{metrics['center_pitch_search_min_deg']:.3f}至{metrics['center_pitch_search_max_deg']:.3f}度，共{metrics['center_pitch_row_count']}行、{metrics['center_raster_waypoint_count']}个栅格点",
        f"- 扫描速度：{mode_definition.speed_deg_s:.2f}度/秒；偏航逻辑步进：{mode_definition.step_deg:.4f}度/帧",
        f"- 检测方式：AirSim simGetDetections；每{scenario.snapshot_interval_s:.1f}秒保存定时截图，并在首次绑定、确认、提示完成和多目标同帧时保存事件截图；不生成视频",
        "",
        "## 结果",
        "",
        f"- actor生成：{metrics['actor_spawn_count']}/{metrics['actor_setup_count']}",
        f"- actor位姿更新成功率：{_format_ratio(metrics['actor_motion_success_rate'])}",
        f"- 运行与记录门控：{'通过' if metrics['execution_record_gate_passed'] else '未通过'}",
        f"- 相机配置回读：{'通过' if metrics['camera_configuration_passed'] else '未通过'}",
        f"- 中心相机实际回读：{center_validation.get('actual_width', 0)}×{center_validation.get('actual_height', 0)}，水平视场{_format_number(center_validation.get('actual_horizontal_fov_deg'))}度",
        f"- 拦截相机实际回读：{interceptor_validation.get('actual_width', 0)}×{interceptor_validation.get('actual_height', 0)}，水平视场{_format_number(interceptor_validation.get('actual_horizontal_fov_deg'))}度",
        f"- 云台更新成功率：{_format_ratio(metrics['gimbal_update_success_rate'])}",
        f"- 中心累计发现：{metrics['center_unique_discovery_count']}/{metrics['target_count']}，比例{_format_ratio(metrics['center_unique_discovery_ratio'])}",
        f"- 中心连续五帧确认：{metrics['center_confirmed_count']}/{metrics['target_count']}，比例{_format_ratio(metrics['center_confirmed_ratio'])}",
        f"- 拦截相机提示后观察比例：{_format_ratio(metrics['interceptor_observed_ratio'])}",
        f"- 二维提示执行：发出{metrics['interceptor_cued_count']}项，开始{metrics['interceptor_cue_execution_started_count']}项，完成{metrics['interceptor_cue_completed_count']}项，完成率{_format_ratio(metrics['interceptor_cue_completion_ratio'])}",
        f"- 可评分关联准确率：{_format_ratio(metrics['association_accuracy'])}",
        f"- 连续可见段：身份切换{mot['id_switch_count']}，短缺口中断{mot['fragmentation_count']}，纯度{_format_ratio(mot['track_purity'])}，连续性{_format_ratio(mot['track_continuity'])}",
        f"- 原始证据：总身份切换{mot['raw_total_id_switch_count']}，总中断{mot['raw_total_fragmentation_count']}，长期重发现{mot['reacquisition_count']}，其中编号变化{mot['reacquisition_identity_changed_count']}",
        f"- 交叉窗口：总计{mot['crossing_window_count']}个，可评分{mot['crossing_evaluable_window_count']}个，不可评分{mot['crossing_not_evaluable_window_count']}个；身份切换{mot['crossing_id_switch_count']}，纯度{_format_ratio(mot['crossing_track_purity'])}，连续性{_format_ratio(mot['crossing_track_continuity'])}，门控{'通过' if mot['gate_passed'] else '未通过'}",
        f"- 已确认时序绑定切换：{metrics['geometric_binding_switch_count']}；逐帧瞬时绑定切换：{metrics['instantaneous_geometric_binding_switch_count']}；重复分配：{metrics['duplicate_assignment_count']}；未匹配检测：{metrics['unmatched_detection_count']}",
        f"- 时序连续性：短时外推记录{temporal['coasted_record_count']}条，恢复{temporal['recovery_count']}次，过期{temporal['expiry_count']}次；有效中断{temporal['effective_fragmentation_count']}次",
        f"- 外推证据控制许可：{temporal['predicted_record_authorization_count']}（要求为0）；绑定事件与掉线记录分别见`temporal_binding_events.csv`和`dropout_events.csv`",
        f"- 相机截图：共保存{metrics['snapshot_saved_count']}/{metrics['snapshot_expected_count']}，其中定时截图{metrics['periodic_snapshot_saved_count']}/{metrics['periodic_snapshot_expected_count']}，事件截图{metrics['event_snapshot_saved_count']}/{metrics['event_snapshot_count']}；视频生成：否",
        f"- 配准图像证据：标注图{metrics.get('visual_evidence', {}).get('annotated_snapshot_count', 0)}幅，中心与拦截相机共同形成证据的全局航迹{metrics.get('visual_evidence', {}).get('shared_track_handover_panel_count', 0)}个",
        f"- 检测RPC平均延迟：{_format_number(metrics['detection_rpc_latency_mean_ms'])}毫秒",
        f"- 逻辑时间/墙钟时间比：{_format_number(metrics['wall_time_realtime_factor'])}",
        "",
        "## 身份边界",
        "",
        "在线关联只使用中心航迹、相机内外参、匿名本地航迹、双时间戳和协方差。AirSim actor名称与对象编号仅写入离线评分侧车。中心航迹由D1/D2夹具合成，本试验未检验真实雷达融合误差。",
        "",
        "## 图表",
        "",
        f"![云台曲线]({paths.get('gimbal_yaw_curve', Path('gimbal_yaw_curve.png')).name})",
        "",
        f"![俯仰曲线]({paths.get('gimbal_pitch_curve', Path('gimbal_pitch_curve.png')).name})",
        "",
        f"![二维扫描栅格]({paths.get('center_scan_raster', Path('center_scan_raster.png')).name})",
        "",
        f"![累计发现]({paths.get('cumulative_discovery_curve', Path('cumulative_discovery_curve.png')).name})",
        "",
        f"![跟踪连续性]({paths.get('mot_continuity_summary', Path('mot_continuity_summary.png')).name})",
        "",
        f"![中心与拦截相机配准视图]({paths.get('camera_registration_overview', Path('visual_evidence/camera_registration_overview.png')).relative_to(path.parent) if paths.get('camera_registration_overview') else 'visual_evidence/camera_registration_overview.png'})",
        "",
        f"完整视觉证据见 [{paths.get('visual_registration_effect_report', Path('visual_evidence/D5_VISUAL_REGISTRATION_EFFECT_REPORT_CN.md')).name}](visual_evidence/D5_VISUAL_REGISTRATION_EFFECT_REPORT_CN.md)。",
        "",
        "## 记录",
        "",
        f"episode级记录：{record_names}。根目录另存settings、scenario、Blocks标准输出和诊断。actor轨迹、检测真值与交叉窗口只用于离线评分。",
        "",
        *[f"- {item}" for item in missing_items],
        "",
        "## 限制",
        "",
        "主场景目标网格比例为1.0。若三千米处没有检测，可显式运行2.0倍网格诊断场景；诊断结果单独标记，不能替代主场景结论。coverage_safe模式还要求两台相机的分辨率和视场回读正确、中心至少发现90%、拦截相机观察和提示完成比例均不低于0.90、可评分关联准确率不低于0.95，且专项多目标跟踪连续性门控通过。中心GlobalTrack仍由合成夹具提供，真实定位误差和漏报需另行验证。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_campaign_comparison(
    output_dir: Path,
    results: Sequence[LongRangeEpisodeResult],
    scenario: LongRangeCVScenario,
) -> dict[str, Path]:
    rows = []
    for result in results:
        metrics = result.metrics
        rows.append(
            {
                "mode": result.mode,
                "center_unique_discovery_ratio": metrics["center_unique_discovery_ratio"],
                "center_confirmed_ratio": metrics["center_confirmed_ratio"],
                "interceptor_observed_ratio": metrics["interceptor_observed_ratio"],
                "interceptor_cue_completion_ratio": metrics.get(
                    "interceptor_cue_completion_ratio"
                ),
                "association_accuracy": metrics["association_accuracy"],
                "id_switch_count": metrics["id_switch_count"],
                "fragmentation_count": metrics.get("mot_continuity", {})
                .get("aggregate", {})
                .get("fragmentation_count"),
                "track_purity": metrics.get("mot_continuity", {})
                .get("aggregate", {})
                .get("track_purity"),
                "track_continuity": metrics.get("mot_continuity", {})
                .get("aggregate", {})
                .get("track_continuity"),
                "crossing_id_switch_count": metrics.get("mot_continuity", {})
                .get("aggregate", {})
                .get("crossing_id_switch_count"),
                "detection_rpc_latency_mean_ms": metrics["detection_rpc_latency_mean_ms"],
                "wall_time_realtime_factor": metrics["wall_time_realtime_factor"],
                "camera_configuration_passed": metrics["camera_configuration_passed"],
                "coverage_gate_required": metrics["coverage_gate_required"],
                "coverage_gate_passed": metrics["coverage_gate_passed"],
            }
        )
    comparison_csv = _write_csv(output_dir / "mode_comparison.csv", rows)
    report_path = output_dir / "D5_LONG_RANGE_CV_SCAN_COMPARISON_CN.md"
    lines = [
        "# D5 长距离扫描模式对比",
        "",
        "## 结论",
        "",
        "机械速度模式用于暴露窄视场在高角速度下的漏扫，不设置强制覆盖门。连续覆盖模式保持20%相邻视场重叠，并按固定门限验收。",
        "",
        "| 模式 | 相机配置 | 中心发现 | 提示完成 | 关联准确率 | 身份切换 | 轨迹中断 | 连续性 | 交叉切换 | 验收 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {mode} | {camera} | {center} | {cue} | {accuracy} | {idsw} | {fragments} | {continuity} | {crossing_idsw} | {gate} |".format(
                mode=row["mode"],
                camera="通过" if row["camera_configuration_passed"] else "未通过",
                center=_format_ratio(row["center_unique_discovery_ratio"]),
                cue=_format_ratio(row["interceptor_cue_completion_ratio"]),
                accuracy=_format_ratio(row["association_accuracy"]),
                idsw=row["id_switch_count"],
                fragments=row["fragmentation_count"] if row["fragmentation_count"] is not None else "不可用",
                continuity=_format_ratio(row["track_continuity"]),
                crossing_idsw=row["crossing_id_switch_count"] if row["crossing_id_switch_count"] is not None else "不可用",
                gate=(
                    "通过"
                    if row["coverage_gate_required"] and row["coverage_gate_passed"]
                    else "未通过"
                    if row["coverage_gate_required"]
                    else "不适用"
                ),
            )
        )
    lines.extend(
        [
            "",
            f"本轮目标数为{scenario.target_count}。两种模式在同一Blocks进程内顺序运行，中间执行reset。报告只比较本轮AirSim接口数据。",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {"comparison_csv": comparison_csv, "comparison_report": report_path}


def _write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    required_fields: Sequence[str] = (),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(
        dict.fromkeys(
            [str(field) for field in required_fields]
            + [key for row in rows for key in row]
        )
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: _csv_value(row.get(key)) for key in fields})
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(_jsonable(row), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _csv_value(value: Any) -> Any:
    if isinstance(value, (tuple, list, dict, np.ndarray)):
        return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)
    return value


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else float(statistics.fmean(values))


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    return None if not values else float(np.percentile(np.asarray(values, dtype=float), percentile))


def _format_ratio(value: Any) -> str:
    return "不可用" if value is None else f"{float(value):.3f}"


def _format_number(value: Any) -> str:
    return "不可用" if value is None else f"{float(value):.3f}"


__all__ = [
    "CENTER_CAMERA_SPEC",
    "INTERCEPTOR_CAMERA_SPEC",
    "CuedGimbalScheduler",
    "LongRangeCVScenario",
    "LongRangeCampaignResult",
    "LongRangeEpisodeResult",
    "OpticalCameraSpec",
    "PitchSearchPlan",
    "SUPPORTED_SCAN_MODES",
    "SUPPORTED_GEOMETRY_PROFILES",
    "ScanModeDefinition",
    "SectorScanScheduler",
    "VelocityAwareAnonymousTracker",
    "build_serpentine_scan_grid",
    "crossing_geometry_preflight",
    "derive_pitch_search_plan",
    "derive_interceptor_camera_spec",
    "generate_long_range_target_specs",
    "minimum_target_separation",
    "pixel_to_world_unit_ray",
    "world_ray_velocity_to_pixel_rate",
    "projected_trajectory_crossing_count",
    "evaluate_mot_continuity",
    "run_long_range_cv_campaign",
    "scan_mode_definition",
    "snapshot_frame_indices",
    "vertical_fov_degrees",
    "write_long_range_cv_settings",
]
