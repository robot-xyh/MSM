"""Typed models for the phase-1 AirSim dry-run interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


Vector3 = tuple[float, float, float]
Vector2 = tuple[float, float]
Matrix3 = tuple[Vector3, Vector3, Vector3]
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class AirSimEpisodeConfig:
    """Configuration for one fake AirSim episode.

    The fields mirror the later real-runtime coordinator surface while staying
    dependency-free for syntax and interface testing.
    """

    scenario_name: str = "nominal_5v5"
    episode_id: str = "episode_001"
    seed: int = 7
    duration_s: float = 5.0
    dt_s: float = 0.5
    target_count: int = 5
    resource_count: int = 5
    radar_latency_s: float = 0.6
    include_acoustic: bool = True
    include_eo: bool = True
    include_lidar: bool = True
    reset_between_episodes: bool = True
    output_root: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AirSimTruthObject:
    """Fake AirSim object state in NED coordinates."""

    object_id: str
    object_type: str
    timestamp: float
    position_ned: Vector3
    velocity_ned: Vector3
    classification_hint: str = "uav"
    threat_score: float = 0.0
    coverage_cell: str = "cell-unknown"
    covariance_ned: Matrix3 = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def state_ned(self) -> tuple[float, float, float, float, float, float]:
        return (*self.position_ned, *self.velocity_ned)


@dataclass(frozen=True)
class AirSimCameraInfo:
    """Pinhole camera metadata used by dry-run vision adapters."""

    camera_id: str
    owner_id: str
    timestamp: float
    position_ned: Vector3
    rotation_world_to_camera: Matrix3 = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    fx: float = 320.0
    fy: float = 320.0
    cx: float = 320.0
    cy: float = 240.0
    width: int = 640
    height: int = 480


@dataclass(frozen=True)
class AirSimResourceState:
    """Fake resource platform state for assignment and terminal adapters."""

    resource_id: str
    timestamp: float
    position_ned: Vector3
    velocity_ned: Vector3 = (0.0, 0.0, 0.0)
    status: str = "available"
    health_score: float = 1.0
    role: str = "interceptor"
    coverage_cell: str = "cell-unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AirSimDetectionBox:
    """Fake camera detector/MOT output in image coordinates."""

    detection_id: str
    camera_id: str
    object_id: str
    local_track_id: str
    timestamp: float
    center_px: Vector2
    bbox_xyxy: BBox
    confidence: float = 0.9
    classification_hint: str = "uav"
    is_friend_hint: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AirSimFrame:
    """One fake AirSim runtime frame."""

    episode_id: str
    scenario_name: str
    frame_index: int
    timestamp: float
    truth_objects: tuple[AirSimTruthObject, ...]
    resources: tuple[AirSimResourceState, ...]
    cameras: tuple[AirSimCameraInfo, ...] = ()
    visual_detections: tuple[AirSimDetectionBox, ...] = ()
    center_node_alive: bool = True
    secondary_nodes_alive: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AirSimAdapterResult:
    """Summary returned by the phase-1 dry-run orchestrator."""

    episode_id: str
    scenario_name: str
    frame_count: int
    module_status: dict[str, str]
    metrics: dict[str, Any]
    output_paths: dict[str, Path]
    metadata: dict[str, Any] = field(default_factory=dict)
