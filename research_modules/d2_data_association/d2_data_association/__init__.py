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
from .metrics import (
    AssociationRiskSummaryWindowGenerator,
    MetricsRecorder,
    RiskBreakdown,
    RiskThresholds,
    classify_risk_summary,
)
from .replay import (
    ReplayAssociationReport,
    load_airsim_replay_frames,
    run_airsim_replay_association,
    run_threshold_sensitivity,
    summarize_replay_risk,
    write_association_logs_jsonl,
    write_replay_association_report,
)
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
    "RiskBreakdown",
    "RiskThresholds",
    "ReplayAssociationReport",
    "classify_risk_summary",
    "load_airsim_replay_frames",
    "run_airsim_replay_association",
    "run_threshold_sensitivity",
    "summarize_replay_risk",
    "write_association_logs_jsonl",
    "write_replay_association_report",
    "RejectedPair",
    "TrackLifecycleState",
    "TrackTransition",
    "Tracker",
    "build_default_dry_run_tracker",
    "detections_from_d1_global_tracks",
    "detections_from_airsim_frame",
    "run_airsim_dry_run_association",
]
