"""Independent dual-optical 40-target association experiment."""

from .core import (
    AnonymousDetection,
    BearingTrack,
    CameraSpec,
    CameraState,
    CrossAssociationResult,
    CrossCameraCandidate,
    CrossCameraMatch,
    RayObservation,
    ScanRevisitTracker,
    ScenarioConfig,
    TargetSpec,
    associate_tracks,
    generate_target_specs,
    pixel_to_world_ray,
    project_world_point,
    scan_yaw_deg,
)

__all__ = [
    "AnonymousDetection",
    "BearingTrack",
    "CameraSpec",
    "CameraState",
    "CrossAssociationResult",
    "CrossCameraCandidate",
    "CrossCameraMatch",
    "RayObservation",
    "ScanRevisitTracker",
    "ScenarioConfig",
    "TargetSpec",
    "associate_tracks",
    "generate_target_specs",
    "pixel_to_world_ray",
    "project_world_point",
    "scan_yaw_deg",
]
