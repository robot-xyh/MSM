"""Typed records used only by the independent search experiment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


Vector3 = tuple[float, float, float]


@dataclass(frozen=True)
class SearchExperimentConfig:
    """Runtime and deterministic-planner configuration."""

    target_count: int
    resource_count: int
    seed: int = 20260816
    assignment_cycles: int = 3
    frames_per_assignment: int = 3
    frame_interval_s: float = 0.1
    camera_name: str = "0"
    image_width: int = 1920
    image_height: int = 1080
    horizontal_fov_deg: float = 19.0
    recognition_extent_px: float = 10.0
    confirmation_frames: int = 2
    local_track_gate_px: float = 180.0
    observation_standoff_m: float = 700.0
    detection_filter_radius_cm: float = 1.0e7
    target_mesh_patterns: tuple[str, ...] = (
        "MSM_TargetActor_*",
        "MSM_TargetActor*",
    )
    gap_cell_count: int | None = None
    corridor_x_bounds_m: tuple[float, float] = (2500.0, 3500.0)
    corridor_y_bounds_m: tuple[float, float] = (-650.0, 650.0)
    corridor_z_bounds_m: tuple[float, float] = (-220.0, -70.0)

    def __post_init__(self) -> None:
        if self.target_count <= 0 or self.resource_count <= 0:
            raise ValueError("target_count and resource_count must be positive")
        if self.assignment_cycles <= 0 or self.frames_per_assignment <= 0:
            raise ValueError("assignment cycles and frame count must be positive")
        if self.frame_interval_s <= 0.0:
            raise ValueError("frame_interval_s must be positive")
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("image dimensions must be positive")
        if not 0.0 < self.horizontal_fov_deg < 180.0:
            raise ValueError("horizontal_fov_deg must be within (0, 180)")
        if self.recognition_extent_px <= 0.0 or self.confirmation_frames <= 0:
            raise ValueError("recognition and confirmation thresholds must be positive")
        if self.frames_per_assignment < self.confirmation_frames:
            raise ValueError("frames_per_assignment cannot be below confirmation_frames")
        if self.gap_cell_count is not None and self.gap_cell_count <= 0:
            raise ValueError("gap_cell_count must be positive when supplied")
        for bounds in (
            self.corridor_x_bounds_m,
            self.corridor_y_bounds_m,
            self.corridor_z_bounds_m,
        ):
            if bounds[1] <= bounds[0]:
                raise ValueError("corridor bounds must be increasing")


@dataclass(frozen=True)
class ProbabilityRegion:
    region_id: str
    center_ned_m: Vector3
    half_extent_ned_m: Vector3
    probability: float
    region_kind: str
    source_track_ids: tuple[str, ...] = ()
    valid_until: float | None = None

    def __post_init__(self) -> None:
        if not self.region_id:
            raise ValueError("region_id must be non-empty")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be within [0, 1]")
        if self.region_kind not in {"source_directed", "unbound_gap"}:
            raise ValueError("unsupported region_kind")


@dataclass(frozen=True)
class SearchCell:
    search_cell_id: str
    region_id: str
    center_ned_m: Vector3
    look_at_ned_m: Vector3
    half_extent_ned_m: Vector3
    target_probability: float
    cell_kind: str
    candidate_source_track_ids: tuple[str, ...] = ()
    valid_until: float | None = None

    def __post_init__(self) -> None:
        if not self.search_cell_id or not self.region_id:
            raise ValueError("cell and region identifiers must be non-empty")
        if not 0.0 <= self.target_probability <= 1.0:
            raise ValueError("target_probability must be within [0, 1]")


@dataclass
class SearchResourceState:
    camera_id: str
    position_ned_m: Vector3
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    available: bool = True


@dataclass(frozen=True)
class AssignmentUtility:
    target_probability: float
    expected_detection_gain: float
    slew_cost: float
    arrival_cost: float
    repeated_coverage_cost: float
    total_utility: float


@dataclass(frozen=True)
class SearchAssignment:
    plan_version: int
    assignment_timestamp: float
    camera_id: str
    search_cell_id: str | None
    region_id: str | None
    utility: AssignmentUtility
    assignment_state: str


@dataclass(frozen=True)
class CameraSearchCommand:
    plan_version: int
    camera_id: str
    search_cell_id: str
    position_ned_m: Vector3
    look_at_ned_m: Vector3
    yaw_deg: float
    pitch_deg: float


@dataclass(frozen=True)
class AnonymousBBoxDetection:
    """Online detection after the AirSim object name has been discarded."""

    detection_uid: str
    camera_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    bbox_xyxy: tuple[float, float, float, float]
    center_px: tuple[float, float]
    recognition_extent_px: float
    recognized: bool


@dataclass(frozen=True)
class OfflineDetectionLabel:
    """Offline-only mapping produced while anonymizing one raw detection."""

    detection_uid: str
    truth_target_id: str | None
    is_false_positive: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)
