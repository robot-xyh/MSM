"""Anonymous cross-view association for interceptor ComputerVision cameras."""

from .association import CrossViewAssociator, associate_crossview_tracks
from .airsim_adapter import AirSimOfflineDetectionLabel, DetectionNameResolver
from .config import CameraCalibration, CrossViewConfig
from .contracts import CrossViewResult
from .evaluation import (
    build_offline_truth_from_detection_labels,
    score_from_offline_detection_labels,
)

__all__ = [
    "AirSimOfflineDetectionLabel",
    "CameraCalibration",
    "CrossViewAssociator",
    "CrossViewConfig",
    "CrossViewResult",
    "DetectionNameResolver",
    "associate_crossview_tracks",
    "build_offline_truth_from_detection_labels",
    "score_from_offline_detection_labels",
]
