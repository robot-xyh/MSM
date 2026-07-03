"""Offline multi-target data association research module."""

from .associators import (
    DataAssociator,
    GNNHungarianAssociator,
    JPDAAssociator,
    MHTAssociator,
)
from .dry_run_adapter import (
    DryRunAssociationFrame,
    DryRunAssociationResult,
    build_default_dry_run_tracker,
    detections_from_d1_global_tracks,
    detections_from_airsim_frame,
    run_airsim_dry_run_association,
)
from .metrics import AssociationRiskSummaryWindowGenerator, MetricsRecorder
from .models import (
    AssociationLogEntry,
    AssociationResult,
    AssociationRiskSummary,
    Detection,
    GlobalTrack,
    MatchedPair,
    RejectedPair,
    TrackLifecycleState,
    TrackTransition,
)
from .tracker import Tracker

__all__ = [
    "AssociationLogEntry",
    "AssociationRiskSummaryWindowGenerator",
    "AssociationRiskSummary",
    "AssociationResult",
    "DataAssociator",
    "Detection",
    "DryRunAssociationFrame",
    "DryRunAssociationResult",
    "GNNHungarianAssociator",
    "GlobalTrack",
    "JPDAAssociator",
    "MHTAssociator",
    "MatchedPair",
    "MetricsRecorder",
    "RejectedPair",
    "TrackLifecycleState",
    "TrackTransition",
    "Tracker",
    "build_default_dry_run_tracker",
    "detections_from_d1_global_tracks",
    "detections_from_airsim_frame",
    "run_airsim_dry_run_association",
]
